---
id: R-988ddf7416
type: report
title: Отчёт T-6BD45D6E
task: T-6BD45D6E
status: final
created_at: 2026-11-28T11:07:09.299Z
updated_at: 2026-11-28T11:07:09.299Z
---

# Отчёт T-6BD45D6E — Навигация-острова LiquidGlass и верхняя панель из двух островов

- Эпик: **E-47FF66EB** (Graphite v2), ТЗ `docs/tz/TZ-9E3B177B.md`, R6 и R0.1–R0.7.
- План: `plans/T-6BD45D6E/v2.md`, статус **approved** (owner, 2026-11-27).
- Ветка: `devkit/T-6BD45D6E`, коммит: `6d13a35d` (`feat(web): [T-6BD45D6E] …`).
- База: `main` = `485430f2` (включает T-12FFB688).

## Что сделано

1. Оболочка (`web/src/app/AppShell.tsx`) переведена на три независимых острова:
   - левый сайдбар — стеклянная плашка (радиус 22, внутренний блик, тень);
     внутри бренд «Atlas», группа «Основное» (Главная/Развитие/Чат/Календарь),
     подпись «Система» и группа (Проекты/Задачи/Люди/Файлы), внизу — блок
     «Индекс знаний» (ссылка на `/files`, без выдуманных чисел);
   - верхняя панель — поисковый остров по центру (фиксированная ширина
     480 px, центрируется по окну) и правый остров профиль/уведомления
     (колокольчик со счётчиком + аватар);
   - контент между островами, фон `Canvas` просвечивает.
2. «Настройки» убраны из сайдбара. Вход остался в меню профиля и добавлен в
   палитру `Ctrl+K` (`web/src/app/SearchOverlay.tsx`, блок «Перейти»).
3. Токены `--island-*` добавлены только в `web/src/app/styles/tokens.css`:
   `--island-bg`, `--island-border`, `--island-highlight`, `--island-shadow`,
   `--island-blur`, `--island-radius` — значения тёмной и светлой тем строго по
   R6.3 (вариант «Графит», блик 3 %). Магических `rgba` по компонентам нет.
4. `prefers-reduced-transparency: reduce` → непрозрачный фон островов, без
   blur; `data-effects="off"` и `prefers-contrast: more` также дают плотный
   fallback.
5. Мобильная ширина (<900 px): сайдбар сворачивается в иконки (ширина 72 px),
   подписи визуально скрыты, но остаются доступными именами ссылок; поиск и
   профиль остаются на месте, острова не пересекаются.
6. e2e `web/e2e/shell.spec.ts` обновлён: три острова и отсутствие пересечений
   по bounding box, «Настройки» нет в сайдбаре и есть в меню профиля, `Ctrl+K`
   открывает палитру с переходом в настройки, мобильный вид 390 px. Старая
   проверка ссылки «Сферы» (её нет в навигации с T-12FFB688) заменена на
   реальные пункты меню.

## Изменения

| Файл | Что |
| --- | --- |
| `web/src/app/AppShell.tsx` | три острова, группы навигации, блок «Индекс знаний», мобильный иконочный сайдбар, центрирование поиска |
| `web/src/app/SearchOverlay.tsx` | блок «Перейти» с входом в «Настройки» (Ctrl+K) |
| `web/src/app/styles/tokens.css` | токены `--island-*` для тёмной/светлой темы, reduced-transparency, effects-off |
| `web/e2e/shell.spec.ts` | e2e: три острова, отсутствие «Настроек» в сайдбаре, Ctrl+K, мобильная ширина 390 |

Diff: `git -C repo/atlas show --stat 6d13a35d` — 4 файла, +354/−147.

## Проверки

Профиль, code-sha `65b51fac` = sha256("atlas:6d13a35d…"):

| Проверка | id | Результат |
| --- | --- | --- |
| web-build | CH-9cf82c1d2bd5 | passed — `npm run build`, vite build ok |
| typecheck-web | CH-cae363a3c365 | passed — `tsc --noEmit`, 0 ошибок |
| lint-web | CH-16e9ea10463a | passed — `eslint .`, 0 |
| arch-web | CH-19a7b67c1de9 | passed — `steiger ./src`, No problems |
| e2e | CH-900ef229ac86 | passed — 21 passed (26.8 s) |
| a11y | CH-87f2bc8c7ce9 | passed — 8 passed (11.6 s), axe serious/critical = 0 |
| unit-tests | CH-84bfa9904dba | passed — Ran 468 tests, OK (272 s) |
| lint-python | CH-d79a0f5fbc79 | passed — ruff check + format --check |
| typecheck-python | CH-d97c3a58b267 | passed — mypy, 146 files |
| arch-python | CH-722d9bcabc5a | passed — 4 tests OK |

Дополнительно: горизонтальный overflow на 390 px проверен на 9 маршрутах —
`documentElement.scrollWidth == innerWidth` (0 переполнений).

Скриншоты «после»: `.tmp/design/out/a1-shell-dark.png`,
`.tmp/design/out/a1-shell-light.png`, `.tmp/design/out/a1-shell-mobile-dark.png`.

## Риски

1. Колокольчик пока показывает серверные уведомления (`/api/notifications`);
   локальная панель и тосты — задача `T-EBDB7D0F`, она заменит поведение.
2. На мобильной ширине раскладка страницы календаря (сегменты видов) занимает
   почти всю ширину; переполнения нет, но полировка тулбара — в `T-E12FC73C`.
3. `prefers-reduced-transparency` проверен по CSS/DevTools-эмуляции, не на
   реальной ОС; в браузерах без поддержки остаётся обычный blur.

## Что не проверено

1. Живой стенд (`start-atlas.ps1`) визуально не снимался: скриншоты сделаны на
   собранном `dist` с моками API, как принято в e2e проекта.
2. В сайдбаре нет пункта «Сферы» (в текущей навигации он отсутствует с
   T-12FFB688; страница доступна по `/spheres` из виджетов). Если нужен пункт в
   острове — это отдельное изменение навигации.
