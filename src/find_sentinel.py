"""Поиск Sentinel-2 L2A tile через AWS Element 84 STAC API.

AWS Element 84 раздаёт публичный каталог `sentinel-2-l2a` бесплатно, без
requester-pays. Файлы лежат в bucket `sentinel-cogs` в формате COG, что
позволяет читать их удалённо через rasterio без полного скачивания.

Использование:
    python src/find_sentinel.py
        [--lon 38.98] [--lat 45.04]
        [--from 2024-06-01] [--to 2024-06-30]
        [--max-cloud 10]
        [--limit 10]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from pystac_client import Client

STAC_URL = "https://earth-search.aws.element84.com/v1"


def _retry_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=6,
        connect=4,
        read=4,
        status=4,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "POST"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=8)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update({"User-Agent": "AgroNDVI portfolio project"})
    return s


def _post_with_retry(session: requests.Session, url: str, payload: dict, max_retries: int = 8) -> dict:
    import urllib3
    last_exc: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = session.post(url, json=payload, timeout=(30, 90))
            resp.raise_for_status()
            return resp.json()
        except (requests.exceptions.RequestException, urllib3.exceptions.ProtocolError, ValueError) as exc:
            last_exc = exc
            wait = min(60, 2 ** attempt)
            print(f"    попытка {attempt} упала ({exc.__class__.__name__}), жду {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"все {max_retries} попыток упали: {last_exc}")


def _search_chunk(session: requests.Session, lon: float, lat: float, date_from: str, date_to: str, max_cloud: float) -> list[dict]:
    url = f"{STAC_URL}/search"
    payload = {
        "collections": [COLLECTION],
        "intersects": {"type": "Point", "coordinates": [lon, lat]},
        "datetime": f"{date_from}T00:00:00Z/{date_to}T23:59:59Z",
        "query": {"eo:cloud_cover": {"lt": max_cloud}},
        "limit": 100,
    }
    items: list[dict] = []
    page = 1
    while True:
        body = _post_with_retry(session, url, payload)
        features = body.get("features", [])
        items.extend(features)
        next_link = next((lk for lk in body.get("links", []) if lk.get("rel") == "next"), None)
        if not next_link:
            break
        payload = next_link.get("body", payload)
        page += 1
        if page > 5:
            break
    return items


def search_series_raw(lon: float, lat: float, date_from: str, date_to: str, max_cloud: float) -> list[dict]:
    """STAC search с разбивкой на месяцы и явным retry."""
    from datetime import date, timedelta

    session = _retry_session()

    def parse(s):
        return date(*[int(x) for x in s.split("-")])

    start = parse(date_from)
    end = parse(date_to)
    chunks: list[tuple[str, str]] = []
    cur = start.replace(day=1)
    while cur <= end:
        if cur.month == 12:
            nxt = cur.replace(year=cur.year + 1, month=1)
        else:
            nxt = cur.replace(month=cur.month + 1)
        chunks.append((max(cur, start).isoformat(), min(nxt - timedelta(days=1), end).isoformat()))
        cur = nxt

    items: list[dict] = []
    for i, (cf, ct) in enumerate(chunks, 1):
        print(f"  чанк {i}/{len(chunks)}: {cf} -- {ct}")
        chunk_items = _search_chunk(session, lon, lat, cf, ct, max_cloud)
        items.extend(chunk_items)
        print(f"    получено {len(chunk_items)}, всего {len(items)}")
    return items


def feature_to_summary(feat: dict) -> dict:
    props = feat.get("properties", {})
    assets = feat.get("assets", {})
    return {
        "id": feat["id"],
        "datetime": props.get("datetime"),
        "cloud_cover": round(props.get("eo:cloud_cover", -1), 2),
        "mgrs_tile": f"{props.get('mgrs:utm_zone','?')}{props.get('mgrs:latitude_band','?')}{props.get('mgrs:grid_square','?')}",
        "platform": props.get("platform", "?"),
        "bbox": feat.get("bbox"),
        "assets": {
            "red_B04": assets.get("red", {}).get("href"),
            "nir_B08": assets.get("nir", {}).get("href"),
            "visual": assets.get("visual", {}).get("href"),
            "scl": assets.get("scl", {}).get("href"),
            "thumbnail": assets.get("thumbnail", {}).get("href"),
        },
    }
COLLECTION = "sentinel-2-l2a"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CATALOG_DIR = PROJECT_ROOT / "data" / "catalog"


def search(lon: float, lat: float, date_from: str, date_to: str, max_cloud: float, limit: int) -> list[dict]:
    client = Client.open(STAC_URL)
    search_result = client.search(
        collections=[COLLECTION],
        intersects={"type": "Point", "coordinates": [lon, lat]},
        datetime=f"{date_from}/{date_to}",
        query={"eo:cloud_cover": {"lt": max_cloud}},
        limit=limit,
    )
    items = list(search_result.items())
    items.sort(key=lambda it: it.properties.get("eo:cloud_cover", 100.0))
    return items


def item_to_summary(item) -> dict:
    assets = item.assets
    return {
        "id": item.id,
        "datetime": str(item.datetime),
        "cloud_cover": round(item.properties.get("eo:cloud_cover", -1), 2),
        "mgrs_tile": f"{item.properties.get('mgrs:utm_zone', '?')}"
        f"{item.properties.get('mgrs:latitude_band', '?')}"
        f"{item.properties.get('mgrs:grid_square', '?')}",
        "platform": item.properties.get("platform", "?"),
        "bbox": item.bbox,
        "assets": {
            "red_B04": assets["red"].href if "red" in assets else None,
            "nir_B08": assets["nir"].href if "nir" in assets else None,
            "visual": assets["visual"].href if "visual" in assets else None,
            "scl": assets["scl"].href if "scl" in assets else None,
            "thumbnail": assets["thumbnail"].href if "thumbnail" in assets else None,
        },
    }


def search_series(lon: float, lat: float, date_from: str, date_to: str, max_cloud: float, tile_filter: str | None = None) -> list:
    """Полная серия за период с фильтром по облачности и (опционально) по MGRS-tile."""
    client = Client.open(STAC_URL)
    sr = client.search(
        collections=[COLLECTION],
        intersects={"type": "Point", "coordinates": [lon, lat]},
        datetime=f"{date_from}/{date_to}",
        query={"eo:cloud_cover": {"lt": max_cloud}},
        limit=500,
    )
    items = list(sr.items())
    if tile_filter:
        utm, lat_band, square = tile_filter[:2], tile_filter[2:3], tile_filter[3:]
        items = [
            it for it in items
            if str(it.properties.get("mgrs:utm_zone")) == utm
            and it.properties.get("mgrs:latitude_band") == lat_band
            and it.properties.get("mgrs:grid_square") == square
        ]
    items.sort(key=lambda it: it.datetime)
    return items


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lon", type=float, default=38.98, help="долгота точки (по умолчанию Краснодар)")
    parser.add_argument("--lat", type=float, default=45.04, help="широта точки (по умолчанию Краснодар)")
    parser.add_argument("--from", dest="date_from", default="2024-06-01")
    parser.add_argument("--to", dest="date_to", default="2024-06-30")
    parser.add_argument("--max-cloud", type=float, default=10.0)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--save", action="store_true", help="сохранить топ-1 в data/catalog/")
    parser.add_argument("--series", action="store_true", help="режим серии: вернуть все tile за период")
    parser.add_argument("--tile", default=None, help="фильтр по MGRS-tile, например 37TDK")
    parser.add_argument("--series-out", default=None, help="путь для multi-catalog JSON")
    args = parser.parse_args()

    if args.series:
        print(f"Серия Sentinel-2 L2A над точкой ({args.lon}, {args.lat})")
        print(f"  период: {args.date_from} -- {args.date_to}, max cloud {args.max_cloud}%")
        if args.tile:
            print(f"  фильтр tile: {args.tile}")
        raw_items = search_series_raw(args.lon, args.lat, args.date_from, args.date_to, args.max_cloud)
        if args.tile:
            utm, lat_band, square = args.tile[:2], args.tile[2:3], args.tile[3:]
            raw_items = [
                f for f in raw_items
                if str(f.get("properties", {}).get("mgrs:utm_zone")) == utm
                and f.get("properties", {}).get("mgrs:latitude_band") == lat_band
                and f.get("properties", {}).get("mgrs:grid_square") == square
            ]
        raw_items.sort(key=lambda f: f.get("properties", {}).get("datetime", ""))
        if not raw_items:
            print("Ничего не найдено.")
            return
        print(f"\nНайдено {len(raw_items)} снимков после фильтра tile:")
        summaries = [feature_to_summary(f) for f in raw_items]
        for i, s in enumerate(summaries, 1):
            print(f"  [{i:2d}] {s['datetime'][:10]} tile {s['mgrs_tile']} облачность {s['cloud_cover']:>5.2f}%  {s['id']}")
        CATALOG_DIR.mkdir(parents=True, exist_ok=True)
        out_path = Path(args.series_out) if args.series_out else CATALOG_DIR / f"series_{args.tile or 'any'}_{args.date_from}_{args.date_to}.json"
        out_path.write_text(json.dumps({"params": vars(args), "items": summaries}, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nСерия сохранена: {out_path.relative_to(PROJECT_ROOT)}")
        return

    print(f"Поиск Sentinel-2 L2A над точкой ({args.lon}, {args.lat})")
    print(f"  период: {args.date_from} -- {args.date_to}")
    print(f"  макс облачность: {args.max_cloud}%\n")

    items = search(args.lon, args.lat, args.date_from, args.date_to, args.max_cloud, args.limit)
    if not items:
        print("Ничего не найдено. Расширь окно дат или порог облачности.")
        return

    print(f"Найдено: {len(items)} (отсортировано по облачности)\n")
    summaries = [item_to_summary(it) for it in items]
    for i, s in enumerate(summaries, 1):
        print(f"[{i}] {s['id']}")
        print(f"    дата: {s['datetime']}, облачность: {s['cloud_cover']}%, tile: {s['mgrs_tile']}")
        print(f"    bbox: {s['bbox']}")

    if args.save:
        CATALOG_DIR.mkdir(parents=True, exist_ok=True)
        out = CATALOG_DIR / f"{summaries[0]['id']}.json"
        out.write_text(json.dumps(summaries[0], indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nЛучший tile сохранён: {out.relative_to(PROJECT_ROOT)}")
        print(f"B04 URL: {summaries[0]['assets']['red_B04']}")
        print(f"B08 URL: {summaries[0]['assets']['nir_B08']}")


if __name__ == "__main__":
    main()
