# Доступ к Sentinel-2 L2A: через AWS Element 84 STAC

## Контекст

Изначально планировали Copernicus Data Space (browser.dataspace.copernicus.eu) -- бесплатный официальный портал ESA. На 2026-05-25 он недоступен с российских IP (санкционный геоблок) и не открывается даже через VPN на проверенных EU-локациях.

Текущее решение -- **AWS Open Data + Element 84 STAC**. Sentinel-2 L2A раздаётся бесплатно в bucket `sentinel-cogs` (us-west-2), без requester-pays, в формате Cloud Optimized GeoTIFF. Каталог -- через STAC API `https://earth-search.aws.element84.com/v1`. Регистрация не нужна.

## Архитектура доступа

```
+-------------------------+        +--------------------------+
| AWS Element 84 STAC API |        | AWS S3: sentinel-cogs    |
| earth-search.aws         |        | us-west-2, public        |
| .element84.com/v1        |        | формат: COG (GeoTIFF)    |
+-----------+-------------+        +-----------+--------------+
            |                                  |
            | поиск по bbox + дате             | HTTPS GET по конкретной полосе
            v                                  v
   +-----------------+              +---------------------+
   | find_sentinel.py |---asset URL->| explore_sentinel.py |
   | (pystac-client)  |              | (rasterio)          |
   +-----------------+              +---------------------+
```

## Преимущества по сравнению с .SAFE

| **Аспект** | **.SAFE (Copernicus)** | **COG (AWS Element 84)** |
|:---|:---|:---|
| Доступ из РФ | заблокирован | работает |
| Регистрация | да | нет |
| Скачивание | архив ~1 ГБ | можно читать удалённо без скачивания |
| Формат | JP2 в .SAFE-папке | COG GeoTIFF, по одной полосе на файл |
| Range-чтение | нет | да (HTTP range -> только нужное окно) |
| Пирамиды overview | нет | да (1:2, 1:4, 1:8, 1:16) |

## Использование

### 1. Поиск tile

```powershell
c:\Projects\AgroNDVI\.venv\Scripts\python.exe c:\Projects\AgroNDVI\src\find_sentinel.py `
    --lon 38.98 --lat 45.04 `
    --from 2024-06-01 --to 2024-06-30 `
    --max-cloud 10 `
    --save
```

Сохраняет каталожный JSON в `data/catalog/<tile-id>.json` с URL на полосы B04, B08, visual, scl, thumbnail.

### 2. Чтение метаданных и preview

```powershell
c:\Projects\AgroNDVI\.venv\Scripts\python.exe c:\Projects\AgroNDVI\src\explore_sentinel.py `
    --catalog data\catalog\S2A_37TDK_20240603_0_L2A.json
```

rasterio тянет данные удалённо через `/vsicurl/`, по HTTP-range запросам. Полное чтение всего tile (10980×10980 px) занимает ~10-30 секунд, но обычно нам нужно лишь окно над конкретными полями -- это секунды.

### 3. Где какая полоса нужна

Для MVP проекта работаем с двумя полосами 10 м:
- **B04** (red, 665 nm) -- знаменатель и числитель NDVI;
- **B08** (NIR, 842 nm) -- числитель NDVI, главный индикатор биомассы.

NDVI = (B08 - B04) / (B08 + B04).

Дополнительно для маскирования облаков и теней:
- **SCL** (Scene Classification Layer, 20 м) -- пиксельные классы Sentinel-2: 4 = vegetation, 5 = bare soil, 6 = water, 8/9 = clouds, 10 = thin cirrus, 11 = snow. Будем фильтровать SCL ∈ {4, 5, 6} для чистых пикселей.

## Что покрывает первый tile

**S2A_37TDK_20240603_0_L2A** (3 июня 2024, облачность 0.09%):

| **Параметр** | **Значение** |
|:---|:---|
| MGRS tile | 37TDK |
| Проекция | EPSG:32637 (UTM zone 37N) |
| Разрешение | 10 м/px (для B04, B08) |
| Размер | 10980 × 10980 px (~120 МП) |
| BBox WGS84 | 37.73 - 39.12 E, 44.16 - 45.15 N |
| Покрывает | юго-запад Краснодарского края: Новороссийск, Анапа, Темрюк, Тамань, северные склоны Кавказа |

Сам город Краснодар лежит на восточной кромке этого tile. Если нужны поля севернее (Кубанские степи, основной массив озимой пшеницы) -- смежные tile 37TEK (восток) или 37TDL (север). Их подберём, когда нарисуем границы реальных полей.

## Когда понадобится автоматизация серии

День 4 плана -- скачивание серии tile за весь вегетационный сезон озимой пшеницы (октябрь 2023 - июль 2024, ~50 tile). Скрипт уже готов в виде `find_sentinel.py` -- расширим его, чтобы он сохранял серию за период, а не один лучший tile.

## Альтернативные источники, тоже доступны из РФ

На случай если Element 84 STAC временно ляжет:
- **Microsoft Planetary Computer:** STAC `https://planetarycomputer.microsoft.com/api/stac/v1`, коллекция `sentinel-2-l2a`. Бесплатно, иногда нужны SAS-токены через `planetary-computer` SDK;
- **Google Cloud Storage:** `gs://gcp-public-data-sentinel-2/L2/tiles/<utm>/<lat>/<grid>/<.SAFE>/`, формат .SAFE. Бесплатно, но придётся качать .zip целиком.
