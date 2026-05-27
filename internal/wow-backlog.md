# Backlog wow-улучшений AgroNDVI

Список дополнительных штук для «удивить рекрутёра» после публикации основного сайта. Делаем партиями.

## Сейчас в работе

- [ ] **1. Интерактивная folium-карта на сайте** -- `data/preview/fields_v1_map.html` → `docs/map.html` + ссылка с index.md. Wow для агронома/банка: кликает -- видит метаданные поля.
- [ ] **4. Badges в README** -- `shields.io`: license, python version, last commit, repo size, top language. Косметика, делает README профессиональнее.
- [ ] **2. Streamlit Community Cloud deploy** -- бесплатный hosting, публичный URL приложения 24/7. Требует OAuth через streamlit.io в браузере. Инструкция в `internal/publish-checklist.md` после реализации.
- [ ] **5. Repository About + Topics** -- в `Settings → About` на github.com: description, website (Pages URL), topics (`remote-sensing`, `sentinel-2`, `lightgbm`, `ndvi`, `agriculture`, `ml-portfolio`, `precision-agriculture`, `python`, `russia`, `kuban`, `rice`). Требует действий пользователя через web.

## Отложено (по мере появления сил)

- [ ] **3. Анимированный GIF NDVI за сезон.** Из 45 кадров серии собрать GIF с подписью даты и кумулятивным GDD. Видна «горбатая» рисовая кривая в движении. Поставить в hero-секцию README. Через PIL + `data/processed/ndvi_series/*.tif` (если эти файлы будут сохранены через `ndvi_series.py --save-ndvi-tif`). ~15-20 минут.
- [ ] **6. CITATION.cff** -- для академической ссылки через GitHub-кнопку «Cite this repository». Wow для исследователей. ~5 минут.
- [ ] **7. Loom-видео 2 минуты** -- сам пользователь, демонстрация Streamlit-приложения с голосовым комментарием. Самое мощное для рекрутёра. Делается вне Claude Code.

## Дополнительные идеи (не из топ-7)

- [ ] **JuxtaposeJS slider «RGB vs NDVI»** -- две картинки одного tile со слайдером между ними. https://juxtapose.knightlab.com/
- [ ] **Sankey-диаграмма потока данных** -- через Mermaid v10+ (`flowchart` или `sankey-beta`).
- [ ] **3D-визуализация рельефа** через `deck.gl` или `leafmap` -- сложно для пет-проекта.
- [ ] **Live NDVI запрос** «введи координаты -- получи NDVI» -- требует server-side, не подходит для GitHub Pages.
- [ ] **GitHub Action smoke-test** -- автотест `python src/smoke_test.py` на каждый push. Профессионально, но дает мало wow для рекрутёра-человека.
- [ ] **English README.md** -- параллельная версия для международной аудитории. Уже есть LinkedIn EN-черновик в `internal/publish-linkedin.md`.
- [ ] **Lighthouse-оптимизация сайта** -- ускорение загрузки, сжатие PNG в `docs/images/`.

## Сделано (из плана 10 дней + после)

- [x] GitHub Pages с темой Cayman, навигацией index, Mermaid-инжектом, кнопками «На главную» и «↑ наверх»;
- [x] Презентация в MD + PPTX + PDF (21 слайд);
- [x] Черновики постов в TenChat и LinkedIn (RU + EN);
- [x] Чеклист публикации;
- [x] Email фикс везде (yandex.ru);
- [x] Полная документация: brief, architecture (C4), metrics, portfolio-report, 2 эксперимент-отчёта.
