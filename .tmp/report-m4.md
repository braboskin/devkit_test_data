# T-9F5FB3D3 — M4: напоминания и push (отчёт)

План: v3 утверждён владельцем 2026-11-22T08:17:20Z, v4 (replan: якорь RRULE-серий)
зарегистрирован как draft. Ветка `repo/atlas`: `devkit/T-9F5FB3D3` (от `main`
@ `2540bc5`), HEAD кода `4c48696`. Режим: AgentTeam, роли backend-engineer,
frontend-engineer, test-engineer; независимые гейты — отдельные роли.

## Что сделано

| WS | Роль | Результат | Коммит |
| --- | --- | --- | --- |
| WS1 | backend-engineer | миграция `0006_notifications` (notifications, push_subscriptions, notification_settings + unique/index), модели, `config` (VAPID/REMINDER_*), `push.py` (pywebpush, статусы sent/gone/failed/disabled, без секретов в логах), `reminders.py` (`dispatch_due`: события + задачи, окно 60 мин, dedupe, тихие часы, дневной лимит), daemon-thread планировщик в `main.py`, `test_migrations` (whitelist + downgrade) | `6f4faa4` |
| WS1-fix | backend-engineer | AB4: вхождение RRULE анкорится от `start_at` (`rrulestr(..., dtstart=start_at).after(now-remind-1s)`); в v3 формула давала `fire_at` на период вперёд | `ef7afdb` |
| WS2 | frontend-engineer | `sw.js` (`push`/`notificationclick`, кэш без изменений), типы в `api.ts`, `push.ts` (VAPID base64url, subscribe/unsubscribe), лента и бейдж в `Today.tsx`, блок «Уведомления» в `Settings.tsx` (+iOS-подсказка), поле «Напоминание, мин» в `Calendar.tsx`, README (VAPID/scheduler/iOS) | `53fb393` |
| WS3 | backend-engineer | `routers/notifications.py` (лента + read, 404/401), `routers/settings_notifications.py` (тихие часы/лимит HH:MM + 422, push-subscription GET/POST upsert/DELETE 204), тела новых маршрутов в `test_isolation` | `17e6f96` |
| WS4 | test-engineer | `tests/test_push.py` — 16 тестов AB2–AB13 (SQLite, фиктивный sender, инъекция `now`, без сети); `devkit.yaml` — `tests.test_push` в `unit-tests` (win/darwin/linux) | `dc8dc9c`, `0a3d5ac` (data) |
| интеграция | lead | push-payload: ключ `link` → `url`, чтобы совпасть с `sw.js` (находка LOW тестировщика; в M4 не проявлялась, но сломала бы ссылку в M5) | `4c48696` |

VAPID-пара сгенерирована ранее и лежит в `.secrets/atlas.env` (gitignored):
публичный ключ в API, приватный — только в env; в git/логи/план не попадает.
`requirements.txt` += `pywebpush>=2.5` (установлен в `.venv`, 2.5.0).

## Изменения

`repo/atlas` (20 файлов, +1910/−4): `app/backend/{models,config,main,push,reminders}.py`,
`app/backend/routers/{notifications,settings_notifications}.py`,
`alembic/versions/0006_notifications.py`, `requirements.txt`,
`viewer/public/sw.js`, `viewer/src/{api,push}.ts`, `viewer/src/pages/{Today,Settings,Calendar}.tsx`,
`README.md`, `tests/{test_push,test_migrations,test_isolation,__init__}.py`.
Data-репо: `devkit.yaml` (только строка `unit-tests`), `plans/T-9F5FB3D3/v{1..4}.md`,
`tasks/T-9F5FB3D3.md`, `docs/reports/T-9F5FB3D3.md`.

Вне scope — правок нет. Секретов в diff нет (`.secrets/` gitignored, ключи только env).

## Проверки

Код-ревизия `51e6cc8c…` (= `repo/atlas` HEAD `4c48696`). Имена — из профиля.

