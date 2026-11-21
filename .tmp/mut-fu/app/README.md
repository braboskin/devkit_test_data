# Atlas Chat

MVP-приложение: два равноправных аккаунта, изоляция данных по `owner_id`,
PostgreSQL и миграции Alembic.

## PostgreSQL

```bash
docker compose up -d postgres
# PostgreSQL 17 на 127.0.0.1:5432, база/пользователь/пароль: atlas
alembic upgrade head
```

Схему создают только миграции; `create_all` в приложении и CLI нет.
Для SQLite (например, в тестах) достаточно `ATLAS_DB_URL=sqlite:///...`:
миграция одинаково работает на обоих диалектах.

## Запуск

```bash
.venv\Scripts\python.exe -m app.backend.cli create-user --username alice
.venv\Scripts\python.exe -m app.backend.cli create-user --username bob
.venv\Scripts\python.exe -m app.backend.cli list-users
.venv\Scripts\python.exe -m app.backend.cli reset-password --username alice
.venv\Scripts\python.exe -m uvicorn app.backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Ролей нет: оба аккаунта равноправны, данные разделены по `owner_id`.
Пароли запрашиваются интерактивно (`--password` — для автоматизации);
в git и чат не попадают.

## Переменные

| Переменная | Значение |
|---|---|
| `ATLAS_DB_URL` | `postgresql+psycopg://atlas:atlas@127.0.0.1:5432/atlas` по умолчанию |
| `ATLAS_COOKIE_SECURE` | `1` за HTTPS |
| `ATLAS_CORS_ORIGINS` | `http://localhost:5173` для dev |
| `ATLAS_SESSION_DAYS` | `30` (сессия продлевается при активности, не чаще раза в сутки) |
| `ATLAS_STORAGE_DIR` | `data/storage` — оригиналы документов, вне web-root |
| `ATLAS_MAX_UPLOAD_MB` | `100` — лимит загружаемого файла |
| `PG_BIN` | каталог `bin` PostgreSQL для PG-smoke в тестах |

## API

- `GET /health`
- `POST /api/auth/login` `{username, password}`
- `POST /api/auth/logout`
- `GET /api/me` → `{id, username}`
- `/api/spheres`, `/api/projects`, `/api/people`, `/api/tasks`, `/api/events`,
  `/api/calendars` — каркасы роутеров, эндпоинты в следующих WS.
- `/api/documents` — загрузка файлом или URL (`multipart`: ровно одно из
  `file`/`url`), список с фильтрами, карточка, `GET /{id}/content` (текст),
  `GET /{id}/file` (оригинал), `POST /{id}/reprocess`, `DELETE /{id}`.

## Документы

Оригиналы лежат в `ATLAS_STORAGE_DIR/<owner_id>/<document_id>.<ext>` и
отдаются только через авторизованный маршрут. Текст хранится в таблице
`chunks`; быстрый путь (MD/TXT/DOCX, PDF с текстовым слоем ≤20 стр.) даёт
`ready` сразу, сканы и большие PDF — `queued` с заданием `extract` /
`extract-full` для воркера.

Лимит загрузки (`ATLAS_MAX_UPLOAD_MB`) проверяется дважды: ранний 413 по
`Content-Length` до разбора multipart и стриминг на диск. Тело без
`Content-Length` (chunked) ранней проверкой не покрывается — его ограничивает
только стриминг при записи; ASGI-контроль chunked — follow-up.

Оригинал >20 МБ при наличии токена выгружается в Яндекс.Диск; локальная копия
при этом остаётся и отдаётся через `GET /{id}/file`. Если копии нет, `/file` и
`reprocess` отвечают 409 — скачивание из облака отдельный follow-up.
`reprocess` при незавершённом задании документа отвечает 409.

## Viewer

Если собран `viewer/dist` (React + Vite, сборка в отдельном WS), FastAPI
отдаёт его статикой на `/`; без сборки `GET /` возвращает JSON.

## Тесты

```bash
.venv\Scripts\python.exe -m unittest tests.test_app_auth tests.test_migrations -v
```

`test_migrations.py` проверяет миграцию на временном SQLite и, если найден
PostgreSQL (`PG_BIN` или `C:\Program Files\PostgreSQL\17\bin`), поднимает
временный кластер и прогоняет `alembic upgrade head` на нём; без PostgreSQL —
skip.
