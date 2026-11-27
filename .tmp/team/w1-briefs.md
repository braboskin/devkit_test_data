# W1 (T-4FC8A97B) — брифы workstreams

Общее для всех WS. Роль — `frontend-engineer`, промпт роли подставляется целиком
(`.agents/prompts/frontend-engineer.md`). Задача devkit: **T-4FC8A97B** (план:
`plans/T-4FC8A97B/v1.md`). ТЗ: `docs/tz/TZ-2F2279C9.md` §R1, R1.1–R1.9.
Спецификация токенов (обязательна): `.tmp/team/design-tokens.md`. Макеты:
`.tmp/design/out/graphite-*.png` и `.tmp/design/mockup.html`.

## Правила (нарушение = задача не принята)

- Работай только в файлах своего scope. Чужие файлы не трогай: в общем дереве
  параллельно работают другие WS.
- **Yarn/npm ставит один WS-A**; B и C после установки зависимостей (если
  `@emotion/*` ещё не в `node_modules`, дождись или сообщи).
- **Git не трогай**: ни `add`, ни `commit`, ни `checkout` — коммитит и мержит
  только lead.
- **Владельческие действия не выполняй**: `--owner`, approve, done — не твои.
- Стили: только `@emotion/styled` + CSS-переменные `var(--*)`; `css`-prop,
  `jsxImportSource`, inline-стили для тем — нельзя.
- 0 подавлений: без `eslint-disable`, `ts-ignore`, `noqa`. `console` запрещён
  (`no-console: error`), `any` запрещён, `consistent-type-imports`.
- Публичный API `shared/ui/index.tsx` и существующие пропсы компонентов —
  **заморожены** (иначе экраны сломаются). Новые экспорты добавлять можно.
- Accessibilty обязательна: семантика, подписи, фокус, клавиатура, контраст
  ≥ 4.5:1, цели ≥ 32px, `aria-live` для статусов, `prefers-reduced-motion`.
- `base.css` не трогать (legacy до T-7E446096). `pages/**`, `app/router.tsx`,
  `app/SetupWizard.tsx` — вне scope W1.

## Проверки (запускать самому, результат — в ответе)

```powershell
cd repo/atlas/viewer
npx tsc --noEmit
npx eslint .
npx steiger ./src
npx prettier --check .   # свои файлы можно `npx prettier --write <files>`
npm run build
```
E2E/axe гоняет lead после сборки. Падение проверок — не оставляй «на потом».

## Формат ответа (строго)

1. `статус:` done / blocked / вопрос;
2. изменённые файлы (пути) и что именно сделано;
3. решения и отклонения от брифа;
4. вывод проверок с exit code (кратко: `tsc 0`, `eslint 0`, `steiger 0`,
   `build 0`);
5. что не проверено и риски.

---

## WS-A — токены, тема, шрифт, motion, vendor

**Файлы:** `viewer/src/app/styles/tokens.css` (переписать),
`viewer/src/shared/lib/theme.ts`, `viewer/src/shared/ui/theme.tsx`,
`viewer/src/shared/ui/global.tsx` (новый), `viewer/src/shared/ui/motion.tsx`
(новый), `viewer/src/shared/ui/vendor.ts` (новый), `viewer/src/app/main.tsx`,
`viewer/public/fonts/**`, `viewer/index.html`, `viewer/package.json`,
`viewer/package-lock.json`. `viewer/src/app/styles/shell.css` — **не удаляй**,
его удаляет lead на интеграции.

**Сделать:**

1. Установить `@emotion/react@^11.14`, `@emotion/styled@^11.14`, `motion@^14`
   (`npm install`), lock — в коммит.
2. Шрифты: взять `roboto-condensed-{cyrillic,latin}-{400,500,700}-normal.woff2`
   из `@fontsource/roboto-condensed@5.3.0` (`npm pack` в `.tmp/`, распаковать),
   положить в `public/fonts/`. В `index.html` — `preload` для
   `cyrillic-400-normal` (as="font" crossorigin) и `theme-color` → `#334155`.
3. `tokens.css` — по спецификации `.tmp/team/design-tokens.md`: Graphite
   dark/light, поверхности S0–S3, стекло, `data-effects="off"`, радиусы,
   длительности, типо-шкала. `:root` — тёмная тема; `body[data-theme="light"]` —
   светлая (текущий `theme.ts` ставит `data-theme` на `html`, проверь и
   поддержи оба селектора: `html[data-theme="light"] body` или
   `:root[data-theme="light"]`).
