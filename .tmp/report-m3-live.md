# Отчёт T-B317AFAE — M3: агент — LLM-ключи, чат, предложения, онбординг, конструктор агентов

Ветка: `devkit/T-B317AFAE` от `main@25db345` (ship `T-07344017`). HEAD: `87094eb`.
Ревизия devkit: `c210681adbd8c937921880b29b1d46e36ad5ae75`.
План: `plans/T-B317AFAE/v4.md` (approved; `v3` superseded). Эпик `E-46E212B4`.
Acceptance: A2, A4, A10, A14 (+ изоляция новых маршрутов).

## Что сделано

- **Данные M3** (`0004_agent`, down_revision `0003_worker_singleflight`):
  `llm_credentials`, `user_profile`, `onboarding_sessions`, `agents`, `chats`,
  `messages`, `proposals`, `audit`, `scenarios`, `scenario_runs`; модели в
  `models.py`; индексы `owner_id`; `test_migrations` (TABLES/OWNER_TABLES,
  JSONB на PG, индексы), downgrade.
- **LLM-ключи (A10)**: `GET|PUT|DELETE /api/settings/llm`,
  `POST /api/settings/llm/check`; Fernet (`ATLAS_FERNET_KEY`), маска, 503 без
  ключа шифрования, 409 без ключа LLM у чата, сеть check → 503; ключ не в
  ответах/логах, **включая 422**: глобальный обработчик `RequestValidationError`
  вычищает `input`/`ctx` (Pydantic клал туда значение поля и всё тело).
- **Агенты (A14)**: 13 пресетов, CRUD (`null`-списки → 422, не 500), тест-запрос
  без истории, ограничение `allowed_spheres/allowed_projects` в инструментах и
  в поиске (`allowed_sphere_ids/allowed_project_ids`), allow-list инструментов
  проверяется в runtime, project-only не светит лишние сферы, модель агента
  используется в чате.
- **Чат (A4)**: SSE (`start`/`delta`/`citation`/`proposal`/`done`/`cancelled`/
  `error`), tool-calling ≤ 6 раундов (исчерпание → `error`), история 20
  сообщений, цитаты из `search` и `get_document`, отмена (204/409), статусы
  `running/complete/cancelled/error`, `chat.updated_at`.
- **Предложения (A4)**: `propose_*` → `pending`; apply/reject с **атомарным
  claim** (`UPDATE … WHERE status='pending'` + rowcount): конкурентный второй
  apply → 409, ровно одна сущность; audit, повторная проверка владения,
  деструктив только с `confirm`; storage-оригинал удаляется после commit.
- **Онбординг (A2)**: `start|answer|finish`, возобновление, профиль
  `GET|PUT /api/profile`, 15 тем; с ключом — LLM-вопрос/структурный профиль,
  без ключа — детерминированная ветка; профиль в системном промпте агента.
- **Сценарии (A14)**: CRUD, run с `chat_id` (пишет в чат) и без (триггер
  «с „Сегодня“»), run cancel, state в БД.
- **Изоляция**: `test_agent_isolation` + матрица `test_isolation` по OpenAPI
  (33 новых `/api/*`: 401 анонимом, 404 по чужому id).

## Изменения

28 файлов, **+5686/−7** (`git diff main..HEAD`), база `25db345`.
11 коммитов: `f1e3e8b` (данные/0004/crypto), `85802be` (A10), `5e9b838` (A14
агенты/инструменты/поиск), `bdec78f` (A4 чат/SSE), `f6b541c` (A4 предложения),
`02056ce` (A2 онбординг), `fb1cd60` (A14 сценарии), `275e862` (изоляция),
`21fc2bf` (матрица `test_isolation`, scope v4), `42d016a` (фиксы по гейтам:
валидационный секрет, null-PATCH, атомарный apply, allow-list, scope, индексы),
`87094eb` (sanitize всех 422 + storage после commit).

