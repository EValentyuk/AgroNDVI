"""Усреднение NDVI по каждому полю (zonal statistics).

Использование:
    python src/zonal_stats.py
        [--fields data/fields/fields_v1.geojson]
        [--ndvi data/processed/<tile-id>_NDVI.tif]
        [--out data/processed/fields_ndvi.csv]

Для каждого поля считает: mean, median, p05, p25, p75, p95 NDVI,
количество всех пикселей в полигоне и долю валидных (без маски).
Сохраняет CSV. Параллельно рендерит карту полей поверх NDVI и
интерактивную folium-карту с popup-ами по каждому полю.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import matplotlib

matplotlib.use("Agg")
import matplotlib.colors as mcolors
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from rasterio.mask import mask as rio_mask
import folium
import geopandas as gpd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
PREVIEW_DIR = PROJECT_ROOT / "data" / "preview"


def compute_zonal_stats(fields_gdf: gpd.GeoDataFrame, ndvi_path: Path) -> pd.DataFrame:
    with rasterio.open(ndvi_path) as src:
        raster_crs = src.crs
        gdf_proj = fields_gdf.to_crs(raster_crs)
        rows = []
        for _, row in gdf_proj.iterrows():
            geom = [row.geometry.__geo_interface__]
            try:
                out_image, _ = rio_mask(src, geom, crop=True, filled=True, nodata=np.nan)
                arr = out_image[0]
            except ValueError:
                rows.append({**row.drop("geometry").to_dict(), "pixel_count": 0, "valid_pixels": 0})
                continue
            valid = arr[~np.isnan(arr)]
            d = {
                "field_id": row["field_id"],
                "osm_id": row["osm_id"],
                "crop_osm": row.get("crop"),
                "area_ha": round(row["area_ha"], 1),
                "pixel_count": int(arr.size),
                "valid_pixels": int(valid.size),
                "valid_share": round(valid.size / arr.size, 3) if arr.size else 0,
                "ndvi_mean": round(float(valid.mean()), 4) if valid.size else None,
                "ndvi_median": round(float(np.median(valid)), 4) if valid.size else None,
                "ndvi_p05": round(float(np.percentile(valid, 5)), 4) if valid.size else None,
                "ndvi_p25": round(float(np.percentile(valid, 25)), 4) if valid.size else None,
                "ndvi_p75": round(float(np.percentile(valid, 75)), 4) if valid.size else None,
                "ndvi_p95": round(float(np.percentile(valid, 95)), 4) if valid.size else None,
            }
            rows.append(d)
    return pd.DataFrame(rows)


def plot_fields_on_ndvi(fields_gdf: gpd.GeoDataFrame, ndvi_path: Path, stats: pd.DataFrame) -> Path:
    with rasterio.open(ndvi_path) as src:
        raster_crs = src.crs
        gdf_proj = fields_gdf.to_crs(raster_crs)
        minx, miny, maxx, maxy = gdf_proj.total_bounds
        pad_m = 2000
        from rasterio.windows import from_bounds
        window = from_bounds(minx - pad_m, miny - pad_m, maxx + pad_m, maxy + pad_m, src.transform)
        ndvi = src.read(1, window=window)
        win_transform = src.window_transform(window)
        extent = (
            win_transform.c,
            win_transform.c + win_transform.a * ndvi.shape[1],
            win_transform.f + win_transform.e * ndvi.shape[0],
            win_transform.f,
        )

    cmap = mcolors.LinearSegmentedColormap.from_list(
        "ndvi_agro",
        [(0.0, "#3a1f0a"), (0.25, "#a05a14"), (0.45, "#d8c84a"),
         (0.65, "#7fbf3f"), (0.85, "#1e7a1e"), (1.0, "#0a3d0a")],
    )
    cmap.set_bad("#202020")

    fig, ax = plt.subplots(figsize=(11, 11))
    im = ax.imshow(ndvi, cmap=cmap, vmin=-0.2, vmax=1.0, extent=extent, origin="upper")

    gdf_proj.boundary.plot(ax=ax, edgecolor="#ff00ff", linewidth=1.5)
    for _, row in gdf_proj.iterrows():
        centroid = row.geometry.centroid
        s_row = stats[stats["field_id"] == row["field_id"]].iloc[0] if (stats["field_id"] == row["field_id"]).any() else None
        label = row["field_id"]
        if s_row is not None and s_row["ndvi_mean"] is not None:
            label += f"\nNDVI={s_row['ndvi_mean']:.2f}"
        ax.annotate(
            label, (centroid.x, centroid.y), color="white", fontsize=8, ha="center", va="center",
            bbox=dict(boxstyle="round,pad=0.2", facecolor="black", alpha=0.55, edgecolor="none"),
        )

    ax.set_title("Поля OSM поверх NDVI (зум на bbox полей + 2 км рамка)")
    ax.set_xlabel("UTM X, м")
    ax.set_ylabel("UTM Y, м")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.02, label="NDVI")
    fig.tight_layout()
    out = PREVIEW_DIR / "fields_v1_overlay_NDVI.png"
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return out


def make_folium_map(fields_gdf: gpd.GeoDataFrame, stats: pd.DataFrame) -> Path:
    gdf_w = fields_gdf.to_crs("EPSG:4326").merge(stats, on="field_id", suffixes=("", "_s"))
    centroid = gdf_w.geometry.unary_union.centroid
    m = folium.Map(location=[centroid.y, centroid.x], zoom_start=11, tiles="OpenStreetMap")
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery", name="Спутник Esri", overlay=False, control=True,
    ).add_to(m)

    def color_for(v):
        if v is None or pd.isna(v):
            return "#888888"
        if v < 0.2:
            return "#a05a14"
        if v < 0.45:
            return "#d8c84a"
        if v < 0.65:
            return "#7fbf3f"
        if v < 0.85:
            return "#1e7a1e"
        return "#0a3d0a"

    for _, row in gdf_w.iterrows():
        color = color_for(row.get("ndvi_mean"))
        popup_html = (
            f"<b>{row['field_id']}</b><br>"
            f"OSM id: {row['osm_id']}<br>"
            f"culture: {row.get('crop_osm') or 'не указана'}<br>"
            f"area: {row['area_ha']} га<br>"
            f"NDVI mean: {row['ndvi_mean']}<br>"
            f"NDVI median: {row['ndvi_median']}<br>"
            f"valid share: {row['valid_share']}<br>"
        )
        folium.GeoJson(
            row.geometry.__geo_interface__,
            style_function=lambda feat, c=color: {"fillColor": c, "color": "#ff00ff", "weight": 1.5, "fillOpacity": 0.55},
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=f"{row['field_id']} -- NDVI {row['ndvi_mean']}",
        ).add_to(m)

    folium.LayerControl().add_to(m)
    out = PREVIEW_DIR / "fields_v1_map.html"
    m.save(str(out))
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fields", default=str(PROJECT_ROOT / "data" / "fields" / "fields_v1.geojson"))
    parser.add_argument("--ndvi", default=str(PROCESSED_DIR / "S2A_37TDK_20240603_0_L2A_NDVI.tif"))
    parser.add_argument("--out", default=str(PROCESSED_DIR / "fields_ndvi.csv"))
    args = parser.parse_args()

    fields_path = Path(args.fields)
    ndvi_path = Path(args.ndvi)
    out_csv = Path(args.out)

    print(f"Поля:  {fields_path}")
    print(f"NDVI:  {ndvi_path}\n")

    fields_gdf = gpd.read_file(fields_path)
    print(f"Загружено {len(fields_gdf)} полей, CRS {fields_gdf.crs}")
    print(f"Атрибуты: {list(fields_gdf.columns)}\n")

    print("Расчёт zonal statistics...")
    stats = compute_zonal_stats(fields_gdf, ndvi_path)
    print(stats[["field_id", "area_ha", "pixel_count", "valid_share", "ndvi_mean", "ndvi_median", "ndvi_p95"]].to_string(index=False))

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    stats.to_csv(out_csv, index=False, encoding="utf-8")
    print(f"\nCSV -> {out_csv.relative_to(PROJECT_ROOT)}")

    print("\nРендер overlay-карты...")
    overlay = plot_fields_on_ndvi(fields_gdf, ndvi_path, stats)
    print(f"  overlay -> {overlay.relative_to(PROJECT_ROOT)}")

    print("\nРендер folium-карты...")
    fm = make_folium_map(fields_gdf, stats)
    print(f"  folium -> {fm.relative_to(PROJECT_ROOT)}")

    print("\nКраткая агрегация по NDVI:")
    print(f"  mean NDVI median: {stats['ndvi_mean'].median():.3f}")
    print(f"  mean NDVI range:  [{stats['ndvi_mean'].min():.3f}, {stats['ndvi_mean'].max():.3f}]")
    print(f"  valid share median: {stats['valid_share'].median():.3f}")


if __name__ == "__main__":
    main()
