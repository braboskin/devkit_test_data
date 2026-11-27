# T-10397B12 — Гант: drag/resize задач

## Что сделано

- `shared/ui/gantt.tsx`: снят `readonly`; подписан `onUpdateTask` (событие
  SVAR `update-task`), даты начала/конца переводятся в настенное время
  (`YYYY-MM-DDTHH:mm:ss`) через dayjs и отдаются наверх через `onUpdate(id,
  {start_at, due_at})`. Задачи без дат по-прежнему не рисуются и не тянутся.
- `ProjectPage`: `onUpdate` → `PATCH /api/tasks/{id}` с изменёнными датами;
  после успеха и после ошибки — `tasks.reload()` (откат при ошибке), ошибка
  показывается `alert` (как в доске).
- E2E: новый сценарий «проект: гант грузится отдельным чанком» — открывает
  `/projects/1`, переключает на «Гант» и проверяет `.ui-gantt`; мок задач
  отдаёт задачу с `start_at/due_at`.
- Существующие e2e/a11y не ломались.

## Изменения

Ветка `devkit/T-10397B12`, коммит `701c552`.

Файлы: `viewer/src/shared/ui/gantt.tsx`,
`viewer/src/pages/projects/ui/ProjectPage.tsx`,
`viewer/e2e/{mockApi.ts,shell.spec.ts}`.

## Проверки

| Проверка | Результат |
|---|---|
| web-build | exit 0 |
| typecheck-web / lint-web / arch-web / format-web | exit 0 |
| e2e | exit 0, 9 passed (в этой ветке; onboarding-спека в отдельном PR) |
| a11y | exit 0, 5 passed |
| web-тесты Python | 17 OK |
| unit-tests | exit 0 (полный прогон) |

## Риски

- **Drag проверен смоук-тестом**, а не реальным перетаскиванием: событие
  `update-task` wiring проверяется типами и загрузкой ганта; ручная проверка
  на стенде рекомендована (SVAR может требовать editor-контекст при первом
  перетаскивании).
- После drag SVAR может оставлять внутреннее состояние до перезагрузки —
  принудительный reload по ответу сервера это снимает.
- Если SVAR в бесплатной версии ограничивает drag (PRO), поведение выявится на
  ручном шаге; тогда — эскалация, а не тихая подмена.
