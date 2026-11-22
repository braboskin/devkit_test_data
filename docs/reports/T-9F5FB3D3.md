---
id: R-d808fc0e01
type: report
title: "M4: напоминания и push (финал 589204c)"
task: T-9F5FB3D3
status: final
created_at: 2026-11-22T10:29:08.783Z
updated_at: 2026-11-22T10:29:08.783Z
---

# T-9F5FB3D3 — M4: напоминания и push (отчёт)

План: v3 утверждён владельцем 2026-11-22T08:17Z; v4/v5/v6 — технические
коррекции по итогам независимых ревью (draft, для гейта нужен approve v6).
Ветка `repo/atlas`: `devkit/T-9F5FB3D3` от `main` @ `2540bc5`, HEAD **`589204c`**.
Режим AgentTeam: backend-engineer, frontend-engineer, test-engineer + независимые
skeptic и test-engineer-verifier (read-only, без права правок).

## Что сделано

| Этап | Роль | Результат | Коммит |
| --- | --- | --- | --- |
| WS1 | backend-engineer | миграция `0006_notifications` (3 таблицы + unique/index), модели, `config` (VAPID/REMINDER_*), `push.py` (sent/gone/failed/disabled, без секретов), `reminders.py` (`dispatch_due`), daemon-thread планировщик, `test_migrations` | `6f4faa4` |
| WS1-fix | backend-engineer | RRULE: якорь серии от `start_at` (v3 терял серию) | `ef7afdb` |
| WS2 | frontend-engineer | `sw.js` push/notificationclick, типы `api.ts`, `push.ts`, лента+бейдж `Today.tsx`, блок уведомлений `Settings.tsx` (+iOS), поле напоминания `Calendar.tsx`, README | `53fb393` |
| WS3 | backend-engineer | `routers/notifications.py`, `routers/settings_notifications.py`, тела маршрутов в `test_isolation` | `17e6f96` |
| WS4 | test-engineer | `tests/test_push.py`, `devkit.yaml` += `tests.test_push` | `dc8dc9c`, `0a3d5ac` (data) |
| интеграция | lead | push-payload `link` → `url` | `4c48696` |
| rework 1 | backend ×2 / test | B1/B2/B3 (локальное время, окно RRULE), M1/M2 (валидация подписки, гонка upsert), тесты AB16/AB17 | `eb7dfc0`, `8eb4ba4`, `d9cb3d9` |
| rework 2 | backend ×2 | F1/F2 (нормализация хоста, локальный `read_at`), N4 (строгий base64url, `is_global`) | `6fbe2d2`, `643abc6` |
| rework 3 | backend / test | N3/N1 (последнее должное вхождение RRULE, aware→локальное настенное), тесты AB18 | `65e5a1c`, `8fc70db` |
| rework 4 | test | AB18 для предложений агента (`proposals._dt`), закрытие F1 | `589204c` |

**Ключевые решения:** одно правило времени — naive в БД = локальное настенное
время сервера; aware-вход конвертируется на границе (events/tasks/proposals/pm);
планировщик `datetime.now()`, `created_at/pushed_at/read_at` в той же шкале.
Дедуп — unique `(owner_id, dedupe_key)`. RRULE: последнее должное вхождение
(`rule.before(now+remind+1s)`, нижняя граница `now+remind−60м`) — sub-hourly
серии без отставания. Push-подписка: https-домен без localhost/.local/не-global
IP и userinfo (DNS-имена не резолвятся — потолок R14), ключи — строгий base64url
(p256dh 65 байт `0x04`, auth 16). Без VAPID-ключей push `disabled`, in-app работает.
VAPID-пара — в `.secrets/atlas.env` (gitignored), приватный ключ вне git/логов.

## Изменения

`repo/atlas` (24 файла): `app/backend/{models,config,main,push,reminders,pm}.py`,
`app/backend/routers/{notifications,settings_notifications,events,tasks}.py`,
`app/backend/agent/proposals.py`, `alembic/versions/0006_notifications.py`,
`requirements.txt` (`pywebpush>=2.5`), `viewer/public/sw.js`,
`viewer/src/{api,push}.ts`, `viewer/src/pages/{Today,Settings,Calendar}.tsx`,
`README.md`, `tests/{test_push,test_migrations,test_isolation,__init__}.py`.
Data-репо: `devkit.yaml` (только `tests.test_push`), `plans/T-9F5FB3D3/v1–v6.md`,
`tasks/T-9F5FB3D3.md`, `docs/reports/T-9F5FB3D3.md`.
Секретов в diff нет, файлов вне scope нет.

