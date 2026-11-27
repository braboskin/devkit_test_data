# T-607A3128 — Качество: E2E, axe, ленивая загрузка, снос старого

## Что сделано

- **Playwright + axe** (`viewer/e2e`, `viewer/playwright.config.ts`):
  devDependencies `@playwright/test`, `@axe-core/playwright`; тесты идут против
  `vite preview` собранного `dist` с замоканными `/api/**` (`e2e/mockApi.ts`) —
  бэкенд и БД в CI не нужны.
  - `shell.spec.ts`: оболочка/навигация, ленивый календарь, сохранение темы.
  - `a11y.spec.ts`: axe на Главной, Сферах, Уведомлениях, Календаре, Профиле;
    падение при `serious`/`critical`. Внутренняя разметка FullCalendar
    исключена точечно (`exclude('.fc')`) с комментарием — это сторонний виджет.
- По итогам axe исправлены две реальные проблемы: контраст описания antd
  `Empty` (`.ant-empty-description`) и отсутствие подписи у поля фона в профиле
  (`aria-label`).
- **Ленивая загрузка**: `/projects/:id` (SVAR) и `/calendar` (FullCalendar)
  грузятся отдельными чанками; `shared/ui` экспортирует `CalendarGrid`,
  `TaskBoard`, `TaskGantt` через `React.lazy`, виды календаря вынесены в
  `calendarViews.ts` без тяжёлых импортов.
- **Снос старого**: удалены неиспользуемые слайсы `pages/today`,
  `pages/documents` и старый диалоговый `pages/onboarding`; редиректы
  `/today`→`/`, `/documents`→`/files`, `/documents/:id`, `/interests`→`/spheres`
  сохранены в роутере.
- **Опрос статусов файлов** перенесён из удалённой страницы документов в
  `pages/files` (`POLL_MS`, `setInterval`/`clearInterval`, `documents.reload`).
- **Проверки**: в профиль добавлены `e2e` и `a11y` (с установкой chromium);
  в CI (`web` job) добавлен шаг Playwright. Существующие проверки не менялись.
- Тесты обновлены без ослабления: `test_web_build` читает `pages/files` вместо
  удалённого `Documents.tsx`; `test_ag12` разрешает ровно две новые
  devDependency (Playwright/axe) с пометкой «по плану S4»;
  `test_ab12` читает `Home.tsx` вместо удалённого `Today.tsx`; `test_ag18` уже
  проверял новый визард.

## Изменения

Ветка `devkit/T-607A3128`:

- `2bf95df` — e2e+axe, ленивые чанки, снос старых страниц.
- `117d834` — удаление неиспользуемого слайса `onboarding`.

Файлы: `viewer/e2e/*`, `viewer/playwright.config.ts`, `viewer/package.json`,
`viewer/src/app/router.tsx`, `viewer/src/shared/ui/{index.tsx,calendar.tsx,calendarViews.ts,ui.css}`,
`viewer/src/pages/{files,profile}`, `.github/workflows/ci.yml`, `devkit.yaml`
(data), `tests/test_web_build.py`, `tests/test_viewer_acceptance.py`,
`viewer/.gitignore`, `viewer/.prettierignore`.

## Проверки

| Проверка | Результат |
|---|---|
| web-build | exit 0; index 155.2 kB + ui 1078.4 kB (≈386 kB gzip), ленивые: calendar 267.8 kB, gantt 271.1 kB, board 95.8 kB; CSS тоже разделён |
| typecheck-web | exit 0 |
| lint-web | exit 0, 0 подавлений |
| arch-web | exit 0, Steiger «No problems found» |
| format-web | exit 0 |
| e2e | exit 0, 8 passed (5 axe + 3 сценария) |
| a11y | exit 0, 5 passed |
| unit-tests | exit 0, 439 OK |
| web-тесты Python | `test_web_build`, `test_viewer_acceptance` — 17 OK |

Начальный бандл до задачи: 1886.6 kB / 582.9 kB gzip; после: 1233.6 kB /
386.1 kB gzip (SVAR и FullCalendar — в отдельных чанках).

## Риски

- **E2E на моках**: расхождение моков с реальным контрактом не поймается
  бэкендом. Правило: при изменении API обновлять `e2e/mockApi.ts`.
- **axe исключает внутренности FullCalendar** (`.fc`): собственные a11y-ошибки
  библиотеки не проверяются; остальная страница аудируется. Кандидат — апгрейд
  FullCalendar.
- **Playwright в CI**: self-hosted Windows должен скачать chromium (шаг добавлен,
  кэш npm-браузеров переиспользуется); при недоступности сети e2e упадёт —
  эскалация, не skip.
- **Один воркер** (`workers: 1`) для стабильности preview/моков: прогон 8 тестов
  ~9 секунд, приемлемо.
- **Обновления тестов** (allowlist devDeps, пути файлов) — следствие плана S4,
  утверждённого владельцем; проверки не ослаблены, P0/P1-покрытие сохранено.
- **Старые экраны** `settings`/`jobs`/`tasks` остаются на нативном HTML —
  отдельная задача T-3FEAB172; бэкенд `/api/onboarding` (диалог) больше не
  используется UI, но остаётся рабочим и покрытым тестами.
