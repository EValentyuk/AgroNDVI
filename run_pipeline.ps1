# AgroNDVI -- end-to-end pipeline run
#
# Запуск:
#     .\run_pipeline.ps1
#     .\run_pipeline.ps1 -SkipFetch        # пропустить шаги скачивания
#     .\run_pipeline.ps1 -SkipNdviSeries   # пропустить тяжёлый NDVI-серия шаг
#
# Все скрипты идут через PowerShell (не bash) -- LightGBM на Windows + Git Bash
# даёт segfault. PowerShell стабилен.

param(
    [switch]$SkipFetch,
    [switch]$SkipNdviSeries,
    [switch]$SkipPlots
)

$ErrorActionPreference = 'Stop'
$script:start = Get-Date

$Python = "$PSScriptRoot\.venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Host "ERROR: venv не найден. Создайте: python -m venv .venv; .venv\Scripts\pip install -r requirements.txt"
    exit 1
}

function Step($name, $cmd) {
    $t0 = Get-Date
    Write-Host ""
    Write-Host "==== $name ====" -ForegroundColor Cyan
    Write-Host "    $cmd" -ForegroundColor DarkGray
    Invoke-Expression $cmd
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAILED: $name (exit $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }
    $dt = (Get-Date) - $t0
    Write-Host "    done in $($dt.TotalSeconds.ToString('F1'))s" -ForegroundColor Green
}

Write-Host ""
Write-Host "AgroNDVI pipeline start: $script:start" -ForegroundColor Yellow

Step "Smoke-test зависимостей" "& '$Python' -X utf8 '$PSScriptRoot\src\smoke_test.py'"

if (-not $SkipFetch) {
    Step "Поиск серии Sentinel-2 (45 снимков за год)" `
        "& '$Python' -X utf8 '$PSScriptRoot\src\find_sentinel.py' --series --tile 37TDK --from 2023-10-01 --to 2024-09-30 --max-cloud 20"

    Step "Скачивание границ полей из OSM" `
        "& '$Python' -X utf8 '$PSScriptRoot\src\fetch_osm_fields.py'"

    Step "Скачивание погоды (Open Meteo + NASA POWER)" `
        "& '$Python' -X utf8 '$PSScriptRoot\src\fetch_weather.py'"
} else {
    Write-Host "  -- шаги скачивания пропущены (--SkipFetch)" -ForegroundColor DarkYellow
}

if (-not $SkipNdviSeries) {
    Step "Расчёт серии NDVI по 20 полям (45 дат × 6 потоков, ~8 минут)" `
        "& '$Python' -X utf8 '$PSScriptRoot\src\ndvi_series.py' --workers 6"
} else {
    Write-Host "  -- расчёт серии пропущен (--SkipNdviSeries)" -ForegroundColor DarkYellow
}

Step "Усреднение NDVI по полям на одной дате (zonal stats для отдельного tile)" `
    "& '$Python' -X utf8 '$PSScriptRoot\src\zonal_stats.py'"

Step "Feature engineering (18 фичей + синтетический yield)" `
    "& '$Python' -X utf8 '$PSScriptRoot\src\feature_engineering.py'"

Step "Обучение LightGBM + 4 baseline + LOO-CV" `
    "& '$Python' -X utf8 '$PSScriptRoot\src\train_lgb.py'"

Step "Anomaly detection (3 метода)" `
    "& '$Python' -X utf8 '$PSScriptRoot\src\anomaly.py'"

if (-not $SkipPlots) {
    Step "Визуализации: NDVI series" `
        "& '$Python' -X utf8 '$PSScriptRoot\src\plot_ndvi_series.py'"
    Step "Визуализации: NDVI vs Weather" `
        "& '$Python' -X utf8 '$PSScriptRoot\src\plot_weather_ndvi.py'"
    Step "Визуализации: model results" `
        "& '$Python' -X utf8 '$PSScriptRoot\src\plot_model_results.py'"
    Step "Визуализации: anomaly" `
        "& '$Python' -X utf8 '$PSScriptRoot\src\plot_anomaly.py'"
} else {
    Write-Host "  -- визуализации пропущены (--SkipPlots)" -ForegroundColor DarkYellow
}

$total = (Get-Date) - $script:start
Write-Host ""
Write-Host "Pipeline finished in $($total.TotalMinutes.ToString('F1')) минут" -ForegroundColor Green
Write-Host ""
Write-Host "Запустить UI: " -NoNewline
Write-Host ".venv\Scripts\streamlit.exe run src\streamlit_app.py" -ForegroundColor Cyan
