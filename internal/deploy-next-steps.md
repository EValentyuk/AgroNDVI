# Следующие шаги публикации -- действия в браузере

Две задачи, которые требуют твоих действий через веб (Claude Code не имеет твоих credentials). 15 минут суммарно.

---

## 1. Repository About + Topics (~2 минуты, чистая косметика)

Открыть https://github.com/EValentyuk/AgroNDVI → справа от описания репо ⚙️ (gear icon рядом с About) → диалог редактирования.

**Description:**
```
Pet-проект: спутниковый мониторинг рисовых полей и прогноз урожайности через Sentinel-2 + LightGBM + Streamlit. 10 дней, открытые данные, доступ из РФ без VPN.
```

**Website:**
```
https://evalentyuk.github.io/AgroNDVI/
```

**Topics (вставить через пробел, GitHub сам разобьёт):**
```
remote-sensing sentinel-2 ndvi agriculture precision-agriculture lightgbm streamlit geopandas rasterio time-series ml-portfolio python russia kuban rice anomaly-detection
```

✅ **Include in the home page:** оставить включёнными `Releases` (когда добавишь v0.1.0) и `Packages`.

Сохранить.

---

## 2. Streamlit Community Cloud deploy (~10-15 минут)

### 2.1. Что нужно изменить в репо ПЕРЕД деплоем

Streamlit Cloud при старте выполняет:
```
pip install -r requirements.txt
streamlit run src/streamlit_app.py
```

Streamlit-приложение читает 5 артефактов, которых сейчас **нет в git** (под `.gitignore`):
- `data/processed/fields_features.csv` (~7 КБ)
- `data/processed/fields_ndvi_series.csv` (~65 КБ)
- `data/processed/fields_anomaly.csv` (~2 КБ)
- `data/weather/weather_daily.csv` (~60 КБ)
- `models/lgb_yield.pkl` (~80 КБ)

**Итого ~215 КБ** -- закоммитить безопасно. Иначе деплой упадёт с FileNotFoundError.

Сделать вручную или через скрипт:
```powershell
git add -f data/processed/fields_features.csv data/processed/fields_ndvi_series.csv data/processed/fields_anomaly.csv data/weather/weather_daily.csv models/lgb_yield.pkl
git commit -m "feat: добавлены артефакты для Streamlit Cloud deploy"
git push origin main
```

Флаг `-f` нужен, потому что эти файлы в `.gitignore`. Альтернативно -- сначала поправить `.gitignore` (добавить исключения), потом `git add` без `-f`.

### 2.2. Создать `runtime.txt` в корне репо

Чтобы Streamlit Cloud выбрал правильную версию Python:
```
python-3.13
```

```powershell
echo "python-3.13" | Out-File -Encoding ASCII runtime.txt
git add runtime.txt
git commit -m "ci: runtime.txt для Streamlit Cloud (Python 3.13)"
git push origin main
```

### 2.3. Деплой через web

1. Открыть https://share.streamlit.io/ → **Sign in with GitHub** → авторизовать;
2. Кнопка **«New app»**;
3. Заполнить форму:
   - **Repository:** `EValentyuk/AgroNDVI`
   - **Branch:** `main`
   - **Main file path:** `src/streamlit_app.py`
   - **App URL** (опционально): `agrondvi` -- получится `agrondvi.streamlit.app`
4. **Advanced settings:**
   - Python version: 3.13 (или auto если runtime.txt уже в репо);
   - Secrets: не нужны;
   - Environment variables: не нужны;
5. **Deploy!**

### 2.4. Что произойдёт

Первый деплой: ~5-10 минут (установка 70+ пакетов, включая rasterio+GDAL).
Последующие деплои при push: ~2-3 минуты.

Если упадёт:
- В логах справа видно ошибки;
- Чаще всего: не хватает артефакта (FileNotFoundError) или несовместимость версий пакетов;
- Если rasterio/GDAL не ставится: добавить `packages.txt` в корень с содержимым `gdal-bin libgdal-dev` (на Streamlit Cloud Linux apt-пакеты).

### 2.5. Если всё ок

- Публичный URL вида `https://agrondvi.streamlit.app/` -- работает 24/7;
- Можно вставить в `README.md` как кнопку **«Open in Streamlit»**;
- Streamlit Cloud сам перезапустит приложение при каждом push в main.

---

## 3. После

После 1 и 2 -- обновить:
- `README.md`: badge для Streamlit Cloud + ссылка в hero-секцию;
- `docs/index.md`: добавить ссылку на live demo рядом с интерактивной картой;
- `docs/portfolio-report.md`: упомянуть live URL в контактах.

Это уже 5 минут. Скажешь Claude Code -- сделает после того как ты пройдёшь шаги 1 и 2.
