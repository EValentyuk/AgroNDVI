# Чеклист публикации AgroNDVI

Шаги после локального коммита и до объявления в соцсетях. Все команды для PowerShell в корне `c:\Projects\AgroNDVI`.

## 1. Создать GitHub-репозиторий

Вариант через `gh` (если авторизация рабочая):
```powershell
gh auth status                              # проверить активный токен
gh auth login                               # если просрочен -- залогиниться заново
gh repo create EValentyuk/AgroNDVI `
    --public `
    --description "Pet-проект: спутниковый мониторинг рисовых полей и прогноз урожайности (Sentinel-2 + LightGBM + Streamlit)" `
    --homepage "https://github.com/EValentyuk" `
    --source . `
    --remote origin `
    --push
```

Вариант через веб-интерфейс:
1. Открыть https://github.com/new;
2. Repository name: `AgroNDVI`;
3. Description: `Pet-проект: спутниковый мониторинг рисовых полей и прогноз урожайности (Sentinel-2 + LightGBM + Streamlit)`;
4. Public, **без** Initialize with README/gitignore (у нас уже всё локально);
5. Нажать «Create»;
6. Скопировать URL и связать локальный репо:
   ```powershell
   git remote add origin https://github.com/EValentyuk/AgroNDVI.git
   git push -u origin main
   ```

## 2. Проверка после push

Открыть https://github.com/EValentyuk/AgroNDVI и пройти по чеклисту:

- [ ] README рендерится, видны 8 скриншотов из `docs/images/`;
- [ ] hero-блок с MAPE 2.95% vs 4.39% виден;
- [ ] Mermaid-диаграммы в `docs/architecture.md` рисуются (3 диаграммы + dependency граф);
- [ ] `docs/portfolio-report.md` -- hero-блок виден сразу под шапкой;
- [ ] `docs/experiments/` оба отчёта читаются, таблицы корректны;
- [ ] `docs/metrics.md` -- все таблицы корректны;
- [ ] `data/fields/fields_v1.geojson` (14 КБ) есть, `data/preview/*.png` нет;
- [ ] `models/lgb_yield.pkl` НЕ попал в репо (правильное поведение -- модель генерируется при запуске);
- [ ] `.venv/` и `__pycache__/` НЕ попали;
- [ ] лог-файлы (`AgroNDVI-results.md`, `AgroNDVI-journal.md`) есть, отображаются с разметкой.

## 3. Тэги и релиз

Создать тэг v0.1.0 -- первый стабильный snapshot:
```powershell
git tag -a v0.1.0 -m "Первый стабильный релиз: 10 дней разработки, pipeline + UI + документация"
git push origin v0.1.0
```

Опционально -- через `gh` создать Release с финальной моделью как ассет:
```powershell
gh release create v0.1.0 `
    --title "AgroNDVI v0.1.0" `
    --notes "См. AgroNDVI-results.md по дням и docs/portfolio-report.md." `
    models/lgb_yield.pkl
```

## 4. About / topics на странице репо

Зайти в https://github.com/EValentyuk/AgroNDVI -> ⚙️ напротив About и заполнить:

- **Description:** `Pet-проект: спутниковый мониторинг рисовых полей и прогноз урожайности через Sentinel-2 + LightGBM + Streamlit`;
- **Website:** `https://github.com/EValentyuk` (или GitHub Pages, если включишь);
- **Topics:** `remote-sensing`, `sentinel-2`, `ndvi`, `agriculture`, `precision-agriculture`, `lightgbm`, `streamlit`, `geopandas`, `rasterio`, `time-series`, `ml-portfolio`, `russia`, `kuban`, `rice`, `python`.

## 5. README визуальная проверка

- Заголовок и hero-блок видны без скролла;
- Картинки крутятся в правильном размере (не растянуты);
- Mermaid-диаграммы в architecture.md рендерятся;
- Ссылки на docs/ работают.

## 6. Социальные сети

См. готовые черновики:
- TenChat -- `publish-tenchat.md`;
- LinkedIn (RU + EN) -- `publish-linkedin.md`.

Запостить **через 1-2 дня** после публикации репо, чтобы пройтись по проекту с холодной головой и поправить найденные баги.

## 7. Что обновить в портфолио

- Резюме на hh.ru: добавить в раздел «Проекты» рядом с MiniProctor;
- LinkedIn profile -> Projects: добавить AgroNDVI с описанием и ссылкой;
- Личный сайт / Notion / Telegraph: ссылка на GitHub-репо + portfolio-report;
- Hacker News / Reddit r/MachineLearning (опционально, если хочется international audience).

## 8. Опциональные шаги

- [ ] Англоязычный README (см. `README.en.md`);
- [ ] GitHub Pages с `docs/` как сайт: Settings -> Pages -> Source = main / `docs/`;
- [ ] CI: GitHub Action для smoke-test (только `python src/smoke_test.py` на push);
- [ ] Citations: `CITATION.cff` для академической ссылки;
- [ ] DOI через Zenodo (если хочется academic visibility).

## 9. Откат, если что-то пошло не так

Если после публикации обнаружится секретный токен или приватные данные в git:
```powershell
# СРАЗУ удалить репо
gh repo delete EValentyuk/AgroNDVI --yes

# вычистить локально
git reset --hard <commit-before-bad>
# или вообще:
rm -rf .git
git init -b main
# заново коммит, заново публикация
```

Поскольку у нас в репо ничего секретного нет (проверено: API без ключей, email и так в README), вероятность отката низкая.
