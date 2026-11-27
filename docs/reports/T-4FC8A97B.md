---
id: R-0b6f59a129
type: report
title: Отчёт T-4FC8A97B
task: T-4FC8A97B
status: final
created_at: 2026-11-27T17:05:45.960Z
updated_at: 2026-11-27T17:05:45.960Z
---

# Отчёт T-4FC8A97B — дизайн-система: токены, Emotion, шрифт, motion, примитивы, каркас

## Что сделано

Фундамент дизайн-системы Graphite: тема, токены, шрифт, motion, примитивы и
каркас приложения переведены на `@emotion/styled` + `motion`, antd-компоненты
получили токены через `ConfigProvider`, сторонние виджеты — через `vendor.ts`.

Выполнено тремя workstream'ами AgentTeam в параллель (WS-A/WS-B/WS-C), затем
сведено лидом: экспорт `m`/`MotionProvider` в публичном API `shared/ui`,
переход маршрутов на `motion` (вместо CSS-анимации WS-C), фикс контраста
antd-уведомлений, обновление allow-list зависимостей в тесте.

- A1 (часть): компонентные стили `shared/ui` и каркаса — Emotion; `ui.css`
  удалён; `styles.css` = `base.css` (legacy) + `tokens.css`.
- A2: Roboto Condensed 400/500/700 из `@fontsource/roboto-condensed@5.3.0`
  (OFL) лежит в `public/fonts`, `@font-face` + `unicode-range`, preload 400
  (cyrillic+latin), `font-display: swap`.
- A4: `data-effects="off"` → непрозрачные поверхности и `--blur: 0`;
  `prefers-reduced-motion` обнуляет длительности, motion уважает
  `MotionConfig reducedMotion="user"`.
- A5 (часть): переход маршрута через `m` (fade + 8px, 260 мс) в `AppShell`.
- A6 (часть): тема/акцент/эффекты/фон применяются сразу, дефолт акцента
  `#334155`, значения переживают перезагрузку.
- A11 (часть): `Avatar`→antd `Avatar`, `Skeleton`→antd `Skeleton`,
  `Badge`/`DocBadge`/`JobBadge`→antd `Tag`, `TreeList`→antd `Tree`,
  `Empty`→antd `Empty`, дубль `EmptyState` удалён.

## Изменения

**Зависимости:** `@emotion/react@^11.14`, `@emotion/styled@^11.14`,
`motion@^14.14` (+ lock). Шрифты вендорены файлами, рантайм-зависимости нет.

**Токены и тема:** `viewer/src/app/styles/tokens.css` переписан на Graphite
(тёмная по умолчанию, `:root[data-theme='light']`); S0–S3, стекло, тень,
радиусы, длительности, `prefers-contrast`, legacy-алиасы для `base.css`.
`shared/lib/theme.ts` — `FONT_STACK` и дефолт акцента. `shared/ui/theme.tsx` —
`ConfigProvider` + Emotion `Global` + `vendor.ts` внутри `ThemeProvider`,
`LazyMotion`/`MotionConfig` там же. Новые `global.tsx`, `motion.tsx`,
`vendor.ts`.

**Примитивы:** `controls.tsx` (11 контролов, API и `name`-проброс сохранены),
`surface.tsx` (+`Panel`, `PageFrame`), `PageHeader`, `Avatar`, `TreeList`,
`States` (antd `Skeleton`), `index.tsx` (antd `Tag`/`Empty`, `Note` с
`aria-live`), `table.tsx`. Удалён `shared/ui/ui.css`, `.ui-gantt`/`.ui-board`
перенесены в `vendor.ts` (классы сохранены — e2e).

**Каркас:** `AppShell.tsx` — стеклянный сайдбар 264px, топбар 60px (поиск
`Ctrl K`, `Tooltip`, `Dropdown` профиля, avatar), активный пункт акцентом,
`Drawer` < 960px, S0-фон, `nav`/`a`-семантика; `App.tsx` — офлайн/логин на
Emotion; `SearchOverlay.tsx` — antd `Modal` + primitives + `aria-live`.
Литеральные строки для `test_web_build` сохранены.

**Документация:** `repo/atlas/docs/DESIGN-SYSTEM.md` (токены, слои,
типографика, motion, antd-first, a11y, запрет css-prop). `docs/DESIGN.md` не
тронут — это отдельный технический дизайн.

