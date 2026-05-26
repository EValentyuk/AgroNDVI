"""Совмещённый график NDVI + погода для контекстуализации сезонной динамики.

Использование:
    python src/plot_weather_ndvi.py

Создаёт:
    data/preview/ndvi_vs_weather.png  -- три панели:
        1. NDVI median по 20 полям + IQR (полупрозрачно);
        2. Daily T2M_max / T2M_min + полоса между ними;
        3. Daily precipitation + cumulative GDD по правой оси.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
NDVI_CSV = PROJECT_ROOT / "data" / "processed" / "fields_ndvi_series.csv"
WEATHER_CSV = PROJECT_ROOT / "data" / "weather" / "weather_daily.csv"
OUT_PNG = PROJECT_ROOT / "data" / "preview" / "ndvi_vs_weather.png"

GDD_BASE = 10.0


def main() -> None:
    ndvi = pd.read_csv(NDVI_CSV)
    ndvi["date"] = pd.to_datetime(ndvi["date"])
    pivot = ndvi.pivot_table(index="date", columns="field_id", values="ndvi_mean", aggfunc="mean").sort_index()
    median = pivot.median(axis=1)
    p25 = pivot.quantile(0.25, axis=1)
    p75 = pivot.quantile(0.75, axis=1)

    w = pd.read_csv(WEATHER_CSV)
    w["date"] = pd.to_datetime(w["date"])
    w = w.sort_values("date").reset_index(drop=True)
    w["gdd_daily"] = (w["temperature_2m_mean"] - GDD_BASE).clip(lower=0)
    w["gdd_cum"] = w["gdd_daily"].cumsum()

    fig, axes = plt.subplots(3, 1, figsize=(13, 11), sharex=True)

    ax = axes[0]
    ax.fill_between(pivot.index, p25, p75, color="#1e7a1e", alpha=0.18, label="IQR 20 полей")
    ax.plot(pivot.index, median, color="#0a3d0a", linewidth=2.0, label="медиана 20 полей")
    ax.axhline(0.0, color="#666", linewidth=0.5)
    ax.axhline(0.3, color="#a05a14", linestyle=":", linewidth=0.7, label="0.3 порог вегетации")
    ax.set_ylabel("NDVI")
    ax.set_title("NDVI рисовых чеков, Темрюкский район, окт 2023 - сен 2024")
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(alpha=0.25)
    ax.set_ylim(-0.2, 0.7)

    ax = axes[1]
    ax.fill_between(w["date"], w["temperature_2m_min"], w["temperature_2m_max"], color="#ef6c00", alpha=0.25, label="диапазон T_min - T_max")
    ax.plot(w["date"], w["temperature_2m_mean"], color="#e53935", linewidth=1.0, label="T_mean")
    ax.axhline(GDD_BASE, color="#999", linestyle="--", linewidth=0.7, label=f"база GDD {GDD_BASE}°C")
    ax.set_ylabel("температура, °C")
    ax.set_title("Температура (Open Meteo, точка центра bbox полей)")
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(alpha=0.25)

    ax = axes[2]
    ax.bar(w["date"], w["precipitation_sum"], width=1.0, color="#1e88e5", alpha=0.7, label="осадки, мм/день")
    ax.set_ylabel("осадки, мм/день", color="#1e88e5")
    ax.tick_params(axis="y", labelcolor="#1e88e5")
    ax.grid(alpha=0.25)

    ax2 = ax.twinx()
    ax2.plot(w["date"], w["gdd_cum"], color="#8e24aa", linewidth=2.0, label="кумулятивный GDD")
    ax2.set_ylabel("кумулятивный GDD, °C·день", color="#8e24aa")
    ax2.tick_params(axis="y", labelcolor="#8e24aa")
    ax.set_title("Осадки + накопленные тёплые градусо-дни")
    ax.set_xlabel("дата")
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=9)

    for a in axes:
        a.xaxis.set_major_locator(mdates.MonthLocator())
        a.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        plt.setp(a.get_xticklabels(), rotation=30, ha="right")

    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"График -> {OUT_PNG.relative_to(PROJECT_ROOT)}")

    print("\nКлючевые маркеры сезона:")
    veg_start = median[median > 0.3].index.min() if (median > 0.3).any() else None
    peak_date = median.idxmax()
    peak_val = median.max()
    gdd_at_peak = float(w.loc[w["date"] == peak_date, "gdd_cum"].iloc[0]) if peak_date in set(w["date"]) else None
    print(f"  начало вегетации (NDVI > 0.3): {veg_start.date() if veg_start is not None else '—'}")
    print(f"  пик медианы NDVI:              {peak_date.date()} = {peak_val:.3f}")
    print(f"  кум. GDD на дату пика:         {gdd_at_peak:.0f}" if gdd_at_peak is not None else "  GDD на пик: —")
    print(f"  всего осадков за период:       {w['precipitation_sum'].sum():.0f} мм")
    print(f"  макс GDD за период:            {w['gdd_cum'].iloc[-1]:.0f}")


if __name__ == "__main__":
    main()
