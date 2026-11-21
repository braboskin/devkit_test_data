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
| `ATLAS_MAX_UPLOAD_MB` | `100` — лимит загружаемого файла; тело запроса ограничено `ATLAS_MAX_UPLOAD_MB` + 1 МБ (multipart-обвязка) |
| `ATLAS_WORKER_LEASE_MINUTES` | `30` — сколько `running` задание считается живым до перезахвата воркером |
| `ATLAS_WORKER_HEARTBEAT_SECONDS` | `60` — период heartbeat ПК-воркера, продлевающего lease во время извлечения |
| `ATLAS_FERNET_KEY` | ключ Fernet (base64, 32 байта) для шифрования токенов интеграций в `integrations.token_enc`; без него `/api/settings/yadisk` отвечает 503 |
| `YANDEX_CLIENT_ID` | OAuth-приложение Яндекса (кнопка «Подключить Яндекс.Диск») |
| `YANDEX_CLIENT_SECRET` | секрет OAuth-приложения (только env, не в БД/UI) |
| `YANDEX_REDIRECT_URI` | `http://127.0.0.1:8000/api/settings/yadisk/callback` по умолчанию |
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
  `GET /{id}/file` (оригинал), `POST /{id}/reprocess`, `POST /{id}/reindex`
  (повтор индексации владельцем), `DELETE /{id}`.
- `/api/worker/claim`, `/api/worker/jobs/{id}/{heartbeat,file,complete,fail}` —
  протокол ПК-воркера (`Authorization: Bearer <worker-token>`);
  `/api/settings/worker-token`, `/api/settings/worker-token` (DELETE).
- `/api/settings/yadisk` — ручной токен (fallback), `GET .../authorize`,
  `GET .../callback` — OAuth Яндекс.Диска.

## Документы

Оригиналы лежат в `ATLAS_STORAGE_DIR/<owner_id>/<document_id>.<ext>` и
отдаются только через авторизованный маршрут. Текст хранится в таблице
`chunks`; быстрый путь (MD/TXT/DOCX, PDF с текстовым слоем ≤20 стр.) даёт
`ready` сразу, сканы и большие PDF — `queued` с заданием `extract` /
`extract-full` для воркера.

Лимит загрузки (`ATLAS_MAX_UPLOAD_MB`) ограничен на уровне ASGI нативным
`FastAPI(max_body_size=...)`: это `ATLAS_MAX_UPLOAD_MB` + 1 МБ на multipart.
Лимит действует и для тела без `Content-Length` (chunked) — 413 до разбора
формы; дополнительный рубеж — стриминг на диск (`storage.save_stream`).

Оригинал >20 МБ при наличии токена выгружается в Яндекс.Диск; локальная копия
при этом остаётся. Если копии нет, `/file` и `reprocess` скачивают облачный
оригинал в `ATLAS_STORAGE_DIR`; без токена/при сбое — 409.
`reprocess` при незавершённом задании документа отвечает 409.

URL-приём защищён от SSRF: хост резолвится до запроса, все адреса обязаны быть
публичными (private/loopback/link-local/NAT64 отсекаются), TCP-коннект идёт на
проверенный IP, Host/SNI остаются исходными, редиректы не читаются
автоматически (каждый хоп проверяется заново).

## Воркер ПК

```bash
$env:ATLAS_WORKER_TOKEN = "..."
.venv\Scripts\python.exe scripts\worker.py --once
.venv\Scripts\python.exe scripts\worker.py --interval 10 --concurrency 2
```

`--concurrency N` — N параллельных claim-циклов (один токен = один владелец;
для владельца допускается одно `running` задание). `claim` возвращает
`job.attempts` — lease-generation: `heartbeat`, `complete` и `fail` передают
его в теле, сервер сверяет `status='running' AND attempts=:attempts` (иначе
409), поэтому старый воркер после перезахвата не допишет результат. Пока идёт
извлечение, воркер шлёт `heartbeat` каждые `ATLAS_WORKER_HEARTBEAT_SECONDS`
(по умолчанию 60 с) — он продлевает `started_at`. Задание, висящее `running`
дольше `ATLAS_WORKER_LEASE_MINUTES`, возвращается в очередь (reclaim не
инкрементирует `attempts` — это делает следующий `claim`); после трёх попыток
помечается `failed` с ошибкой `worker timeout`. Reclaim атомарный
(`UPDATE ... WHERE status='running' AND started_at < cutoff`, rowcount=1),
поэтому конкурентный `complete`/`claim` не перетирается. Ошибки воркера
передаются категорией (`extract_failed`, `unsupported_format`, `too_large`,
`timeout`, `cancelled`) — произвольный текст в `document.error` не пишется.

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
