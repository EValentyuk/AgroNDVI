"""Скачивание границ полей (landuse=farmland) из OpenStreetMap через Overpass API.

Использование:
    python src/fetch_osm_fields.py
        [--bbox "37.85,44.85,38.80,45.15"]   -- юг,запад,север,восток
        [--min-area-ha 20]                    -- минимальная площадь поля
        [--max-fields 20]                     -- сколько крупных полей оставить
        [--out data/fields/fields_v1.geojson]

Регион по умолчанию -- северная часть tile 37TDK (Темрюкский и Анапский районы
Краснодарского края), где видна квадратная нарезка пашни.

Что делает:
    1. Запрашивает Overpass API: все объекты с landuse=farmland в bbox;
    2. Парсит ответ через osm2geojson, получает Feature[];
    3. Считает площадь каждого полигона в гектарах (через метрическую проекцию);
    4. Фильтрует по min-area-ha (отсеять межи и микро-участки);
    5. Сортирует по площади убывающе, берёт топ-max-fields;
    6. Назначает field_id (F001, F002, ...), сохраняет в GeoJSON.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import geopandas as gpd
import osm2geojson
import requests
from shapely.geometry import shape

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
]
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIELDS_DIR = PROJECT_ROOT / "data" / "fields"


def build_query(bbox: tuple[float, float, float, float]) -> str:
    s, w, n, e = bbox
    return f"""
[out:json][timeout:120];
(
  way["landuse"="farmland"]({s},{w},{n},{e});
  relation["landuse"="farmland"]({s},{w},{n},{e});
);
out geom;
""".strip()


def fetch_overpass(query: str) -> dict:
    headers = {
        "User-Agent": "AgroNDVI portfolio project (https://github.com/EValentyuk)",
        "Accept": "application/json",
    }
    last_error = None
    for endpoint in OVERPASS_ENDPOINTS:
        for attempt in range(1, 4):
            t0 = time.perf_counter()
            print(f"Overpass {endpoint} (попытка {attempt})...")
            try:
                resp = requests.post(endpoint, data={"data": query}, headers=headers, timeout=180)
                if resp.status_code == 200:
                    data = resp.json()
                    dt = time.perf_counter() - t0
                    n_elem = len(data.get("elements", []))
                    print(f"  ok: {n_elem} объектов за {dt:.1f}s ({len(resp.content)/1024:.1f} KB)")
                    return data
                snippet = resp.text[:200].replace("\n", " ")
                print(f"  HTTP {resp.status_code}: {snippet}")
                last_error = f"HTTP {resp.status_code}"
                if resp.status_code in (429, 504, 503):
                    time.sleep(5 * attempt)
                    continue
                break
            except requests.exceptions.RequestException as exc:
                print(f"  исключение: {exc}")
                last_error = str(exc)
                time.sleep(3)
    raise RuntimeError(f"Overpass не ответил ни на одном endpoint, последняя ошибка: {last_error}")


def osm_to_gdf(overpass_json: dict) -> gpd.GeoDataFrame:
    fc = osm2geojson.json2geojson(overpass_json)
    features = [f for f in fc["features"] if f["geometry"]["type"] in {"Polygon", "MultiPolygon"}]
    print(f"  полигональных features: {len(features)}")

    rows = []
    for feat in features:
        props = feat.get("properties", {}) or {}
        tags = props.get("tags", {}) or {}
        rows.append(
            {
                "osm_id": props.get("id", props.get("osm_id", "?")),
                "osm_type": props.get("type", "?"),
                "name": tags.get("name"),
                "crop": tags.get("crop"),
                "operator": tags.get("operator"),
                "geometry": shape(feat["geometry"]),
            }
        )
    return gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")


def compute_area_ha(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    metric = gdf.to_crs("EPSG:3857")
    gdf = gdf.copy()
    gdf["area_ha"] = metric.geometry.area / 10_000.0
    return gdf


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bbox", default="45.00,38.10,45.15,38.45", help="юг,запад,север,восток (WGS84)")
    parser.add_argument("--min-area-ha", type=float, default=20.0)
    parser.add_argument("--max-fields", type=int, default=20)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    bbox = tuple(float(x) for x in args.bbox.split(","))
    assert len(bbox) == 4, "bbox должен быть из 4 чисел: юг,запад,север,восток"
    s, w, n, e = bbox
    print(f"bbox: юг={s}, запад={w}, север={n}, восток={e}")
    print(f"  размер: {(n-s)*111:.1f} км по долготе, {(e-w)*78:.1f} км по широте")

    query = build_query(bbox)
    raw_json = fetch_overpass(query)

    FIELDS_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = FIELDS_DIR / "raw_osm_response.json"
    raw_path.write_text(json.dumps(raw_json, ensure_ascii=False), encoding="utf-8")
    print(f"  сырой ответ -> {raw_path.relative_to(PROJECT_ROOT)}")

    print("\nКонвертация OSM -> GeoJSON...")
    gdf = osm_to_gdf(raw_json)
    if gdf.empty:
        print("Ни одного полигона не найдено. Расширь bbox или проверь Overpass.")
        return

    gdf = compute_area_ha(gdf)
    print(f"\nСтатистика площадей (до фильтрации):")
    print(f"  всего:    {len(gdf)} полигонов")
    print(f"  min:      {gdf['area_ha'].min():.2f} га")
    print(f"  median:   {gdf['area_ha'].median():.2f} га")
    print(f"  max:      {gdf['area_ha'].max():.2f} га")
    print(f"  >= {args.min_area_ha:>4.0f} га: {(gdf['area_ha'] >= args.min_area_ha).sum()} полигонов")

    filtered = gdf[gdf["area_ha"] >= args.min_area_ha].sort_values("area_ha", ascending=False)
    if len(filtered) > args.max_fields:
        filtered = filtered.head(args.max_fields).copy()

    filtered = filtered.reset_index(drop=True)
    filtered["field_id"] = [f"F{i+1:03d}" for i in range(len(filtered))]
    filtered = filtered[["field_id", "osm_id", "osm_type", "name", "crop", "operator", "area_ha", "geometry"]]

    print(f"\nИтоговый выбор: {len(filtered)} полей")
    print(filtered[["field_id", "osm_id", "name", "crop", "area_ha"]].to_string(index=False))

    out_path = Path(args.out) if args.out else FIELDS_DIR / "fields_v1.geojson"
    filtered.to_file(out_path, driver="GeoJSON")
    print(f"\nGeoJSON -> {out_path.relative_to(PROJECT_ROOT)}")
    print(f"  размер: {out_path.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
