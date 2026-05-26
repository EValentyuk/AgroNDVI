# Архитектура AgroNDVI

Диаграммы по уровням C4 (Context -> Container -> Component) через Mermaid. GitHub рендерит их прямо в браузере.

## Уровень 1: Context

Окружение проекта и внешние источники данных.

```mermaid
graph LR
    User[👤 Пользователь<br/>агроном / страховщик / аналитик]:::user
    App[🛰️ AgroNDVI<br/>Streamlit-приложение]:::system

    S2[Sentinel-2 L2A<br/>AWS Element 84 STAC<br/>us-west-2]:::ext
    OSM[OpenStreetMap<br/>Overpass API]:::ext
    OM[Open Meteo<br/>Historical Weather]:::ext
    NP[NASA POWER<br/>Solar Radiation]:::ext

    User -->|выбирает поле,<br/>смотрит прогноз| App
    App <-->|STAC search,<br/>HTTP-range COG read| S2
    App <-->|landuse=farmland<br/>polygons| OSM
    App <-->|daily T, осадки, ET0| OM
    App <-->|ALLSKY_SFC_SW_DWN| NP

    classDef user fill:#e3f2fd,stroke:#1e88e5,stroke-width:2px
    classDef system fill:#e8f5e9,stroke:#43a047,stroke-width:2px
    classDef ext fill:#fff3e0,stroke:#ef6c00,stroke-width:1px
```

**Ключевые решения:**
- Все внешние источники бесплатные и доступны из РФ без VPN;
- Sentinel-2 берём через AWS, а не Copernicus -- последний под санкциями для РФ;
- Данные кэшируются локально, после первого прогона приложение работает без интернета.

## Уровень 2: Containers

Что внутри проекта -- основные слои данных и кода.

```mermaid
graph TB
    subgraph External[Внешние источники]
        S2X[Sentinel-2 STAC]:::ext
        OSMX[OSM Overpass]:::ext
        WX[Open Meteo + NASA POWER]:::ext
    end

    subgraph Pipeline[src/ -- Python pipeline]
        Find[find_sentinel.py<br/>STAC search + retry]:::code
        Fetch[fetch_osm_fields.py<br/>fetch_weather.py]:::code
        Ndvi[ndvi.py<br/>ndvi_series.py]:::code
        FE[feature_engineering.py<br/>zonal_stats.py]:::code
        ML[train_lgb.py<br/>LightGBM + LOO-CV]:::code
        Anom[anomaly.py<br/>z-score + IsoForest + L2]:::code
        Plot[plot_*.py<br/>matplotlib + folium]:::code
    end

    subgraph Storage[data/ + models/]
        Raw[data/catalog/<br/>STAC JSON]:::data
        Fields[data/fields/<br/>fields_v1.geojson]:::data
        Weather[data/weather/<br/>weather_daily.csv]:::data
        Proc[data/processed/<br/>NDVI series, features, anomaly]:::data
        Mdl[models/<br/>lgb_yield.pkl]:::data
        Prev[data/preview/<br/>PNG + HTML]:::data
    end

    subgraph UI[Streamlit UI]
        App[streamlit_app.py<br/>folium + plotly]:::ui
    end

    S2X -.->|HTTPS| Find
    OSMX -.->|Overpass QL| Fetch
    WX -.->|REST| Fetch
    S2X -.->|COG range read| Ndvi

    Find --> Raw
    Fetch --> Fields
    Fetch --> Weather
    Ndvi --> Proc
    Raw --> Ndvi
    Fields --> FE
    Fields --> Anom
    Proc --> FE
    Weather --> FE
    FE --> Proc
    Proc --> ML
    Proc --> Anom
    Anom --> Proc
    ML --> Mdl

    Proc --> App
    Fields --> App
    Mdl --> App
    Weather --> App
    Plot --> Prev

    classDef ext fill:#fff3e0,stroke:#ef6c00
    classDef code fill:#e1f5fe,stroke:#0277bd
    classDef data fill:#f3e5f5,stroke:#8e24aa
    classDef ui fill:#e8f5e9,stroke:#43a047
```

**Слои:**
- **External** -- 4 источника данных, все бесплатные;
- **Pipeline** -- 11 Python-скриптов, разделены по ответственности (download / NDVI / feature engineering / ML / anomaly / visualization);
- **Storage** -- 6 категорий артефактов; `data/` под `.gitignore`, на GitHub попадает только `data/fields/*.geojson` (объёмом меньше 20 КБ);
- **UI** -- Streamlit + folium + plotly, читает финальные артефакты, не вычисляет.

## Уровень 3: Components -- pipeline сценарий

Подробный flow одного полного прогона.

