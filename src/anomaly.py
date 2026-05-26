"""Anomaly detection по NDVI-кривым полей.

Использование:
    python src/anomaly.py
        [--ndvi-csv data/processed/fields_ndvi_series.csv]
        [--features-csv data/processed/fields_features.csv]
        [--out data/processed/fields_anomaly.csv]
        [--top-k 3]

Три независимых метода, чтобы получить устойчивый ранжированный список:

1. **Pointwise z-score** -- по каждой дате считаем медиану и MAD по 20 полям.
   Для поля считаем z = (ndvi_f - median_all_fields) / MAD. Если |z| > 2 -- это
   аномальная точка. Сумма |z| и число аномальных точек по полю даёт
   anomaly_z_total и anomaly_z_count.
2. **IsolationForest** -- на тех же 18 фичах что у LightGBM. Контаминация 0.15
   (3 аномалии из 20 ожидаемых). decision_function: чем ниже -- тем аномальнее.
3. **L2 от медианы** -- сглаженная NDVI-кривая поля (rolling 21d) сравнивается
   с медианной кривой по 20 полям через L2-норму.

Итоговый ранг = mean(rank_z, rank_iso, rank_l2). Top-K -- финальные аномалии.

ВАЖНО (для портфолио). На реальной задаче «исторический коридор» строится
из multi-year данных по тому же полю: 5 лет NDVI 2020-2024 даёт коридор
p10-p90 на каждый календарный день. У нас данных за один год, поэтому
коридор строится по соседним полям того же года -- это слабый proxy. Соседние
поля могут отличаться сортом, датой затопления, фазой ротации. Этот
выбор зафиксирован честно. См. docs/experiments/2026-05-26-anomaly.md.
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

import numpy as np
from sklearn.ensemble import IsolationForest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

DROP_FEATURE_COLS = {"field_id", "crop_osm", "ndvi_date_peak", "yield_centner_ha"}
Z_THRESHOLD = 2.0


def smooth_ndvi(series_long: pd.DataFrame) -> pd.DataFrame:
    s = series_long.copy()
    s["date"] = pd.to_datetime(s["date"])
    pivot = s.pivot_table(index="date", columns="field_id", values="ndvi_mean", aggfunc="mean").sort_index()
    full_idx = pd.date_range(pivot.index.min(), pivot.index.max(), freq="D")
    pivot = pivot.reindex(full_idx).interpolate(method="time", limit_direction="both")
    return pivot.rolling(window=21, center=True, min_periods=5).mean()


def pointwise_z(smoothed: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    median = smoothed.median(axis=1)
    mad = (smoothed.sub(median, axis=0)).abs().median(axis=1).replace(0, np.nan)
    z = smoothed.sub(median, axis=0).div(mad, axis=0).fillna(0.0)
    z_count = (z.abs() > Z_THRESHOLD).sum(axis=0).rename("anomaly_z_count")
    z_total = z.abs().sum(axis=0).rename("anomaly_z_total")
    per_field = pd.concat([z_count, z_total], axis=1)
    per_field.index.name = "field_id"
    return z, per_field


def isolation_forest(features_csv: Path, contamination: float = 0.15) -> pd.Series:
    df = pd.read_csv(features_csv)
    feature_cols = [c for c in df.columns if c not in DROP_FEATURE_COLS and df[c].dtype.kind in "fi"]
    feature_cols = [c for c in feature_cols if df[c].nunique() > 1]
    X = df[feature_cols].fillna(df[feature_cols].median())
    iso = IsolationForest(contamination=contamination, n_estimators=200, random_state=42)
    iso.fit(X)
    score = -iso.decision_function(X)
    return pd.Series(score, index=df["field_id"], name="isoforest_score")


def l2_from_median(smoothed: pd.DataFrame) -> pd.Series:
    median = smoothed.median(axis=1)
    diff = smoothed.sub(median, axis=0)
    l2 = np.sqrt((diff ** 2).sum(axis=0))
    l2.name = "l2_from_median"
    return l2


def rank_desc(s: pd.Series) -> pd.Series:
    """Высокое значение → ранг 1 (самый аномальный)."""
    return s.rank(ascending=False, method="min").astype(int)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ndvi-csv", default=str(PROCESSED_DIR / "fields_ndvi_series.csv"))
    parser.add_argument("--features-csv", default=str(PROCESSED_DIR / "fields_features.csv"))
    parser.add_argument("--out", default=str(PROCESSED_DIR / "fields_anomaly.csv"))
    parser.add_argument("--out-z", default=str(PROCESSED_DIR / "fields_anomaly_z_matrix.csv"))
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()

    print("Загрузка...")
    ndvi = pd.read_csv(args.ndvi_csv)
    print(f"  NDVI: {len(ndvi)} строк, {ndvi['field_id'].nunique()} полей")

    print("Сглаживание (rolling 21d)...")
    smoothed = smooth_ndvi(ndvi)
    print(f"  daily grid: {smoothed.shape}")

    print("\nМетод 1: pointwise z-score (порог |z|>2)...")
    z_matrix, z_per_field = pointwise_z(smoothed)
    z_matrix.to_csv(args.out_z, encoding="utf-8")
    print(f"  z-matrix -> {Path(args.out_z).relative_to(PROJECT_ROOT)}")
    print(z_per_field.sort_values("anomaly_z_total", ascending=False).to_string())

    print("\nМетод 2: IsolationForest на 18 фичах (contamination=0.15)...")
    iso = isolation_forest(Path(args.features_csv))
    print(iso.sort_values(ascending=False).to_string())

    print("\nМетод 3: L2 от медианной кривой...")
    l2 = l2_from_median(smoothed)
    print(l2.sort_values(ascending=False).to_string())

    print("\nОбъединение и ранжирование...")
    result = z_per_field.join(iso).join(l2)
    result["rank_z"] = rank_desc(result["anomaly_z_total"])
    result["rank_iso"] = rank_desc(result["isoforest_score"])
    result["rank_l2"] = rank_desc(result["l2_from_median"])
    result["mean_rank"] = result[["rank_z", "rank_iso", "rank_l2"]].mean(axis=1).round(2)
    result["is_anomaly_top_k"] = result["mean_rank"].rank(method="min").astype(int) <= args.top_k
    result = result.sort_values("mean_rank")

    result.to_csv(args.out, encoding="utf-8")
    print(f"\nfields_anomaly.csv -> {Path(args.out).relative_to(PROJECT_ROOT)}")
    print(result.to_string())

    top_k = result[result["is_anomaly_top_k"]].index.tolist()
    print(f"\nTop-{args.top_k} аномалий по объединённому рангу: {top_k}")
    print("Согласованность методов (Spearman correlations):")
    rho = result[["anomaly_z_total", "isoforest_score", "l2_from_median"]].corr(method="spearman")
    print(rho.to_string())


if __name__ == "__main__":
    main()
