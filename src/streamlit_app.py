"""AgroNDVI -- Streamlit UI.

Запуск:
    cd c:\\Projects\\AgroNDVI
    .venv\\Scripts\\streamlit.exe run src\\streamlit_app.py

Что показывает:
    - KPI всего проекта: 20 полей, 45 снимков, амплитуда NDVI, top-K аномалий;
    - Folium-карта 20 рисовых чеков Темрюкского района Краснодарского края,
      окраска по предсказанной урожайности (LightGBM full-train);
    - Top-K аномалий выделены красной рамкой;
    - Селектор поля + детальная панель:
        * сводка (площадь, культура OSM, прогноз yield, anomaly flag);
        * time-series NDVI с коридором p10-p90 от 20 полей;
        * погода рисового сезона + накопленный GDD;
        * метрики аномалии трёх методов.
"""

from __future__ import annotations

import os
import pickle
import sys
from pathlib import Path

os.environ.setdefault("PANDAS_USE_PYARROW_STRINGS", "0")

import pandas as pd

pd.options.future.infer_string = False

import folium
import geopandas as gpd
import numpy as np
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots
from streamlit_folium import st_folium

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
FIELDS_PATH = PROJECT_ROOT / "data" / "fields" / "fields_v1.geojson"
WEATHER_PATH = PROJECT_ROOT / "data" / "weather" / "weather_daily.csv"
MODEL_PATH = PROJECT_ROOT / "models" / "lgb_yield.pkl"

