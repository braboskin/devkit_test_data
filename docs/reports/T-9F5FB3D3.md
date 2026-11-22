---
id: R-d808fc0e01
type: report
title: "M4: напоминания и push (финал)"
task: T-9F5FB3D3
status: final
created_at: 2026-11-22T10:06:28.274Z
updated_at: 2026-11-22T10:06:28.274Z
---

# T-9F5FB3D3 — M4: напоминания и push (отчёт)

План: v3 утверждён владельцем 2026-11-22T08:17Z; v4/v5/v6 — технические
коррекции по итогам независимых ревью (все draft, требует approve v6).
Ветка `repo/atlas`: `devkit/T-9F5FB3D3` от `main` @ `2540bc5`, HEAD **`8fc70db`**.
Режим AgentTeam: backend-engineer, frontend-engineer, test-engineer + независимые
skeptic и test-engineer-verifier (read-only).

## Что сделано

| Этап | Роль | Результат | Коммит |
| --- | --- | --- | --- |
| WS1 | backend-engineer | миграция `0006_notifications` (notifications, push_subscriptions, notification_settings + unique/index), модели, `config` (VAPID/REMINDER_*), `push.py` (pywebpush: sent/gone/failed/disabled, без секретов в логах), `reminders.py` (`dispatch_due`), daemon-thread планировщик, `test_migrations` (whitelist + downgrade) | `6f4faa4` |
| WS1-fix | backend-engineer | AB4: якорь RRULE от `start_at` (в v3 формула теряла серию) | `ef7afdb` |
| WS2 | frontend-engineer | `sw.js` push/notificationclick, типы в `api.ts`, `push.ts` (VAPID base64url, subscribe/unsubscribe), лента+бейдж в `Today.tsx`, блок «Уведомления» в `Settings.tsx` (+iOS), поле «Напоминание, мин» в `Calendar.tsx`, README | `53fb393` |
| WS3 | backend-engineer | `routers/notifications.py` (лента + read, 404/401), `routers/settings_notifications.py` (тихие часы/лимит, push-subscription), тела новых маршрутов в `test_isolation` | `17e6f96` |
| WS4 | test-engineer | `tests/test_push.py` (AB2–AB13, затем AB16–AB18), `devkit.yaml` += `tests.test_push` | `dc8dc9c`, `0a3d5ac` (data) |
| интеграция | lead | payload `link` → `url` (совпадение с `sw.js`) | `4c48696` |
| rework 1 | backend-engineer / backend-engineer / test-engineer | B1/B2/B3: локальное настенное время планировщика, окно RRULE; M1/M2: валидация подписки и гонка upsert; тесты AB16/AB17 | `eb7dfc0`, `8eb4ba4`, `d9cb3d9` |
| rework 2 | backend-engineer / backend-engineer | F1/F2: нормализация хоста подписки, локальный `read_at`; N4: строгий base64url + `ip.is_global` | `6fbe2d2`, `643abc6` |
| rework 3 | backend-engineer / test-engineer | N3/N1: последнее должное вхождение RRULE (sub-hourly без отставания), aware-вход → локальное настенное; тесты AB18 | `65e5a1c`, `8fc70db` |

**Ключевые решения:** одно правило времени — naive в БД = локальное настенное
время сервера; aware-вход конвертируется на границе (events/tasks/proposals/pm);
планировщик `datetime.now()`; `created_at/pushed_at/read_at` уведомлений в той же
шкале. Дубли исключает unique `(owner_id, dedupe_key)`. Push-подписка: endpoint
только https-домен (без localhost/.local/не-global IP, без userinfo; DNS-имена не
резолвятся — потолок R14), ключи — строгий base64url (p256dh 65 байт с 0x04,
auth 16). Нет VAPID-ключей → push `disabled`, in-app работает.

VAPID-пара сгенерирована и лежит в `.secrets/atlas.env` (gitignored):
публичный ключ в API, приватный — только env; в git/план/логи не попадает.
`requirements.txt` += `pywebpush>=2.5` (установлен 2.5.0 в `.venv`).

## Изменения

`repo/atlas` (24 файла): `app/backend/{models,config,main,push,reminders,pm}.py`,
`app/backend/routers/{notifications,settings_notifications,events,tasks}.py`,
`app/backend/agent/proposals.py`, `alembic/versions/0006_notifications.py`,
`requirements.txt`, `viewer/public/sw.js`, `viewer/src/{api,push}.ts`,
`viewer/src/pages/{Today,Settings,Calendar}.tsx`, `README.md`,
`tests/{test_push,test_migrations,test_isolation,__init__}.py`.
Data-репо: `devkit.yaml` (только `tests.test_push`), `plans/T-9F5FB3D3/v1–v6.md`,
`tasks/T-9F5FB3D3.md`, `docs/reports/T-9F5FB3D3.md`.

Секретов в diff нет (`.secrets/` gitignored). Файлов вне scope — нет.

## Проверки

