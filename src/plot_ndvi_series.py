"""Визуализация серии NDVI: time-series графики по 20 полям.

Использование:
    python src/plot_ndvi_series.py
        [--csv data/processed/fields_ndvi_series.csv]
        [--fields data/fields/fields_v1.geojson]

Графики:
    1. Все 20 полей одной серией -- полупрозрачные линии + медиана + IQR;
    2. Grid 4×5 subplots: по одному полю на subplot;
    3. Гистограмма valid_share по сезону.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import geopandas as gpd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PREVIEW_DIR = PROJECT_ROOT / "data" / "preview"


def plot_all_on_one(df: pd.DataFrame) -> Path:
    fig, ax = plt.subplots(figsize=(13, 6))
    pivot = df.pivot_table(index="date", columns="field_id", values="ndvi_mean", aggfunc="mean")
    pivot.index = pd.to_datetime(pivot.index)
    pivot = pivot.sort_index()
    for col in pivot.columns:
        ax.plot(pivot.index, pivot[col], color="#1e7a1e", alpha=0.20, linewidth=0.9)
    median = pivot.median(axis=1)
    p25 = pivot.quantile(0.25, axis=1)
    p75 = pivot.quantile(0.75, axis=1)
    ax.fill_between(pivot.index, p25, p75, color="#1e7a1e", alpha=0.15, label="IQR 20 полей")
    ax.plot(pivot.index, median, color="#0a3d0a", linewidth=2.0, label="медиана 20 полей")
    ax.set_xlabel("дата")
    ax.set_ylabel("NDVI mean по полю")
    ax.set_title("NDVI time-series, рисовые чеки Темрюкский район, окт 2023 - сен 2024")
    ax.axhline(0.0, color="#666", linewidth=0.5)
    ax.axhline(0.5, color="#999", linestyle="--", linewidth=0.6)
    ax.axhline(0.8, color="#1e7a1e", linestyle="--", linewidth=0.6)
    ax.grid(alpha=0.25)
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    ax.legend(loc="upper left")
    fig.tight_layout()
    out = PREVIEW_DIR / "ndvi_series_all_fields.png"
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_grid_per_field(df: pd.DataFrame, areas: dict[str, float]) -> Path:
    fields = sorted(df["field_id"].unique())
    n_cols = 5
    n_rows = (len(fields) + n_cols - 1) // n_cols
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(4 * n_cols, 2.6 * n_rows), sharey=True)
    axes = np.atleast_2d(axes)
    pivot = df.pivot_table(index="date", columns="field_id", values="ndvi_mean", aggfunc="mean")
    pivot.index = pd.to_datetime(pivot.index)
    pivot = pivot.sort_index()
    median = pivot.median(axis=1)
    for i, fid in enumerate(fields):
        ax = axes[i // n_cols, i % n_cols]
        series = pivot[fid]
        ax.plot(series.index, series, color="#0a3d0a", linewidth=1.5, marker="o", markersize=2.5)
        ax.plot(median.index, median, color="#999", linewidth=0.8, alpha=0.7)
        ax.fill_between(series.index, 0, series, color="#1e7a1e", alpha=0.18)
        ax.set_title(f"{fid} ({areas.get(fid, 0):.0f} га)", fontsize=9)
        ax.set_ylim(-0.3, 1.0)
        ax.grid(alpha=0.25)
        ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%y"))
        plt.setp(ax.get_xticklabels(), rotation=45, ha="right", fontsize=7)
    for j in range(len(fields), n_rows * n_cols):
        axes[j // n_cols, j % n_cols].axis("off")
    fig.suptitle("NDVI по каждому полю (серый -- медиана 20 полей)", fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    out = PREVIEW_DIR / "ndvi_series_grid.png"
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_valid_share(df: pd.DataFrame) -> Path:
    by_date = df.groupby("date")["valid_share"].mean().sort_index()
    by_date.index = pd.to_datetime(by_date.index)
    fig, ax = plt.subplots(figsize=(13, 4))
    ax.bar(by_date.index, by_date.values, width=4, color="#1e7a1e", alpha=0.65)
    ax.set_ylabel("средняя доля валидных пикселей по полям")
    ax.set_xlabel("дата")
    ax.set_title("Качество снимков (1.0 = все пиксели валидны, 0.0 = всё в маске)")
    ax.axhline(0.5, color="#999", linestyle="--", linewidth=0.7)
    ax.grid(alpha=0.25)
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    ax.set_ylim(0, 1)
    fig.tight_layout()
    out = PREVIEW_DIR / "ndvi_series_valid_share.png"
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default=str(PROJECT_ROOT / "data" / "processed" / "fields_ndvi_series.csv"))
    parser.add_argument("--fields", default=str(PROJECT_ROOT / "data" / "fields" / "fields_v1.geojson"))
    args = parser.parse_args()

    df = pd.read_csv(args.csv)
    print(f"Серия: {len(df)} строк, {df['field_id'].nunique()} полей, {df['date'].nunique()} дат")
    print(f"  диапазон дат: {df['date'].min()} -- {df['date'].max()}")
    print(f"  доля строк с валидным NDVI: {df['ndvi_mean'].notna().mean():.2%}")

    areas = gpd.read_file(args.fields).set_index("field_id")["area_ha"].to_dict()

    print("\nГрафики:")
    p1 = plot_all_on_one(df)
    print(f"  все 20 полей -> {p1.relative_to(PROJECT_ROOT)}")
    p2 = plot_grid_per_field(df, areas)
    print(f"  grid 4×5     -> {p2.relative_to(PROJECT_ROOT)}")
    p3 = plot_valid_share(df)
    print(f"  valid share  -> {p3.relative_to(PROJECT_ROOT)}")

    print("\nКлючевые статистики кривой median:")
    pivot = df.pivot_table(index="date", columns="field_id", values="ndvi_mean", aggfunc="mean")
    pivot.index = pd.to_datetime(pivot.index)
    pivot = pivot.sort_index()
    median = pivot.median(axis=1)
    print(f"  минимум median: {median.min():.3f} @ {median.idxmin().date()}")
    print(f"  максимум median: {median.max():.3f} @ {median.idxmax().date()}")
    print(f"  амплитуда: {median.max() - median.min():.3f}")


if __name__ == "__main__":
    main()
