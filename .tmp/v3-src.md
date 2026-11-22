---
task_id: T-9F5FB3D3
version: 3
status: approved
created_by: agent:T-9F5FB3D3/architect
created_at: 2026-11-22T08:15:37.533Z
approved_by: owner
approved_at: 2026-11-22T08:17:20.363Z
---

# M4: напоминания и push

Черновик плана M4. Эпик E-46E212B4, ТЗ `TZ-52EEACD7` v0.8, M1–M3 выпущены
(`main` @ `2540bc5`), зависимость `T-B317AFAE` выполнена. Старт кода — после
регистрации версии плана и approve владельцем.

## Контекст

**Что уже есть (проверено по коду `repo/atlas` на `main` @ `2540bc5`):**

- События: `Event.remind_minutes` есть (`app/backend/models.py:228`),
  `EventIn`/`EventPatch` валидируют `ge=0`
  (`app/backend/routers/events.py:38,51`), но значение нигде не используется:
  планировщика напоминаний нет. В форме события
  (`viewer/src/pages/Calendar.tsx`) поля напоминания нет.
- Задачи: `Task.due_at` есть (`routers/tasks.py`), напоминаний нет; закрытые
  статусы — `pm.CLOSED_STATUSES`; повторения — `pm.next_occurrence`,
  `pm.validate_rrule` (готовые helper-ы, новые не пишем).
- Миграции 0001–0005 (`alembic/versions/`). `tests/test_migrations.py:21`
  держит whitelist `TABLES` — новая таблица без правки теста валит
  `unit-tests`. `schema-check` валидирует legacy-схему `docs/SCHEMA.md` (kb) и
  схему приложения не покрывает.
- Изоляция: `tests/test_isolation.py:194` требует валидное тело в `_body` для
  каждого маршрута не-GET/DELETE из OpenAPI; новый маршрут без записи в словарь
  валит тест. Аноним → 401 и чужой id → 404 проверяются автоматически.
- PWA: `viewer/public/sw.js` — только кэш, обработчиков `push`/
  `notificationclick` нет; SW регистрируется в `viewer/src/main.tsx` (только
  PROD); есть `manifest.webmanifest`, `offline.html`.
- API: роутеры подключаются автоматически (`main.py:132`), сессия —
  `auth.current_user`; `user_profile.data` перезаписывается `PUT /api/profile`
  целиком — настройки уведомлений там хранить нельзя.
- Профиль: `unit-tests` (required, явный список модулей в `devkit.yaml`),
  `web-build`, `ingest-fixtures`, `schema-check`; `viewer/dist` в `.gitignore`,
  а `test_web_build` читает собранный dist → порядок `web-build` →
  `unit-tests` обязателен.

**Цель:** пользователь получает напоминание о событии (за N минут, включая
повторяющиеся) и о задаче (в момент `due_at`) — всегда в in-app ленте и web
push при подписке; настраиваются категория, тихие часы и лимит push в день;
ограничение iOS задокументировано. Acceptance: A6 (напоминание), A9; FR-9,
FR-12.

**Требование → шаг → проверка:**

| Требование | Шаги | Проверки |
| --- | --- | --- |
| A6 (напоминание события) | S1, S3, S4, S7 | AB2–AB4, AB6, AB12, S10 |
| A9 (push в PWA, iOS) | S1, S2, S5, S7, S8 | AB8–AB12, AB13, S10 |
| FR-12 (лента, категории, тихие часы, отписка) | S5, S7 | AB6–AB10 |
| FR-9 (напоминание за N минут) | S3, S7 | AB2–AB4 |
| A13 (проверки профиля) | S1–S9 | AB14 |

**Принятые допущения:**

1. Web Push — `pywebpush` (VAPID ES256 + aes128gcm). **Ключи сгенерированы
   2026-11-22** и лежат в `.secrets/atlas.env` (gitignored, `start-atlas.ps1`
   экспортирует все переменные файла):
   `ATLAS_VAPID_PUBLIC_KEY=BCGifmqJXHemx6hKBAp9le4VXd3nbKMQhzJoim26BVNs6PxwvQrGgG7zF24UroMrzDzQJFyztvmX182SqgOmTps`
   (публичный, 65 байт base64url), `ATLAS_VAPID_PRIVATE_KEY` (только в файле —
   в план, логи и API не попадает), `ATLAS_VAPID_SUBJECT=mailto:admin@example.com`.
   Пара проверена (публичный ключ восстанавливается из приватного). Нет
   ключей → push выключен, in-app работает (деградация, не 503).
