---
id: R-54377ffebe
type: report
title: UI + A15/A16 report
task: T-CA6FF8E2
status: final
created_at: 2026-11-21T22:08:34.441Z
updated_at: 2026-11-21T22:08:34.441Z
---

# Отчёт T-CA6FF8E2 — UI агента + A15/A16

Ветка: `devkit/T-CA6FF8E2` от `main@b897d53` (M3 shipped). HEAD: `6ca7c40`.
Ревизия devkit: `6194e4b52a2efbce321744fc289f8ef3ba4b818e`.
План: `plans/T-CA6FF8E2/v3.md` (approved, `planVersion=3`; v2 superseded).
Scope фактический: UI M3 + backend A15 (пауза сценария) + A16 (сабагенты),
плюс второй раунд по ручному чеку (usage сабагентов, конфиг OAuth Яндекса,
инлайн-обработка текстовых PDF) — план v3.
Карточка задачи не редактируется (web/CLI): остаётся `L`/`viewer-*` при плане
`XL`/backend — осознанное расхождение метаданных (см. «Отклонения»).

## Что сделано

- **A16 — внутренние сабагенты.** `agent_calls` (миграция `0005_agent_calls`),
  `agent/subagents.py`: «Критик»/«Редактор» на ключе владельца, без чата и
  истории; запись трейса `parent/child/chat/input/output`; «Врач»/«Юрист»/
  «Финансист» имеют `use_critic` по умолчанию. Ответ у таких агентов собирается
  так: черновик **стримится сразу** (`delta`), затем «Критик» (замечание
  учитывается в переписанном ответе) и «Редактор» (формулировки; цитаты не
  меняются), после чего клиент получает `replace` с финальным текстом и `done`.
  Внутренние агенты скрыты из `GET /api/agents` и недоступны через
  patch/delete/чат/сценарий.
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

- **Второй раунд по замечаниям владельца** (`69d17e2`, `52bfcdf`): токены
  «Критика/Редактора» теперь **входят в счёт** (`complete_with_usage`,
  `usage` суммируется в UI, `agent_calls.tokens` заполняется); у Яндекс.Диска
  появился `GET /api/settings/yadisk/config` — в UI видно, настроен ли OAuth
  на сервере, и какие env-переменные нужны (`YANDEX_CLIENT_ID/SECRET`),
  кнопка блокируется до настройки; текстовые PDF до **200 страниц / 50 МБ**
  (env `ATLAS_PDF_INLINE_MAX_PAGES/BYTES`) обрабатываются на сервере сразу,
  без воркера; в «Документах» уточнён текст, что Яндекс.Диск не влияет и
  ждут только сканы/OCR/сверхбольшие PDF. Для серверного OCR/кнопки
  «обработать на сервере» создана задача **`T-46BE9A0F`**.
- **После ручного чека владельца** (`3505d5a`): у агентов с
  «Критиком/Редактором» черновик теперь **стримится сразу** (частичный вывод),
  а после критики приходит событие `replace` с финальным текстом — отмена
  работает и на этом пути; в SSE добавлен `usage` (DeepSeek
  `stream_options.include_usage`), UI показывает вход/выход токенов и оценку
  стоимости с учётом off-peak; в настройках LLM дефолты
  `https://api.deepseek.com/v1` + `deepseek-chat` и подсказка со списком
  моделей; для «Яндекс.Диска» при ненастроенном OAuth показывается причина и
  совет вставить токен вручную; для документов в `queued` — подсказка открыть
  «Задания» (токен воркера/статус).

## Изменения

30 файлов, **+3845/−148** (`git diff main..HEAD`), база `b897d53`, 12 коммитов:
`dfe411a` (миграция 0005/agent_calls), `3c89cbb` (A16 сабагенты/трейс/флаги),
`49f0f94` (A15 пауза/resume/cancel), `e12e799` (UI: чат/агенты/онбординг/
«Сегодня»/настройки), `52bb1d3` (тест списка прогонов), `2cfd8b1` (фиксы гейтов),
`3505d5a` (стриминг черновика/`replace`, usage и off-peak, дефолты модели),
`7b19234` (fallback `stream_options`, позитивные тесты `replace`/`usage`),
`69d17e2` (usage сабагентов, конфиг OAuth Яндекса, inline-PDF),
`52bfcdf` (тест настраиваемого лимита PDF),
`cf4de27` (inline-PDF байты 50 МБ по умолчанию, тест config-флага),
`6ca7c40` (тесты DOC.1: env/байты/дефолты; UI.8: false/true и отсутствие секрета).

