# План T-4FC8A97B — дизайн-система: токены, Emotion, шрифт, motion, примитивы, каркас

## Контекст

- Стили: 7 `.css`, 1431 строка. `base.css` 682 — панели, поля, бейджи,
  `inline-form`, `stack`, `muted`; `shell.css` 486 — каркас, дерево,
  `skeleton-line`, `cards-grid`, `row`; `tokens.css` 122 — текущие токены;
  `ui.css` 41 — классы antd-обёрток (`.ui-*`, `.ui-board`, `.ui-gantt`);
  `calendar.css` 87, `files.css` 17, `styles.css` 3 (импорты).
- Обёртки antd уже есть (`controls`, `surface`, `overlay`, `table`, `toast`,
  `theme`), но экраны на 40% состоят из нативных контролов (115 `<button>`,
  52 `<input>`, 31 `<select>`, 6 `<textarea>`). Нативные кнопки вообще ничем не
  стилизованы: класса `.btn` нет ни в одном файле.
- Тема живёт в рантайме: `shared/lib/theme.ts` пишет в `<html>` `data-theme`,
  `data-effects`, `data-bg`, `--accent`, `--accent-contrast`; пресеты фона
  `none/aurora/mist/night` объявлены.
- E2E: `e2e/shell.spec.ts` (ссылки «Сферы»/«Календарь», тема в
  `localStorage` → `data-theme`, класс `.ui-gantt`), `e2e/a11y.spec.ts` — 5
  маршрутов, axe serious/critical = 0. `tests/test_web_build.py` читает
  исходники литералами (`status === 401`, подписи вкладок).
- Решения владельца: Graphite + стекло, компактная плотность, Roboto
  Condensed, Emotion, motion, antd-first (ТЗ R1.9). Макеты:
  `.tmp/design/out/graphite-*.png`, `mockup.html`.
- `base.css` остаётся legacy-слоем до последней экранной задачи
  (T-7E446096): экраны ещё не переведены, их классы живут там.

## Шаги

### 0. Подготовка (lead)

- `git checkout -b devkit/T-4FC8A97B` в `repo/atlas`, `devkit task status in_progress`.
- Baseline проверок профиля до правок — зафиксировать в отчёте.

### 1. Фундамент токенов и темы (WS-A, frontend-engineer)

1. Зависимости: `@emotion/react@11.14`, `@emotion/styled@11.14`, `motion@14`
   в `viewer/package.json`, `npm install` (lock в коммите).
2. `viewer/public/fonts/roboto-condensed-{400,500,700}.woff2` — взять из
   `@fontsource/roboto-condensed@5.3` (`npm pack` во временный каталог,
   subset latin/cyrillic), preload 400 в `index.html`.
3. `tokens.css` (Graphite, light/dark): canvas (`--bg0/--bg1`, 2 glow от
   акцента), поверхности (`--surface`, `--raised`, `--menu-bg`, `--sunken`,
   `--hover`), текст (`--text`, `--muted`, `--faint`), линии, семантика
   (`--accent`, `--accent-soft`, `--on-accent`, `--ok/--warn/--danger`),
   `--shadow`, стекло (`--blur`, `--blur-raised`), радиусы, длительности,
   типо-шкала. `--accent-soft`/glow — `color-mix` от `--accent`;
   `body[data-effects="off"]` → непрозрачные поверхности и `--blur: 0`;
   `prefers-reduced-motion` и `prefers-contrast` учтены.
4. `shared/lib/theme.ts`: `DEFAULT_THEME.accent = '#334155'`; остальное
   (пресеты, фон, режимы, хранение) не меняется.
5. `shared/ui/theme.tsx`: сохранить публичный API `ThemeProvider`,
   `ThemePanel`, `ThemeModeSwitch`, `useTheme`; внутри — antd `ConfigProvider`
   с `algorithm` по теме, токенами (`colorPrimary`, `colorBgContainer`,
   `colorBgElevated`, `colorBorder`, `colorText`, `borderRadius`, `fontFamily`,
   `controlHeight` 32) и Emotion `Global` (reset, `@font-face`,
   `font-variant-numeric`, скроллбары, фокус).
6. `shared/ui/global.tsx` при необходимости вынести reset; `motion.tsx` —
   `LazyMotion` + `domAnimation`, `MotionConfig reducedMotion="user"`, экспорт
   `m`; учёт `effects=off`.
7. `shared/ui/vendor.ts` — один Emotion `Global` для antd/FullCalendar/SVAR/
   Recharts: границы, фоны оверлеев, `--fc-*`, таблицы без стекла.

### 2. Примитивы (WS-B, frontend-engineer, параллельно с WS-A)

Публичный API `shared/ui/index.tsx` не меняется (`Button`, поля, `Card`,
`Tabs`, `EmptyState`, `Alert`, `Spinner`, `Modal`, `useConfirm`, `Toast`,
`PageHeader`, `Avatar`, `Avatar`, `TreeList`, `Table`, `Skeleton`, `Badge`,
`DocBadge`, `JobBadge`, `Empty`, `ErrorNote`, `Note`, `Loading`, `Panel`,
`PageFrame`).

1. `controls.tsx` — стили на Emotion поверх antd-компонентов, размеры 32/36,
   фокус-рамка акцентом.
2. `surface.tsx` — `Panel` (S2: alpha .52, blur 30, r18, border, shadow),
   `PageFrame` (header → контент max-width 1280, gutter 24), `Card`, `Tabs`,
   `Alert`, `EmptyState` на antd, `Spinner`.
