# Размещение backend

Публичный деплой в этой поставке **не выполнен**: хостинг и репозиторий команды не предоставлены. Dockerfile подготовлен, но сборка контейнера не проверена — Docker в текущем окружении отсутствует.

## Обычный Python-хостинг

Из корня репозитория:

```text
Build: pip install -r backend/requirements-lock.txt
Start: uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port $PORT
```

Команда с `$PORT` рассчитана на POSIX shell хостинга. Для локального PowerShell укажи `--port 8000`.

Переменные окружения:

- `SAPAR_DEMO_MODE=false`.
- `CORS_ORIGINS=https://your-frontend.example` — точный origin без пути и завершающего `/`; несколько через запятую.
- `SAPAR_DATA_DIR` — необязательно: по умолчанию корневой `data/`, путь вычисляется от кода.
- `DATABASE_URL` — необязательно: по умолчанию SQLite в backend. Каталог должен быть доступен для записи.
- `AI_TIMEOUT_SECONDS=8`.
- `GROQ_API_KEY` — после подключения реального провайдера Ерасыла.

`.env` автоматически не читается. Локально используй `uvicorn --env-file backend/.env` из корня либо `--env-file .env` из backend. На хостинге задавай environment variables через его настройки.

Сначала проверь `GET /api/health`, затем реальный generate-запрос. HTTP 200 health сам по себе не означает наличие пригодных маршрутов. Нужно `dataset_ready=true`, `data_mode=real`, источники и фактически подходящий маршрут на выбранные параметры.

## Docker

Контекст сборки — корень SAPAR-AI, не backend:

```sh
docker build -f backend/Dockerfile -t sapar-backend .
docker run --rm -p 8000:8000 -e CORS_ORIGINS=https://your-frontend.example sapar-backend
```

Production-образ содержит `backend/app` и `data`, но не синтетические fixtures. Данные импортируются в SQLite при старте, поэтому временный диск годится для текущего read-only каталога: оригиналы находятся в JSON. Для будущих пользовательских записей потребуется постоянное хранилище.

Не включай `--reload` на хостинге. Настрой HTTPS и лимиты запросов на платформе перед внешним запуском, особенно после подключения платного AI. Этот пакет не содержит авторизации и rate limiter; CORS не заменяет их. Проверки нагрузки и внешней безопасности пока не проводились.
