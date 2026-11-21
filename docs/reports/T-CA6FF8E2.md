---
id: R-54377ffebe
type: report
title: UI + A15/A16 report
task: T-CA6FF8E2
status: final
created_at: 2026-11-21T20:01:57.786Z
updated_at: 2026-11-21T20:01:57.786Z
---

# Отчёт T-CA6FF8E2 — UI агента + A15/A16

Ветка: `devkit/T-CA6FF8E2` от `main@b897d53` (M3 shipped). HEAD: `52bb1d3`.
Ревизия devkit: `acf198ce10c3e1a1ec8c590227a45c172219d9d1`.
План: `plans/T-CA6FF8E2/v2.md` (approved). Эпик `E-46E212B4`.
Scope фактический: UI M3 + backend A15 (пауза сценария) + A16 (сабагенты).
Карточка задачи не редактируется (web/CLI): остаётся `L`/`viewer-*` при плане
`XL`/backend — осознанное расхождение метаданных (см. «Отклонения»).

## Что сделано

- **A16 — внутренние сабагенты.** `agent_calls` (миграция `0005_agent_calls`),
  `agent/subagents.py`: «Критик»/«Редактор» на ключе владельца, без чата и
  истории; запись трейса `parent/child/chat/input/output`; «Врач»/«Юрист»/
  «Финансист» имеют `use_critic` по умолчанию. Для агентов с
  `use_critic`/`use_editor` ответ собирается нестримингово: черновик (tool-loop)
  → «Критик» (замечание учитывается в переписанном ответе) → «Редактор»
  (формулировки, цитаты не меняются) → один `delta`+`done`. Внутренние агенты
  скрыты из `GET /api/agents` и недоступны через patch/delete.
- **A15 — пауза сценария.** Шаг, породивший предложение, переводит прогон в
  `awaiting_apply` (`state.awaiting` с индексами шагов и `proposal_ids`);
  `POST /api/scenario-runs/{id}/resume` продолжает с сохранённого шага и
  возвращает 409, пока предложения `pending`; `cancel` работает и из ожидания;
  `GET /api/scenario-runs` отдаёт список прогонов для UI.
- **UI M3**: вкладки «Сегодня», «Чат», «Агенты» (`App.tsx`); чат — SSE-стрим
  через `fetch`+`ReadableStream`, цитаты, «Отменить», карточки предложений
  «Применить/Отменить», трейс сабагентов; конструктор агентов (доступ к
  сферам/проектам, инструменты, модель/температура, `use_critic/use_editor`,
  тест-вопрос); онбординг-интервью с продолжением и профиль; настройки LLM
  (маска, проверка, удаление) и профиль; «Сегодня» — запуск сценариев,
  `awaiting_apply` с «Продолжить/Отменить», список предложений.
- API: `GET /api/agents/tools`, `GET /api/agent-calls?chat_id=`,
  `use_critic/use_editor` в `AgentOut/In/Patch`, `GET /api/scenario-runs`,
  `POST /api/scenario-runs/{id}/resume`.

## Изменения

24 файла, **+3178/−84** (`git diff main..HEAD`), база `b897d53`, 5 коммитов:
`dfe411a` (миграция 0005/agent_calls), `3c89cbb` (A16 сабагенты/трейс/флаги),
`49f0f94` (A15 пауза/resume/cancel), `e12e799` (UI: чат/агенты/онбординг/
«Сегодня»/настройки), `52bb1d3` (тест списка прогонов).

Файлы: `app/backend/{models}.py`, `alembic/versions/0005_agent_calls.py`,
`app/backend/agent/{presets,subagents,chat,scenarios,tools}.py`,
`app/backend/routers/{agents,chats,scenarios,agent_calls}.py`;
`viewer/src/{api.ts,App.tsx,styles.css}`, `viewer/src/pages/{Chat,Agents,
Onboarding,Today,Settings}.tsx`; тесты `test_agent_subagents.py`,
`test_agent_scenario_runs.py`, правки `test_agent_*`, `test_migrations`,
`test_isolation`, `test_web_build`; data-репо `devkit.yaml` (модули в
`unit-tests`).

## Проверки

Ревизия `52bb1d3`; `devkit profile test`:

| Проверка | Результат | Доказательство |
| --- | --- | --- |
| `unit-tests` (required) | passed, 164 с | `CH-c2615116d7bb`: **308 тестов OK** |
| `web-build` | passed | `CH-4bb862b8692a` (tsc + vite) |
| `ingest-fixtures` | passed | `CH-c52c2dd46ff5` |
| `schema-check` | passed | `CH-329545b80243` |