**Интеграция (лид):** экспорт `m`/`MOTION_EASE`/`MotionProvider`;
`AppShell` — переход маршрута на `m` (`PAGE_ENTER`, 260 мс); antd-токены
переведены с `var(--*)` на конкретные цвета по резолвнутой теме (antd выводит
палитры арифметикой и не понимает CSS-переменные — из-за этого фон alert был
`#404040` и axe давал `color-contrast`); `Alert` получил токенный цвет текста;
`tests/test_viewer_acceptance.py` — allow-list зависимостей дополнен тремя
разрешёнными по ТЗ пакетами (тест по-прежнему запрещает любые другие).

**Коммиты (repo/atlas, ветка `devkit/T-4FC8A97B`):**

- `dafeadf` build(web): Emotion и motion для дизайн-системы
- `39802a7` feat(web): Graphite-токены, тема antd, Roboto Condensed, motion, vendor-стили
- `1d0d68b` feat(web): примитивы shared/ui на Emotion и antd-first
- `d17fcb0` feat(web): каркас с стеклом, Drawer и переходом маршрутов, DESIGN-SYSTEM.md
- `e0d192f` test: разрешённые зависимости pass 2 (Emotion, motion)

**Отклонения от плана (осознанные):**

1. `shell.css` не удалён вместе с каркасом: классы `.cards-grid`,
   `.profile-menu`, `.accent-swatch*` ещё используются экранами и панелью темы.
   `base.css` и `shell.css` удаляет T-7E446096 — ТЗ R1.4 обновлено.
2. Дизайн-система положена в `docs/DESIGN-SYSTEM.md`: имя `docs/DESIGN.md`
   занято техническим дизайном на 524 строки.
3. `PageFrame` без собственного padding — отступы задаёт контент каркаса
   (иначе двойные).
4. `Alert` — antd с токенным цветом текста (внутренности не перекрашиваем,
   кроме контраста заголовка).

## Проверки

`devkit profile test` на `e0d192f` → exit 0; обязательные проверки passed:

| Проверка | Результат |
|---|---|
| web-build | passed (2.0 с) |
| typecheck-web | passed (1.3 с) |
| lint-web | passed (5.9 с) |
| arch-web | passed (1.8 с) |
| e2e | passed (7.1 с), 6 тестов |
| a11y | passed (12.1 с), 7 маршрутов, axe serious/critical = 0 |
| unit-tests | passed (279 с) |
| lint-python / typecheck-python / arch-python | passed |
| format-web | passed |

`schema-check` (required:false) красный по среде: скрипт поднимает временный
PostgreSQL и не может забиндить localhost в песочнице; на `ok` профиля не
влияет (учитываются только required).

Отдельно: baseline на `main` до правок показал ту же картину по schema-check и
падавший `e2e` — причина была в команде профиля под cmd.exe (`if
($LASTEXITCODE…)`), исправлено коммитом `f9e7f7f` в data-репозитории.

Визуальная сверка: `.tmp/design/out/ws-c-shell-real-dark.png` и
`ws-c-shell-real-light.png` (каркас совпадает с макетами
`graphite-home-dark`/`light`: стекло, сайдбар 264, топбар 60, активная плашка,
Roboto Condensed, дефолтный графитовый акцент).

## Риски

1. **Экраны ещё на legacy `base.css`/`shell.css`** — карточки и формы страниц
   остаются классового вида до своих задач (T-F4778357, T-7805803A,
   T-28C2A79F, T-7E446096). Это план, но визуально промежуточное состояние.
2. **`components` antd vs стекло** — antd получает плотные цвета из
   `ConfigProvider`, стекло живёт только в наших `Panel`/каркасе; при переносе
   карточек на `Panel` возможны двойные фоны — следить в экранных задачах.
3. **Размер бандла** — `ui`-чанк 1.26 MB (≈409 KB gzip), предупреждение Vite
   существовало и раньше; Emotion+motion добавляют немного, но за размером
   стоит следить при переводе экранов.
4. **`Tag` использует presets antd** (`success/warning/error`) вместо
   `--ok/--warn/--danger`; при требовании строгой токенности — правка в
   экранных задачах.
5. **`e2e` зависит от собранного `dist`** — при ручных прогонах без
   `npm run build` тесты идут против старой сборки (наступил в этой задаче:
   после правки `Alert` тест видел старый CSS).
