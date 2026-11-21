---
id: R-54377ffebe
type: report
title: UI + A15/A16 report
task: T-CA6FF8E2
status: final
created_at: 2026-11-21T20:27:28.359Z
updated_at: 2026-11-21T20:27:28.359Z
---

# Отчёт T-CA6FF8E2 — UI агента + A15/A16

Ветка: `devkit/T-CA6FF8E2` от `main@b897d53` (M3 shipped). HEAD: `2cfd8b1`.
Ревизия devkit: `895daf90d0d5f4cbf68e24a08bbd66b5c7136454`.
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
- API: `GET /api/agents/tools`, `GET /api/agent-calls?chat_id=`
  (обработчик в `routers/scenarios.py`, отдельного роутера нет),
  `use_critic/use_editor` в `AgentOut/In/Patch`, `GET /api/scenario-runs`,
  `POST /api/scenario-runs/{id}/resume`.
- **Исправления по гейтам** (`2cfd8b1`): внутренние агенты запрещены для чатов/
  сценариев (404/422); удаление агента с трейсом → 409; `resume` — атомарный
  CAS; чужой `chat_id` в трейсе → 404; сабагент получает доступ родителя в
  промпте; в UI работает `AbortController.abort()` после серверного cancel,
  человеческие тексты для 409/422, подсказка «пусто = все инструменты»,
  редактор `profile.data` (JSON). Downgrade `0005` покрыт тестом.

## Изменения

23 файла, **+3365/−91** (`git diff main..HEAD`), база `b897d53`, 6 коммитов:
`dfe411a` (миграция 0005/agent_calls), `3c89cbb` (A16 сабагенты/трейс/флаги),
`49f0f94` (A15 пауза/resume/cancel), `e12e799` (UI: чат/агенты/онбординг/
«Сегодня»/настройки), `52bb1d3` (тест списка прогонов), `2cfd8b1` (фиксы гейтов).

Файлы: `app/backend/{models}.py`, `alembic/versions/0005_agent_calls.py`,
`app/backend/agent/{presets,subagents,chat,scenarios,tools}.py`,
`app/backend/routers/{agents,chats,scenarios}.py`;
`viewer/src/{api.ts,App.tsx,styles.css}`, `viewer/src/pages/{Chat,Agents,
Onboarding,Today,Settings}.tsx`; тесты `test_agent_subagents.py`,
`test_agent_scenario_runs.py`, правки `test_migrations`, `test_isolation`,
`test_web_build`; data-репо `devkit.yaml` (модули в `unit-tests`).

## Проверки

Ревизия `2cfd8b1`; `devkit profile test`:

| Проверка | Результат | Доказательство |
| --- | --- | --- |
| `unit-tests` (required) | passed, 162 с | `CH-cac35c392243`: **311 тестов OK** |
| `web-build` | passed | `CH-b6b75e6fc579` (tsc + vite) |
| `ingest-fixtures` | passed | `CH-dcbc29814b61` |
| `schema-check` | passed | `CH-f39bbd5a1f94` |

Новые тесты: `test_agent_subagents` 9, `test_agent_scenario_runs` 4,
`test_migrations` +деградация `0005`, `test_web_build` +1 (вкладки в бандле),
`test_isolation` — маршрут resume.

## Гейты

Все на ревизии `895daf9…` (`2cfd8b1`), независимые роли, автор вердиктов не
выдавал:

| kind | id | verdict | роль |
| --- | --- | --- | --- |
| code | `G-3092102dc80c` | approve | architect |
| architecture | `G-ffad86c78080` | approve | architect |
| test | `G-f9cb8d0202c9` | approve | test-engineer |
| security | `G-87c12d5d2c11` | approve | skeptic |

Первые гейты на `acf198c…` дали `code/architecture = changes` (internal-агенты
как обычные, 500 при удалении агента с трейсом, неатомарный resume) и
`test/security = approve`; после фиксов `2cfd8b1` все четыре перевыпущены.
`agent_calls` без ретенции и 409 при удалении агента с трейсом — принятые
ограничения (owner-only, кросс-доступа нет; нужен follow-up на purge/retention).

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
- `agent_calls` растёт без ретенции (трейс) — чистка не реализована (принято).
- Миграция `0005` проверена upgrade (SQLite+PG) и downgrade (SQLite-тест);
  PG-downgrade отдельно не гонялся.

## Sync: план → acceptance → факт

| Пункт | Acceptance | Доказательство | Статус |
| --- | --- | --- | --- |
| A15.1 | Пауза на шаге с proposal, `awaiting.proposal_ids` | `test_agent_scenario_runs` | выполнен |
| A15.2 | resume при pending → 409; после apply → done, 3 шага | `test_agent_scenario_runs` | выполнен |
| A15.3 | cancel из ожидания → cancelled | `test_agent_scenario_runs` | выполнен |
| A15.4 | чужой прогон → 404, state изолирован | `test_agent_scenario_runs` | выполнен |
| A16.1 | «Врач» → «Критик»: `agent_calls`, замечание учтено | `test_agent_subagents` | выполнен |
| A16.2 | сабагенты скрыты, без чатов/сообщений, internal-id нельзя использовать для чата/сценария | `test_agent_subagents` | выполнен |
| A16.3 | «Редактор» не меняет citations | `test_agent_subagents` | выполнен |
| A16.4 | флаги off → нет вызовов; трейс изолирован, чужой `chat_id` → 404 | `test_agent_subagents` | выполнен |
| UI.1 | сборка, вкладки в бандле | `web-build`, `test_web_build` | выполнен |
| UI.2–UI.7 | чат/предложения/конструктор/онбординг/ключ/«Сегодня» | ручной чек владельца | **не проверен** |
| M1 | `0005` upgrade/downgrade, `agent_calls` с owner_id | `test_migrations` | выполнен |
| A1' | новые маршруты в матрице 401/404 | `test_isolation`, `test_agent_isolation` | выполнен |

## Что не проверено / дальше

- Ручной UI-чек по acceptance UI.2–UI.7 (нужен браузер; можно поднять
  `uvicorn app.backend.main:app` на временной БД).
- Живой прогон A15/A16: пауза/продолжение сценария с реальным DeepSeek и
  вызов «Критика/Редактора» — по желанию владельца; ключ и стенд есть.
- Независимые гейты 4 ролей (перевыпуск на `2cfd8b1`) → `needs_review` → ship.
- Ретенция `agent_calls` — принятое ограничение (трейс растёт), отдельная задача.
