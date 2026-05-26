"""Чтение Sentinel-2 L2A COG через rasterio.

Принимает либо путь к сохранённому каталожному JSON
(`data/catalog/<tile-id>.json`, сгенерирован find_sentinel.py),
либо два HTTPS-URL на полосы B04 и B08 напрямую.

Запуск:
    python src/explore_sentinel.py --catalog data/catalog/<tile-id>.json
    python src/explore_sentinel.py --b04 <url> --b08 <url>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from rasterio.warp import transform_bounds

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PREVIEW_DIR = PROJECT_ROOT / "data" / "preview"


def describe_band(url: str) -> dict:
    with rasterio.open(url) as src:
        bounds_4326 = transform_bounds(src.crs, "EPSG:4326", *src.bounds, densify_pts=21)
        return {
            "source": url,
            "size": (src.width, src.height),
            "crs": str(src.crs),
            "transform": tuple(src.transform)[:6],
            "bounds_native": tuple(round(b, 2) for b in src.bounds),
            "bounds_wgs84": tuple(round(b, 4) for b in bounds_4326),
            "dtype": src.dtypes[0],
            "nodata": src.nodata,
            "block_size": src.block_shapes[0] if src.block_shapes else None,
            "overviews": src.overviews(1),
        }


def save_preview(url: str, out_png: Path, downscale: int = 10) -> None:
    with rasterio.open(url) as src:
        h, w = src.height // downscale, src.width // downscale
        arr = src.read(1, out_shape=(h, w), resampling=rasterio.enums.Resampling.average)
    valid = arr[arr > 0]
    vmin, vmax = (np.percentile(valid, [2, 98]) if valid.size else (0, 1))
    plt.figure(figsize=(6, 6))
    plt.imshow(arr, cmap="gray", vmin=vmin, vmax=vmax)
    plt.title(f"{out_png.stem} (downscale ×{downscale})")
    plt.axis("off")
    plt.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_png, dpi=120, bbox_inches="tight")
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", help="путь к JSON-каталогу из find_sentinel.py --save")
    parser.add_argument("--b04", help="HTTPS-URL на полосу B04 (red)")
    parser.add_argument("--b08", help="HTTPS-URL на полосу B08 (nir)")
    parser.add_argument("--downscale", type=int, default=10)
    args = parser.parse_args()

    if args.catalog:
        cat = json.loads(Path(args.catalog).read_text(encoding="utf-8"))
        tile_id = cat["id"]
        urls = {"B04": cat["assets"]["red_B04"], "B08": cat["assets"]["nir_B08"]}
    elif args.b04 and args.b08:
        tile_id = "custom"
        urls = {"B04": args.b04, "B08": args.b08}
    else:
        print("Нужен либо --catalog, либо одновременно --b04 и --b08")
        sys.exit(1)

    print(f"Tile: {tile_id}\n")

    for band, url in urls.items():
        print(f"== Полоса {band} ==")
        meta = describe_band(url)
        for key, value in meta.items():
            print(f"  {key}: {value}")
        preview = PREVIEW_DIR / f"{tile_id}_{band}.png"
        save_preview(url, preview, downscale=args.downscale)
        print(f"  preview: {preview.relative_to(PROJECT_ROOT)}")
        print()


if __name__ == "__main__":
    main()