Код-ревизия `4eb82bca…` (= `repo/atlas` HEAD `8fc70db`). Имена — из профиля.

| Проверка | Команда | Exit | Доказательство | Check id |
| --- | --- | --- | --- | --- |
| `web-build` | `npm ci && npm run build` (viewer) | 0 | npm_ci=0, build=0, vite dist built | `CH-5c3487742058` |
| `unit-tests` (required) | python -m unittest (35 модулей + `tests.test_push`) | 0 | **Ran 353 tests, OK** (178 s) | `CH-de66e14c0366` |
| `ingest-fixtures` | python -m unittest fixtures_processed | 0 | Ran 1 OK | `CH-7070d79aec6c` |
| `schema-check` | scripts\validate-schema.ps1 (temp PG) | 0 | exit 0, Cleanup done | `CH-e4a99f6d5290` |

Точечно на `8fc70db`: `tests.test_push` 34 OK (×2 без флейков); связка
`test_push+test_migrations+test_isolation+test_events+test_web_build` 69 OK.
Независимая проверка (test-engineer, read-only): полный профиль 353 OK,
`test_push` ×5 OK, мутации 8/8 пойманы (на `d9cb3d9`), 8/8 — на предыдущем
кандидате. Независимое ревью (skeptic): два раунда с блокерами B1–B4/N3,
все закрыты в коде, кроме B4 (план/card — действие владельца).
Мутационные артефакты — временные копии вне репо (не коммитились).

S10 (реальный push в установленной PWA, iOS 16.4+) — **не выполнено**, нужно
устройство владельца. PG-ветка `test_migrations` проверяет upgrade + схему;
**downgrade 0006 на PostgreSQL не покрыт** (на SQLite — покрыт).

## Sync (план ↔ acceptance ↔ факт)

| Пункт | Доказательство | Статус |
| --- | --- | --- |
| S1 миграция/модели | `0006_notifications`, `test_migrations` (SQLite + PG upgrade) | done |
| S2 push | `push.py`, env VAPID, `disabled` без ключей | done |
| S3 напоминания | `reminders.py`, AB2–AB5/AB8/AB9/AB11/AB18 | done |
| S4 планировщик | lifespan-thread, local `datetime.now()`, тест старт/стоп | done |
| S5 API | 4 маршрута, валидация (AB16), гонка upsert | done |
| S6 тесты | `test_push.py` 34 теста, профиль `unit-tests` | done |
| S7 viewer | SW, push.ts, Today/Settings/Calendar, `npm run build` | done |
| S8 документация | README: VAPID, scheduler, iOS | done |
| S9 проверки/сдача | 4 check на одном codeSha, отчёт | done |
| S10 ручной push | требуется владелец | **не проверено** |
| S11 время на границе | events/tasks/proposals/pm, AB18 | done |
| AB1–AB18 | check-события + `test_push` + статические проверки | AB1–AB18 зелёные, кроме S10 (часть A9) |

`git status --porcelain`: `repo/atlas` — пусто; data-репо — пусто. Коммиты только
в `devkit/T-9F5FB3D3`; force-push нет.

**Расхождения с утверждённым планом v3 и их судьба:** v4 — якорь RRULE;
v5 — локальное время, окно RRULE, валидация подписки, гонка upsert;
v6 — последнее должное вхождение (sub-hourly), aware-вход, строгий base64url,
`is_global`. Все зафиксированы в новых версиях (не правкой утверждённой).
Для гейтов нужен **approve v6** и приведение карточки (scope, `plan_version`) —
пункт B4, действие владельца.

## Риски

| # | Риск | Состояние |
| --- | --- | --- |
| R1 | Реальный Web Push/iOS не проверялись | S10 за владельцем; без ключей — in-app |
| R2 | Время: naïve = локальное сервера; на другой TZ сдвинется | допущение 4; tz/UTC — отдельная задача |
| R3 | Планировщик в процессе API, один воркер | unique dedupe; при масштабировании вынести |
| R4 | RRULE-скан перебирает серию от `dtstart` (линейно) | личный масштаб; кэш/лимит истории — отдельная задача (R15) |
| R5 | SSRF-потолок: DNS-имена не резолвятся, public IP-литералы отклоняются | R14; endpoint — домены push-сервисов |
| R6 | `notifications` растёт без TTL | `ponytail:` не чистим в M4 |
| R7 | `pywebpush` — новая зависимость | pin `>=2.5`, профиль `install-requirements`; откат — строка из requirements |
| R8 | AB17 scheduler-тест поднимает поток (тайминг) | 5 прогонов стабильны; помечен как timing-based |
| R9 | Гейты/`needs_review` не выставлены | нужны ролевые токены и assignee=owner (B4) |

**Откат:** `ATLAS_REMINDER_SCAN_SEC=0` + рестарт (мгновенно); revert коммитов
`6f4faa4..8fc70db` + `npm run build`; `alembic downgrade 0005_agent_calls`
(удаляет 3 таблицы; перед откатом после эксплуатации — `pg_dump`/`devkit backup`).