2. Настройки уведомлений — отдельная таблица `notification_settings`, не
   `user_profile.data` (см. перезапись `PUT /api/profile`).
3. Задача напоминает в момент `due_at` без своего offset; у событий —
   существующий `remind_minutes`. `tasks.remind_minutes` — отдельная миграция,
   если понадобится (в коде помечено `ponytail:`).
4. Тихие часы сравниваются с локальным временем сервера (в БД UTC naive);
   колонка tz — когда появятся пользователи в других зонах.
5. Планировщик — daemon-thread в процессе API, шаг `ATLAS_REMINDER_SCAN_SEC`
   (default 30, `0` — выключен); тесты ставят `0` в `tests/__init__.py`.
   Запуск — один процесс uvicorn; от дублей защищает уникальный индекс.
6. Окно «не спамить после простоя» — 60 минут (`REMINDER_LATENESS_MIN`);
   `fire_at` старше — пропуск.
7. Push — только после успешного INSERT уведомления; дедуп по
   `(owner_id, dedupe_key)`.
8. iOS: push только для установленной PWA (iOS 16.4+), in-app — основной
   канал; документируется в README.
9. `link` в уведомлении хранится (`/`), deep-link в M4 не делается: табы
   `App.tsx` не URL-роутинг.

**Открытые вопросы к владельцу (блокирующих нет):**

- **VAPID — решено (2026-11-22).** Пара сгенерирована и лежит в
  `.secrets/atlas.env` (вне git), публичный ключ — в допущении 1. Владелец
  может заменить `ATLAS_VAPID_SUBJECT` на свой mailto/URL, если push-сервис
  отклонит `mailto:admin@example.com`; на код и тесты не влияет.
- **Scope против карточки** (карточка: `app/backend/**`,
  `tests/test_push*.py`) — расширяется; по пунктам A6/A9 обоснование ниже.
  Утверждается approve плана, карточку обновить при переводе в `in_progress`.

**Почему `viewer/**` в scope — что именно нельзя доказать без него:**

| Пункт требования | Где живёт | Без `viewer/**` |
| --- | --- | --- |
| A6 «напоминание приходит (in-app)» | лента и бейдж — `pages/Today.tsx`; поле «напоминание за N мин» — `pages/Calendar.tsx` | API принимает `remind_minutes`, но из UI его не задать, а in-app уведомление негде увидеть: «приходит» проверяется только curl-ом, это не пользовательский acceptance |
| A6/A9 «push» | подписка — `push.ts` + кнопка в `pages/Settings.tsx`, приём — `public/sw.js` (`push`, `notificationclick`) | сервер шлёт только на endpoint; endpoint создаёт браузер через `pushManager.subscribe`, уведомление показывает SW. Без этих файлов кода доставки в браузер нет вообще |
| A9 «подписка в PWA работает» | `push.ts` + `pages/Settings.tsx` | подписка из devtools не доказывает пользовательский путь; тест проверяет только фиктивный sender |
| FR-12 «категории, тихие часы, отписка» | `pages/Settings.tsx` | API тестируется, но UI-пути для настройки/отписки не существует |

Backend-тесты доказывают контракт (AB2–AB11) и идемпотентность, но не
доставку в браузер. Остальные расширения — служебные: `tests/test_migrations.py`
(whitelist таблиц), `tests/test_isolation.py` (тела новых маршрутов),
`tests/__init__.py` (выключить фоновый поток в тестах), `requirements.txt`
(`pywebpush`), `README.md` (A9/iOS, VAPID), `devkit.yaml` (`tests.test_push` в
`unit-tests`). Без них проверки либо красные, либо не покрывают новый код.

## Шаги

Ветка `devkit/T-9F5FB3D3` в `repo/atlas` от `main` @ `2540bc5`; коммиты с id
задачи. Порядок: S1 → (S2 ∥ S3) → S4 → S5 → S6 → S7 → S8 → S9; каждый шаг
оставляет работоспособное состояние (проверки не краснеют дольше шага).