4. `shared/lib/theme.ts`: `DEFAULT_THEME.accent = '#334155'`; `applyTheme` —
   без изменений API; добавь `applyAccentVars` при необходимости, чтобы
   `--accent-soft`/`--glow-accent` пересчитывались из `--accent` (через
   `color-mix` в CSS, без JS).
5. `shared/ui/theme.tsx`: сохранить экспорты `ThemeProvider`, `ThemePanel`,
   `ThemeModeSwitch`, `useTheme`; внутри — antd `ConfigProvider` с
   `theme={{ algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm, token }}`,
   токены: `colorPrimary` = accent, `colorBgContainer` = `var(--surface)`,
   `colorBgElevated` = `var(--raised)`, `colorBgSpotlight` = `var(--menu-bg)`,
   `colorBorder` = `var(--border)`, `colorBorderSecondary` = `var(--border)`,
   `colorText` = `var(--text)`, `colorTextSecondary` = `var(--muted)`,
   `colorError` = `var(--danger)`, `borderRadius` 10, `controlHeight` 32,
   `fontFamily` = Roboto Condensed stack. `ThemePanel`/`ThemeModeSwitch` не
   переписывай: секция «Оформление» на `/settings` — задача T-7E446096.
6. `global.tsx`: Emotion `Global` — reset (box-sizing, margin 0), `@font-face` ×6,
   `body` фон/типографика/`tabular-nums`, `::selection`, фокус-кольцо
   (`:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px }`),
   скроллбары, `prefers-reduced-motion`.
7. `motion.tsx`: `LazyMotion` + `domAnimation`, экспорт `m`, `MotionConfig
   reducedMotion="user"`; если `data-effects="off"` — анимации 0 (проверять
   эффекты через `useTheme`).
8. `vendor.ts`: Emotion `Global` для antd (оверлеи/границы/меню — на токенах
   `var(--*)`), FullCalendar (`--fc-*` переменные, границы, today), SVAR
   (`.ui-gantt`, `.ui-board` — сохрани классы!), Recharts (цвет линий/сетки).
   `.ui-gantt`/`.ui-board` — перенести их размеры сюда, чтобы `ui.css` можно было
   удалить в WS-B.
9. `app/main.tsx`: импорт `./styles.css` оставить; обернуть в `MotionProvider`
   (из `shared/ui`), если так решишь — согласуй экспорт через
   `shared/ui/index.tsx` (это файл WS-B; либо экспорт из `motion.tsx` напрямую
   внутри `app/`, что допустимо по FSD: `app → shared`).

**Acceptance WS-A:** тёмная и светлая тема применяются, акцент из настроек
перекрашивает кнопки/фокус/прогресс; `data-effects="off"` убирает прозрачность
и blur; шрифт грузится локально (network: `/fonts/...`), preload есть;
`tsc/eslint/steiger/build` — 0.

---

## WS-B — примитивы shared/ui на Emotion + antd-first

**Файлы:** `viewer/src/shared/ui/{controls,surface,PageHeader,Avatar,TreeList,States,index,overlay,toast,table}.tsx`,
`viewer/src/shared/ui/ui.css` (удалить в конце). Не трогай `theme.tsx`,
`motion.tsx`, `global.tsx`, `vendor.ts` (WS-A) и `app/**` (WS-C).

**Сделать:**

1. `controls.tsx`: те же имена и пропсы (`Button`, `IconButton`, `TextField`,
   `TextAreaField`, `NumberField`, `SelectField`, `CheckboxField`, `SwitchField`,
   `DateField`, `ColorField`, `SearchField`); antd-компоненты внутри; стили —
   `styled` (высота 32, радиус 10, фон `var(--sunken)`, граница
   `var(--border)`, фокус-кольцо акцентом). Сохрани проброс `name` для FormData
   и `aria`-подписи (`Field`).
2. `surface.tsx`: `Card`, `Tabs`, `EmptyState`, `Spinner`, `Alert` — оставить
   API; добавить `Panel` (`styled.section` со S2-стеклом: `var(--surface)`,
   `backdrop-filter: var(--blur)`, radius 18, border, shadow) и `PageFrame`
   (`header slot + main`, max-width 1280, padding 24, gap 16).
