---
id: R-d808fc0e01
type: report
title: "M4: напоминания и push (финал 210f274)"
task: T-9F5FB3D3
status: final
created_at: 2026-11-22T17:29:55.342Z
updated_at: 2026-11-22T17:29:55.342Z
---

# T-9F5FB3D3 — M4: напоминания и push (финальный отчёт)

Задача: M4 «напоминания и push» (эпик E-46E212B4, ТЗ `TZ-52EEACD7` v0.8,
acceptance A6, A9). План: **v6 approved** (`PL-d3883d5ff4`, владелец,
2026-11-22T10:30Z); v4–v6 — технические коррекции по итогам независимых ревью.
Ветка `repo/atlas`: `devkit/T-9F5FB3D3` (31 коммит от `main` @ `2540bc5`),
HEAD **`210f274`**, codeSha **`4ad890ce`**. Статус: **`needs_review`**, все
4 обязательных гейта `approve`, 4 проверки профиля `passed` — на одном codeSha.

## Что сделано

| Этап | Роль | Результат | Коммиты |
| --- | --- | --- | --- |
| WS1 ядро | backend-engineer | миграция `0006_notifications` (notifications, push_subscriptions, notification_settings + unique/index), модели, `config`, `push.py` (pywebpush: sent/gone/failed/disabled, без секретов в логах), `reminders.py` (`dispatch_due`), daemon-thread планировщик, `test_migrations` | `6f4faa4`, `ef7afdb` |
| WS2 viewer | frontend-engineer | `sw.js` push/notificationclick, `api.ts`, `push.ts` (VAPID base64url, subscribe/unsubscribe), лента+бейдж на «Сегодня», блок «Уведомления» в настройках (+iOS), поле «Напоминание, мин» в календаре, README | `53fb393` |
| WS3 API | backend-engineer | `routers/notifications.py` (лента+read, 404/401), `routers/settings_notifications.py` (тихие часы/лимит, push-subscription), матрица изоляции | `17e6f96` |
| WS4 тесты | test-engineer | `tests/test_push.py` (AB2–AB18), `devkit.yaml` += `tests.test_push` | `dc8dc9c`, `0a3d5ac` |
| интеграция | lead | payload `link` → `url`; единая шкала времени; финальные guard'ы (см. rework) | `4c48696`, `cba511d`, `5c45573` |
| rework 1 | backend×2 / test | локальное настенное время, окно RRULE, валидация подписки + гонка upsert, тесты AB16/AB17 | `eb7dfc0`, `8eb4ba4`, `d9cb3d9` |
| rework 2 | backend×2 | нормализация хоста, локальный `read_at`, строгий base64url + `is_global` | `6fbe2d2`, `643abc6` |
| rework 3 | backend / test | последнее должное вхождение RRULE (sub-hourly), aware-вход → локальное настенное, тесты AB18 | `65e5a1c`, `8fc70db` |
| rework 4–6 | backend / test | валидация RRULE с dtstart, семантика частей/дубли/BY, guard сканера и expand, инвертированное окно, глобальный top-N и cap 500 | `5a5e624`, `6fdeb4c`, `7adffab`, `15bf02b`, `494b7d8`, `f0b475f` и тесты |
| rework 7–8 | backend / test | aware-`UNTIL` безусловно 422, эффективное правило задачи, BY-множители (`BYWEEKNO/BYYEARDAY/BYSETPOS`), потоковый expand, безусловный cap/sort | `7adffab`, `15bf02b`, `5c45573`, `210f274` и тесты |

**Ключевые решения:**

- **Время:** naive в БД = локальное настенное время сервера; aware-вход
  конвертируется на границе (`astimezone().replace(tzinfo=None)`), aware-`UNTIL`
  отвергается (422); планировщик `datetime.now()`, `created_at/pushed_at/read_at`
  уведомлений в той же шкале.