**S1. Миграция 0006 и модели.** `alembic/versions/0006_notifications.py`:

- `notifications(id, owner_id→users CASCADE, kind, title, body, link, read_at,
  pushed_at, dedupe_key, created_at)`, unique `(owner_id, dedupe_key)`, index
  `(owner_id, created_at)`;
- `push_subscriptions(id, owner_id→users CASCADE, endpoint, keys jsonb,
  created_at)`, unique `(owner_id, endpoint)`;
- `notification_settings(owner_id PK→users CASCADE, reminders_enabled bool
  default true, quiet_start string(5) null, quiet_end string(5) null,
  max_push_per_day int default 10, updated_at)`.

Модели — в `models.py` (стиль `bigint()`/`json_type()` как в 0002–0005).
`tests/test_migrations.py`: три таблицы в `TABLES` + тест upgrade/downgrade 0006
по образцу `test_downgrade_removes_only_agent_calls`.

*Результат:* `alembic upgrade head` и `downgrade 0005_agent_calls` проходят;
`tests.test_migrations` зелёный.

**S2. Push-обвязка.** `config.py`: `VAPID_PRIVATE_KEY`, `VAPID_PUBLIC_KEY`,
`VAPID_SUBJECT` (default `mailto:`), `REMINDER_SCAN_SEC` (default 30),
`REMINDER_LATENESS_MIN = 60`. Новый `app/backend/push.py`: `public_key()`,
`enabled()`, `send(subscription, payload) -> "sent" | "gone" | "failed" |
"disabled"` поверх `pywebpush.webpush` (timeout 10 с); статусы 404/410 → `gone`
(подписку удаляем), прочие ошибки → лог без ключей/endpoint-ов, `failed`.
`requirements.txt`: `pywebpush>=2.5`; установка через профиль
`install-requirements`. Ключи уже в `.secrets/atlas.env` (S2 их только читает,
в git и тесты не попадают).

*Результат:* `import app.backend.push` работает без ключей
(`enabled() == False`), тесты не ходят в сеть.

**S3. Ядро напоминаний.** Новый `app/backend/reminders.py`: функция
`dispatch_due(db, now, sender=push.send) -> int`:

- события (`remind_minutes is not null`): без rrule `fire_at = start_at -
  remind`; с rrule — ближайшее вхождение через `pm.next_occurrence(rrule,
  now - remind - 1s)`, `fire_at = occurrence - remind`;
- задачи: `due_at is not null`, `status not in pm.CLOSED_STATUSES`,
  `fire_at = due_at`;
- отбор: `fire_at <= now <= fire_at + 60 мин`, иначе пропуск;
- INSERT уведомления: `kind='reminder'`, `title`, `body`, `link='/'`,
  `dedupe_key = f"event:{id}:{fire_at.isoformat()}"` /
  `f"task:{id}:{due_at.isoformat()}"`; конфликт unique → пропуск
  (идемпотентность);
- `reminders_enabled == false` → ничего не создаётся;
- тихие часы (окно, в т.ч. через полночь): уведомление создаётся, push не
  отправляется (`pushed_at` null);
- лимит `max_push_per_day` (count `pushed_at` за локальные сутки) → push
  пропускается, in-app остаётся;
- push после коммита INSERT: `sent` → `pushed_at`; `gone` → удалить подписку;
  `failed` → лог, подписка на месте (дедуп не даст дубль уведомления).

*Результат:* функция тестируется напрямую с `now` и фиктивным sender, без
сети и потоков.

**S4. Планировщик.** `main.py`: lifespan стартует daemon-thread при
`REMINDER_SCAN_SEC > 0`; своя сессия `SessionLocal`; `dispatch_due(db,
utcnow())` в try/except (лог, поток не падает); поток daemon — умирает с
процессом. `tests/__init__.py`:
`os.environ.setdefault("ATLAS_REMINDER_SCAN_SEC", "0")`.

*Результат:* `TestClient(create_app(...))` не запускает фоновых запросов к
SQLite; в проде сканирование работает.

**S5. API.** Новые `routers/notifications.py` и
`routers/settings_notifications.py` (подхватываются автоматически):

- `GET /api/notifications?limit=50` → `{"items": [...], "unread_count": N}`
  (только свои, новые первыми);
