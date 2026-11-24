# SAPAR AI — часть Абзала

Backend и пакет интеграции, подготовлены 25 ноября 2026. Контракт **предложен как v1.0**, согласование команды ещё не проводилось. Frontend и Groq-провайдер здесь не реализованы: это части Самира и Ерасыла.

Сначала прочитай [START_HERE.md](START_HERE.md). Передай коллегам весь архив, затем укажи их инструкции в `docs/handoffs/`.

## Быстрый запуск (PowerShell, Python 3.12)

Открой терминал в папке SAPAR-AI:

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r backend/requirements-lock.txt
Copy-Item backend/.env.example backend/.env
cd backend
../.venv/Scripts/python -m uvicorn app.main:app --env-file .env --reload --host 127.0.0.1 --port 8000
```

Документация: http://127.0.0.1:8000/docs. Состояние: http://127.0.0.1:8000/api/health.

По умолчанию `data/` пуст: `dataset_ready=false`, генерация вернёт `no_results`. Это ожидаемое поведение до получения данных Ерасыла, а не сбой backend.

## Деморежим для разработки frontend

Останови сервер, в том же терминале из `backend/`:

```powershell
$env:SAPAR_DEMO_MODE = 'true'
../.venv/Scripts/python -m uvicorn app.main:app --env-file .env --reload --host 127.0.0.1 --port 8000
```

В Swagger отправь `integration/examples/generate-request.json` в `/api/trips/generate`. Объекты, цены и координаты синтетические. `data_mode=demo` и предупреждения должны отображаться во frontend. Для реального запуска убери переменную `SAPAR_DEMO_MODE` или установи `false`, заполни четыре файла `data/`, перезапусти сервер.

## Проверки

Из корня SAPAR-AI:

```powershell
.venv/Scripts/python scripts/validate_data.py
.venv/Scripts/python scripts/validate_data.py backend/tests/fixtures/demo
.venv/Scripts/python scripts/export_contract.py
tsc --noEmit --strict --target ES2020 --module ESNext --moduleResolution bundler --lib 'ES2020,DOM' integration/api-client.ts
cd backend
../.venv/Scripts/python -m pytest -q
```

TypeScript нужен только для проверки клиента; backend работает без Node. На macOS/Linux путь к интерпретатору `.venv/bin/python`, переменная задаётся через `export SAPAR_DEMO_MODE=true`.

## Файлы

- `backend/app/` — API, SQLAlchemy, Pydantic, планировщик, граница подключения AI.
- `backend/tests/` — расчёты, валидация, API, отказ AI, синтетические fixtures.
- `docs/openapi.json` — машинный контракт REST, автоматически экспортируется из приложения.
- `docs/dataset.schema.json` — полный контракт объединённого датасета.
- `integration/api-types.ts`, `api-client.ts` — типы и fetch-клиент для Самира.
- `integration/examples/` — запрос и реальные результаты алгоритма на синтетическом датасете.
- `docs/api-contract.md`, `data-contract.md`, `architecture.md` — правила интеграции.
- `docs/handoffs/` — готовые задания нейросетям участников.
- `docs/deployment.md` — инструкции размещения; публичный деплой ещё не выполнен.

## Граница готовности

Алгоритмы и API реализованы и проверяются локально. Для туристического MVP необходимы реальные данные, проверенные шаблоны и расписания Ерасыла, его Groq-провайдер, frontend Самира, совместное тестирование и публичное размещение. Наличие URL в датасете не доказывает достоверность сведений: её проверяет автор данных.
