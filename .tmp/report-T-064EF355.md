# T-064EF355 — Гант: bulk-эндпоинт зависимостей проекта

## Что сделано

- `GET /api/tasks/dependencies?project_id=`: один запрос отдаёт пары
  `[{source: blocked_by_id, target: task_id}]` по задачам проекта; ownership
  фильтруется по `Task.owner_id`, объявлен до `/{task_id}`, чтобы не попасть в
  int-роут.
- `repository.dependencies` + `service.dependencies`; ответ типизирован
  `DependencyOut`.
- `shared/api.taskDependencies(projectId)`; `ProjectPage` больше не делает
  N+1 запросов карточек — один запрос на проект.
- Тест `test_dependencies_endpoint`: пара создаётся, чужой пользователь видит
  пустой список.

## Изменения

Общая ветка/PR с T-46E9ECB5 и T-1E96C968; коммит `ccca923`.

Файлы: `app/backend/features/tasks/{repository,service,router}.py`,
`viewer/src/shared/api/index.ts`, `viewer/src/pages/projects/ui/ProjectPage.tsx`,
`tests/test_tasks.py`.

## Проверки

| Проверка | Результат |
|---|---|
| unit-tests | exit 0, 441 OK |
| lint-python / typecheck-python / arch-python | exit 0 |
| web-build / typecheck-web / lint-web / arch-web / format-web | exit 0 |
| e2e / a11y | exit 0, 8 / 5 passed |

## Риски

- Несуществующий/чужой `project_id` возвращает пустой список, а не 404:
  ownership гарантирует отсутствие утечки, но семантика «нет проекта» и
  «нет зависимостей» не различается.
- Циклы зависимостей не отсекаются на этом эндпоинте (как и раньше — это
  логика задач).