3. `PageHeader.tsx`: сохранить пропсы `title/description/actions`, добавить
   необязательный `eyebrow`; Emotion.
4. `Avatar.tsx`: antd `Avatar` (инициалы из имени, `size` sm/md/lg → 24/32/40),
   `title`/`alt` сохранить.
5. `TreeList.tsx`: antd `Tree` — `treeData` из существующего `TreeNode[]`
   (`key`, `title` через `titleRender`, ссылки — `<a>`), `defaultExpandAll`,
   `blockNode`; `emptyLabel` → antd `Empty`.
6. `States.tsx`: `Skeleton` → antd `Skeleton` (строки, `aria-busy`); дубль
   `EmptyState` удалить, экспортируется один одноимённый из `surface.tsx`.
7. `index.tsx`: `Badge`/`DocBadge`/`JobBadge` → antd `Tag` (tone → цвет:
   ok→success, warn→warning, danger→error, info→processing, neutral→default;
   текст всегда рядом с цветом), `Empty` → antd `Empty` (компактный, с
   `description`), `ErrorNote`/`Note`/`Loading` — сохранить роли
   (`role="alert"`, `role="status"` + `aria-live`), `useResource`/`useAction`
   не менять.
8. `overlay.tsx`/`toast.tsx`/`table.tsx`: оставить API; тема через
   `ConfigProvider` (WS-A), свои классы — `styled`. `.ui-gantt`/`.ui-board`
   больше не нужны в `ui.css` — их размеры переезжают в `vendor.ts` (WS-A).
9. Удалить `viewer/src/shared/ui/ui.css`.

**Acceptance WS-B:** экраны, использующие эти компоненты, компилируются без
изменений; ни один пропс не переименован; `ui.css` удалён; `tsc/eslint/steiger/
build` — 0; визуально Button/поля/бейджи/таблицы на токенах (стекло и акцент).

---

## WS-C — каркас AppShell/App/SearchOverlay + DESIGN.md

**Файлы:** `viewer/src/app/AppShell.tsx`, `viewer/src/app/App.tsx`,
`viewer/src/app/SearchOverlay.tsx`, `repo/atlas/docs/DESIGN.md` (новый),
`viewer/e2e/shell.spec.ts`. Не трогай `shared/ui/**`, `router.tsx`,
`SetupWizard.tsx`, `pages/**`.

**Сделать:**

1. `AppShell.tsx`: сайдбар 264px (`--surface`, стекло, `border-right`), топбар
   60px (поиск `Ctrl K`, `Tooltip` у иконок, `Dropdown` меню профиля, аватар),
   активный пункт — `var(--accent-soft)` + `inset 2px 0 0 var(--accent)`, фон S0
   (canvas с glow), при `<960px` — antd `Drawer` вместо сайдбара, контент
   max-width 1280. Навигация — `<a>`/`<nav>` (не `role="menu"`). Строки,
   которые читает `tests/test_web_build.py`, сохранить: подписи «Файлы»,
   «Поиск», «Задания», «Настройки» в исходнике `AppShell.tsx`; обработку
   `has('yadisk')`.
2. `App.tsx`: офлайн-экран и логин — на примитивах; переход между маршрутами —
   `AnimatePresence` + `m`, длительность 260мс, при `effects=off`/
   `reduced-motion` — без анимации; сохранить `status === 401`,
   `setOffline(true)`, `<Offline` (литеральные тесты).
3. `SearchOverlay.tsx`: antd `Modal` + примитивы; `aria-live` статуса;
   поведение `Ctrl K`/`Esc` не ломать.
4. `docs/DESIGN.md`: токены (ссылка на `.tmp/team/design-tokens.md`),
   слои S0–S3, типографика, motion-правила, antd-first, a11y-минимум,
   правило «стекло не на теле таблиц», запрет `css`-prop.
5. `e2e/shell.spec.ts`: селекторы по ролям/подписям; `.ui-gantt` и
   `data-theme` сохранить; не ослаблять (без `force`, без таймаутов «на всякий
   случай»).

**Acceptance WS-C:** каркас как на `graphite-home-dark` (сайдбар, топбар,
стекло, активный пункт), мобильный drawer работает, переходы маршрутов
анимированы и отключаемы, `docs/DESIGN.md` существует, e2e shell — зелёный.