- `POST /api/notifications/{notification_id}/read` → уведомление с `read_at`;
  чужой id → 404;
- `GET /api/settings/notifications` → `{reminders, quiet_start, quiet_end,
  max_push_per_day}` (дефолты, если строки нет);
- `PUT /api/settings/notifications` → `HH:MM` (00:00–23:59), обе границы тихих
  часов заданы или обе пусты, `max_push_per_day` 0..50, иначе 422;
- `GET /api/settings/push-subscription` → `{enabled, public_key, subscribed}`;
- `POST /api/settings/push-subscription` → `{endpoint: https://…, keys:
  {p256dh, auth}}`, upsert по `(owner_id, endpoint)`;
- `DELETE /api/settings/push-subscription` → 204 идемпотентно.

*Результат:* маршруты в OpenAPI; аноним → 401; чужой id → 404.

**S6. Тесты.** Новый `tests/test_push.py` (SQLite + TestClient, фиктивный
sender, инъекция `now`) — сценарии AB2–AB11, AB13; в
`tests/test_isolation.py` — тела для новых POST/PUT; в `devkit.yaml` —
`tests.test_push` в `unit-tests` для windows/darwin/linux.

*Результат:* `python -m unittest tests.test_push tests.test_migrations
tests.test_isolation` зелёный.

**S7. Viewer.** `viewer/public/sw.js`: `push` (showNotification по payload) и
`notificationclick` (focus/open). `viewer/src/api.ts`: типы `Notification`,
`NotificationSettings`, `PushSettings`, `Event.remind_minutes`.
`viewer/src/push.ts`: `subscribePush()` (permission → `pushManager.subscribe` с
public key → POST), `unsubscribePush()`, `pushSupported()`.
`pages/Today.tsx`: лента уведомлений, бейдж непрочитанных, отметка
«прочитано». `pages/Settings.tsx`: блок «Уведомления» — тумблер напоминаний,
тихие часы, лимит push, подписка/отписка, статус разрешения, подсказка про iOS.
`pages/Calendar.tsx`: поле «Напоминание, мин» в форме и показ в карточке.

*Результат:* `npm run build` зелёный; в бандле есть `/api/notifications` и
`/api/settings/push-subscription`.

**S8. Документация.** `README.md`: раздел «Уведомления и push» — env
`ATLAS_VAPID_PUBLIC_KEY/ATLAS_VAPID_PRIVATE_KEY/ATLAS_VAPID_SUBJECT`,
генерация ключей, `ATLAS_REMINDER_SCAN_SEC`, ограничение iOS (push только в
установленной PWA, iOS 16.4+), in-app как основной канал.

*Результат:* AB13 проверяется grep-ом.

**S9. Проверки и сдача.** Полный прогон `web-build` → `unit-tests` →
`ingest-fixtures` → `schema-check`; check-события на финальном sha; отчёт
`docs/reports/T-9F5FB3D3.md`; `devkit-team-sync`; независимые гейты skeptic +
test-engineer; `needs_review`; ship — только владелец.

*Результат:* зелёные проверки на одном sha, отчёт с фактами.

**S10 (владелец, ручная приёмка).** Установленная PWA → «Включить push» →
событие через 2 минуты с напоминанием за 1 мин → push и запись в ленте;
проверка тихих часов и отписки; iOS — push только в установленной PWA. Иначе
фиксируется как непроверенное.

## Acceptance

