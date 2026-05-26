"""Визуализация результатов LightGBM: scatter predicted vs actual, feature importance, residuals.

Использование:
    python src/plot_model_results.py

Читает:
    data/processed/cv_predictions.csv     -- LOO predictions
    data/processed/feature_importance.csv -- gain/split/permutation
    data/processed/lgb_metrics.csv        -- сводная метрик

Рендерит:
    data/preview/cv_scatter.png       -- predicted vs actual, LightGBM full
    data/preview/feature_importance.png -- bar chart top-N
    data/preview/residuals.png        -- residuals по полям
    data/preview/model_compare.png    -- сравнение MAPE / R² для всех моделей
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("PANDAS_USE_PYARROW_STRINGS", "0")
sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

pd.options.future.infer_string = False

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
PREVIEW_DIR = PROJECT_ROOT / "data" / "preview"


def plot_cv_scatter(preds_df: pd.DataFrame) -> Path:
    fig, ax = plt.subplots(figsize=(7, 7))
    y_true = preds_df["y_true"].values
    y_pred = preds_df["lgb_full_pred_loo"].values
    lo, hi = min(y_true.min(), y_pred.min()) - 1, max(y_true.max(), y_pred.max()) + 1
    ax.plot([lo, hi], [lo, hi], color="#999", linestyle="--", linewidth=1, label="идеальное равенство")
    ax.scatter(y_true, y_pred, s=80, color="#1e7a1e", edgecolor="black", linewidth=0.6, alpha=0.85)
    for _, row in preds_df.iterrows():
        ax.annotate(row["field_id"], (row["y_true"], row["lgb_full_pred_loo"]), fontsize=7, xytext=(4, 4), textcoords="offset points")
    ax.set_xlabel("реальная урожайность, ц/га")
    ax.set_ylabel("предсказание LightGBM (LOO-CV), ц/га")
    ax.set_title("LightGBM: predicted vs actual (Leave-One-Out)")
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.grid(alpha=0.3)
    ax.legend(loc="upper left")
    mape = (np.abs(y_pred - y_true) / y_true).mean() * 100
    mae = np.abs(y_pred - y_true).mean()
    r2 = 1 - ((y_pred - y_true) ** 2).sum() / ((y_true - y_true.mean()) ** 2).sum()
    ax.text(
        0.98, 0.02, f"MAPE = {mape:.2f}%\nMAE = {mae:.2f} ц/га\nR² = {r2:.3f}\nn = {len(y_true)}",
        transform=ax.transAxes, ha="right", va="bottom",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="#fff8e1", edgecolor="#999"),
    )
    fig.tight_layout()
    out = PREVIEW_DIR / "cv_scatter.png"
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_feature_importance(imp_df: pd.DataFrame) -> Path:
    df = imp_df.copy()
    df.index.name = "feature"
    df = df.reset_index()
    df = df[df["gain"] > 0].sort_values("gain", ascending=True)
    if df.empty:
        df = imp_df.reset_index().rename(columns={"index": "feature"}).sort_values("gain", ascending=True)

    fig, axes = plt.subplots(1, 3, figsize=(15, max(5, 0.4 * len(df))), sharey=True)
    for ax, col, title, color in zip(
        axes,
        ["gain", "split", "permutation"],
        ["Gain importance", "Split count", "Permutation importance"],
        ["#1e7a1e", "#1e88e5", "#8e24aa"],
    ):
        ax.barh(df["feature"], df[col], color=color, alpha=0.85, edgecolor="black", linewidth=0.5)
        ax.set_title(title)
        ax.grid(alpha=0.25, axis="x")
    axes[0].set_ylabel("фича")
    fig.suptitle("LightGBM feature importance (после fit на всех 20 строках)", fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    out = PREVIEW_DIR / "feature_importance.png"
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_residuals(preds_df: pd.DataFrame) -> Path:
    df = preds_df.sort_values("y_true").reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(12, 5))
    colors = ["#43a047" if abs(r) < 2 else ("#ef6c00" if abs(r) < 4 else "#e53935") for r in df["residual"]]
    ax.bar(df["field_id"], df["residual"], color=colors, edgecolor="black", linewidth=0.5)
    ax.axhline(0, color="#333", linewidth=0.8)
    ax.axhline(2, color="#999", linestyle="--", linewidth=0.5)
    ax.axhline(-2, color="#999", linestyle="--", linewidth=0.5)
    ax.set_xlabel("field_id (отсортированы по y_true)")
    ax.set_ylabel("residual = predicted - actual, ц/га")
    ax.set_title("LightGBM LOO residuals по полям (зелёный |err|<2, жёлтый <4, красный >=4)")
    ax.grid(alpha=0.25, axis="y")
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right", fontsize=8)
    fig.tight_layout()
    out = PREVIEW_DIR / "residuals.png"
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_model_compare(metrics_df: pd.DataFrame) -> Path:
    df = metrics_df.copy()
    df.index.name = "model"
    df = df.reset_index()
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    colors = {
        "baseline_mean": "#999999",
        "baseline_lr_peak": "#1e88e5",
        "baseline_lr_ndvi": "#42a5f5",
        "lightgbm": "#1e7a1e",
        "lightgbm_ndvi_only": "#66bb6a",
    }
    bar_colors = [colors.get(m, "#777") for m in df["model"]]

    ax = axes[0]
    ax.barh(df["model"], df["MAPE_%"], color=bar_colors, edgecolor="black", linewidth=0.5)
    ax.set_xlabel("MAPE, %")
    ax.set_title("MAPE LOO-CV (меньше -- лучше)")
    ax.grid(alpha=0.3, axis="x")
    for i, v in enumerate(df["MAPE_%"]):
        ax.text(v + 0.05, i, f"{v:.2f}%", va="center", fontsize=9)

    ax = axes[1]
    ax.barh(df["model"], df["R2"], color=bar_colors, edgecolor="black", linewidth=0.5)
    ax.set_xlabel("R²")
    ax.set_title("R² LOO-CV (больше -- лучше)")
    ax.axvline(0, color="#333", linewidth=0.5)
    ax.grid(alpha=0.3, axis="x")
    for i, v in enumerate(df["R2"]):
        ax.text(v + 0.02 if v >= 0 else v - 0.02, i, f"{v:.2f}", va="center", ha="left" if v >= 0 else "right", fontsize=9)

    fig.suptitle("Сравнение 5 моделей на одном датасете 20 × 18", fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    out = PREVIEW_DIR / "model_compare.png"
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return out


def main() -> None:
    preds = pd.read_csv(PROCESSED_DIR / "cv_predictions.csv")
    imp = pd.read_csv(PROCESSED_DIR / "feature_importance.csv", index_col=0)
    metrics_df = pd.read_csv(PROCESSED_DIR / "lgb_metrics.csv", index_col=0)

    print(f"Загружено: predictions {len(preds)}, importance {len(imp)}, metrics {len(metrics_df)}")

    p1 = plot_cv_scatter(preds)
    print(f"  scatter -> {p1.relative_to(PROJECT_ROOT)}")
    p2 = plot_feature_importance(imp)
    print(f"  feature importance -> {p2.relative_to(PROJECT_ROOT)}")
    p3 = plot_residuals(preds)
    print(f"  residuals -> {p3.relative_to(PROJECT_ROOT)}")
    p4 = plot_model_compare(metrics_df)
    print(f"  model compare -> {p4.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
