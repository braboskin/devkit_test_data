# T-DD797EDB — бэкенд: миграции и эндпоинты под новый UI

## Что сделано

- Миграция `0009_ui_fields`: аддитивные колонки `spheres.color/icon/description`
  (цвет по умолчанию `#64748b`), `tasks.start_at/progress` (0), `projects.start_at`,
  `users.display_name/avatar_ref/timezone`, `people.photo_ref`; полный downgrade.
- API отдаёт новые поля: `UserOut`, `SphereOut`, `ProjectOut`, `TaskOut`,
  `PersonOut`. Запись: цвет/иконка/описание интереса, `start_at` проекта,
  `start_at`/`progress` задачи (null для `progress` запрещён, 0–100).
- Медиа: `core/media.py` нормализует картинку в PNG (square-fit для аватара и
  фото, max-edge для фона), лимит 8 МБ, MIME-allowlist, EXIF срезается
  перекодированием; файлы лежат в каталоге владельца (`core/storage.write_media`).
  Маршруты: `POST|GET /api/profile/avatar`, `POST|GET /api/profile/background`
  (ссылка в `user_profile.data.ui.background_ref`), `POST|GET
  /api/people/{person_id}/photo`. Чужой id — 404, плохой файл — 422.
- Счётчики карточек: `GET /api/spheres/{id}/summary` (проекты, задачи, done,
  люди, файлы, последняя активность) и `GET /api/projects/{id}/summary`.
- Глобальный поиск: `GET /api/search?scope=all` — группы tasks, projects,
  spheres, people, documents, chats; лимит на группу, `owner_id` в каждом
  запросе, документы — через существующий гибридный поиск.
- `viewer/src/shared/api`: `uploadAvatar`, `uploadBackground`,
  `uploadPersonPhoto`, `avatarSrc`, `backgroundSrc`, `personPhotoSrc`,
  `searchAll`, типы `SearchGroup*`, новые поля в `Sphere`/`Project`/`Task`.
- Тесты: медиа (auth, people), summary (spheres/projects), `scope=all` с
  изоляцией, матрица `/api/*` в `test_isolation` расширена на новые маршруты
  (401 без сессии и 404 по чужому id, multipart-загрузки через `files=`).

## Изменения

Коммиты ветки `devkit/T-DD797EDB`:

- `2adc417` — миграция 0009 и поля UI в API.
- `98ccef0` — аватар, фото человека и фон профиля.
- `6bb8e77` — summary, глобальный поиск и запись UI-полей.
- `cdc29d4` — изоляция и 401 для медиа-маршрутов.

Файлы: `alembic/versions/0009_ui_fields.py`, `app/backend/core/{media,storage}.py`,
`app/backend/features/{auth,people,spheres,projects,tasks,search}`,
`app/backend/schemas.py`, `viewer/src/shared/api/index.ts`, тесты
`test_app_auth.py`, `test_people.py`, `test_spheres_projects.py`,
`test_search.py`, `test_isolation.py`.

## Проверки

| Проверка | Команда | Результат |
|---|---|---|
| unit-tests | `python -m unittest discover -s tests` | exit 0, Ran 439 tests, OK (256 с) |
| lint-python | `python -m ruff check .` | exit 0, «All checks passed» |
| typecheck-python | `python -m mypy` | exit 0, 145 файлов без ошибок |
| arch-python | `python -m unittest tests.test_architecture` | exit 0 (в составе unit-tests и отдельно) |
| schema-check | `scripts/validate-schema.ps1` | exit 0: tables=17 views=10, CREATE/INSERT всё применилось |
| web-build (вне списка задачи) | `npm run build` | exit 0, 1.01 MB JS / 311 KB gzip |

`schema-check` локально падает на порту 55432: Windows исключил диапазон
55429–55528 из bind. Проверка выполнена той же копией скрипта на свободном порту
56000 (подмена только порта, SQL тот же) — `PSQL_EXIT=0`, кластер поднят и
погашен, временный скрипт удалён.

## Риски

- `scope=all` использует `ILIKE`: на SQLite (dev-тесты) Unicode-регистр не
  складывается, поэтому тест ищет с тем же регистром; на PostgreSQL ILIKE
  работает. Для точного поиска на SQLite — FTS5 или Python-фильтр.
- Медиа хранится локально в каталоге владельца; при переезде на внешнее
  хранилище `storage.write_media` — единственная точка замены.
- Ресайз идёт в памяти запроса; для очень больших фонов выносить в фоновую
  задачу (помечено в `core/media.py`).
- Ссылка на фон живёт в `user_profile.data.ui.background_ref`; профиль
  перезаписывается целиком через `PUT /api/profile` — клиент обязан сохранять
  `ui` при полной записи.
- Проверки на новом codeSha не записывались повторно после merge-коммита S0:
  задача шла от чистого `main`, конфликтов не было.