| # | Проверяемое утверждение | Доказательство |
| --- | --- | --- |
| AB1 | `alembic upgrade head` создаёт `notifications`, `push_subscriptions`, `notification_settings`; downgrade до `0005_agent_calls` удаляет ровно их; whitelist `TABLES` совпадает | `tests.test_migrations`, exit 0 |
| AB2 | Событие `remind_minutes=15`, начало через 10 мин: `dispatch_due` создаёт ровно одно уведомление `kind='reminder'`; повторный вызов — по-прежнему одно | `tests.test_push` |
| AB3 | Событие, чей `fire_at` старше 60 мин, уведомления не создаёт | `tests.test_push` |
| AB4 | Повторяющееся событие: дата напоминания = ближайшее вхождение − `remind_minutes`; на каждое вхождение своё уведомление (разные `dedupe_key`) | `tests.test_push` |
| AB5 | Открытая задача с `due_at` в прошлом (≤60 мин) → уведомление; `done`/`cancelled` → нет | `tests.test_push` |
| AB6 | `GET /api/notifications` → свои записи + `unread_count`; `POST …/{id}/read` ставит `read_at`; чужой id → 404; аноним → 401 | `tests.test_push`, `tests.test_isolation` |
| AB7 | `PUT /api/settings/notifications` сохраняет тихие часы/лимит; `GET` возвращает их; `quiet_start="25:00"` → 422; без строки — дефолты | `tests.test_push` |
| AB8 | Тихие часы, покрывающие «сейчас»: уведомление создано, sender не вызван, `pushed_at is null` | `tests.test_push` (fake sender) |
| AB9 | `max_push_per_day=1`, два напоминания за день: sender вызван один раз, оба уведомления в ленте | `tests.test_push` |
| AB10 | `GET push-subscription` → `enabled=true` + public key (env в тесте); POST сохраняет; повторный POST того же endpoint не плодит строк; DELETE → 204 и строка удалена; чужой endpoint не виден | `tests.test_push` |
| AB11 | sender вернул `gone` → подписка удалена, уведомление осталось; `failed` → уведомление осталось, подписка на месте, процесс не падает | `tests.test_push` |
| AB12 | `sw.js` содержит `push` и `notificationclick`; в собранном бандле есть `/api/notifications` и `/api/settings/push-subscription`; форма события отправляет `remind_minutes` | `tests.test_push` + `web-build` |
| AB13 | `README.md` содержит `ATLAS_VAPID_` и «установленной PWA» (iOS) | `tests.test_push` (чтение файла) |
| AB14 | `unit-tests`, `web-build`, `ingest-fixtures`, `schema-check` — exit 0 на одном commit sha | check-события |
| AB15 | Приватного VAPID-ключа и секретов в git/логах нет | `git grep`, ревью |

## Проверки

Имена — из профиля `devkit.yaml`; запуск из `repo/atlas` на финальном sha.

| Проверка | Команда (windows) | Ожидание |
| --- | --- | --- |
| `web-build` | `npm ci && npm run build` в `viewer/` | exit 0; обязательна до `unit-tests` (`test_web_build` читает `viewer/dist`, каталог в `.gitignore`) |
| `unit-tests` (required) | `.venv\Scripts\python.exe -m unittest … tests.test_push` | exit 0; `tests.test_push` добавлен в список профиля |
| `ingest-fixtures` | `.venv\Scripts\python.exe -m unittest tests.test_ingest.IngestTests.test_fixtures_processed` | exit 0 (регресс knowledge не задет) |
| `schema-check` | `powershell … scripts\validate-schema.ps1` (из профиля) | exit 0; legacy `docs/SCHEMA.md` не меняется |

- Точечно до полного прогона: `.venv\Scripts\python.exe -m unittest
  tests.test_push tests.test_migrations tests.test_isolation`.
- Ручная: S10 (push на реальном устройстве) — единственное, что нельзя
  доказать unit-тестом; результат фиксируется в отчёте как проверено/нет.
- Фиксация: `devkit task check T-9F5FB3D3 --name <name> --status passed
  --commit-sha <sha> --output <лог>`; новый коммит инвалидирует старые
  проверки — гонять на финальном sha.
- Дополнительно: `tests.test_isolation` подтверждает 401/404 на всех новых
  маршрутах без отдельных тестов.

## Scope

**Входит (`repo/atlas`, ветка `devkit/T-9F5FB3D3`):**

- `app/backend/models.py`, `config.py`, `main.py`;
- `app/backend/push.py`, `app/backend/reminders.py` (новые);
- `app/backend/routers/notifications.py`,
  `app/backend/routers/settings_notifications.py` (новые);
- `alembic/versions/0006_notifications.py` (новый);
- `requirements.txt`;
- `viewer/public/sw.js`, `viewer/src/api.ts`, `viewer/src/push.ts` (новый),
  `viewer/src/pages/Today.tsx`, `viewer/src/pages/Settings.tsx`,
  `viewer/src/pages/Calendar.tsx`;
- `tests/test_push.py` (новый), `tests/test_migrations.py`,
  `tests/test_isolation.py`, `tests/__init__.py`;
- `README.md`.

