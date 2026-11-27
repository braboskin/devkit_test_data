# T-3FEAB172 — Настройки и Задания на дизайн-системе

## Что сделано

- `pages/settings` и `pages/jobs`: все кнопки переведены на `Button` из
  `shared/ui` (включая submit-кнопки через `htmlType="submit"`), нативные
  `<button>` удалены; прямых импортов antd в страницах нет.
- Логика не менялась: LLM/Яндекс.Диск/OAuth, уведомления, push, воркер,
  задания и их отмена работают через те же обработчики.
- E2E: axe прогоняется теперь и по `/settings`, и по `/jobs` — оба без
  `serious`/`critical`. Для этого в моки добавлены `/api/settings/notifications`,
  `/api/settings/push-subscription`, `/api/jobs*`.
- Итого e2e в ветке: 10 passed (5 старых a11y + 2 новых экрана + 3 shell).

## Изменения

Ветка `devkit/T-3FEAB172`, коммит `feat(viewer): [T-3FEAB172] ...`.

Файлы: `viewer/src/pages/settings/ui/Settings.tsx`,
`viewer/src/pages/jobs/ui/Jobs.tsx`, `viewer/e2e/{mockApi.ts,a11y.spec.ts}`.

## Проверки

| Проверка | Результат |
|---|---|
| web-build | exit 0 |
| typecheck-web / lint-web / arch-web / format-web | exit 0 |
| e2e | exit 0, 10 passed |
| a11y | exit 0, 7 passed (включая Настройки и Задания) |
| web-тесты Python | 17 OK |
| unit-tests | exit 0 (полный прогон) |

## Риски

- **Переведены кнопки, а не поля**: `input`/`select`/`textarea` в формах
  настроек и фильтрах заданий остались нативными. Полный перевод полей на
  `TextField`/`SelectField` — следующий шаг; поведение и a11y сейчас сохранены
  (axe зелёный).
- **antd `Table` для очереди заданий не внедрён**: список остался прежним,
  чтобы не менять поведение пагинации/отмены; кандидат на отдельную задачу.
- Формы настроек большие: меняли только кнопки, поэтому поведение
  сохранения/проверки ключа/OAuth не затронуто.