Новые файлы: `app/backend/crypto.py`,
`app/backend/agent/{llm,context,tools,presets,chat,proposals,onboarding,
scenarios}.py`, `app/backend/routers/{settings_llm,agents,chats,proposals,
onboarding,scenarios}.py`, `alembic/versions/0004_agent.py`,
`tests/test_agent_{llm,onboarding,chat,proposals,builder,isolation}.py`.
Правки существующих: `models.py`, `knowledge/search.py`, `main.py` (глобальный
sanitizer 422, security-фикс), `tests/{test_migrations,test_isolation}.py`.

## Проверки

Ревизия `87094eb`; `devkit profile test` (полный, два независимых прогона —
автор и test-engineer):

| Проверка | Результат | Доказательство |
| --- | --- | --- |
| `unit-tests` (required) | passed, ~149 с | `CH-3f4cbfc98f30`: **297 тестов OK** (agent-модули 57) |
| `web-build` | passed | `CH-50909f8e600e` |
| `ingest-fixtures` | passed | `CH-fd241e4321a7` |
| `schema-check` | passed | `CH-3a82b6b5a94a` |
| Повторы agent-модулей | 10/10 OK | флейков не воспроизведено |

## Гейты

Все на `c210681` (`87094eb`), роли независимые, автор вердиктов не выдавал:

| kind | id | verdict | роль |
| --- | --- | --- | --- |
| code | `G-788211ed13da` | approve | architect |
| architecture | `G-859b49d72a65` | approve | architect |
| test | `G-cd7aea010a57` | approve | test-engineer |
| security | `G-c9096c585cba` | approve | skeptic |

История: первые гейты на `21fc2bf` дали `code=changes`, `security=changes`
(утечка ключа/пароля в 422, 500 на null-PATCH, гонка apply, обход allow-list,
утечка сфер) — исправлено в `42d016a`/`87094eb`, гейты перевыпущены.

## Отклонения и границы

1. **Scope delta (v4):** `unit-tests` упал на `tests/test_isolation.py` —
   матрица из OpenAPI требует тела для каждого нового POST/PATCH/PUT; правка
   тестов 76 строк (билдеры + id M3-сущностей).
2. **Scope delta (v5):** `main.py` был в «не трогаем» v4; security-гейт нашёл
   утечку секретов через `RequestValidationError.input` (ключ LLM в теле 422 и
   пароль логина без аутентификации). Глобальный sanitizer в `main.py` —
   аддитивный фикс; автоподключение роутеров не задето.
3. **A10.4** (без ключа чат 409) доказан в `test_agent_chat` — модуль
   `test_agent_llm` не мог проверить чат до его появления.
4. **A15/A16 вне acceptance:** сценарии — последовательный прогон без паузы на
   применении; сабагенты/`agent_calls` не реализованы — отдельная задача M3.
5. **UI вне задачи:** `viewer/**` не менялся; UI-части A2/A4/A10/A14 и экран
   «Сегодня» — задача **`T-CA6FF8E2`**.
6. **Ключи целей:** `list_goals`/`propose_create_goal` — после появления
   таблицы `goals` в M5 (пустышку модели не отдаём).
7. **Undo** предложений не реализован (API §6: apply/reject); деструктив —
   с `confirm`; `undo_until` пуст.
8. **Массивы** `allowed_spheres/projects/tools` — JSON (как `tags`), а не
   `int[]` §7: переносимость SQLite/PG в тестах.
9. **`step` онбординга 0-based** (число отвеченных вопросов): в плане A2.1
   написано `step=1` — фактически `step=0` на старте, тест сверяет счётчик.
10. **LLM в CI — моки**: автотесты на `httpx.MockTransport` (ключа в CI нет);
    живой прогон DeepSeek выполнен владельцем — см. «Live smoke» ниже.
11. **Принятые ограничения:** гонка ленивого сида пресетов (unique нет),
    синхронный прогон сценария (отмена между шагами), дублирование
    `crypto.py`/`yadisk.py` (ponytail-долг), `ownership`-хелперы не переиспользованы
    в новых роутерах (дублируют одну проверку).

## Риски

