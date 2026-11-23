---
id: R-9b4e335bbd
type: report
title: "T-46BE9A0F: приоритет очереди, сканы на воркере, inline-PDF без OCR"
task: T-46BE9A0F
status: final
created_at: 2026-11-23T18:03:12.887Z
updated_at: 2026-11-23T18:03:12.887Z
---

# T-46BE9A0F — Сканы на воркере ПК, приоритет в очереди, inline-PDF без OCR

Задача: `T-46BE9A0F` (feature/M, эпик `E-46E212B4`). План: `plans/T-46BE9A0F/v1.md` (v1, approved 2026-11-23). Ветка приложения `devkit/T-46BE9A0F` от `main@1baa23f373611ffd4c8409f4fb44b6af4a02d043`. Режим AgentTeam (backend-engineer, frontend-engineer, architect, test-engineer, skeptic).

## Что сделано

- **Ручное поднятие в очереди (LIFO только для поднятых).** `jobs.prioritized_at` (nullable) + миграция `0007_job_priority`. `claim` и `GET /api/jobs?status=queued` сортируют `prioritized_at IS NULL, prioritized_at DESC, created_at, id`: поднятые идут первыми в обратном порядке поднятия, остальные — FIFO. Новый `POST /api/documents/{id}/prioritize`: 404 на чужой/несуществующий документ, 409 если задания нет / оно не `queued`, атомарный `UPDATE ... WHERE owner_id=? AND status='queued'` с проверкой rowcount → при гонке с claim 409 и `prioritized_at` не записан. Новой job не создаётся, статус документа и текущая обработка не меняются, повторный вызов обновляет время.
- **Серверный OCR не выполняется.** `analyze_file(..., ocr=False)` в `_run_fast`; `extract_file(..., ocr)` пробрасывает флаг в `extract_pdf`; изображение при `ocr=False` даёт `needs_review` с причиной `ocr disabled on server` и не вызывает tesseract. Политика `should_defer` не менялась: сканы и PDF без текстового слоя по-прежнему `queued`; текстовый PDF с пустой страницей загружается `ready`/`needs_review` без 500 и без удаления оригинала.
- **UI.** `viewer`: тип `WorkerStatusInfo`, одна константа порога 10 мин, `workerConnection` (UTC-парсинг naive `last_seen_at`, битая дата → offline) и общие подписи; «Документы» — баннер состояния воркера (не настроен / не подключался / нет связи >10 мин / на связи) с текстом «файл сохранён, обработка не отменена, начнётся при подключении ПК», опрос статуса воркера вместе со списком, кнопка «Обработать следующим» в списке и карточке для `queued`, человеческие 409/404; «Задания» — названия файлов из `/api/documents`, «Сейчас обрабатывается: <название>», отдельная панель «Очередь (порядок обработки)» по `/api/jobs?status=queued` с пометкой «Следующий, позиция N из M», состояние воркера в блоке токена.
- **Тесты.** Добавлены сценарии в `tests/test_documents.py` (prioritize 200/409/404/гонка, inline-PDF без tesseract), `tests/test_ingest_acceptance.py` (LIFO C→B→A для claim и списка), `tests/test_knowledge.py` (ocr=False не вызывает tesseract, `should_defer` не изменился). Расширение scope, согласованное владельцем в этой сессии: одна строка реестра в `tests/test_isolation.py` — новый маршрут в матрице тел запросов, без ослабления проверки.

## Изменения

Коммиты в `repo/atlas` (diff от `main@1baa23f`, кандидат `c3d420776cda20fbc5756bad70443537d9a3f4be`):

- `8edd2a5` `[T-46BE9A0F] job priority queue + server fast path without OCR`
- `5e1125c` `[T-46BE9A0F] viewer: worker status banner, prioritize, queue order`
- `c3d4207` `[T-46BE9A0F] test: register prioritize route in isolation body map`

Файлы (14): `app/backend/models.py`, `alembic/versions/0007_job_priority.py` (новый), `app/backend/routers/{documents,worker,jobs}.py`, `app/backend/knowledge/{pipeline,extract}.py`, `viewer/src/api.ts`, `viewer/src/pages/{Documents,Jobs}.tsx`, `tests/test_documents.py`, `tests/test_ingest_acceptance.py`, `tests/test_knowledge.py`, `tests/test_isolation.py` (+1 строка, согласовано владельцем).