- **Напоминания:** события (за `remind_minutes`, включая повторения — «последнее
  должное вхождение» серии от `start_at`, sub-hourly без отставания) и задачи
  (в момент `due_at`); окно догона 60 мин; идемпотентность через unique
  `(owner_id, dedupe_key)`; тихие часы и дневной лимит push не отключают in-app;
  push после коммита INSERT, `gone` удаляет подписку.
- **RRULE-защита:** семантическая валидация (INTERVAL/COUNT ≥1, дубли частей,
  диапазоны BY, невыполнимые `BYMONTH×BYMONTHDAY`), density-guard с BY-множителями
  и потолком 50k — hostile/legacy-строки сканер и expand пропускают за <0.1 с,
  без зависаний; expand: инвертированное окно → 422, глобальный top-500 с
  сортировкой для всех строк.
- **Push:** Web Push (VAPID ES256 + aes128gcm) через `pywebpush`; без ключей —
  `disabled`, in-app работает. Подписка: https-домен без userinfo/localhost/
  .local/не-global IP-литералов (в т.ч. «почти-IP» и CGNAT), ключи — строгий
  base64url (p256dh 65 байт `0x04`, auth 16). DNS-имена не резолвятся (потолок
  R14). Гонка upsert обрабатывается (`IntegrityError` → update).
- **VAPID-пара** сгенерирована и лежит в `.secrets/atlas.env` (gitignored);
  приватный ключ не попадает в git/логи/API. В git — только имена переменных.

## Изменения

`repo/atlas`: **24 файла, +3718/−52** (от `2540bc5`).
`app/backend/{models,config,main,push,reminders,pm}.py`,
`app/backend/routers/{notifications,settings_notifications,events,tasks}.py`,
`app/backend/agent/proposals.py`, `alembic/versions/0006_notifications.py`,
`requirements.txt` (`pywebpush>=2.5`), `viewer/public/sw.js`,
`viewer/src/{api,push}.ts`, `viewer/src/pages/{Today,Settings,Calendar}.tsx`,
`README.md`, `tests/{test_push,test_migrations,test_isolation,__init__}.py`.

Data-репо: `devkit.yaml` (только `tests.test_push` в `unit-tests`),
`plans/T-9F5FB3D3/v1–v6.md`, `tasks/T-9F5FB3D3.md`,
`docs/reports/T-9F5FB3D3.md`. Секретов в diff нет, файлов вне scope нет.

**Отклонение от карточки (принято владельцем):** `scope` карточки
(`app/backend/**`, `tests/test_push*.py`) устарел; devkit 0.1.0 не поддерживает
редактирование scope существующей задачи (нет `task update` в CLI, нет
PATCH/PUT задачи в web, `updateTask()` не вызывается). Источник истины — план v6
(см. комментарий `C-d6851b155c`).

## Проверки

Код-ревизия `4ad890ce` (= HEAD `210f274`), `git status` чист в обоих репозиториях.

| Проверка | Команда | Exit | Доказательство | Check id |
| --- | --- | --- | --- | --- |
| `web-build` | `npm ci && npm run build` (viewer) | 0 | npm_ci=0, build=0, vite dist | `CH-aaec661324d7` |
| `unit-tests` (required) | python -m unittest (35 модулей + `tests.test_push`) | 0 | **Ran 370 tests, OK** (196 с), `test_push` 51 | `CH-7afe2b26e559` |
| `ingest-fixtures` | fixtures_processed | 0 | Ran 1 OK | `CH-37b0f25c0af3` |
| `schema-check` | `validate-schema.ps1` (temp PG) | 0 | exit 0, Cleanup done | `CH-fabfd21aac79` |

Независимые проверки: `test_push` ×3 без флейков; `test_push+migrations+
isolation+events+tasks` — 84 OK; scheduler-тест ×5 стабилен; `alembic
upgrade/downgrade 0006` на SQLite — ровно 3 таблицы; мутационные проверки по
раундам (финальные: инвертированное окно, cap/sort, BY-множители, aware-UNTIL,
эффективный task-rrule — каждая ловится регресс-тестом).

