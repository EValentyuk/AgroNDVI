"""Визуализация anomaly detection:
    1. Heatmap z-score (поле × дата);
    2. Кривые top-K аномалий vs медиана + IQR коридор;
    3. Folium-карта с anomaly_score окраской полей.
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
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import folium
import geopandas as gpd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
PREVIEW_DIR = PROJECT_ROOT / "data" / "preview"
FIELDS_PATH = PROJECT_ROOT / "data" / "fields" / "fields_v1.geojson"

TOP_K = 3


def plot_heatmap(z_path: Path) -> Path:
    z = pd.read_csv(z_path, index_col=0, parse_dates=True)
    field_order = z.abs().sum(axis=0).sort_values(ascending=False).index.tolist()
    z = z[field_order]

    fig, ax = plt.subplots(figsize=(14, 7))
    im = ax.imshow(z.T.values, aspect="auto", cmap="RdBu_r", vmin=-3, vmax=3, interpolation="nearest")
    ax.set_yticks(range(len(field_order)))
    ax.set_yticklabels(field_order, fontsize=9)
    n_dates = z.shape[0]
    tick_step = max(1, n_dates // 12)
    ax.set_xticks(range(0, n_dates, tick_step))
    ax.set_xticklabels([z.index[i].strftime("%Y-%m") for i in range(0, n_dates, tick_step)], rotation=45, ha="right", fontsize=9)
    ax.set_title("Z-score аномалий по полям и датам (синий -- NDVI ниже медианы 20 полей, красный -- выше)")
    ax.set_xlabel("дата")
    ax.set_ylabel("field_id (отсортированы по сумме |z|)")
    cbar = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.01)
    cbar.set_label("z-score")
    fig.tight_layout()
    out = PREVIEW_DIR / "anomaly_heatmap.png"
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_top_curves(ndvi_csv: Path, anomaly_csv: Path, k: int = TOP_K) -> Path:
    ndvi = pd.read_csv(ndvi_csv)
    ndvi["date"] = pd.to_datetime(ndvi["date"])
    pivot = ndvi.pivot_table(index="date", columns="field_id", values="ndvi_mean", aggfunc="mean").sort_index()
    full_idx = pd.date_range(pivot.index.min(), pivot.index.max(), freq="D")
    smoothed = pivot.reindex(full_idx).interpolate(method="time", limit_direction="both").rolling(21, center=True, min_periods=5).mean()
    median = smoothed.median(axis=1)
    p25 = smoothed.quantile(0.25, axis=1)
    p75 = smoothed.quantile(0.75, axis=1)
    p10 = smoothed.quantile(0.10, axis=1)
    p90 = smoothed.quantile(0.90, axis=1)

    anomaly = pd.read_csv(anomaly_csv, index_col=0).sort_values("mean_rank")
    top_fields = anomaly.head(k).index.tolist()

    fig, axes = plt.subplots(k, 1, figsize=(13, 3 * k), sharex=True)
    if k == 1:
        axes = [axes]
    for ax, fid in zip(axes, top_fields):
        ax.fill_between(smoothed.index, p10, p90, color="#1e7a1e", alpha=0.10, label="коридор p10-p90 (20 полей)")
        ax.fill_between(smoothed.index, p25, p75, color="#1e7a1e", alpha=0.20, label="коридор p25-p75")
        ax.plot(median.index, median, color="#0a3d0a", linewidth=1.5, label="медиана 20 полей")
        ax.plot(smoothed.index, smoothed[fid], color="#e53935", linewidth=2.2, label=f"{fid}")
        ax.axhline(0.0, color="#666", linewidth=0.5)
        ax.set_ylim(-0.2, 0.7)
        info = anomaly.loc[fid]
        ax.set_title(
            f"{fid} -- rank {int(anomaly.index.get_loc(fid)) + 1}, "
            f"mean_rank={info['mean_rank']:.2f}, |z|count={int(info['anomaly_z_count'])}, "
            f"iso_score={info['isoforest_score']:.3f}, L2={info['l2_from_median']:.2f}",
            fontsize=10,
        )
        ax.grid(alpha=0.25)
        ax.legend(loc="upper left", fontsize=8, ncol=4)
        ax.xaxis.set_major_locator(mdates.MonthLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        plt.setp(ax.get_xticklabels(), rotation=30, ha="right")

    fig.suptitle(f"Top-{k} аномальных полей: индивидуальная кривая vs коридор 20 полей", fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    out = PREVIEW_DIR / "anomaly_top_curves.png"
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return out


def make_anomaly_map(anomaly_csv: Path, k: int = TOP_K) -> Path:
    anomaly = pd.read_csv(anomaly_csv).rename(columns={anomaly_csv.name: "x"})
    if "Unnamed: 0" in anomaly.columns:
        anomaly = anomaly.rename(columns={"Unnamed: 0": "field_id"})
    elif "field_id" not in anomaly.columns:
        anomaly = pd.read_csv(anomaly_csv, index_col=0).reset_index().rename(columns={"index": "field_id"})

    fields_gdf = gpd.read_file(FIELDS_PATH).to_crs("EPSG:4326")
    merged = fields_gdf.merge(anomaly, on="field_id", how="left")
    top_set = set(merged.sort_values("mean_rank").head(k)["field_id"])

    centroid = merged.geometry.unary_union.centroid
    m = folium.Map(location=[centroid.y, centroid.x], zoom_start=11, tiles="OpenStreetMap")
    m.get_root().header.add_child(folium.Element(
        '<style>'
        '.leaflet-attribution-flag,'
        '.leaflet-control-attribution svg { display: none !important; }'
        '.leaflet-control-attribution a[href*="leafletjs.com"] { display: none !important; }'
        '</style>'
    ))
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery", name="Спутник Esri", overlay=False, control=True,
    ).add_to(m)

    rank_vals = merged["mean_rank"].astype(float)
    rmin, rmax = rank_vals.min(), rank_vals.max()

    def color_for(rank):
        if pd.isna(rank):
            return "#888888"
        norm = (rank - rmin) / max(1e-6, rmax - rmin)
        if norm < 0.20:
            return "#b71c1c"
        if norm < 0.40:
            return "#ef6c00"
        if norm < 0.65:
            return "#fbc02d"
        return "#1e7a1e"

    for _, row in merged.iterrows():
        is_top = row["field_id"] in top_set
        color = color_for(row["mean_rank"])
        border = "#000000" if is_top else "#666666"
        weight = 3.5 if is_top else 1.2
        popup = (
            f"<b>{row['field_id']}</b> {'⚠ TOP АНОМАЛИЯ' if is_top else ''}<br>"
            f"OSM id: {row['osm_id']}<br>"
            f"area: {row['area_ha']:.0f} га<br>"
            f"culture: {row.get('crop') or 'не указано'}<br>"
            f"<hr>"
            f"mean_rank: {row['mean_rank']:.2f}<br>"
            f"|z|count: {int(row['anomaly_z_count'])}<br>"
            f"|z|total: {row['anomaly_z_total']:.1f}<br>"
            f"iso_score: {row['isoforest_score']:.3f}<br>"
            f"L2: {row['l2_from_median']:.2f}<br>"
        )
        folium.GeoJson(
            row.geometry.__geo_interface__,
            style_function=lambda feat, c=color, w=weight, b=border: {
                "fillColor": c, "color": b, "weight": w, "fillOpacity": 0.65,
            },
            popup=folium.Popup(popup, max_width=320),
            tooltip=f"{row['field_id']} (rank {row['mean_rank']:.2f})",
        ).add_to(m)

    folium.LayerControl().add_to(m)
    out = PREVIEW_DIR / "anomaly_map.html"
    m.save(str(out))
    return out


def plot_consistency_scatter(anomaly_csv: Path) -> Path:
    df = pd.read_csv(anomaly_csv, index_col=0)
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    pairs = [
        ("anomaly_z_total", "isoforest_score", "Z vs IsolationForest"),
        ("anomaly_z_total", "l2_from_median", "Z vs L2-distance"),
        ("isoforest_score", "l2_from_median", "IsolationForest vs L2"),
    ]
    for ax, (xc, yc, title) in zip(axes, pairs):
        ax.scatter(df[xc], df[yc], s=70, color="#1e7a1e", edgecolor="black", linewidth=0.5)
        for fid, row in df.iterrows():
            color = "#e53935" if fid in df.sort_values("mean_rank").head(TOP_K).index else "#444"
            ax.annotate(fid, (row[xc], row[yc]), fontsize=8, xytext=(4, 4), textcoords="offset points", color=color)
        rho = df[[xc, yc]].corr(method="spearman").iloc[0, 1]
        ax.set_xlabel(xc)
        ax.set_ylabel(yc)
        ax.set_title(f"{title}  (Spearman ρ = {rho:.2f})")
        ax.grid(alpha=0.25)
    fig.suptitle("Согласованность 3 методов anomaly detection (красные подписи -- top-3)", fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    out = PREVIEW_DIR / "anomaly_consistency.png"
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return out


def main() -> None:
    z_path = PROCESSED_DIR / "fields_anomaly_z_matrix.csv"
    a_path = PROCESSED_DIR / "fields_anomaly.csv"
    ndvi_path = PROCESSED_DIR / "fields_ndvi_series.csv"

    print("1. Heatmap z-score...")
    p1 = plot_heatmap(z_path)
    print(f"  -> {p1.relative_to(PROJECT_ROOT)}")

    print("2. Top-3 curves vs коридор...")
    p2 = plot_top_curves(ndvi_path, a_path, k=TOP_K)
    print(f"  -> {p2.relative_to(PROJECT_ROOT)}")

    print("3. Folium-карта с anomaly_score окраской...")
    p3 = make_anomaly_map(a_path, k=TOP_K)
    print(f"  -> {p3.relative_to(PROJECT_ROOT)}")

    print("4. Scatter согласованности 3 методов...")
    p4 = plot_consistency_scatter(a_path)
    print(f"  -> {p4.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
