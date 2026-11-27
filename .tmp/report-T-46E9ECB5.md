# T-46E9ECB5 — Файлы: серверные фильтры и пагинация

## Что сделано

- `GET /api/documents`: добавлены `limit` (1–200, по умолчанию 100) и
  `offset` (≥0); существующие фильтры (`sphere_id`, `project_id`, `status`,
  `q`, даты) сохранены. Ответ — тот же массив `DocumentItem`.
- `repository.list_documents`: `offset`/`limit` в SQL; при фильтре `tag`
  (пост-фильтрация в Python) страница вырезается после фильтра.
- `pages/files`: фильтры «сфера», «статус», поиск (`SearchField`) и смещение
  в URL (`?sphere=&status=&q=&offset=`), «Показать ещё» (+100), сортировка
  по имени/дате, пустое состояние с кнопкой сброса; автоопрос статусов
  (`POLL_MS`) сохранён.
- Тест `test_list_pagination_and_search`: limit/offset, разные страницы,
  пустая выдача по `q`.

## Изменения

Общая ветка/PR с T-064EF355 и T-1E96C968; коммит `ccca923`.

Файлы: `app/backend/features/documents/{repository,service,router}.py`,
`viewer/src/pages/files/ui/Files.tsx`, `tests/test_documents.py`.

## Проверки

| Проверка | Результат |
|---|---|
| unit-tests | exit 0, 441 OK (2 новых) |
| lint-python | exit 0, ruff check + format |
| typecheck-python | exit 0, mypy 145 файлов |
| arch-python | exit 0 |
| web-build | exit 0, index 158.5 kB (+ lazy-чанки) |
| typecheck-web / lint-web / arch-web / format-web | exit 0 |
| e2e / a11y | exit 0, 8 passed / 5 passed |
| web-тесты Python | 17 OK |

## Риски

- Дерево группирует загруженные страницы; полное дерево «всё сразу» требует
  серверной агрегации — не входит в задачу.
- `q` на SQLite регистронезависим только для ASCII (известное ограничение).
- `tag` по-прежнему фильтруется в Python (после выборки) — при большом объёме
  нужен JSON-фильтр в SQL (отдельная задача).