**Не проверено:** S10 (реальная доставка push в установленной PWA, iOS 16.4+ —
нужно устройство владельца), `downgrade 0006` на PostgreSQL (SQLite покрыт),
сервер в таймзоне ≠ Europe/Moscow, DNS-rebinding (потолок R14).

## Гейты (независимые роли, все `valid` на `4ad890ce`)

| Гейт | Роль | Вердикт | Id |
| --- | --- | --- | --- |
| `code` | backend-engineer | approve | `G-7a827bba7c8e` |
| `test` | test-engineer | approve | `G-4280de2368a9` |
| `architecture` | architect | approve | `G-15c57bf375ec` |
| `security` | skeptic | approve | `G-03cdef2a1df0` |

Ревью шло раундами: закрыты B1–B4 (UTC/время, RRULE-якорь/окно, план/карточка),
M1–M2 (валидация подписки, гонка upsert), N1–N4 (aware-вход, `read_at`, дубли
RRULE, base64/is_global), затем RRULE-зависания (INTERVAL=0, дубли, BY-каверзы),
инвертированное окно expand (CPU-DoS) и голодание выдачи плотной серией.

## Sync (план ↔ acceptance ↔ факт)

| Пункт | Доказательство | Статус |
| --- | --- | --- |
| S1–S11 плана v6 | коммиты WS1–WS4 + rework | done |
| AB1–AB18 | `tests.test_push` 51 тест + check-события + статические проверки | зелёные |
| A6 (напоминание in-app/push) | AB2–AB5, AB8, AB17 | done (S10 — ручная доставка) |
| A9 (подписка/доставка/iOS) | AB10–AB13, AB16, README | код/доки done, доставка — S10 |
| A13 (проверки профиля) | 4 check на одном codeSha | done |
| план v6 / карточка | v6 approved; scope карточки — принятое отклонение | done/принято |
| S10 | ручная приёмка владельца | **не проверено** |

## Риски

| # | Риск | Состояние |
| --- | --- | --- |
| R1 | Реальная доставка push (FCM/Mozilla/Apple), iOS 16.4+ | S10 за владельцем; без ключей push `disabled`, in-app работает |
| R2 | Планировщик в процессе API, один воркер | unique dedupe; при масштабировании вынести сканер |
| R3 | RRULE: потолок плотности 50k + BY-множители (cap 10k) | осознанные false-negatives очень старых/плотных серий (warning, пропуск) и возможные false-positives фильтрующих BY; R15 |
| R4 | `_AWARE_UNTIL` не ловит offset без минут (`+03`) при `dtstart=None` | задача без `due_at` может сохранить такое правило; `next_occurrence → None`, без зависания; follow-up |
| R5 | naive = локальное настенное время сервера (R13) | DST/перенос сервера/другие TZ — отдельная задача |
| R6 | SSRF-потолок: DNS-имена подписки не резолвятся (R14) | private/«почти-IP»/CGNAT/userinfo блокируются; DNS-rebinding — отдельная задача |
| R7 | События из agent-proposals не несут `remind_minutes` (R16) | вне AB M4; отдельная задача на напоминания из предложений агента |
| R8 | `notifications` растёт без TTL | `ponytail:` не чистим в M4; очистка — отдельная задача |
| R9 | `pywebpush` — новая зависимость | pin `>=2.5`, ставится профилем `install-requirements`; откат — удалить строку |
| R10 | scheduler-тест поднимает поток (тайминг) | 5+ прогонов стабильны; помечен как timing-based |
| R11 | Отчёт/план под rework | отчёт обновлён на финал; план v3 superseded, v6 approved |

**Откат:** `ATLAS_REMINDER_SCAN_SEC=0` + рестарт (мгновенно, напоминания не
создаются); revert коммитов `6f4faa4..210f274` + `npm run build`;
`alembic downgrade 0005_agent_calls` (удаляет 3 таблицы; перед откатом после
эксплуатации — `pg_dump`/`devkit backup` и согласие владельца).