3. `PageHeader.tsx` — Emotion, `eyebrow`; `Avatar.tsx` → antd `Avatar`
   (инициалы/размеры сохранить); `TreeList.tsx` → antd `Tree` (ссылки через
   `titleRender`); `States.tsx` → antd `Skeleton`, дубль `EmptyState` удалить.
4. `Badge`/`DocBadge`/`JobBadge` → antd `Tag`; `Empty` → antd `Empty`.
5. `overlay.tsx`, `toast.tsx`, `table.tsx` — themed; `.ui-gantt` и `.ui-board`
   сохраняются (перенести в Emotion-классы обёрток).
6. Удалить `shared/ui/ui.css`.

### 3. Каркас (WS-C, frontend-engineer, параллельно; API примитивов заморожен)

1. `AppShell.tsx`: сайдбар 264 (9 пунктов, активная плашка + 2px индикатор,
   `nav`/`a` семантика), топбар 60 (поиск `Ctrl K`, `Tooltip` у иконок,
   `Dropdown` меню профиля, аватар), `Drawer` при <960, S0-фон.
2. `App.tsx`: переходы маршрутов через `AnimatePresence`/`m`; офлайн-экран и
   логин на примитивах; строки `status === 401`, `setOffline(true)`,
   `<Offline` сохранить (`test_web_build`).
3. `SearchOverlay.tsx` — на примитивах и antd `Modal`, `aria-live` статуса.
4. `docs/DESIGN.md`: токены, слои S0–S3, типографика, motion, antd-first,
   a11y-минимум, правила «стекло не на теле таблиц».
5. `e2e`: классы `.ui-gantt` и `data-theme` сохранить; селекторы по ролям и
   подписям не ослаблять.

### 4. Интеграция (lead)

1. Свести WS: `styles.css` → `@import './styles/tokens.css'` +
   legacy `base.css`; удалить `shell.css`.
2. Прогнать `web-build`, `typecheck-web`, `lint-web`, `arch-web`,
   `format-web`, `e2e`, `a11y`; чинить интеграционные стыки минимально.
3. Сверить визуально с макетами `graphite-home-dark`, `graphite-chat-dark`,
   `graphite-home-light`; зафиксировать скриншот-сравнение в отчёте.
4. Коммиты: `feat(web): [T-4FC8A97B] ...` — отдельно зависимости, токены,
   примитивы, каркас; отчёт `docs/reports/T-4FC8A97B.md`; `needs_review`.

## Acceptance

- A1 (foundation-часть): `styles.css` = tokens + legacy base; `shell.css`,
  `ui.css` удалены; компонентные стили `shared/ui` и каркаса — Emotion;
  `tsc`, eslint, steiger, prettier зелёные.
- A2: Roboto Condensed 400/500/700 отдаётся с нашего origin, preload 400,
  `swap`, fallback-стек; невидимого текста нет.
- A4: `data-effects="off"` → поверхности непрозрачны, blur 0;
  `prefers-reduced-motion` отключает анимации.
- A5: переход маршрута, появление панелей/модалок, stagger списков — `motion`.
- A6 (foundation-часть): тема/акцент/эффекты/фон применяются и переживают
  перезагрузку; дефолт акцента `#334155`.
- A11 (foundation-часть): `Avatar`, `Skeleton`, `Badge`, `TreeList`, `Empty`,
  дубль `EmptyState` — antd; своих дублей не осталось.
- `e2e` и `a11y` зелёные; axe serious/critical = 0 на 5 маршрутах.
- Визуальная сверка с макетами: сайдбар/топбар/панели как на
  `graphite-home-dark`, в тёмной теме нет светлых островов.

## Проверки

`web-build` → `typecheck-web` → `lint-web` → `arch-web` → `format-web` →
`e2e` → `a11y`. Результаты — check-события devkit с commit sha; вывод с
exit code в отчёте.

## Scope

`viewer/src/shared/ui/**`, `viewer/src/shared/lib/theme.ts`,
`viewer/src/app/AppShell.tsx`, `viewer/src/app/App.tsx`,
`viewer/src/app/main.tsx`, `viewer/src/app/styles/**`,
`viewer/src/app/styles.css`, `viewer/public/fonts/**`, `viewer/package.json`,
`viewer/package-lock.json`, `viewer/index.html`, `viewer/e2e/**`,
`docs/DESIGN.md`.

Вне scope: экраны (`pages/**`, `app/SetupWizard.tsx`), `app/router.tsx`,
бэкенд, `base.css` (удаляется в T-7E446096).

## Риски

1. **base.css legacy.** Экраны до своих задач остаются на классовых стилях.
   Если фундамент уберёт `base.css`, e2e/a11y упадут — поэтому удаление
   отложено в T-7E446096 (ТЗ R1.4 уточнено).
2. **Литеральные тесты.** `test_web_build.py` ищет строки в `App.tsx`/
   `AppShell.tsx` — тексты и структуру сохраняем; ассерты не ослабляем.
3. **antd + стекло.** antd берёт цвета из `ConfigProvider`; стекло только на
   обёртках, внутренности не перекрашиваем. Контраст проверяется axe.
4. **Шрифты.** Если `@fontsource` недоступен — fallback-стек и файлы от
   владельца; код к обоим вариантам готов.
5. **Вес бандла.** `LazyMotion` + 3 веса woff2; проверить размер `dist`.
6. **Параллельные WS.** B и C идут параллельно с замороженным публичным API
   примитивов; конфликтующие правки сводит lead.