| Проверка | Команда | Exit | Доказательство | Check id |
| --- | --- | --- | --- | --- |
| `web-build` | `npm ci && npm run build` (viewer) | 0 | `npm_ci=0`, `build=0`, vite: `dist/assets/index-Ct4FgzPC.js 335.40 kB`, built in 195 ms | `CH-90a6d6f6fe71` |
| `unit-tests` (required) | `.venv\Scripts\python.exe -m unittest <35 модулей + tests.test_push>` | 0 | `Ran 335 tests`, `OK` (168 s) | `CH-0e4659716233` |
| `ingest-fixtures` | `.venv\Scripts\python.exe -m unittest tests.test_ingest.IngestTests.test_fixtures_processed` | 0 | `Ran 1 test`, `OK` | `CH-ea6feb28f362` |
| `schema-check` | `scripts\validate-schema.ps1` через powershell (temp PG) | 0 | `tables=17 views=10`, `Cleanup done.` | `CH-9c55949da41c` |

Точечно на том же HEAD: `tests.test_push` 16 тестов OK; `test_migrations` 4 OK
(SQLite + временный PostgreSQL, downgrade 0006); `test_isolation` 9 OK (401/404
по всем маршрутам OpenAPI); `test_events` 11 OK. Мутационная проверка
тестировщика: 10/10 внесённых дефектов (dedupe, окно, `dtstart`, закрытые задачи,
порядок, границы, тихие часы, лимит, 204, gone) ловятся тестами.

Не выполнено: S10 — реальный push в установленной PWA (нужно устройство и
браузер владельца); iOS 16.4+ — только документально.

## Sync (план ↔ acceptance ↔ факт)

| Пункт | Доказательство | Статус |
| --- | --- | --- |
| S1 миграция/модели | `0006_notifications`, `test_migrations` (SQLite+PG) | done |
| S2 push-обвязка | `push.py`, ключи в env, `enabled=false` без ключей | done |
| S3 ядро напоминаний | `reminders.py`, AB2–AB5/AB8/AB9/AB11 | done |
| S4 планировщик | lifespan-thread, env `ATLAS_REMINDER_SCAN_SEC`, тесты выключены | done |
| S5 API | 4 маршрута в OpenAPI, изоляция 401/404 | done |
| S6 тесты | `test_push.py`, профиль `unit-tests` | done |
| S7 viewer | SW, push.ts, Today/Settings/Calendar, `npm run build` | done |
| S8 документация | README: VAPID, scheduler, iOS | done |
| S9 проверки/сдача | check-события на одном codeSha, отчёт | done |
| S10 ручной push | требуется владелец | **не проверено** |
| AB1–AB15 | check-события + `test_push` + статические проверки | AB1–AB15 зелёные (S10 — часть A9, вынесено) |

`git status --porcelain` в `repo/atlas` — пусто; в data-репо — пусто. Коммиты
только в `devkit/T-9F5FB3D3`, force-push нет.

Разногласие с планом (устранено): v3 S3 давал `dtstart=after` → `fire_at` на
период вперёд (AB4 не выполнялся для `FREQ=DAILY`). Зарегистрирован план **v4**
(PL-a76ac28ab7) с якорем от `start_at`; правка техническая в рамках AB4,
комментарий в задаче `C-e0f19b4286`. Требует approve владельца (v3 уже approved).

## Риски

| # | Риск | Состояние |
| --- | --- | --- |
| R1 | Реальный Web Push (FCM/Mozilla) и iOS не проверялись | S10 за владельцем; деградация без ключей -> in-app лента |
| R2 | Тихие часы сравниваются с локальным временем сервера | допущение плана; tz-колонка — отдельная задача |
| R3 | Планировщик в процессе API, один воркер | unique dedupe защищает от дублей; при масштабировании — вынести сканер |
| R4 | `notifications` растёт без TTL | `ponytail:` в M4 не чистим; отдельная задача при объёме |
| R5 | `pywebpush` — новая зависимость | pinned `>=2.5`, ставится профилем `install-requirements`; откат — удалить строку |
| R6 | `userVisibleOnly`/permission отказан | UI показывает состояние и не падает (`pushSupported`, ошибки permission) |
| R7 | Гейты и `needs_review` не выставлены | нужны ролевые токены (owner): skeptic, test-engineer, backend-engineer; assignee reset, чтобы architect мог выдать architecture-гейт |
| R8 | План v4 в статусе draft | v3 approved; v4 — техническая коррекция, approve владельцем |

**Откат:** `ATLAS_REMINDER_SCAN_SEC=0` + рестарт (мгновенно); revert коммитов
`6f4faa4..4c48696` + `npm run build`; `alembic downgrade 0005_agent_calls`
(удаляет 3 таблицы; перед откатом после эксплуатации — `pg_dump`/`devkit backup`).
