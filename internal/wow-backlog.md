# Backlog wow-улучшений AgroNDVI

Список дополнительных штук для «удивить рекрутёра». Делаем партиями.

## Сделано

### Этап 1: основная публикация
- [x] GitHub Pages с темой Cayman, навигацией index, Mermaid-инжектом, кнопками «На главную» и «↑ наверх»;
- [x] Презентация в MD + PPTX + PDF (21 слайд);
- [x] Черновики постов в TenChat и LinkedIn (RU + EN);
- [x] Чеклист публикации;
- [x] Email фикс везде (yandex.ru);
- [x] Полная документация: brief, architecture (C4), metrics, portfolio-report, 2 эксперимент-отчёта.

### Этап 2: pro-портфолио
- [x] **1. Интерактивная folium-карта на сайте** (`docs/map.html`);
- [x] **4. Badges в README** через shields.io (Python, LightGBM, Streamlit, rasterio, Pages, License, Last commit, Repo size);
- [x] **2. Streamlit Community Cloud deploy** -- https://agrondvi.streamlit.app/ (24/7);
- [x] **5. Repository About + Topics** на GitHub (description, homepage, 16 topics).

### Этап 3: wow-finishing (текущий)
- [x] **3. Анимированный GIF NDVI за сезон** -- `docs/images/ndvi_animation.gif`, 44 кадра, 11 секунд, ~800 КБ. Встроен в hero README и в docs/index.md;
- [x] **6. CITATION.cff** -- для академической ссылки через GitHub-кнопку «Cite this repository»;
- [x] **GitHub Action smoke-test** -- `.github/workflows/smoke-test.yml`, badge в README, прогоняет `src/smoke_test.py` на каждый push;
- [x] **JuxtaposeJS slider SCL vs NDVI** -- `docs/comparison.md`, страница со слайдером для визуального сравнения двух слоёв.

## Отложено

- [ ] **7. Loom-видео 2 минуты** -- сам пользователь, демонстрация Streamlit-приложения с голосовым комментарием. Самое мощное для рекрутёра. Делается вне Claude Code.
- [ ] **English README.md** -- параллельная версия для международной аудитории. Уже есть LinkedIn EN-черновик в `internal/publish-linkedin.md`. Объём перевода большой -- отложено.
- [ ] **Sankey-диаграмма потока данных** -- через Mermaid v10+ (`sankey-beta`). Не уверен куда впишется -- архитектура уже покрыта C4.
- [ ] **3D-визуализация рельефа** через `deck.gl` или `leafmap` -- сложно для пет-проекта.
- [ ] **Live NDVI запрос** «введи координаты → получи NDVI» -- требует server-side, не подходит для GitHub Pages.
- [ ] **Lighthouse-оптимизация сайта** -- ускорение загрузки, сжатие PNG в `docs/images/`. Не критично пока.
- [ ] **GitHub Release v0.1.0** -- через веб https://github.com/EValentyuk/AgroNDVI/releases/new?tag=v0.1.0, приложить `models/lgb_yield.pkl`. Делать когда TLS позволит.
- [ ] **Посты в TenChat / LinkedIn** -- черновики в `internal/publish-tenchat.md` и `publish-linkedin.md`. Лучше через 1-2 дня после финальной публикации, чтобы прийти со свежей головой.

## Полностью реализованные точки входа в портфолио

| Канал | URL | Аудитория |
|:---|:---|:---|
| 💻 GitHub-репо | https://github.com/EValentyuk/AgroNDVI | Программисты, code review |
| 📄 Сайт документации | https://evalentyuk.github.io/AgroNDVI/ | Рекрутёры, нанимающие менеджеры |
| 🚀 Live приложение | https://agrondvi.streamlit.app/ | Кто угодно, без установки |
| 🗺️ Статичная folium-карта | https://evalentyuk.github.io/AgroNDVI/map.html | Запасной wow |
| 🔀 SCL vs NDVI slider | https://evalentyuk.github.io/AgroNDVI/comparison | Wow для не-программиста |
| 🎞️ Анимация NDVI | в README + docs/index | Hero визуал |
| 📊 PDF/PPTX презентация | через сайт | Email-attach |
| 📚 CITATION.cff | в репо | Academic citation |