Новые тесты: `test_agent_subagents` 6, `test_agent_scenario_runs` 4,
`test_web_build` +1 (вкладки в бандле), миграции/изоляция — правки.

## Гейты

Пока **не выданы**: нужны независимые роли (`code`, `test`, `architecture`,
`security` — XL) с task-токенами `T-CA6FF8E2`; токенов у задачи нет. Автор
вердикт не выдаёт.

## Отклонения и границы

1. **Карточка задачи** остаётся `L`/`viewer-*`: правка scope/size недоступна в
   web и CLI; контракт — план v2 (`XL`, backend+UI), расхождение метаданных
   фиксируется здесь и на гейтах (не выдаём за расширение «по факту»).
2. **Браузерного E2E нет**: UI-пункты UI.2–UI.7 подтверждаются сборкой,
   smoke-тестом вкладок и ручным чеком владельца; Playwright не добавлялся
   (новая зависимость — отдельная задача).
3. **Живой LLM не прогонялся** для A15/A16/UI: тесты на `httpx.MockTransport`.
   Ограничения: нестриминговый путь для «Врача/Юриста/Финансиста» (латентность
   выше), `agent_calls.tokens` пуст (стриминговый `complete()` не отдаёт usage),
   критик в тест-эндпоинте пишется с `chat_id=null`.
4. **Новые маршруты вне минимума §6 ТЗ** (`GET /api/scenario-runs`,
   `GET /api/agents/tools`, `GET /api/agent-calls`) — нужны UI/трейсу.
5. **A2/A4/A10/A14** поведение не менялось, кроме: нестриминговый путь для
   агентов с флагами и пауза сценариев.

## Риски

- Сабагенты добавляют 2–3 вызова LLM на ответ «Врача/Юриста/Финансиста» —
  стоимость/латентность; отключается флагом у агента.
- Пауза сценария хранится в `state` прогона; повторный `resume` защищён
  статусом (409), но гонка двух `resume` под нагрузкой не тестировалась (PG).
- UI без браузерных тестов: регрессии вёрстки/потока ловятся только руками.
- `agent_calls` растёт без ретенции (трейс) — чистка не реализована.
- Миграция `0005` проверена SQLite+PG upgrade; PG-downgrade не гонялся.

## Sync: план → acceptance → факт

| Пункт | Acceptance | Доказательство | Статус |
| --- | --- | --- | --- |
| A15.1 | Пауза на шаге с proposal, `awaiting.proposal_ids` | `test_agent_scenario_runs` | выполнен |
| A15.2 | resume при pending → 409; после apply → done, 3 шага | `test_agent_scenario_runs` | выполнен |
| A15.3 | cancel из ожидания → cancelled | `test_agent_scenario_runs` | выполнен |
| A15.4 | чужой прогон → 404, state изолирован | `test_agent_scenario_runs` | выполнен |
| A16.1 | «Врач» → «Критик»: `agent_calls`, замечание учтено | `test_agent_subagents` | выполнен |
| A16.2 | сабагенты скрыты, без чатов/сообщений | `test_agent_subagents` | выполнен |
| A16.3 | «Редактор» не меняет citations | `test_agent_subagents` | выполнен |
| A16.4 | флаги off → нет вызовов; изоляция трейса | `test_agent_subagents` | выполнен |
| UI.1 | сборка, вкладки в бандле | `web-build`, `test_web_build` | выполнен |
| UI.2–UI.7 | чат/предложения/конструктор/онбординг/ключ/«Сегодня» | ручной чек владельца | **не проверен** |
| M1 | `0005` upgrade/downgrade, `agent_calls` с owner_id | `test_migrations` | выполнен |
| A1' | новые маршруты в матрице 401/404 | `test_isolation`, `test_agent_isolation` | выполнен |

## Что не проверено / дальше

- Ручной UI-чек по acceptance UI.2–UI.7 (нужен браузер; можно поднять
  `uvicorn app.backend.main:app` на временной БД).
- Живой прогон A15/A16: пауза/продолжение сценария с реальным DeepSeek и
  вызов «Критика/Редактора» — по желанию владельца; ключ и стенд есть.
- Независимые гейты 4 ролей (нужны токены задачи) → `needs_review` → ship.