Файлы: `app/backend/{models}.py`, `alembic/versions/0005_agent_calls.py`,
`app/backend/agent/{presets,subagents,chat,scenarios,tools}.py`,
`app/backend/routers/{agents,chats,scenarios,settings_yadisk}.py`,
`app/backend/knowledge/pipeline.py` (env-лимиты inline-PDF);
`viewer/src/{api.ts,App.tsx,styles.css}`, `viewer/src/pages/{Chat,Agents,
Onboarding,Today,Settings,Documents}.tsx`; тесты `test_agent_subagents.py`,
`test_agent_scenario_runs.py`, правки `test_migrations`, `test_isolation`,
`test_web_build`, `test_knowledge`, `test_yadisk`; data-репо `devkit.yaml`
(модули в `unit-tests`), план v3/отчёт.

## Проверки

Ревизия `6ca7c40`; `devkit profile test`:

| Проверка | Результат | Доказательство |
| --- | --- | --- |
| `unit-tests` (required) | passed | `CH-535b762ab2ce`: **318 тестов OK** |
| `web-build` | passed | `CH-7a06fd307480` (tsc + vite) |
| `ingest-fixtures` | passed | `CH-092960899f64` |
| `schema-check` | passed | `CH-24617c912d20` |

Новые тесты: `test_agent_subagents` 11, `test_agent_scenario_runs` 4,
`test_migrations` +деградация `0005`, `test_web_build` +1 (вкладки в бандле),
`test_isolation` — маршрут resume; `test_knowledge` +3 (DOC.1: дефолты/ env/
байты), `test_yadisk` +1 (UI.8: false/true, секрет не в ответе).

## Гейты

Ревизия `6194e4b…` (`6ca7c40`), все независимые роли — `approve`:

| kind | id | verdict | роль |
| --- | --- | --- | --- |
| code | `G-22f9b813a606` | approve | architect |
| architecture | `G-0fbc06a43f3b` | approve | architect |
| test | `G-6b32045b0e94` | approve | test-engineer |
| security | `G-fe16e912895c` | approve | skeptic |

История: на `7b19234` все четыре approve; `3505d5a` — code/arch changes
(stream_options, исправлено); `52bfcdf` — test changes (DOC.1/UI.8 не доказаны,
исправлено в `6ca7c40`) и code/arch changes (scope вне v2 — закрыто планом v3).
Независимые роли (`code`, `test`, `architecture`, `security` — XL), автор
вердикт не выдаёт.

## Отклонения и границы

1. **Карточка задачи** остаётся `L`/`viewer-*`: правка scope/size недоступна в
   web и CLI; контракт — план v3 (`XL`, backend+UI), расхождение метаданных
   фиксируется здесь и на гейтах (не выдаём за расширение «по факту»).
2. **Браузерного E2E нет**: UI-пункты UI.2–UI.7 подтверждаются сборкой,
   smoke-тестом вкладок и ручным чеком владельца; Playwright не добавлялся
   (новая зависимость — отдельная задача).
3. **Живой LLM не прогонялся** для A15/A16/UI: тесты на `httpx.MockTransport`.
   Ограничения: `usage` не персистится (виден в UI до перезагрузки), критик в
   тест-эндпоинте пишется с `chat_id=null`.
4. **Новые маршруты вне минимума §6 ТЗ** (`GET /api/scenario-runs`,
   `GET /api/agents/tools`, `GET /api/agent-calls`) — нужны UI/трейсу.
5. **SSE-контракт расширен** (`replace`, `usage`) сверх базового списка —
   `replace` нужен для правок «Критика/Редактора», `usage` для токенов; старая
   схема (`delta/citation/proposal/done/cancelled/error/start`) сохранена.
