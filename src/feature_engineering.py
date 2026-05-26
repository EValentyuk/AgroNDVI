"""Feature engineering: фичи по полям из NDVI-серии + погода + синтетический таргет.

Использование:
    python src/feature_engineering.py
        [--ndvi-csv data/processed/fields_ndvi_series.csv]
        [--weather-csv data/weather/weather_daily.csv]
        [--fields data/fields/fields_v1.geojson]
        [--out data/processed/fields_features.csv]
        [--target-noise 2.0]

Что делает:
    1. Грузит NDVI-серию (20 полей × 45 дат) и погоду (366 дней);
    2. Для каждого поля интерполирует пропуски NDVI и сглаживает (rolling 21d);
    3. Считает фичи NDVI: peak, date_peak, integral, vegetation_days,
       NDVI по фазам (весна/лето/осень), производная роста, аномалия от
       медианы 20 полей;
    4. Агрегирует погоду по рисовому сезону (1 апреля -- 30 сентября):
       сумма GDD (база 10°C), сумма осадков, сумма солнечной радиации,
       средняя температура, ET0, влажность;
    5. Назначает синтетический таргет урожайности по правилу
       yield = 55 + 30*(NDVI_peak - median) + N(0, target_noise) ц/га.
       Это НЕ реальные данные. Реальной пол-уровневой урожайности риса
       нет в открытом доступе. Используем синтетику для демонстрации
       feature engineering + ML pipeline;
    6. Сохраняет fields_features.csv: 20 строк × ~18 колонок.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import geopandas as gpd
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent

RICE_SEASON_FROM = "2024-04-01"
RICE_SEASON_TO = "2024-09-30"
GDD_BASE_C = 10.0
NDVI_VEG_THRESHOLD = 0.3

YIELD_BASE = 55.0
YIELD_NDVI_COEF = 30.0


def smooth_ndvi(series_long: pd.DataFrame) -> pd.DataFrame:
    """Для каждого поля: интерполяция пропусков по дате + rolling 21d."""
    series_long = series_long.copy()
    series_long["date"] = pd.to_datetime(series_long["date"])
    pivot = series_long.pivot_table(index="date", columns="field_id", values="ndvi_mean", aggfunc="mean")
    pivot = pivot.sort_index()
    full_idx = pd.date_range(pivot.index.min(), pivot.index.max(), freq="D")
    pivot = pivot.reindex(full_idx)
    pivot = pivot.interpolate(method="time", limit_direction="both")
    smoothed = pivot.rolling(window=21, center=True, min_periods=5).mean()
    return smoothed


def ndvi_features_for_field(field_id: str, series: pd.Series) -> dict:
    s = series.dropna()
    if s.empty:
        return {"field_id": field_id}
    season_mask = (s.index >= pd.Timestamp(RICE_SEASON_FROM)) & (s.index <= pd.Timestamp(RICE_SEASON_TO))
    s_season = s[season_mask]
    if s_season.empty:
        return {"field_id": field_id}

    peak = float(s_season.max())
    date_peak = s_season.idxmax()
    veg_mask = s_season > NDVI_VEG_THRESHOLD
    veg_days = int(veg_mask.sum())
    integral = float(s_season.clip(lower=0).sum())

    growth_rate = float(s_season.diff().clip(lower=0).max()) if len(s_season) > 1 else 0.0

    spring = s.loc[(s.index >= "2024-04-01") & (s.index <= "2024-05-31")].mean()
    summer = s.loc[(s.index >= "2024-06-01") & (s.index <= "2024-07-31")].mean()
    late = s.loc[(s.index >= "2024-08-01") & (s.index <= "2024-09-30")].mean()

    return {
        "field_id": field_id,
        "ndvi_peak": round(peak, 4),
        "ndvi_date_peak": date_peak.strftime("%Y-%m-%d"),
        "ndvi_doy_peak": int(date_peak.dayofyear),
        "ndvi_integral_season": round(integral, 2),
        "ndvi_vegetation_days": veg_days,
        "ndvi_growth_rate_max": round(growth_rate, 5),
        "ndvi_spring_mean": round(float(spring), 4) if not np.isnan(spring) else None,
        "ndvi_summer_mean": round(float(summer), 4) if not np.isnan(summer) else None,
        "ndvi_late_mean": round(float(late), 4) if not np.isnan(late) else None,
    }


def weather_features(weather: pd.DataFrame) -> dict:
    weather = weather.copy()
    weather["date"] = pd.to_datetime(weather["date"])
    mask = (weather["date"] >= pd.Timestamp(RICE_SEASON_FROM)) & (weather["date"] <= pd.Timestamp(RICE_SEASON_TO))
    season = weather[mask]
    gdd = (season["temperature_2m_mean"] - GDD_BASE_C).clip(lower=0).sum()
    return {
        "weather_gdd_season": round(float(gdd), 1),
        "weather_t_mean_season": round(float(season["temperature_2m_mean"].mean()), 2),
        "weather_t_max_season": round(float(season["temperature_2m_max"].max()), 2),
        "weather_t_min_season": round(float(season["temperature_2m_min"].min()), 2),
        "weather_precip_season_mm": round(float(season["precipitation_sum"].sum()), 1),
        "weather_solar_season_mj": round(float(season["ALLSKY_SFC_SW_DWN"].sum()), 1),
        "weather_et0_season_mm": round(float(season["et0_fao_evapotranspiration"].sum()), 1),
        "weather_humidity_season": round(float(season["relative_humidity_2m_mean"].mean()), 2),
    }


def synthetic_yield(ndvi_peak: float, median_peak: float, noise_sd: float, rng: np.random.Generator) -> float:
    return float(YIELD_BASE + YIELD_NDVI_COEF * (ndvi_peak - median_peak) + rng.normal(0, noise_sd))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ndvi-csv", default=str(PROJECT_ROOT / "data" / "processed" / "fields_ndvi_series.csv"))
    parser.add_argument("--weather-csv", default=str(PROJECT_ROOT / "data" / "weather" / "weather_daily.csv"))
    parser.add_argument("--fields", default=str(PROJECT_ROOT / "data" / "fields" / "fields_v1.geojson"))
    parser.add_argument("--out", default=str(PROJECT_ROOT / "data" / "processed" / "fields_features.csv"))
    parser.add_argument("--target-noise", type=float, default=2.0)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    print("Загрузка...")
    ndvi_series = pd.read_csv(args.ndvi_csv)
    weather = pd.read_csv(args.weather_csv)
    fields_gdf = gpd.read_file(args.fields)
    print(f"  NDVI:    {len(ndvi_series)} строк, {ndvi_series['field_id'].nunique()} полей")
    print(f"  Weather: {len(weather)} дней")
    print(f"  Fields:  {len(fields_gdf)} полей")

    print("\nСглаживание NDVI (интерполяция + rolling 21d)...")
    smoothed = smooth_ndvi(ndvi_series)

    print("Расчёт фичей NDVI по полям...")
    rows = []
    for fid in sorted(smoothed.columns):
        feats = ndvi_features_for_field(fid, smoothed[fid])
        rows.append(feats)
    ndvi_df = pd.DataFrame(rows)

    print("Расчёт фичей погоды (рисовый сезон 1 апр -- 30 сен)...")
    w_feats = weather_features(weather)
    for k, v in w_feats.items():
        print(f"  {k}: {v}")

    print("\nОбъединение с площадью + расчёт аномалии NDVI...")
    fields_df = fields_gdf[["field_id", "area_ha", "crop"]].rename(columns={"crop": "crop_osm"})
    df = ndvi_df.merge(fields_df, on="field_id", how="left")
    for k, v in w_feats.items():
        df[k] = v

    median_peak = df["ndvi_peak"].median()
    df["ndvi_peak_anomaly"] = (df["ndvi_peak"] - median_peak).round(4)

    print(f"\nСинтетический таргет урожайности:")
    print(f"  yield = {YIELD_BASE} + {YIELD_NDVI_COEF}*(NDVI_peak - {median_peak:.3f}) + N(0, {args.target_noise})")
    print(f"  это НЕ реальные данные, поле-уровневой урожайности риса в открытом доступе нет.")
    rng = np.random.default_rng(args.seed)
    df["yield_centner_ha"] = [round(synthetic_yield(p, median_peak, args.target_noise, rng), 2) for p in df["ndvi_peak"]]

    cols_order = [
        "field_id", "area_ha", "crop_osm",
        "ndvi_peak", "ndvi_date_peak", "ndvi_doy_peak",
        "ndvi_integral_season", "ndvi_vegetation_days",
        "ndvi_growth_rate_max", "ndvi_peak_anomaly",
        "ndvi_spring_mean", "ndvi_summer_mean", "ndvi_late_mean",
        "weather_gdd_season", "weather_t_mean_season", "weather_t_max_season", "weather_t_min_season",
        "weather_precip_season_mm", "weather_solar_season_mj",
        "weather_et0_season_mm", "weather_humidity_season",
        "yield_centner_ha",
    ]
    df = df[cols_order]

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False, encoding="utf-8")
    print(f"\nfields_features.csv -> {out_path.relative_to(PROJECT_ROOT)}  ({len(df)} строк × {len(df.columns)} колонок)")
    print("\nТаблица:")
    print(df.to_string(index=False))

    print("\nКорреляции фичей NDVI с таргетом yield:")
    ndvi_cols = [c for c in df.columns if c.startswith("ndvi_") and df[c].dtype.kind in "fi"]
    corrs = df[ndvi_cols + ["yield_centner_ha"]].corr()["yield_centner_ha"].drop("yield_centner_ha").sort_values(ascending=False)
    print(corrs.to_string())


if __name__ == "__main__":
    main()
