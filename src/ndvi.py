"""Расчёт NDVI для Sentinel-2 L2A tile с маскированием по SCL.

Использование:
    python src/ndvi.py --catalog data/catalog/<tile-id>.json
        [--out data/processed/<tile-id>_NDVI.tif]
        [--no-mask]   -- не применять SCL-маску
        [--no-viz]    -- пропустить визуализацию

Что делает:
    1. Читает B04 (10 м, red) и B08 (10 м, NIR) из удалённого COG;
    2. Читает SCL (20 м), ресемплит nearest до 10 м;
    3. Считает NDVI = (B08 - B04) / (B08 + B04);
    4. Маскирует пиксели с SCL ∈ {0, 1, 3, 8, 9, 10, 11}
       (no_data, defective, shadow, cloud_med, cloud_high, cirrus, snow);
    5. Сохраняет NDVI как Cloud Optimized GeoTIFF;
    6. Рисует визуализации: цветовая карта NDVI, гистограмма, маска SCL.

Шкала SCL (Sentinel-2 L2A Scene Classification):
    0  no_data, 1  saturated/defective, 2  dark area pixels,
    3  cloud shadows, 4  vegetation, 5  bare soil, 6  water,
    7  unclassified, 8  cloud medium prob, 9  cloud high prob,
    10 thin cirrus, 11 snow / ice.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import matplotlib

matplotlib.use("Agg")
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from rasterio.enums import Resampling

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
PREVIEW_DIR = PROJECT_ROOT / "data" / "preview"

SCL_BAD_CLASSES = {0, 1, 3, 8, 9, 10, 11}
SCL_LABELS = {
    0: "no_data",
    1: "defective",
    2: "dark_area",
    3: "cloud_shadow",
    4: "vegetation",
    5: "bare_soil",
    6: "water",
    7: "unclassified",
    8: "cloud_med",
    9: "cloud_high",
    10: "thin_cirrus",
    11: "snow_ice",
}


def read_band(url: str, *, out_shape: tuple[int, int] | None = None, resampling: Resampling = Resampling.bilinear) -> tuple[np.ndarray, dict]:
    t0 = time.perf_counter()
    with rasterio.open(url) as src:
        if out_shape is None:
            arr = src.read(1)
            shape = (src.height, src.width)
        else:
            arr = src.read(1, out_shape=out_shape, resampling=resampling)
            shape = out_shape
        profile = src.profile.copy()
        if out_shape is not None:
            scale_y = src.height / out_shape[0]
            scale_x = src.width / out_shape[1]
            transform = src.transform * src.transform.scale(scale_x, scale_y)
            profile.update(transform=transform, width=out_shape[1], height=out_shape[0])
    dt = time.perf_counter() - t0
    print(f"  загружено {url.rsplit('/', 1)[-1]} -> {arr.shape} {arr.dtype} за {dt:.1f}s")
    return arr, profile


def compute_ndvi(red: np.ndarray, nir: np.ndarray) -> np.ndarray:
    red_f = red.astype(np.float32)
    nir_f = nir.astype(np.float32)
    denom = nir_f + red_f
    with np.errstate(divide="ignore", invalid="ignore"):
        ndvi = np.where(denom > 0, (nir_f - red_f) / denom, np.nan)
    nodata_mask = (red == 0) & (nir == 0)
    ndvi[nodata_mask] = np.nan
    return ndvi.astype(np.float32)


def apply_scl_mask(ndvi: np.ndarray, scl: np.ndarray) -> np.ndarray:
    bad = np.isin(scl, list(SCL_BAD_CLASSES))
    out = ndvi.copy()
    out[bad] = np.nan
    return out


def save_cog(arr: np.ndarray, profile: dict, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    profile = profile.copy()
    profile.update(
        dtype="float32",
        count=1,
        nodata=np.nan,
        driver="GTiff",
        tiled=True,
        blockxsize=512,
        blockysize=512,
        compress="deflate",
        predictor=3,
    )
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(arr, 1)
        dst.build_overviews([2, 4, 8, 16], Resampling.average)
        dst.update_tags(ns="rio_overview", resampling="average")


def plot_ndvi(ndvi: np.ndarray, tile_id: str, downscale: int = 10) -> None:
    h, w = ndvi.shape
    small = ndvi[::downscale, ::downscale]

    cmap = mcolors.LinearSegmentedColormap.from_list(
        "ndvi_agro",
        [
            (0.00, "#3a1f0a"),
            (0.25, "#a05a14"),
            (0.45, "#d8c84a"),
            (0.65, "#7fbf3f"),
            (0.85, "#1e7a1e"),
            (1.00, "#0a3d0a"),
        ],
    )
    cmap.set_bad(color="#202020")

    fig, ax = plt.subplots(figsize=(7, 7))
    im = ax.imshow(small, cmap=cmap, vmin=-0.2, vmax=1.0, interpolation="nearest")
    ax.set_title(f"{tile_id} -- NDVI (downscale ×{downscale})")
    ax.axis("off")
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.02)
    cbar.set_label("NDVI")
    fig.tight_layout()
    out = PREVIEW_DIR / f"{tile_id}_NDVI.png"
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"  карта NDVI -> {out.relative_to(PROJECT_ROOT)}")


def plot_histogram(ndvi: np.ndarray, tile_id: str) -> None:
    valid = ndvi[~np.isnan(ndvi)]
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.hist(valid, bins=120, range=(-0.3, 1.0), color="#3f8f3f", edgecolor="black", linewidth=0.3)
    ax.axvline(0.2, color="#999", linestyle="--", linewidth=1, label="0.2 голая земля")
    ax.axvline(0.4, color="#cc8800", linestyle="--", linewidth=1, label="0.4 средняя растительность")
    ax.axvline(0.7, color="#1e7a1e", linestyle="--", linewidth=1, label="0.7 густая вегетация")
    ax.set_xlabel("NDVI")
    ax.set_ylabel("число пикселей")
    ax.set_title(f"{tile_id} -- распределение NDVI (без замаскированных)")
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    out = PREVIEW_DIR / f"{tile_id}_NDVI_hist.png"
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"  гистограмма -> {out.relative_to(PROJECT_ROOT)}")


def plot_scl(scl: np.ndarray, tile_id: str, downscale: int = 10) -> None:
    small = scl[::downscale, ::downscale]
    palette = {
        0: "#000000", 1: "#ff0000", 2: "#2f2f2f", 3: "#643200",
        4: "#00a000", 5: "#ffe65a", 6: "#0000ff", 7: "#808080",
        8: "#c0c0c0", 9: "#ffffff", 10: "#64c8ff", 11: "#ff96ff",
    }
    classes = sorted(palette)
    cmap = mcolors.ListedColormap([palette[c] for c in classes])
    boundaries = [c - 0.5 for c in classes] + [classes[-1] + 0.5]
    norm = mcolors.BoundaryNorm(boundaries, cmap.N)

    fig, ax = plt.subplots(figsize=(7, 7))
    im = ax.imshow(small, cmap=cmap, norm=norm, interpolation="nearest")
    ax.set_title(f"{tile_id} -- SCL Scene Classification (downscale ×{downscale})")
    ax.axis("off")
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.02, ticks=classes)
    cbar.ax.set_yticklabels([f"{c} {SCL_LABELS[c]}" for c in classes], fontsize=8)
    fig.tight_layout()
    out = PREVIEW_DIR / f"{tile_id}_SCL.png"
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"  карта SCL -> {out.relative_to(PROJECT_ROOT)}")


def summarize_scl(scl: np.ndarray) -> dict:
    total = scl.size
    classes, counts = np.unique(scl, return_counts=True)
    return {
        int(c): {
            "label": SCL_LABELS.get(int(c), "?"),
            "pixels": int(cnt),
            "share_pct": round(100.0 * cnt / total, 3),
        }
        for c, cnt in zip(classes, counts)
    }


def summarize_ndvi(ndvi: np.ndarray) -> dict:
    valid = ndvi[~np.isnan(ndvi)]
    total = ndvi.size
    return {
        "total_pixels": int(total),
        "valid_pixels": int(valid.size),
        "masked_share_pct": round(100.0 * (total - valid.size) / total, 3),
        "min": round(float(valid.min()), 4) if valid.size else None,
        "max": round(float(valid.max()), 4) if valid.size else None,
        "mean": round(float(valid.mean()), 4) if valid.size else None,
        "median": round(float(np.median(valid)), 4) if valid.size else None,
        "p05": round(float(np.percentile(valid, 5)), 4) if valid.size else None,
        "p95": round(float(np.percentile(valid, 95)), 4) if valid.size else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True, help="путь к JSON-каталогу из find_sentinel.py")
    parser.add_argument("--out", default=None, help="путь для NDVI GeoTIFF (по умолчанию data/processed/<tile-id>_NDVI.tif)")
    parser.add_argument("--no-mask", action="store_true", help="не применять SCL-маску")
    parser.add_argument("--no-viz", action="store_true", help="не рисовать визуализации")
    args = parser.parse_args()

    cat = json.loads(Path(args.catalog).read_text(encoding="utf-8"))
    tile_id = cat["id"]
    b04_url = cat["assets"]["red_B04"]
    b08_url = cat["assets"]["nir_B08"]
    scl_url = cat["assets"].get("scl")

    print(f"Tile: {tile_id}\n")
    print("Загрузка полос (через HTTPS):")
    red, profile = read_band(b04_url)
    nir, _ = read_band(b08_url)

    print("\nРасчёт NDVI...")
    t0 = time.perf_counter()
    ndvi = compute_ndvi(red, nir)
    print(f"  готово за {time.perf_counter() - t0:.1f}s, форма {ndvi.shape}, dtype {ndvi.dtype}")

    scl = None
    if scl_url and not args.no_mask:
        print("\nЗагрузка SCL (с ресемплом 20m -> 10m):")
        scl, _ = read_band(scl_url, out_shape=ndvi.shape, resampling=Resampling.nearest)
        scl_stats = summarize_scl(scl)
        print("\nКлассификация SCL:")
        for c in sorted(scl_stats):
            s = scl_stats[c]
            tag = " <- маскируем" if c in SCL_BAD_CLASSES else ""
            print(f"  {c:2d} {s['label']:<14} {s['share_pct']:>6.2f}% ({s['pixels']:>10,} px){tag}")
        print("\nПрименяю SCL-маску...")
        ndvi = apply_scl_mask(ndvi, scl)
    elif args.no_mask:
        print("\nSCL-маска отключена (--no-mask)")
    else:
        print("\nSCL не найден в каталоге, пропускаю маскирование")

    print("\nСтатистика NDVI:")
    ndvi_stats = summarize_ndvi(ndvi)
    for k, v in ndvi_stats.items():
        print(f"  {k}: {v}")

    out_path = Path(args.out) if args.out else PROCESSED_DIR / f"{tile_id}_NDVI.tif"
    print(f"\nСохранение в {out_path.relative_to(PROJECT_ROOT)}...")
    save_cog(ndvi, profile, out_path)
    print(f"  размер: {out_path.stat().st_size / 1024 / 1024:.1f} МБ")

    if not args.no_viz:
        print("\nВизуализации:")
        plot_ndvi(ndvi, tile_id)
        plot_histogram(ndvi, tile_id)
        if scl is not None:
            plot_scl(scl, tile_id)

    stats_path = PROCESSED_DIR / f"{tile_id}_NDVI.stats.json"
    stats_payload = {
        "tile_id": tile_id,
        "ndvi": ndvi_stats,
        "scl": summarize_scl(scl) if scl is not None else None,
        "scl_masked_classes": sorted(SCL_BAD_CLASSES),
    }
    stats_path.write_text(json.dumps(stats_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nСтатистика -> {stats_path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