st.set_page_config(
    page_title="AgroNDVI -- спутниковый мониторинг полей",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data
def load_fields() -> gpd.GeoDataFrame:
    return gpd.read_file(FIELDS_PATH).to_crs("EPSG:4326")


@st.cache_data
def load_features() -> pd.DataFrame:
    return pd.read_csv(PROCESSED_DIR / "fields_features.csv")


@st.cache_data
def load_ndvi_series() -> pd.DataFrame:
    df = pd.read_csv(PROCESSED_DIR / "fields_ndvi_series.csv")
    df["date"] = pd.to_datetime(df["date"])
    return df


@st.cache_data
def load_anomaly() -> pd.DataFrame:
    return pd.read_csv(PROCESSED_DIR / "fields_anomaly.csv")


@st.cache_data
def load_weather() -> pd.DataFrame:
    df = pd.read_csv(WEATHER_PATH)
    df["date"] = pd.to_datetime(df["date"])
    return df


@st.cache_resource
def load_model() -> dict:
    with open(MODEL_PATH, "rb") as f:
        return pickle.load(f)


@st.cache_data
def smoothed_ndvi(ndvi: pd.DataFrame) -> pd.DataFrame:
    pivot = ndvi.pivot_table(index="date", columns="field_id", values="ndvi_mean", aggfunc="mean").sort_index()
    full_idx = pd.date_range(pivot.index.min(), pivot.index.max(), freq="D")
    return pivot.reindex(full_idx).interpolate(method="time", limit_direction="both").rolling(21, center=True, min_periods=5).mean()


@st.cache_data
def merged_field_table(fields_gdf_json: str, features_json: str, anomaly_json: str, predictions: dict[str, float]) -> pd.DataFrame:
    fields = pd.read_json(fields_gdf_json)
    feats = pd.read_json(features_json)
    anom = pd.read_json(anomaly_json)
    df = fields.merge(feats, on="field_id").merge(anom, on="field_id")
    df["predicted_yield"] = df["field_id"].map(predictions)
    return df


def yield_color(y: float, lo: float, hi: float) -> str:
    if pd.isna(y):
        return "#888888"
    norm = (y - lo) / max(1e-6, hi - lo)
    if norm < 0.20:
        return "#b71c1c"
    if norm < 0.40:
        return "#ef6c00"
    if norm < 0.60:
        return "#fbc02d"
    if norm < 0.80:
        return "#7cb342"
    return "#1e7a1e"


def main() -> None:
    fields_gdf = load_fields()
    features = load_features()
    ndvi = load_ndvi_series()
    anomaly = load_anomaly().rename(columns={"Unnamed: 0": "field_id"} if "Unnamed: 0" in load_anomaly().columns else {})
    if "field_id" not in anomaly.columns:
        anomaly = load_anomaly().reset_index().rename(columns={"index": "field_id"})
    weather = load_weather()
    model_payload = load_model()
    model = model_payload["model"]
    feature_cols = model_payload["feature_cols"]

    X = features[feature_cols].copy()
    predicted_yield = model.predict(X)
    predictions = dict(zip(features["field_id"], predicted_yield))

    features_for_merge = features.drop(columns=[c for c in ("area_ha", "crop_osm") if c in features.columns])
    df = fields_gdf.merge(features_for_merge, on="field_id").merge(
        anomaly[["field_id", "mean_rank", "anomaly_z_count", "isoforest_score", "l2_from_median", "is_anomaly_top_k"]],
        on="field_id",
    )
    df = df.rename(columns={"crop": "crop_osm"})
    df["predicted_yield"] = df["field_id"].map(predictions)

    smoothed = smoothed_ndvi(ndvi)

    st.title("🛰️ AgroNDVI -- спутниковый мониторинг рисовых полей")
    st.caption("Темрюкский район Краснодарского края · сезон октябрь 2023 -- сентябрь 2024 · 45 безоблачных снимков Sentinel-2 · 20 полей из OpenStreetMap")

    with st.sidebar:
        st.header("⚙️ Настройки")
        top_k = st.slider("Подсветить top-K аномалий", min_value=1, max_value=10, value=3)
        show_anomaly_border = st.checkbox("Красная рамка вокруг аномалий", value=True)
        st.markdown("---")
        st.markdown("**Источники данных:**")
        st.markdown("- Sentinel-2 L2A → AWS Element 84 STAC")
        st.markdown("- OpenStreetMap landuse=farmland")
        st.markdown("- Open Meteo Historical")
        st.markdown("- NASA POWER")
        st.markdown("---")
        st.markdown("**⚠️ Таргет урожайности синтетический.**")
        st.markdown("Реальной пол-уровневой урожайности в открытом доступе нет. См. `docs/portfolio-report.md`.")

    top_anomalies = anomaly.sort_values("mean_rank").head(top_k)["field_id"].tolist()
    df["is_top_anomaly"] = df["field_id"].isin(top_anomalies)

    kpi_cols = st.columns(5)
    kpi_cols[0].metric("Полей", len(df), help="Рисовые чеки из OSM (landuse=farmland, площадь >=20 га)")
    kpi_cols[1].metric("Снимков Sentinel-2", "45", help="После фильтра облачности <20% за полный сезон")
    kpi_cols[2].metric("Медианный NDVI пик", f"{features['ndvi_peak'].median():.2f}", help="Аналог максимальной биомассы за сезон")
    kpi_cols[3].metric("Средний прогноз yield", f"{df['predicted_yield'].mean():.1f} ц/га", help="LightGBM full-train, синтетический таргет")
    kpi_cols[4].metric(f"Top-{top_k} аномалии", ", ".join(top_anomalies), help="Объединённый ранг 3 методов: z-score + IsolationForest + L2")

    st.markdown("---")

    col_map, col_detail = st.columns([3, 2])

    with col_map:
        st.subheader("Карта полей")
        st.caption("Окраска -- предсказанная урожайность. Чем зеленее, тем выше прогноз. Чёрная рамка -- top-K аномалия.")

        y_lo, y_hi = df["predicted_yield"].min(), df["predicted_yield"].max()
        centroid = df.geometry.union_all().centroid

        m = folium.Map(location=[centroid.y, centroid.x], zoom_start=11, tiles=None, control_scale=True)
        folium.TileLayer("OpenStreetMap", name="OSM").add_to(m)
        folium.TileLayer(
            tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            attr="Esri World Imagery", name="Спутник Esri",
        ).add_to(m)

        for _, row in df.iterrows():
            color = yield_color(row["predicted_yield"], y_lo, y_hi)
            is_marked_anomaly = show_anomaly_border and row["is_top_anomaly"]
            border_color = "#e53935" if is_marked_anomaly else "#555"
            weight = 4.0 if is_marked_anomaly else 1.5
            anomaly_badge = " ⚠️" if row["is_top_anomaly"] else ""
            popup_html = (
                f"<b>{row['field_id']}{anomaly_badge}</b><br>"
                f"OSM id: {row['osm_id']}<br>"
                f"culture: {row.get('crop_osm') or 'не указано'}<br>"
                f"area: {row['area_ha']:.0f} га<br>"
                f"<hr>"
                f"NDVI peak: {row['ndvi_peak']:.3f}<br>"
                f"NDVI peak date: {row['ndvi_date_peak']}<br>"
                f"vegetation days: {int(row['ndvi_vegetation_days'])}<br>"
                f"<hr>"
                f"<b>Прогноз yield: {row['predicted_yield']:.1f} ц/га</b><br>"
                f"<hr>"
                f"anomaly rank: {row['mean_rank']:.2f}<br>"
                f"|z| count: {int(row['anomaly_z_count'])}<br>"
                f"L2 от медианы: {row['l2_from_median']:.2f}<br>"
            )
            folium.GeoJson(
                row.geometry.__geo_interface__,
                style_function=lambda feat, c=color, b=border_color, w=weight: {
                    "fillColor": c, "color": b, "weight": w, "fillOpacity": 0.65,
                },
                popup=folium.Popup(popup_html, max_width=320),
                tooltip=f"{row['field_id']}{anomaly_badge} · {row['predicted_yield']:.1f} ц/га",
            ).add_to(m)

        folium.LayerControl().add_to(m)
        legend_html = """
        <div style="position: fixed; bottom: 20px; left: 20px; z-index:1000; background:white; padding:8px 12px; border:1px solid #999; border-radius:6px; font-size:12px;">
            <b>Прогноз yield</b><br>
            <span style="background:#1e7a1e;width:14px;height:14px;display:inline-block;"></span> ≥ 60 ц/га<br>
            <span style="background:#7cb342;width:14px;height:14px;display:inline-block;"></span> 57 - 60<br>
            <span style="background:#fbc02d;width:14px;height:14px;display:inline-block;"></span> 54 - 57<br>
            <span style="background:#ef6c00;width:14px;height:14px;display:inline-block;"></span> 51 - 54<br>
            <span style="background:#b71c1c;width:14px;height:14px;display:inline-block;"></span> < 51<br>
            <span style="border:3px solid #e53935;width:12px;height:12px;display:inline-block;"></span> top-аномалия
        </div>
        """
        m.get_root().html.add_child(folium.Element(legend_html))

        map_state = st_folium(m, width=None, height=600, returned_objects=["last_object_clicked_tooltip"], key="main_map")

    with col_detail:
        st.subheader("Детали поля")

        clicked_field = None
        if map_state and map_state.get("last_object_clicked_tooltip"):
            tooltip = map_state["last_object_clicked_tooltip"]
            for fid in df["field_id"]:
                if fid in tooltip:
                    clicked_field = fid
                    break

        all_fields = sorted(df["field_id"].tolist())
        default_idx = all_fields.index(clicked_field) if clicked_field else 0
        selected = st.selectbox(
            "Выбрать поле (или кликнуть на карте)",
            options=all_fields,
            index=default_idx,
            format_func=lambda x: f"{x}{' ⚠️' if x in top_anomalies else ''}",
        )

        row = df[df["field_id"] == selected].iloc[0]

        info_cols = st.columns(2)
        info_cols[0].metric("Прогноз yield", f"{row['predicted_yield']:.1f} ц/га")
        info_cols[1].metric("Площадь", f"{row['area_ha']:.0f} га")

        info_cols2 = st.columns(2)
        info_cols2[0].metric("NDVI peak", f"{row['ndvi_peak']:.3f}", delta=f"{row['ndvi_peak'] - df['ndvi_peak'].median():+.3f} от медианы")
        info_cols2[1].metric("Дней вегетации", int(row["ndvi_vegetation_days"]))

        if selected in top_anomalies:
            st.error(f"⚠️ Top-{top_k} аномалия (rank {row['mean_rank']:.2f})")
        elif row["mean_rank"] <= top_k + 3:
            st.warning(f"Близко к top: rank {row['mean_rank']:.2f}")
        else:
            st.success(f"В коридоре нормы: rank {row['mean_rank']:.2f}")

        ndvi_field = smoothed[selected]
        median_curve = smoothed.median(axis=1)
        p10 = smoothed.quantile(0.10, axis=1)
        p25 = smoothed.quantile(0.25, axis=1)
        p75 = smoothed.quantile(0.75, axis=1)
        p90 = smoothed.quantile(0.90, axis=1)

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=p90.index, y=p90, line=dict(color="rgba(30,122,30,0)"), showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=p10.index, y=p10, fill="tonexty", fillcolor="rgba(30,122,30,0.10)", line=dict(color="rgba(30,122,30,0)"), name="p10 - p90 (20 полей)", hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=p75.index, y=p75, line=dict(color="rgba(30,122,30,0)"), showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=p25.index, y=p25, fill="tonexty", fillcolor="rgba(30,122,30,0.22)", line=dict(color="rgba(30,122,30,0)"), name="p25 - p75 (IQR)", hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=median_curve.index, y=median_curve, mode="lines", line=dict(color="#0a3d0a", width=1.5, dash="dot"), name="медиана 20 полей"))
        line_color = "#e53935" if selected in top_anomalies else "#1e88e5"
        fig.add_trace(go.Scatter(x=ndvi_field.index, y=ndvi_field, mode="lines", line=dict(color=line_color, width=2.5), name=selected))
        fig.update_layout(
            title=f"NDVI кривая {selected} в коридоре 20 полей",
            xaxis_title="дата",
            yaxis_title="NDVI",
            yaxis_range=[-0.2, 0.7],
            height=340,
            margin=dict(l=10, r=10, t=40, b=10),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig, width="stretch")

        with st.expander("Метрики аномалии (3 метода)"):
            anom_cols = st.columns(3)
            anom_cols[0].metric("|z| count (метод 1)", int(row["anomaly_z_count"]), help="Сколько раз за сезон NDVI выходил за |z|>2")
            anom_cols[1].metric("IsolationForest", f"{row['isoforest_score']:.3f}", help="decision_function; чем выше, тем аномальнее")
            anom_cols[2].metric("L2 от медианы (метод 3)", f"{row['l2_from_median']:.2f}", help="Геометрическое расстояние кривой от медианы 20 полей")

        with st.expander("Погода рисового сезона (одна точка центра bbox)"):
            season = weather[(weather["date"] >= "2024-04-01") & (weather["date"] <= "2024-09-30")].copy()
            season["gdd_cum"] = (season["temperature_2m_mean"] - 10).clip(lower=0).cumsum()
            fig_w = make_subplots(specs=[[{"secondary_y": True}]])
            fig_w.add_trace(go.Bar(x=season["date"], y=season["precipitation_sum"], name="осадки, мм", marker_color="#1e88e5", opacity=0.7), secondary_y=False)
            fig_w.add_trace(go.Scatter(x=season["date"], y=season["temperature_2m_mean"], name="T_mean, °C", line=dict(color="#e53935", width=1.5)), secondary_y=True)
            fig_w.add_trace(go.Scatter(x=season["date"], y=season["gdd_cum"] / 30, name="GDD кум / 30", line=dict(color="#8e24aa", width=1.5, dash="dot")), secondary_y=True)
            fig_w.update_layout(
                title="Осадки + T_mean + GDD (1 апр -- 30 сен 2024)",
                height=320,
                margin=dict(l=10, r=10, t=40, b=10),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            fig_w.update_yaxes(title_text="осадки, мм", secondary_y=False)
            fig_w.update_yaxes(title_text="T_mean, °C / GDD кум /30", secondary_y=True)
            st.plotly_chart(fig_w, width="stretch")

        with st.expander("OSM-метаданные"):
            st.json({
                "field_id": row["field_id"],
                "osm_id": str(row["osm_id"]),
                "osm_type": row.get("osm_type"),
                "crop_osm": row.get("crop_osm"),
                "area_ha": float(row["area_ha"]),
                "name": row.get("name"),
            })

    st.markdown("---")
    foot_cols = st.columns([2, 1, 1])
    with foot_cols[0]:
        st.caption(
            "AgroNDVI · пет-проект Валентюка Е.Г. для портфолио (агро + спутник). "
            "Документация: [brief](docs/brief.md), [portfolio-report](docs/portfolio-report.md), "
            "[эксперимент LightGBM](docs/experiments/2026-05-26-lgb-baseline.md), "
            "[эксперимент аномалий](docs/experiments/2026-05-26-anomaly.md)."
        )
    with foot_cols[1]:
        st.caption(f"Модель: LightGBM full-train на 20 строках × {len(feature_cols)} фичей")
    with foot_cols[2]:
        st.caption(f"LOO-CV MAPE: {model_payload['metrics_loo']['MAPE_%']}%, R²: {model_payload['metrics_loo']['R2']}")


if __name__ == "__main__":
    main()