Вне scope правок нет: `should_defer`, `scripts/worker.py`, протокол `claim/complete/fail`, `settings_worker.py`, миграции 0001–0006, `tests/test_worker*.py`, `tests/test_migrations.py`, остальные страницы viewer, Яндекс.Диск, зависимости, `devkit.yaml` не тронуты. `git status --porcelain` пуст; артефакты `viewer/dist` не коммитятся.

Data-репозиторий: план v1 (не менялся) и этот отчёт. Временные логи проверок, случайно попавшие в автоматический devkit-коммит `cd2d762`, удалены отдельным коммитом `35baae3`.

## Проверки

Кандидат `c3d4207`; devkit codeSha `bce4ad9d19107904f5fcc15698e57675aa026481`.

| Проверка | check id | exit | sha | результат |
| --- | --- | --- | --- | --- |
| `unit-tests` (required) | `CH-57bf1cb82fae` | 0 | `bce4ad9d…` | Ran 379 tests, OK |
| `web-build` | `CH-91553a7af144` | 0 | `bce4ad9d…` | `npm ci && npm run build`, tsc+vite OK |
| `ingest-fixtures` | `CH-c873cb06767e` | 0 | `bce4ad9d…` | `tests.test_ingest.IngestTests.test_fixtures_processed`, OK |

Baseline на базе `main@1baa23f` (codeSha `eb3223dd`): `unit-tests` `CH-9aa44bc51127` passed, `web-build` `CH-5a9826d185a1` passed. Промежуточный кандидат `5e1125c` падал `CH-68c7d432b592` (тест-реестр изоляции не знал новый маршрут); исправлено `c3d4207`, падение больше не воспроизводится.

Дополнительно (не check-события): `alembic upgrade head` → `downgrade 0006_notifications` → `upgrade head` на временной SQLite: exit 0/0/0, `alembic current` = `0007_job_priority (head)`, временная БД удалена. Ручной API-сценарий A2/A5 на временной SQLite (TestClient): 18/18 PASS — скан → `queued`, `worker-status` (не настроен → never connected → online после claim), prioritize running → 409 с человеческим detail, LIFO order и claim `scan3 → scan2`, чужой/несуществующий → 404, `processing`-документ в списке.

Независимые гейты на кандидате:

| kind | роль | id | вердикт |
| --- | --- | --- | --- |
| `code` | architect | `G-0e04cd579923` | approve |
| `test` | test-engineer | `G-9363e3e7f25a` | approve |
| `security` | skeptic | `G-563739356d50` | approve (advisory) |

Проверяющие не авторы кода; код не правили. test-engineer воспроизвёл все три обязательные проверки на `c3d4207` (379 OK, build 0, fixtures 0), негативные сценарии (48/48), PG-порядок на временном кластере и мутационные проверки (тесты падают без `prioritized_at` в ORDER BY / при `ocr=True`); architect проверил `ORDER BY` на обоих диалектах, гонку claim↔prioritize, миграцию; skeptic — ownership/404, стрессе 60 итераций (0×500, при 409 `prioritized_at` NULL), минимальность и свежесть доказательств.

### Сверка плана/acceptance/scope (sync)