## Проверки

Код-ревизия `fc598978…` (= HEAD `589204c`). Имена — из профиля.

| Проверка | Exit | Доказательство | Check id |
| --- | --- | --- | --- |
| `web-build` (`npm ci && npm run build`) | 0 | npm_ci=0, build=0, dist built | `CH-e75b2efafc32` |
| `unit-tests` (required, 35 модулей + `tests.test_push`) | 0 | **Ran 354 tests, OK** (181 s) | `CH-5d9aee0cd78e` |
| `ingest-fixtures` | 0 | Ran 1 OK | `CH-edf1acc6120b` |
| `schema-check` | 0 | validate-schema.ps1, temp PG, exit 0 | `CH-bf14fccdde1b` |

Точечно: `tests.test_push` 35 OK (×3 подряд, не flaky); связка
`test_push+test_migrations+test_isolation+test_events+test_web_build` 70 OK.
Независимый verifier на `8fc70db` воспроизвёл полный профиль 353 OK, `test_push`
×5 OK; на финальном `589204c` добавлен один тест (`proposals` aware) — профиль
354 OK, проверено lead.

**Мутации (честно):** ранние раунды — 10/10 (WS4) и 8/8 (verifier), финальная
дельта — **6/9**: не ловятся `pm._naive_utc` (защитная, недостижимая ветка),
`proposals._dt` (закрыто тестом `589204c`, теперь ловится) и изолированное
снятие `ip.is_global` (маскируется TLD/IP-бэкстопом; снятие обоих ловится —
defense in depth). Артефакты мутаций — временные копии вне репо, не коммитились.

**Не проверено:** S10 — реальный push в установленной PWA и iOS 16.4+ (нужно
устройство владельца); downgrade 0006 на PostgreSQL (на SQLite покрыт);
таймзона сервера, отличная от Europe/Moscow; DNS-rebinding (потолок R14).

## Sync (план ↔ acceptance ↔ факт)

| Пункт | Доказательство | Статус |
| --- | --- | --- |
| S1–S11 плана | коммиты WS1–WS4 + rework 1–4 | done |
| AB1–AB18 | `tests.test_push` 35 тестов + check-события + статические проверки | зелёные |
| S10 / A9 «доставлено» | ручная приёмка владельца | **не проверено** |
| план v6 | registered `PL-d3883d5ff4`, status draft | ждёт approve владельца |
| карточка (scope, plan_version) | `plan_version: 3`, scope уже́ кода | **требует владельца (B4)** |

`git status --porcelain`: `repo/atlas` — пусто; data-репо — пусто. Коммиты
только в `devkit/T-9F5FB3D3`, force-push нет.

## Риски

| # | Риск | Состояние |
| --- | --- | --- |
| R1 | Реальный Web Push/iOS не проверялись | S10 за владельцем; без ключей — in-app |
| R2 | naïve = локальное время сервера | допущение 4; tz/UTC — отдельная задача |
| R3 | Планировщик в процессе API, один воркер | unique dedupe; при масштабировании вынести |
| R4 | RRULE-скан от `dtstart` линейно дорожает | R15: личный масштаб, кэш/лимит истории — отдельная задача |
| R5 | SSRF-потолок (DNS-имена не резолвятся) | R14; endpoint — домены push-сервисов |
| R6 | `notifications` растёт без TTL | `ponytail:` не чистим в M4 |
| R7 | `pywebpush` — новая зависимость | pin `>=2.5`; откат — строка requirements |
| R8 | AB17 scheduler-тест поднимает поток | 5+ прогонов стабильны (timing-based) |
| R9 | Гейты/`needs_review` не выставлены | нужны approve v6, scope карточки, assignee=owner, ролевые токены |
| R16 | События, созданные агентом через proposal, не несут `remind_minutes` (нет поля в `propose_create_event` и в `_apply_create_event`) → напоминание не включить | известно, вне AB M4; отдельная задача (агентские напоминания) |

**Откат:** `ATLAS_REMINDER_SCAN_SEC=0` + рестарт (мгновенно); revert коммитов
`6f4faa4..589204c` + `npm run build`; `alembic downgrade 0005_agent_calls`
(удаляет 3 таблицы; перед откатом после эксплуатации — `pg_dump`/`devkit backup`).
