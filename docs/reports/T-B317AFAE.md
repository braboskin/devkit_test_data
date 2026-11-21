---
id: R-9d2e0f6eb8
type: report
title: M3 report
task: T-B317AFAE
status: final
created_at: 2026-11-21T18:18:44.167Z
updated_at: 2026-11-21T18:18:44.167Z
---

# Отчёт T-B317AFAE — M3: агент — LLM-ключи, чат, предложения, онбординг, конструктор агентов

Ветка: `devkit/T-B317AFAE` от `main@25db345` (ship `T-07344017`). HEAD: `21fc2bf`.
Ревизия devkit: `b32bc0271dd1a3f7d7fc2c753c6518fd1aaedbc9`.
План: `plans/T-B317AFAE/v3.md` (approved); v4 — уточнение scope после падения
`unit-tests` (см. «Отклонения»). Эпик `E-46E212B4`. Acceptance: A2, A4, A10, A14.

## Что сделано

- **Данные M3** (`0004_agent`, down_revision `0003_worker_singleflight`):
  `llm_credentials`, `user_profile`, `onboarding_sessions`, `agents`, `chats`,
  `messages`, `proposals`, `audit`, `scenarios`, `scenario_runs`; модели в
  `app/backend/models.py`; `tests/test_migrations.py` (TABLES/OWNER_TABLES +
  JSONB-проверки на PG).
- **LLM-ключи (A10)**: `GET|PUT|DELETE /api/settings/llm`,
  `POST /api/settings/llm/check`; Fernet (`ATLAS_FERNET_KEY`), маска, 503 без
  ключа шифрования, 409 без ключа LLM у чата; ключ не в ответе/логе.
- **Агенты (A14)**: 13 пресетов (ленивый сид на владельца), CRUD,
  `POST /api/agents/{id}/test` (без записи в историю), ограничение
  `allowed_spheres/allowed_projects` в инструментах и в `search()`
  (`allowed_sphere_ids/allowed_project_ids`), 20 инструментов чтения/предложений.
- **Чат (A4)**: `StreamingResponse` SSE (`delta`/`citation`/`proposal`/`done`/
  `cancelled`/`error`), tool-calling ≤ 6 раундов, история 20 сообщений, цитаты
  из `search`, отмена через `POST /api/chats/{id}/messages/{mid}/cancel`
  (реестр в памяти процесса), статусы `running/complete/cancelled/error`.
- **Предложения (A4)**: `propose_*` создают `pending`; `POST /api/proposals/{id}/
  apply|reject`, повторная проверка владения, `audit`, деструктив только с
  `confirm`, повторный apply → 409.
- **Онбординг (A2)**: `start|answer|finish`, возобновление `GET /api/onboarding`,
  профиль `GET|PUT /api/profile`, 15 тем; с LLM-ключом вопрос переформулируется
  и профиль собирается структурно, без ключа — детерминированная ветка;
  профиль подмешивается в системный промпт агента.
- **Сценарии (A14)**: CRUD, `POST /api/scenarios/{id}/run` (с `chat_id` пишет
  сообщения в чат, без него — только прогон), `GET /api/scenario-runs/{id}`,
  cancel; «с „Сегодня“» закрывается запуском без `chat_id`.
- **Изоляция новых маршрутов**: `tests/test_agent_isolation.py`; матрица
  `tests/test_isolation.py` расширена id M3-сущностей и телами запросов
  (маршруты проверяются на 401/404 автоматически по OpenAPI).

## Изменения

26 файлов, +5311/−5 (`git diff main..HEAD`), база `25db345`.

- Коммиты:
  - `f1e3e8b` data: M3-таблицы, миграция 0004, `crypto.py`;
  - `85802be` LLM-настройки, клиент, ключ шифром и маской (A10);
  - `5e9b838` агенты, 13 пресетов, scoped-инструменты, фильтр поиска (A14);
  - `bdec78f` SSE-чат, tool-calling, цитаты, отмена, тест агента (A4);
  - `f6b541c` apply/reject предложений, audit, confirm (A4);
  - `02056ce` онбординг, профиль, контекст агента (A2);
  - `fb1cd60` сценарии: CRUD, запуск из чата, cancel (A14);
  - `275e862` изоляция новых маршрутов (A1);
  - `21fc2bf` матрица `test_isolation` для M3 (scope delta).
- Новые файлы backend: `app/backend/crypto.py`,
  `app/backend/agent/{llm,context,tools,presets,chat,proposals,onboarding,
  scenarios}.py`, `app/backend/routers/{settings_llm,agents,chats,proposals,
  onboarding,scenarios}.py`; миграция `alembic/versions/0004_agent.py`.
- Новые тесты: `tests/test_agent_{llm,onboarding,chat,proposals,builder,
  isolation}.py`.
- Data-репо: `devkit.yaml` (модули `unit-tests`), план/отчёт задачи.

## Проверки

Ревизия `21fc2bf` (HEAD ветки). Профиль полный: `devkit profile test`.