```mermaid
sequenceDiagram
    autonumber
    participant U as Пользователь
    participant FS as find_sentinel.py
    participant FOF as fetch_osm_fields.py
    participant FW as fetch_weather.py
    participant NS as ndvi_series.py
    participant FE as feature_engineering.py
    participant TR as train_lgb.py
    participant AN as anomaly.py
    participant ST as streamlit_app.py

    U->>FS: запустить поиск серии<br/>(год, tile, max-cloud)
    FS-->>FS: POST STAC search<br/>(chunk по месяцам, retry x8)
    FS-->>U: data/catalog/series_*.json<br/>(45 снимков, ~95 КБ)

    U->>FOF: запросить поля<br/>(bbox, min-area)
    FOF-->>FOF: Overpass query<br/>landuse=farmland
    FOF-->>U: data/fields/fields_v1.geojson<br/>(20 полей, ~14 КБ)

    U->>FW: погода за период
    FW-->>FW: GET Open Meteo + NASA POWER
    FW-->>U: data/weather/weather_daily.csv<br/>(366 дней × 18 колонок)

    U->>NS: серия NDVI по окну
    loop 45 дат, ThreadPoolExecutor (6 workers)
        NS-->>NS: rasterio.read window B04, B08, SCL<br/>compute NDVI, apply SCL mask<br/>zonal stats по 20 полям
    end
    NS-->>U: data/processed/fields_ndvi_series.csv<br/>(900 строк × 11 колонок)

    U->>FE: построить фичи
    FE-->>FE: smooth NDVI (rolling 21d)<br/>extract 10 NDVI + 8 weather фичей<br/>+ синтетический yield-таргет
    FE-->>U: data/processed/fields_features.csv<br/>(20 × 22)

    U->>TR: обучить LightGBM<br/>+ baselines + LOO-CV
    TR-->>TR: 5 моделей × LOO<br/>feature importance × 3
    TR-->>U: models/lgb_yield.pkl<br/>+ cv_predictions.csv<br/>+ feature_importance.csv<br/>+ lgb_metrics.csv

    U->>AN: anomaly detection
    AN-->>AN: pointwise z-score<br/>IsolationForest<br/>L2-distance<br/>mean(ranks)
    AN-->>U: data/processed/fields_anomaly.csv<br/>(20 × 10)

    U->>ST: streamlit run
    ST-->>ST: @st.cache_data<br/>загрузка всех артефактов
    ST-->>U: 🛰️ http://localhost:8501
```

## Ключевые архитектурные решения

| **Решение** | **Что выбрали** | **Почему** |
|:---|:---|:---|
| Источник Sentinel-2 | AWS Element 84 STAC | Бесплатно, без регистрации, доступно из РФ. Альтернатива (Copernicus) заблокирована санкциями. |
| Формат снимков | COG + HTTP-range read | Не нужно качать 1 ГБ tile целиком, читаем окно над полями (~5 МБ). 30-кратное сокращение трафика. |
| Источник границ полей | OSM `landuse=farmland` | Реальные данные, не выдуманные. Доступ через Overpass API без VPN. |
| Source granularity | 20 полей одного района одного года | Pet-проект для портфолио. Для реальной задачи нужно multi-year + multi-region. |
| Синхронизация | Файлы, не БД | Простота, наглядность. Каждый этап читает CSV/GeoJSON предыдущего. |
| Модель ML | LightGBM + LinearRegression baseline | Сравниваем гипотезы. На 20 строках baseline побеждает (см. [docs/experiments/2026-05-26-lgb-baseline.md](experiments/2026-05-26-lgb-baseline.md)). |
| Anomaly detection | 3 независимых метода + объединение | Устойчивость к выбору алгоритма. Согласованность через Spearman ρ. |
| UI | Streamlit + folium + plotly | Быстрый интерактив без фронтенд-разработки. |
| HTTP retry | Собственная функция _post_with_retry | pystac-client падал на нестабильном канале РФ -> us-west-2. Сделали 8 попыток с экспоненциальным backoff. |
| Pandas-pyarrow конфликт | `pd.options.future.infer_string = False` | На Windows pandas 3.0 + pyarrow 24 даёт access violation при `read_csv`. |

## Зависимости

```mermaid
graph LR
    Py[Python 3.13]:::lang

    subgraph GeoStack[Геостек]
        Ras[rasterio 1.5<br/>+ GDAL 3.12]
        Gp[geopandas 1.1]
        Shp[shapely 2.1]
        Pp[pyproj 3.7]
        Fol[folium 0.20]
    end

    subgraph MLStack[ML стек]
        Np[numpy 2.4]
        Pd[pandas 3.0]
        Sk[scikit-learn 1.8]
        Lgb[lightgbm 4.6]
    end

    subgraph UIStack[UI]
        St[streamlit 1.57]
        StF[streamlit-folium 0.27]
        Plt[plotly 6.7]
    end

    subgraph APIs[API клиенты]
        Pys[pystac-client 0.9]
        Osm[osm2geojson 0.3]
        Req[requests 2.34]
    end

    Py --> GeoStack
    Py --> MLStack
    Py --> UIStack
    Py --> APIs

    classDef lang fill:#fff8e1,stroke:#fb8c00,stroke-width:2px
```

Полный список -- в [requirements.txt](../requirements.txt).