**Входит (data-репозиторий):** `plans/T-9F5FB3D3/**`, `devkit.yaml` (только
список `unit-tests` += `tests.test_push`), `docs/reports/T-9F5FB3D3.md`,
карточка `tasks/T-9F5FB3D3.md` (статус/plan_version после approve).

**Не трогать:** `docs/SCHEMA.md` и схему `kb`, `data/**`, `.secrets/**` и
секреты в git, `mcp*.json`, `viewer/dist` (генерируется), `app/backend/agent/**`,
`knowledge/**`, `routers/{worker,documents,yadisk,settings_llm}.py`, чужие
тесты, default branch, историю git.

**Пересечение с другими задачами:** `in_progress` нет (`shipped` M1–M3,
`inbox` M5 `T-2DC56276`, OCR `T-46BE9A0F`). M5 позже пишет
`reviews`/проактивность и переиспользует `notifications` — контракт (`kind`,
`dedupe_key`, лента, настройки) фиксируется этим планом; файлы не
пересекаются: M5 — `goals/habits/metrics/reviews/journal`, M4 — уведомления.
OCR трогает `documents`/`worker` — пересечения нет. Расширение scope против
карточки (обоснование — раздел «Почему `viewer/**` в scope») утверждается
approve плана; карточку обновить при переводе в `in_progress` (иначе devkit не
даст править).

## Риски

| # | Риск | Мера |
| --- | --- | --- |
| R1 | Новая зависимость `pywebpush` (+ `http-ece`, `py-vapid`), установка/версия | pin `>=2.5`, установка профилем `install-requirements`; без ключей приложение работает; откат — удалить из `requirements.txt` |
| R2 | Дубли push/уведомлений при нескольких процессах uvicorn | unique `(owner_id, dedupe_key)`, INSERT до push, один процесс; `ponytail:` один процесс — при масштабировании вынести сканер в отдельный процесс |
| R3 | iOS: push только в установленной PWA (16.4+), возможны пропуски | документировано; in-app лента — основной канал (A9), подсказка в UI |
| R4 | Тихие часы в локальном времени сервера, в БД UTC naive | допущение задокументировано; tz-колонка при необходимости |
| R5 | Утечка VAPID-ключей/подписок | ключи только env/`.secrets` (вне git), лог без ключей и endpoint-ов, проверка AB15 |
| R6 | Фоновый поток в тестах ломает SQLite/флаки | `ATLAS_REMINDER_SCAN_SEC=0` в `tests/__init__.py`; `dispatch_due` тестируется напрямую с `now` |
| R7 | `test_isolation` требует тело для каждого не-GET маршрута | маршруты и `_body` в одном коммите (S5+S6) |
| R8 | `viewer/dist` в `.gitignore`: `unit-tests` без `web-build` увидит старый dist | порядок проверок зафиксирован: web-build → unit-tests |
| R9 | Scope шире карточки | утверждается планом; карточка обновляется при `in_progress` |
| R10 | Шум/пачка просроченных напоминаний после простоя | окно 60 мин, фильтр закрытых задач, тихие часы, лимит push |
| R11 | `notifications` растёт без очистки | `ponytail:` в M4 не чистим; TTL-очистка/архив — отдельная задача, если объём станет заметным |

### Откат

1. **Мгновенно:** `ATLAS_REMINDER_SCAN_SEC=0` + рестарт API — новые напоминания
   не создаются, API и данные целы.
2. **Код:** revert коммитов M4 в `devkit/T-9F5FB3D3` (или возврат на `main`) и
   пересборка `viewer` (`npm run build`). SW обновится сам (кэш
   `atlas-shell-v1`); обработчики `push` без серверной отправки не мешают.
3. **БД:** `alembic downgrade 0005_agent_calls` удаляет `notifications`,
   `push_subscriptions`, `notification_settings` — история ленты и настройки
   теряются. Перед откатом после реальной эксплуатации — `pg_dump` /
   `devkit backup` и согласие владельца.
4. **Подписки:** после downgrade сервер не шлёт, `pushManager` в браузере
   остаётся — пользователь отписывается в настройках браузера; отдельная
   очистка не нужна.
5. **Проверка после отката:** `unit-tests` без `tests.test_push` (вернуть
   строку профиля), `/api/notifications` → 404, `devkit task check` на новом
   sha.