| Проверка | Результат | Доказательство |
| --- | --- | --- |
| `unit-tests` (required) | passed, 146.0 с | `CH-98f618b48499`: **289 тестов OK** |
| `web-build` | passed, 2.5 с | `CH-434bc6b93f49` (viewer не менялся, сборка + `test_web_build`) |
| `ingest-fixtures` | passed | `CH-85289cec42a4` |
| `schema-check` | passed | `CH-7cb7a8af28ce` (legacy `kb`; M3-таблицы покрыты PG-smoke в `test_migrations`) |

Точечные прогоны до полного профиля: `test_agent_llm` 11, `test_agent_chat` 10,
`test_agent_proposals` 7, `test_agent_onboarding` 7, `test_agent_builder` 11,
`test_agent_isolation` 3, `test_migrations` 2 — зелёные.

## Отклонения и границы

1. **Scope delta:** `unit-tests` упал на `tests/test_isolation.py`
   (`test_anonymous_401_on_every_api_route`) — матрица строится из OpenAPI и
   требует валидное тело для каждого нового POST/PATCH/PUT. Файл был в списке
   «не трогать» плана v3; правка минимальна (билдеры тел + id M3-сущностей в
   `_alice_graph` + `OWNED_ID`), 76 строк. Оформляется планом v4 (replan).
2. **A10.4** (без ключа чат 409) доказан в `test_agent_chat`, а не в
   `test_agent_llm`, как в таблице v3 — иначе модуль не мог проверить чат до
   его появления.
3. **A15/A16 вне acceptance** (пауза многошагового сценария, сабагенты
   «Критик»/«Редактор»): сценарии прогоняются последовательно без паузы на
   применении; вызовы сабагентов и `agent_calls` не реализованы — отдельная
   задача M3.
4. **UI вне задаче**: `viewer/**` не менялся. UI-части A2/A4/A10/A14 и экран
   «Сегодня» — задача **`T-CA6FF8E2`** (inbox, зависит от этой).
5. **Ключи целей**: `list_goals`/`propose_create_goal` не реализованы — таблица
   `goals` появится в M5; в M3 нет пустышки, инструменты добавятся с моделью.
6. **Undo** предложений не реализован (API §6 только apply/reject);
   `undo_until` остаётся пустым, деструктив — с `confirm`.
7. **Массивы** `allowed_spheres/projects/tools` — JSON (как `tags`), а не `int[]`
   §7: переносимость SQLite/PG в тестах.
8. **Реального LLM не было**: тесты на `httpx.MockTransport`; живой прогон
   DeepSeek и замер «первого токена ≤ 8 с» — за владельцем (в CI нет ключа).
9. `crypto.py` дублирует Fernet-хелперы `yadisk.py` — помечено `ponytail:`;
   свести после отдельной задачи.

## Риски

- **Ключ Fernet**: смена `ATLAS_FERNET_KEY` делает нечитаемыми и ключ LLM, и
  токены Яндекс.Диска — ротация только с перезаписью секретов.
- **Отмена** — реестр в памяти процесса: при нескольких uvicorn-воркерах
  понадобится общее хранилище (помечено в коде).
- **apply деструктивных** удаляет связанные строки вручную; подзадачи задачи
  полагаются на `ON DELETE CASCADE` (SQLite-FK в тестах может не включён).
- **Сценарии** при сбое LLM остаются `failed` с категорией ошибки; resume нет.
- **PG-only** часть (JSONB, миграция) проверена временным кластером; прод
  PostgreSQL не запускался.

## Sync: план → acceptance → факт

| Пункт | Acceptance | Доказательство | Статус |
| --- | --- | --- | --- |
| A10.1–A10.5 | ключи: маска, шифр, check, 409 без ключа, изоляция | `test_agent_llm`, `test_agent_chat`, `test_agent_isolation` | выполнен |
| A2.1–A2.5 | интервью, пауза/возобновление, профиль, контекст | `test_agent_onboarding` | выполнен |
| A4.1–A4.7 | чат SSE, цитаты, предложения, apply/reject, confirm, отмена | `test_agent_chat`, `test_agent_proposals` | выполнен |
| A14.1–A14.6 | 13 агентов, «Врач» с доступом, ограничение поиска, тест без истории, сценарий из чата | `test_agent_builder` | выполнен (UI-часть — `T-CA6FF8E2`) |
| A1 (новые маршруты) | чужой id → 404, матрица 401/404 | `test_agent_isolation`, `test_isolation` | выполнен |
| A13 | профильные проверки зелёные | `CH-98f618b48499`, `CH-434bc6b93f49`, `CH-85289cec42a4`, `CH-7cb7a8af28ce` | выполнен |

## Что не проверено / дальше

- Живой LLM (цитаты, стриминг, «Применить», онбординг, тест «Врача») — ручной
  прогон владельца с его ключом; результат внести в этот отчёт.
- Независимые гейты (`code`, `test`, `architecture`, `security`) — отдельными
  агентами; автор вердикт не выдаёт.
- UI-задача `T-CA6FF8E2` — после `done` этой задачи.
- A15/A16 — отдельная задача M3.
