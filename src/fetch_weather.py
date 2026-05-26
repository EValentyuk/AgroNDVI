"""Скачивание погоды и солнечной радиации за период.

Использование:
    python src/fetch_weather.py
        [--lon 38.275] [--lat 45.075]
        [--from 2023-10-01] [--to 2024-09-30]
        [--out-dir data/weather]

Источники:
    1. Open Meteo Historical API -- температура (max/min/mean), осадки,
       влажность, ветер, ET0 эвапотранспирация. Бесплатно, без ключа.
    2. NASA POWER -- солнечная радиация (ALLSKY_SFC_SW_DWN, MJ/m²/день).
       Бесплатно, без ключа.

Точка по умолчанию -- центр bbox 20 полей в Темрюкском районе.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEATHER_DIR = PROJECT_ROOT / "data" / "weather"

OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"
NASA_POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"

OPEN_METEO_VARS = [
    "temperature_2m_max",
    "temperature_2m_min",
    "temperature_2m_mean",
    "precipitation_sum",
    "rain_sum",
    "snowfall_sum",
    "relative_humidity_2m_mean",
    "wind_speed_10m_max",
    "et0_fao_evapotranspiration",
    "soil_moisture_0_to_7cm_mean",
    "soil_temperature_0_to_7cm_mean",
]

NASA_POWER_VARS = [
    "ALLSKY_SFC_SW_DWN",
    "T2M_MAX",
    "T2M_MIN",
    "T2M",
    "PRECTOTCORR",
    "RH2M",
]


def fetch_open_meteo(lon: float, lat: float, date_from: str, date_to: str) -> pd.DataFrame:
    print(f"Open Meteo: точка ({lon}, {lat}), период {date_from} -- {date_to}")
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": date_from,
        "end_date": date_to,
        "daily": ",".join(OPEN_METEO_VARS),
        "timezone": "Europe/Moscow",
    }
    t0 = time.perf_counter()
    resp = requests.get(OPEN_METEO_URL, params=params, timeout=60)
    resp.raise_for_status()
    body = resp.json()
    dt = time.perf_counter() - t0
    daily = body.get("daily", {})
    df = pd.DataFrame(daily)
    df = df.rename(columns={"time": "date"})
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    print(f"  получено {len(df)} строк за {dt:.1f}s")
    return df


def fetch_nasa_power(lon: float, lat: float, date_from: str, date_to: str) -> pd.DataFrame:
    start = date_from.replace("-", "")
    end = date_to.replace("-", "")
    print(f"\nNASA POWER: точка ({lon}, {lat}), период {start} -- {end}")
    params = {
        "parameters": ",".join(NASA_POWER_VARS),
        "community": "AG",
        "longitude": lon,
        "latitude": lat,
        "start": start,
        "end": end,
        "format": "JSON",
    }
    t0 = time.perf_counter()
    resp = requests.get(NASA_POWER_URL, params=params, timeout=120)
    resp.raise_for_status()
    body = resp.json()
    dt = time.perf_counter() - t0
    parameters = body.get("properties", {}).get("parameter", {})
    if not parameters:
        raise RuntimeError("NASA POWER вернул пустые параметры")
    dates = sorted(next(iter(parameters.values())).keys())
    rows = []
    for d in dates:
        row = {"date": f"{d[:4]}-{d[4:6]}-{d[6:]}"}
        for var, values in parameters.items():
            v = values.get(d)
            row[var] = None if v == -999.0 else v
        rows.append(row)
    df = pd.DataFrame(rows)
    print(f"  получено {len(df)} строк за {dt:.1f}s")
    return df


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lon", type=float, default=38.275, help="центр bbox полей")
    parser.add_argument("--lat", type=float, default=45.075)
    parser.add_argument("--from", dest="date_from", default="2023-10-01")
    parser.add_argument("--to", dest="date_to", default="2024-09-30")
    parser.add_argument("--out-dir", default=str(WEATHER_DIR))
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    om = fetch_open_meteo(args.lon, args.lat, args.date_from, args.date_to)
    om_path = out_dir / "open_meteo.csv"
    om.to_csv(om_path, index=False, encoding="utf-8")
    print(f"  -> {om_path.relative_to(PROJECT_ROOT)}")

    np_df = fetch_nasa_power(args.lon, args.lat, args.date_from, args.date_to)
    np_path = out_dir / "nasa_power.csv"
    np_df.to_csv(np_path, index=False, encoding="utf-8")
    print(f"  -> {np_path.relative_to(PROJECT_ROOT)}")

    merged = om.merge(np_df, on="date", how="outer", suffixes=("_om", "_np"))
    merged_path = out_dir / "weather_daily.csv"
    merged.to_csv(merged_path, index=False, encoding="utf-8")
    print(f"\nОбъединённый daily CSV -> {merged_path.relative_to(PROJECT_ROOT)}")
    print(f"  колонки ({len(merged.columns)}): {list(merged.columns)}")

    print("\nКлючевые агрегаты:")
    if "temperature_2m_mean" in merged:
        print(f"  T2M_mean: mean {merged['temperature_2m_mean'].mean():.2f}°C, min {merged['temperature_2m_mean'].min():.2f}, max {merged['temperature_2m_mean'].max():.2f}")
    if "precipitation_sum" in merged:
        print(f"  precipitation_sum: total {merged['precipitation_sum'].sum():.1f} мм")
    if "ALLSKY_SFC_SW_DWN" in merged:
        print(f"  solar radiation: mean {merged['ALLSKY_SFC_SW_DWN'].mean():.2f} MJ/m²/день, total {merged['ALLSKY_SFC_SW_DWN'].sum():.0f} MJ/m²/год")


if __name__ == "__main__":
    main()
