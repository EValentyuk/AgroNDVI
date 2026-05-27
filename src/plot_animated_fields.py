"""Анимированный GIF: 20 рисовых чеков раскрашены по NDVI на каждую дату серии.

Использование:
    python src/plot_animated_fields.py
        [--out docs/images/ndvi_animation.gif]
        [--fps 4]

Что даёт:
    Самый сильный wow-эффект для не-агронома: видно как поля меняют цвет
    от затопления (бурый) через всходы к пику (тёмно-зелёный) и обратно к
    жатве (жёлтый). 45 кадров за сезон октябрь 2023 -- сентябрь 2024,
    ~11 секунд при fps=4.

ВАЖНО: не требует никаких новых зависимостей. Использует PillowWriter из
matplotlib (Pillow уже в venv через streamlit). НЕ нужно imageio.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("PANDAS_USE_PYARROW_STRINGS", "0")
sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

pd.options.future.infer_string = False

import matplotlib

matplotlib.use("Agg")
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter
import geopandas as gpd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIELDS_PATH = PROJECT_ROOT / "data" / "fields" / "fields_v1.geojson"
NDVI_PATH = PROJECT_ROOT / "data" / "processed" / "fields_ndvi_series.csv"


def make_cmap() -> mcolors.LinearSegmentedColormap:
    cmap = mcolors.LinearSegmentedColormap.from_list(
        "ndvi_agro",
        [(0.0, "#3a1f0a"), (0.25, "#a05a14"), (0.45, "#d8c84a"),
         (0.65, "#7fbf3f"), (0.85, "#1e7a1e"), (1.0, "#0a3d0a")],
    )
    cmap.set_bad("#404040")
    return cmap


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(PROJECT_ROOT / "docs" / "images" / "ndvi_animation.gif"))
    parser.add_argument("--fps", type=int, default=4)
    parser.add_argument("--dpi", type=int, default=85)
    args = parser.parse_args()

    print("Загрузка данных...")
    fields = gpd.read_file(FIELDS_PATH).to_crs("EPSG:32637")
    ndvi = pd.read_csv(NDVI_PATH)
    ndvi["date"] = pd.to_datetime(ndvi["date"])
    dates = sorted(ndvi["date"].unique())
    print(f"  полей: {len(fields)}, дат: {len(dates)}")

    cmap = make_cmap()
    fig, ax = plt.subplots(figsize=(10, 7), dpi=args.dpi)

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(vmin=-0.2, vmax=1.0))
    cbar = fig.colorbar(sm, ax=ax, fraction=0.04, pad=0.02)
    cbar.set_label("NDVI", fontsize=11)
    cbar.ax.tick_params(labelsize=9)

    minx, miny, maxx, maxy = fields.total_bounds
    pad_x = (maxx - minx) * 0.04
    pad_y = (maxy - miny) * 0.04
    ax.set_xlim(minx - pad_x, maxx + pad_x)
    ax.set_ylim(miny - pad_y, maxy + pad_y)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_edgecolor("#999")

    title = ax.set_title("", fontsize=13, fontweight="bold", pad=8)
    subtitle = ax.text(
        0.5, -0.04, "20 рисовых чеков, Темрюкский район Краснодарского края",
        transform=ax.transAxes, ha="center", va="top", fontsize=10, color="#555",
    )

    drawn_polys = []

    def update(frame_idx):
        date = dates[frame_idx]
        nonlocal drawn_polys
        for p in drawn_polys:
            p.remove()
        drawn_polys = []

        df_date = ndvi[ndvi["date"] == date][["field_id", "ndvi_mean"]]
        merged = fields.merge(df_date, on="field_id", how="left")
        plot_obj = merged.plot(
            column="ndvi_mean", cmap=cmap, vmin=-0.2, vmax=1.0,
            ax=ax, edgecolor="black", linewidth=0.6, missing_kwds={"color": "#404040"},
        )
        drawn_polys = [coll for coll in ax.collections if coll not in {sm}]

        valid = df_date["ndvi_mean"].dropna()
        median = valid.median() if len(valid) else float("nan")
        title.set_text(f"{pd.Timestamp(date).strftime('%Y-%m-%d')}   ·   медиана NDVI = {median:.2f}")
        return drawn_polys + [title]

    print(f"\nГенерация {len(dates)} кадров (это займёт минуту)...")
    anim = FuncAnimation(fig, update, frames=len(dates), interval=1000 // args.fps, blit=False)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    anim.save(out_path, writer=PillowWriter(fps=args.fps))
    plt.close(fig)

    size_kb = out_path.stat().st_size / 1024
    print(f"\nGIF готов: {out_path.relative_to(PROJECT_ROOT)}  ({size_kb:.0f} КБ)")
    print(f"  кадров: {len(dates)}, fps: {args.fps}, длительность ~{len(dates)/args.fps:.1f}s")


if __name__ == "__main__":
    main()