6. **`stream_options.include_usage`** уходит любому OpenAI-совместимому
   провайдеру, но при 400/422 чат **повторяет запрос без него** (usage
   отсутствует, ответ работает) — покрыто тестом
   `test_provider_without_stream_options_falls_back`.
7. **Оценка стоимости** включает черновик и вызовы «Критика/Редактора/ревизии»
   (`usage` суммируется, `agent_calls.tokens` заполняется); `usage` не
   персистится — цена оценочная, не биллинг.
8. **Сканы/OCR на сервере** не реализованы: изображения и PDF без текстового
   слоя по-прежнему обрабатывает воркер на ПК (VPS 4 ГБ); для этого создана
   задача **`T-46BE9A0F`**. Текстовые PDF до 200 стр/50 МБ идут на сервере.
9. **Выбор моделей** у провайдеров — базовый список DeepSeek + ручной ввод;
   расширенный каталог оставлен на будущее (решение владельца).
10. **A2/A4/A10/A14** поведение не менялось, кроме: стриминг черновика и
    `replace` для агентов с флагами, событие `usage`, пауза сценариев.

## Риски

- Сабагенты добавляют 2–3 вызова LLM на ответ «Врача/Юриста/Финансиста» —
  стоимость/латентность; отключается флагом у агента.
- Пауза сценария хранится в `state` прогона; повторный `resume` защищён
  статусом (409), но гонка двух `resume` под нагрузкой не тестировалась (PG).
- UI без браузерных тестов: регрессии вёрстки/потока ловятся только руками.
- `agent_calls` растёт без ретенции (трейс) — чистка не реализована (принято).
- Миграция `0005` проверена upgrade (SQLite+PG) и downgrade (SQLite-тест);
  PG-downgrade отдельно не гонялся.
- Токены/стоимость: `usage` — числа от провайдера, цена — оценка по публичным
  тарифам DeepSeek; off-peak окно 16:30–00:30 UTC; не биллинг, не персистится.
- **Инлайн-обработка текстовых PDF** до 200 стр / 50 МБ идёт синхронно в
  upload-запросе на VPS 4 ГБ — риск памяти/латентности; лимиты настраиваются
  `ATLAS_PDF_INLINE_MAX_PAGES/BYTES`, риск принят владельцем ради UX (R11 в
  плане v3); сканы по-прежнему воркер (`T-46BE9A0F`).

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
| A16.5 | usage всех вызовов суммируется, `agent_calls.tokens` заполнен | `test_agent_subagents` | выполнен |
| A16.6 | черновик стримится, финал — `replace`, сохранённый текст = финалу; отмена → cancelled | `test_agent_subagents` | выполнен |
| UI.8 | `GET /api/settings/yadisk/config` → `oauth_configured`; false/true без/с env, секрет не отдаётся | `test_yadisk`, ручной чек | выполнен (API), ручной — в UI.2–UI.7 |
| DOC.1 | 200 стр/50 МБ дефолты, env-override, 30 МБ inline / 60 МБ defer | `test_knowledge` | выполнен |
| UI.1 | сборка, вкладки в бандле | `web-build`, `test_web_build` | выполнен |
| UI.2–UI.7 | чат/предложения/конструктор/онбординг/ключ/«Сегодня» | ручной чек владельца | **не проверен** |
| M1 | `0005` upgrade/downgrade, `agent_calls` с owner_id | `test_migrations` | выполнен |
| A1' | новые маршруты в матрице 401/404 | `test_isolation`, `test_agent_isolation` | выполнен |

## Что не проверено / дальше

- Ручной UI-чек по acceptance UI.2–UI.7 (нужен браузер; можно поднять
  `uvicorn app.backend.main:app` на временной БД).
- Живой прогон A15/A16: пауза/продолжение сценария с реальным DeepSeek и
  вызов «Критика/Редактора» — по желанию владельца; ключ и стенд есть.
- Независимые гейты 4 ролей (перевыпуск на `6ca7c40`) → `needs_review` → ship.
- Сканы/OCR на сервере — задача `T-46BE9A0F` (после этой).
- Ретенция `agent_calls` — принятое ограничение (трейс растёт), отдельная задача.
