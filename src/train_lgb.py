"""LightGBM regressor для прогноза урожайности + baselines + LOO-CV + feature importance.

Использование:
    python src/train_lgb.py
        [--features data/processed/fields_features.csv]
        [--out-model models/lgb_yield.pkl]
        [--out-preds data/processed/cv_predictions.csv]

Дисциплина:
    - Датасет 20 строк -- маленький. Любая регрессионная модель в этом режиме
      склонна к переобучению. Используем Leave-One-Out CV: модель учится
      на 19 строках, предсказывает 20-ю, повторяем для всех 20 -- получаем
      честную оценку out-of-sample.
    - Сравниваем LightGBM с тремя baseline моделями: mean, linear на одной
      ndvi_peak, linear на всех NDVI-фичах. LightGBM должен побеждать только
      если ловит нелинейности.
    - Метрики: MAPE, MAE, RMSE, R². Целевой MAPE 15-20% (индустриальная норма
      для прогноза урожайности по спутникам).
    - Feature importance: gain + split + permutation. Permutation -- из
      sklearn, считается на полной train-выборке после фитинга.
    - Финальная модель -- LightGBM на всех 20 точках, сохраняется в pkl.

ВАЖНО: таргет -- синтетический, см. feature_engineering.py. Метрики честные
по отношению к pipeline, но не доказывают качество модели на реальных
данных. Для реальной задачи нужен multi-year + multi-region датасет.
"""

from __future__ import annotations

import argparse
import os
import pickle
import sys
from pathlib import Path

os.environ.setdefault("PANDAS_USE_PYARROW_STRINGS", "0")
sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

pd.options.future.infer_string = False

import lightgbm as lgb
import numpy as np
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import LeaveOneOut

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = PROJECT_ROOT / "models"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

DROP_COLS = {"field_id", "crop_osm", "ndvi_date_peak", "yield_centner_ha"}


def select_features(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, list[str]]:
    feature_cols = [c for c in df.columns if c not in DROP_COLS]
    X = df[feature_cols].copy()
    for c in X.columns:
        if X[c].dtype.kind not in "fi":
            X = X.drop(columns=[c])
    y = df["yield_centner_ha"]
    return X, y, list(X.columns)


def mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.mean(np.abs((y_true - y_pred) / y_true)) * 100)


def metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    return {
        "MAPE_%": round(mape(y_true, y_pred), 2),
        "MAE": round(float(mean_absolute_error(y_true, y_pred)), 3),
        "RMSE": round(float(np.sqrt(mean_squared_error(y_true, y_pred))), 3),
        "R2": round(float(r2_score(y_true, y_pred)), 3),
    }