- **Fernet-ключ:** смена `ATLAS_FERNET_KEY` делает нечитаемыми и ключ LLM, и
  токены Яндекс.Диска — ротация только с перезаписью секретов.
- **Отмена** — реестр в памяти процесса: несколько uvicorn-воркеров потребуют
  общего хранилища.
- **apply деструктивных** чистит связи вручную; подзадачи задачи полагаются на
  `ON DELETE CASCADE` (SQLite-FK в тестах может быть выключен).
- **Сценарии** при сбое LLM остаются `failed`; resume нет (A15). `/api/agents/
  {id}/test` при исчерпании tool-раундов вернёт 200 с пустым `answer` (LLM-ветка).
- **SSE `start`** отдаётся до входа в генератор: disconnect сразу после старта
  может оставить `message.status=running`.
- **PG-only** часть проверена временным кластером (`test_migrations`), прод
  PostgreSQL не запускался.
- Рабочее дерево `repo/atlas` показывает 102 `M`-файла из-за CRLF
  (`git diff --ignore-cr-at-eol` пуст) — артефакт окружения, в коммиты не входит.

## Sync: план → acceptance → факт

| Пункт | Acceptance | Доказательство | Статус |
| --- | --- | --- | --- |
| A10.1–A10.5 | маска/шифр/check/409 без ключа/изоляция + 422 без секретов | `test_agent_llm`, `test_agent_chat`, `test_agent_isolation` | выполнен |
| A2.1–A2.5 | интервью, resume, профиль, контекст | `test_agent_onboarding` | выполнен |
| A4.1–A4.7 | SSE, цитаты (`search`/`get_document`), предложения, apply/reject/confirm, отмена | `test_agent_chat`, `test_agent_proposals` | выполнен |
| A14.1–A14.6 | 13 агентов, «Врач»+ограничение сфер сквозь чат, тест без истории, сценарий из чата | `test_agent_builder`, `test_agent_chat` | выполнен (UI — `T-CA6FF8E2`) |
| A1 (новые маршруты) | 401-матрица и 404 по чужим id | `test_agent_isolation`, `test_isolation` | выполнен |
| A13 | профильные проверки зелёные | `CH-3f4cbfc98f30`, `CH-50909f8e600e`, `CH-fd241e4321a7`, `CH-3a82b6b5a94a` | выполнен |
| Гейты | code/architecture/test/security approve | `G-788211ed13da`, `G-859b49d72a65`, `G-cd7aea010a57`, `G-c9096c585cba` | выполнен |

## Live smoke (реальный DeepSeek)

Прогон владельца, 2026-11-21, `repo/atlas` HEAD `87094eb` (codeSha `c210681…`),
модель `deepseek-chat`, `https://api.deepseek.com/v1`, скрипт
`.tmp/smoke_agent_llm.py` (временная SQLite/хранилище, `.tmp` вне git).

**22/22 проверок PASS**:

| Что | Факт |
| --- | --- |
| `POST /api/settings/llm/check` | 200 `ok=true`, 0.76 с |
| Стрим чата (SSE) | ответ с цитатой из «Анализы» (1 citation); **первый токен 0.62 с** (≤ 8 с) |
| Предложение | `propose_create_task` → `pending` → apply 200, задача создана, `audit` записан |
| Тест агента «Врач» (только сфера «Здоровье») | ответ по документу; история чатов/сообщений не изменилась |
| Онбординг | 15 ответов → профиль (15 тем + сводка) сохранён |
| Секреты | ключ маскирован в API, в БД только шифр, в ответах API не встречается |

Ограничения прогона: эмбеддинги fake (поиск лексический на SQLite), поэтому
проверены LLM + API + tool-calling + цитаты, но не BGE-M3/Qdrant и не
прод-PostgreSQL; UI не проверялся (`T-CA6FF8E2`).

## Что не проверено / дальше

- PG-downgrade `0004→0003` (SQLite-downgrade проверен; PG upgrade + JSONB smoke
  внутри `test_migrations`).
- UI `viewer/**` (задача `T-CA6FF8E2`), A15/A16 — отдельные задачи M3.
