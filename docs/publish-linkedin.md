# Черновики постов в LinkedIn

LinkedIn aлгоритм любит:
- структуру списком;
- 1-2 эмодзи в начале строки для визуальной разбивки;
- упоминание конкретных компаний и стека через @ (если возможно);
- длинные посты до 3000 символов работают, но первые 2 строки решают всё (cut-off).

## RU-вариант (для российской аудитории LinkedIn)

> 🛰️ Завершил второй пет-проект для ML/DS-портфолио: **AgroNDVI** -- спутниковый мониторинг рисовых полей.
>
> Хотел показать домен «спутник + ML» для перехода в банковский агро-сегмент: РСХБ-Цифровые решения, Сбер для агробизнеса, Совкомбанк Страхование. 10 дней плотной разработки, всё на бесплатных открытых данных.
>
> Что собрал:
> ✅ 45 безоблачных снимков Sentinel-2 за полный сезон 2023-2024 (через AWS Open Data, обход санкционного блока Copernicus)
> ✅ 20 рисовых чеков Темрюкского района из OpenStreetMap (площадь 700-1500 га каждый)
> ✅ 900 точек NDVI time-series + погода (Open Meteo + NASA POWER)
> ✅ 5 моделей прогноза урожайности через Leave-One-Out CV
> ✅ Anomaly detection в 3 независимых метода (Spearman ρ ≥ 0.70 между парами -- устойчивый сигнал)
> ✅ Streamlit UI с интерактивной картой
> ✅ Полная документация: C4-диаграммы, отчёты экспериментов, метрики, voice-over для рекрутёра
>
> 💡 Главный методологический результат -- неудобный для меня, но честный: на N=20 простая LinearRegression на одной фиче `ndvi_peak` побеждает LightGBM на 18 фичах (MAPE 2.95% vs 4.39%, R² 0.70 vs 0.32). Включил это в отчёт **как есть**.
>
> Это и есть зрелый ML: начинаешь с baseline, доказываешь оправданность сложной модели. А не «лишь бы LightGBM запустить и сказать что я ML-инженер».
>
> 🔗 Репозиторий + полный отчёт: https://github.com/EValentyuk/AgroNDVI
>
> Стек: Python 3.13, rasterio + GDAL, geopandas, LightGBM, scikit-learn, Streamlit, folium, plotly, pystac-client, Mermaid.
>
> Открыт к обсуждениям, собеседованиям и сотрудничеству. Особенно интересны команды агро-скоринга, спутникового мониторинга залогов, агро-страхования.
>
> #DataScience #MachineLearning #RemoteSensing #Sentinel2 #PrecisionAgriculture #LightGBM #Python #OpenToWork

## EN-вариант (для международных рекрутёров и technical audience)

> 🛰️ Just finished my second ML/DS portfolio project: **AgroNDVI** -- satellite monitoring of rice fields in the Kuban region of Russia.
>
> Built end-to-end in 10 days on open-data infrastructure:
> ✅ 45 cloud-free Sentinel-2 L2A scenes over a full season (Oct 2023 -- Sep 2024) pulled from AWS Open Data via STAC
> ✅ 20 real rice paddies (700-1500 ha each) from OpenStreetMap landuse=farmland
> ✅ 900-point NDVI time-series, 98.9% valid pixels after SCL masking
> ✅ Weather merged in from Open-Meteo + NASA POWER (temperature, precipitation, GDD, solar radiation)
> ✅ 5 yield-forecast models compared via Leave-One-Out CV (mean, 2x LinearRegression, 2x LightGBM)
> ✅ Anomaly detection through 3 independent methods (pointwise z-score, IsolationForest, L2-distance from median curve), Spearman ρ ≥ 0.70 between pairs -- robust signal
> ✅ Streamlit UI with interactive folium map + plotly time-series per field
> ✅ Full documentation: C4 Mermaid diagrams, experiment reports, metrics, portfolio brief
>
> 💡 The key methodological finding -- inconvenient but honest: at N=20, simple **LinearRegression on a single feature `ndvi_peak` beats LightGBM on 18 features**: MAPE 2.95% vs 4.39%, R² 0.70 vs 0.32. Train MAPE LightGBM = 0.03% with LOO MAPE 4.39% -- textbook overfitting symptom.
>
> I included this result **as is** in the report. This is what mature ML looks like: start with a baseline, prove the more complex model is justified. Not "let's bolt LightGBM on it and call ourselves ML engineers."
>
> 🔗 Repository + full reports: https://github.com/EValentyuk/AgroNDVI
>
> Stack: Python 3.13, rasterio + GDAL, geopandas, LightGBM, scikit-learn, Streamlit, folium, plotly, pystac-client, Mermaid.
>
> Open to ML engineering / data science opportunities, especially in agro-credit scoring, satellite collateral monitoring, agricultural insurance, or geospatial fintech.
>
> #DataScience #MachineLearning #RemoteSensing #Sentinel2 #PrecisionAgriculture #LightGBM #Python #OpenToWork

## Технические заметки по постингу

- Использовать LinkedIn native upload для 1-2 ключевых картинок (карта полей + кривая NDVI). Не давать только текст со ссылкой -- алгоритм такие посты режет;
- Не вставлять ссылку GitHub в первую строку -- LinkedIn даунграйдит посты с внешними ссылками сверху. Лучше ссылка во второй половине поста или в первом комментарии;
- Время постинга: вторник-четверг 09:00-11:00 МСК для российской аудитории, 14:00-16:00 МСК для международной (это утро-полдень в Европе);
- В первом комментарии добавить ссылку на portfolio-report.md и MiniProctor (это даёт алгоритму сигнал, что пост релевантен ML-сообществу).

## Что НЕ делать

- Не упоминать конкретные конкретные таргетные компании в посте «иду к вам в РСХБ»;
- Не делать ставку на хайповые слова (AI, GPT, LLM) -- проект про другое, аудитория поймёт;
- Не обещать «99% точности» -- честно говорить про N=20 и синтетический таргет;
- Не упоминать санкционные блоки эмоционально -- говорить «обход через AWS Open Data» как факт инфраструктуры.