def loo_cv(model_factory, X: pd.DataFrame, y: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    loo = LeaveOneOut()
    preds = np.zeros(len(y))
    for train_idx, test_idx in loo.split(X):
        m = model_factory()
        m.fit(X.iloc[train_idx], y.iloc[train_idx])
        preds[test_idx] = m.predict(X.iloc[test_idx])
    return y.values, preds


def lgb_params() -> dict:
    return {
        "n_estimators": 300,
        "learning_rate": 0.05,
        "num_leaves": 7,
        "min_data_in_leaf": 2,
        "max_depth": 4,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 3,
        "lambda_l2": 0.1,
        "verbose": -1,
        "random_state": 42,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--features", default=str(PROCESSED_DIR / "fields_features.csv"))
    parser.add_argument("--out-model", default=str(MODELS_DIR / "lgb_yield.pkl"))
    parser.add_argument("--out-preds", default=str(PROCESSED_DIR / "cv_predictions.csv"))
    args = parser.parse_args()

    df = pd.read_csv(args.features)
    X, y, feature_cols = select_features(df)
    print(f"Датасет: {len(X)} строк × {len(feature_cols)} фичей")
    print(f"  таргет yield: mean {y.mean():.2f}, std {y.std():.2f}, range [{y.min():.2f}, {y.max():.2f}] ц/га")
    print(f"  фичи: {feature_cols}\n")

    results = {}

    print("=== Baseline 1: mean predictor ===")
    y_true, preds = y.values, np.full(len(y), y.mean())
    results["baseline_mean"] = metrics(y_true, preds)
    print(f"  {results['baseline_mean']}\n")

    print("=== Baseline 2: LinearRegression на одной ndvi_peak ===")
    y_true, preds = loo_cv(lambda: LinearRegression(), X[["ndvi_peak"]], y)
    results["baseline_lr_peak"] = metrics(y_true, preds)
    print(f"  {results['baseline_lr_peak']}\n")

    ndvi_cols = [c for c in feature_cols if c.startswith("ndvi_")]
    print(f"=== Baseline 3: LinearRegression на NDVI-фичах ({len(ndvi_cols)} шт) ===")
    y_true, preds = loo_cv(lambda: LinearRegression(), X[ndvi_cols], y)
    results["baseline_lr_ndvi"] = metrics(y_true, preds)
    print(f"  {results['baseline_lr_ndvi']}\n")

    print(f"=== LightGBM на всех фичах ({len(feature_cols)} шт), LOO-CV ===")
    y_true, lgb_preds = loo_cv(lambda: lgb.LGBMRegressor(**lgb_params()), X, y)
    results["lightgbm"] = metrics(y_true, lgb_preds)
    print(f"  {results['lightgbm']}\n")

    print(f"=== LightGBM только на NDVI-фичах ({len(ndvi_cols)} шт), LOO-CV ===")
    y_true, lgb_ndvi_preds = loo_cv(lambda: lgb.LGBMRegressor(**lgb_params()), X[ndvi_cols], y)
    results["lightgbm_ndvi_only"] = metrics(y_true, lgb_ndvi_preds)
    print(f"  {results['lightgbm_ndvi_only']}\n")

    print("=== Сводная таблица ===")
    summary = pd.DataFrame(results).T
    print(summary.to_string())
    print()

    print("=== Финальная LightGBM на всех 20 строках ===")
    final_model = lgb.LGBMRegressor(**lgb_params())
    final_model.fit(X, y)
    train_preds = final_model.predict(X)
    train_metrics = metrics(y.values, train_preds)
    print(f"  train fit: {train_metrics}")
    print(f"  (нормально что train сильно лучше LOO -- это и есть оценка переобучения)\n")

    print("=== Feature importance ===")
    gain_imp = pd.Series(final_model.booster_.feature_importance(importance_type="gain"), index=feature_cols).sort_values(ascending=False)
    split_imp = pd.Series(final_model.booster_.feature_importance(importance_type="split"), index=feature_cols).sort_values(ascending=False)
    perm = permutation_importance(final_model, X, y, n_repeats=30, random_state=42, scoring="neg_mean_absolute_error")
    perm_imp = pd.Series(perm.importances_mean, index=feature_cols).sort_values(ascending=False)

    imp_df = pd.DataFrame({"gain": gain_imp, "split": split_imp, "permutation": perm_imp}).sort_values("gain", ascending=False)
    print(imp_df.to_string())
    print()

    out_preds_df = pd.DataFrame({
        "field_id": df["field_id"].values,
        "y_true": y.values,
        "lgb_full_pred_loo": lgb_preds,
        "lgb_ndvi_pred_loo": lgb_ndvi_preds,
    })
    out_preds_df["residual"] = (out_preds_df["lgb_full_pred_loo"] - out_preds_df["y_true"]).round(3)
    out_preds_df["abs_pct_error"] = ((out_preds_df["residual"].abs() / out_preds_df["y_true"]) * 100).round(2)
    out_preds_df.to_csv(args.out_preds, index=False, encoding="utf-8")
    print(f"LOO predictions -> {Path(args.out_preds).relative_to(PROJECT_ROOT)}")

    imp_path = PROCESSED_DIR / "feature_importance.csv"
    imp_df.to_csv(imp_path, encoding="utf-8")
    print(f"Feature importance -> {imp_path.relative_to(PROJECT_ROOT)}")

    metrics_path = PROCESSED_DIR / "lgb_metrics.csv"
    summary.to_csv(metrics_path, encoding="utf-8")
    print(f"Metrics summary -> {metrics_path.relative_to(PROJECT_ROOT)}")

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "model": final_model,
        "feature_cols": feature_cols,
        "metrics_loo": results["lightgbm"],
        "metrics_train": train_metrics,
        "params": lgb_params(),
        "feature_importance": imp_df.to_dict(),
        "y_train_mean": float(y.mean()),
        "y_train_std": float(y.std()),
        "n_train": int(len(y)),
        "note": "Таргет синтетический (см. feature_engineering.py). LOO-CV для честной оценки.",
    }
    with open(args.out_model, "wb") as f:
        pickle.dump(payload, f)
    print(f"Model -> {Path(args.out_model).relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
