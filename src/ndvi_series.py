"""Расчёт серии NDVI по окну над полями + zonal statistics по каждому полю.

Использование:
    python src/ndvi_series.py
        [--series data/catalog/series_37TDK_2023-10-01_2024-09-30.json]
        [--fields data/fields/fields_v1.geojson]
        [--out data/processed/fields_ndvi_series.csv]
        [--workers 4]
        [--save-ndvi-tif]    -- сохранять NDVI tif на каждую дату

Что делает:
    1. Загружает serie JSON и поля GeoJSON;
    2. Вычисляет общий bbox полей + рамка 2 км в CRS снимка (UTM 37N);
    3. Параллельно для каждой даты:
       - читает B04, B08, SCL ТОЛЬКО в этом окне (HTTP range);
       - считает NDVI, применяет SCL-маску;
       - опционально сохраняет окно как маленький COG;
       - считает zonal stats по 20 полям внутри окна;
    4. Собирает long-format DataFrame: field_id × date × ndvi_mean × ndvi_median × ...;
    5. Сохраняет CSV.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

os.environ.setdefault("GDAL_HTTP_MULTIPLEX", "YES")
os.environ.setdefault("GDAL_HTTP_VERSION", "2")
os.environ.setdefault("CPL_VSIL_CURL_CHUNK_SIZE", "1048576")
os.environ.setdefault("CPL_VSIL_CURL_CACHE_SIZE", "200000000")
os.environ.setdefault("GDAL_CACHEMAX", "512")
os.environ.setdefault("VSI_CACHE", "TRUE")
os.environ.setdefault("VSI_CACHE_SIZE", "268435456")

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.enums import Resampling
from rasterio.mask import mask as rio_mask
from rasterio.warp import transform_bounds
from rasterio.windows import Window, from_bounds

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
NDVI_SERIES_DIR = PROCESSED_DIR / "ndvi_series"

SCL_BAD = {0, 1, 3, 8, 9, 10, 11}


def fields_bbox_utm(fields_path: Path, target_crs: str, pad_m: float = 2000.0) -> tuple[float, float, float, float]:
    gdf = gpd.read_file(fields_path).to_crs(target_crs)
    minx, miny, maxx, maxy = gdf.total_bounds
    return (minx - pad_m, miny - pad_m, maxx + pad_m, maxy + pad_m)


def read_window(url: str, bbox_utm: tuple[float, float, float, float], target_shape: tuple[int, int] | None = None, resampling: Resampling = Resampling.bilinear) -> tuple[np.ndarray, rasterio.windows.Window, dict]:
    with rasterio.open(url) as src:
        window = from_bounds(*bbox_utm, transform=src.transform)
        window = window.round_lengths().round_offsets()
        if target_shape is None:
            arr = src.read(1, window=window)
            shape = (int(window.height), int(window.width))
        else:
            arr = src.read(1, window=window, out_shape=target_shape, resampling=resampling)
            shape = target_shape
        win_transform = src.window_transform(window)
        profile = src.profile.copy()
        profile.update(
            width=shape[1],
            height=shape[0],
            transform=win_transform,
            count=1,
            driver="GTiff",
        )
        return arr, window, profile


def compute_ndvi_window(red: np.ndarray, nir: np.ndarray, scl: np.ndarray | None) -> np.ndarray:
    red_f = red.astype(np.float32)
    nir_f = nir.astype(np.float32)
    denom = nir_f + red_f
    with np.errstate(divide="ignore", invalid="ignore"):
        ndvi = np.where(denom > 0, (nir_f - red_f) / denom, np.nan).astype(np.float32)
    ndvi[(red == 0) & (nir == 0)] = np.nan
    if scl is not None:
        ndvi[np.isin(scl, list(SCL_BAD))] = np.nan
    return ndvi


def save_ndvi_window(ndvi: np.ndarray, profile: dict, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    p = profile.copy()
    p.update(
        dtype="float32",
        nodata=np.nan,
        tiled=True,
        blockxsize=256,
        blockysize=256,
        compress="deflate",
        predictor=3,
    )
    with rasterio.open(out_path, "w", **p) as dst:
        dst.write(ndvi, 1)
        dst.build_overviews([2, 4, 8], Resampling.average)


def zonal_for_fields(ndvi: np.ndarray, transform, crs: str, fields_gdf_proj: gpd.GeoDataFrame) -> list[dict]:
    rows = []
    with rasterio.io.MemoryFile() as memfile:
        h, w = ndvi.shape
        p = {
            "driver": "GTiff",
            "dtype": "float32",
            "width": w,
            "height": h,
            "count": 1,
            "crs": crs,
            "transform": transform,
            "nodata": np.nan,
        }
        with memfile.open(**p) as dst:
            dst.write(ndvi, 1)
        with memfile.open() as src:
            for _, row in fields_gdf_proj.iterrows():
                geom = [row.geometry.__geo_interface__]
                try:
                    out_image, _ = rio_mask(src, geom, crop=True, filled=True, nodata=np.nan)
                    arr = out_image[0]
                except ValueError:
                    rows.append({"field_id": row["field_id"], "pixel_count": 0, "valid_pixels": 0})
                    continue
                valid = arr[~np.isnan(arr)]
                rows.append(
                    {
                        "field_id": row["field_id"],
                        "pixel_count": int(arr.size),
                        "valid_pixels": int(valid.size),
                        "valid_share": round(valid.size / arr.size, 3) if arr.size else 0.0,
                        "ndvi_mean": round(float(valid.mean()), 4) if valid.size else None,
                        "ndvi_median": round(float(np.median(valid)), 4) if valid.size else None,
                        "ndvi_p25": round(float(np.percentile(valid, 25)), 4) if valid.size else None,
                        "ndvi_p75": round(float(np.percentile(valid, 75)), 4) if valid.size else None,
                    }
                )
    return rows


def process_one_date(item: dict, fields_gdf: gpd.GeoDataFrame, save_tif: bool) -> list[dict]:
    tile_id = item["id"]
    date_str = item["datetime"][:10]
    cloud = item["cloud_cover"]
    b04, b08, scl = item["assets"]["red_B04"], item["assets"]["nir_B08"], item["assets"].get("scl")

    t0 = time.perf_counter()
    with rasterio.open(b04) as src:
        target_crs = src.crs
    bbox_utm = fields_bbox_utm(PROJECT_ROOT / "data" / "fields" / "fields_v1.geojson", target_crs.to_string(), pad_m=2000.0)

    red, win, profile = read_window(b04, bbox_utm)
    nir, _, _ = read_window(b08, bbox_utm)
    scl_arr = None
    if scl:
        scl_arr, _, _ = read_window(scl, bbox_utm, target_shape=red.shape, resampling=Resampling.nearest)

    ndvi = compute_ndvi_window(red, nir, scl_arr)
    dt_io = time.perf_counter() - t0

    if save_tif:
        save_ndvi_window(ndvi, profile, NDVI_SERIES_DIR / f"{date_str}_{tile_id}_NDVI.tif")

    fields_proj = fields_gdf.to_crs(target_crs.to_string())
    stats_rows = zonal_for_fields(ndvi, profile["transform"], target_crs.to_string(), fields_proj)
    dt_total = time.perf_counter() - t0

    for r in stats_rows:
        r["date"] = date_str
        r["tile_id"] = tile_id
        r["cloud_cover"] = cloud
    print(f"  {date_str} ({tile_id}, облачность {cloud:.2f}%) -- io {dt_io:.1f}s, total {dt_total:.1f}s, полей {len(stats_rows)}")
    return stats_rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--series", default=str(PROJECT_ROOT / "data" / "catalog" / "series_37TDK_2023-10-01_2024-09-30.json"))
    parser.add_argument("--fields", default=str(PROJECT_ROOT / "data" / "fields" / "fields_v1.geojson"))
    parser.add_argument("--out", default=str(PROCESSED_DIR / "fields_ndvi_series.csv"))
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--save-ndvi-tif", action="store_true")
    parser.add_argument("--limit", type=int, default=None, help="ограничить число дат (для отладки)")
    args = parser.parse_args()

    series_path = Path(args.series)
    fields_path = Path(args.fields)
    out_csv = Path(args.out)

    cat = json.loads(series_path.read_text(encoding="utf-8"))
    items = cat["items"]
    if args.limit:
        items = items[: args.limit]
    print(f"Серия: {len(items)} дат")
    print(f"Поля:  {fields_path}")
    print(f"Параллелизм: {args.workers} потоков\n")

    fields_gdf = gpd.read_file(fields_path)

    all_rows: list[dict] = []
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(process_one_date, item, fields_gdf, args.save_ndvi_tif): item for item in items}
        done = 0
        for fut in as_completed(futures):
            item = futures[fut]
            try:
                rows = fut.result()
                all_rows.extend(rows)
            except Exception as exc:
                print(f"  {item['datetime'][:10]} ОШИБКА: {exc.__class__.__name__}: {exc}")
            done += 1
            if done % 5 == 0:
                print(f"  [progress] {done}/{len(items)} дат обработано")

    dt_total = time.perf_counter() - t0
    print(f"\nГотово за {dt_total:.1f}s ({dt_total/len(items):.1f}s/дата)")

    df = pd.DataFrame(all_rows)
    if df.empty:
        print("Пустой результат, нечего сохранять.")
        return
    df = df.sort_values(["field_id", "date"]).reset_index(drop=True)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv, index=False, encoding="utf-8")
    print(f"\nCSV -> {out_csv.relative_to(PROJECT_ROOT)}  ({len(df)} строк)")

    print("\nСводка по полям (число валидных дат):")
    by_field = df[df["ndvi_mean"].notna()].groupby("field_id").size().sort_values(ascending=False)
    print(by_field.to_string())


if __name__ == "__main__":
    main()