| # / шаг | Доказательство | Статус |
| --- | --- | --- |
| A1 скан → `queued`, job `extract`, оригинал, без серверного tesseract | `test_documents`, `test_ingest_acceptance`, `test_knowledge`; `_run_fast(ocr=False)` | выполнен |
| A2 UI: состояние воркера + текст «сохранён/не отменена/начнётся» | код `Documents.tsx`/`api.ts`, `workerConnection` 10/10 границ (test-engineer, skeptic), строки в собранном бандле, ручной API-сценарий `worker-status`; **визуально не проверено** | выполнен по коду/данным, визуальный чек — за владельцем |
| A3 prioritize 200/409/404/гонка | `test_documents` (5 тестов), ручной API-сценарий, стресс skeptic (0×500, 409 без записи) | выполнен |
| A4 LIFO поднятых, FIFO остальных, тот же порядок в `GET /api/jobs` | `test_ingest_acceptance`, ручной сценарий, PG-проверка test-engineer/architect | выполнен |
| A5 «Задания»: название и порядок; «Документы»: кнопка и офлайн-сообщение | код `Jobs.tsx`/`Documents.tsx`, `web-build`, dist-бандл; **визуально не проверено** | выполнен по коду/сборке, визуальный чек — за владельцем |
| A6 inline-PDF без tesseract → `ready`/`needs_review`, не 500, оригинал на месте; скан-PDF `queued` | `test_documents`, `test_knowledge`, мутация (`ocr=True` ломает тест) | выполнен |
| A7 single-flight/lease/cancel/изоляция/статусы; три проверки зелёные | `CH-57bf1cb82fae`, `CH-91553a7af144`, `CH-c873cb06767e`; `test_worker`, `test_worker_pg`, `test_migrations`, `test_isolation` без ослаблений | выполнен |
| Шаг 0 baseline/alembic head | baseline-проверки зелёные; `alembic heads` = `0006_notifications` до ветвления | выполнен |
| Шаг 1 приоритет | миграция `0007_job_priority`, claim/list_jobs, `POST .../prioritize` | выполнен |
| Шаг 2 inline-PDF без OCR | `extract_file`/`analyze_file`/`_run_fast` | выполнен |
| Шаг 3 backend-тесты | три тестовых модуля | выполнен |
| Шаг 4 UI | `viewer/src/api.ts`, `Documents.tsx`, `Jobs.tsx` | выполнен |
| Шаг 5 сборка/сдача | проверки, ручной API-сценарий, этот отчёт | выполнен (визуальный чек не выполнен) |
| Scope плана | 13 файлов плана; +`tests/test_isolation.py` (1 строка, согласовано владельцем) | расхождение согласовано |
| Uncommitted/секреты/временные артефакты | `git status --porcelain` пуст; логи удалены; токены не печатались | чисто |

## Риски

- **Визуальный UI A2/A5 не проверен**: браузерного E2E в проекте нет. Подтверждены данные API, скомпилированная логика состояний и наличие строк/кнопок в собранном бандле; внешний вид и реальные клики требуют ручного чека владельцем. За ручную проверку не выдаётся.
- **Карточка задачи устарела**: «100 МБ» и «скан становится ready на сервере» не соответствуют решению владельца от 2026-11-22 (серверный tesseract на VPS не разрешён) и фактическому дефолту `ATLAS_PDF_INLINE_MAX_BYTES` = 50 МБ. Лимит не менялся; серверный OCR не делался.
- **Minor (architect/skeptic, не блокеры):** `prioritize` отвечает `UploadOut` вместо обещанного планом `DocumentOut` (совместимо, `UploadOut` — наследник); нет `except OperationalError` вокруг UPDATE (на SQLite при удержанной write-блокировке редкий 500 вместо 409; прод-дефолт — PostgreSQL, в стрессе 60 итераций не воспроизвелось); `last_seen_at` с микросекундами парсится в V8 успешно, в не-V8 даст `offline` (безопасное направление); панель «Очередь» в «Заданиях» добавляет до 4 запросов на reload и дублирует список при фильтре `queued`, `JobOut` не отдаёт `prioritized_at` (поднятые визуально не отличаются — вне acceptance); счётчики баннера считают отфильтрованный список.
- **Pre-existing, не в diff:** при прочих ошибках извлечения `_upload_file` по-прежнему удаляет оригинал; A6 «оригинал не удаляется» гарантирован для пути без tesseract. Отдельная задача при необходимости.
- **R3 плана:** порог 10 минут может дать ложный «офлайн» при сильном расхождении часов сервера и браузера — одна константа для правки.
- **Без воркера очередь остаётся `queued` неограниченно** (принято): UI объясняет ожидание и позволяет поднять документ вручную; TTL/автоотмены нет.
- **PG:** порядок и миграция проверены на временном PG-кластере, но `prioritize` по HTTP на PG и downgrade `0007` на заполненной PG-БД не гонялись.

**Откат:** revert коммитов `8edd2a5`, `5e1125c`, `c3d4207`; `alembic downgrade 0006_notifications` (удаляет только `jobs.prioritized_at`). UI-изменения аддитивные, старый API и статусы продолжают работать.
