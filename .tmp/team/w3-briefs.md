# W3–W5 — брифы: экраны и переименование

Общие правила (как в `w1-briefs.md`): роль `frontend-engineer` / `test-engineer`,
промпт роли читать из `.agents/prompts/`, только свой scope, git и devkit не
трогать, `console`/`any`/подавлений нет, стили — `@emotion/styled` + `var(--*)`
(никакого css-prop), публичный API `shared/ui` заморожен, antd-first (ТЗ R1.9),
перед ответом — `tsc`, `eslint .`, `steiger ./src`, `prettier --check .`,
`npm run build` с exit code. e2e/a11y гонит lead после сборки.

Каждая задача — отдельная ветка `devkit/<task-id>`; WS внутри задачи работают
параллельно по непересекающимся файлам.

---

## T-F4778357 — Главная, Чат, Вход, Онбординг

**WS-H1 (frontend, Главная + Вход):** `pages/home/**`, `pages/login/**`.
`PageFrame` + `PageHeader` (eyebrow с датой), KPI на `Panel` с `tabular-nums`,
виджеты `Panel`, задачи с antd `Checkbox` + `Tag`, состояния
`Skeleton`/`EmptyState`/`ErrorNote`, появление панелей `m` (stagger ≤ 8).
Вход: `Panel` + `TextField` (пароль `autoComplete="current-password"`), ошибка
`Alert`, `Button loading`.

**WS-H2 (frontend, Чат + Онбординг):** `pages/chat/**`, `app/SetupWizard.tsx`.
Чат: список чатов `Panel` (активный `--accent-soft`), выбор агента `SelectField`
вместо нативного `<select>`, тред `m` на появлении, композер с фокус-кольцом
(Enter/Shift+Enter сохранить), tool-call карточка на `--sunken`, трейс `<details>`
→ antd `Collapse`. Онбординг: `PageFrame`, степпер antd `Steps`, поля — обёртки,
`ModelStep` не переписывать (импорт `LlmSettingsForm`), deep link/localStorage
логику не менять.

**Проверки:** e2e `onboarding.spec.ts` зелёный; axe на `/`; ручная сверка с
`graphite-home-dark`.

---

## T-7805803A — Календарь, Задачи, Файлы

**WS-C1 (frontend, Календарь):** `pages/calendar/**`, `shared/ui/calendar.tsx`
(скин), `shared/ui/vendor.ts` (только переменные FullCalendar).
Вид (`Год/Месяц/Неделя/День/Agenda`) — antd `Segmented`; тулбар `Button`;
панель — `Panel`; тема через `--fc-*` на токенах; удалить
`pages/calendar/ui/calendar.css`.

**WS-C2 (frontend, Задачи + Файлы):** `pages/tasks/**`, `pages/files/**`.
Задачи: 8 `<select>`/5 `<input>`/5 `<button>` → обёртки (`SelectField`,
`TextField`, `DateField withTime`, `SelectField mode="multiple"`, `Button`),
статусы `Tag`, `.ui-board`/`.ui-gantt` сохранить. Файлы: фильтры `SelectField`,
`Table`, `DocBadge`, antd `Pagination` при наличии `total` (иначе «Дальше» —
зафиксировать), удалить `pages/files/ui/files.css`.

**Проверки:** e2e `shell.spec.ts` (`.ui-gantt`, ленивые чанки), axe
`/calendar` (exclude `.fc`).

---

## T-28C2A79F — Сферы, Проекты, Проект, Люди, Профиль, Развитие

**WS-S1 (frontend, Сферы + Проекты + Проект):** `pages/spheres/**`,
`pages/projects/**`. Карточки `Panel`, прогресс antd `Progress` (с подписью
процента), список проектов `Table`, статусы `Tag`, `PageFrame`.

**WS-S2 (frontend, Люди + Профиль + Развитие):** `pages/people/**`,
`pages/profile/**`, `pages/growth/**`. Фото → antd `Upload` (`beforeUpload`:
тип/размер, `showUploadList`, `customRequest` на существующий эндпоинт),
фолбэк `Avatar`; поля — обёртки; Growth: 5 `<select>`/19 `<input>`/15 `<button>`
→ обёртки, табы antd `Tabs`, Recharts не переписывать (цвета через
`vendor.ts`/пропсы).

**Проверки:** axe `/spheres`, `/profile`; ручная сверка обеих тем.

---

## T-7E446096 — Настройки, Агенты, Уведомления, Задания, Поиск, Space + legacy

**WS-F1 (frontend, Настройки):** `pages/settings/**` — секции `Panel`:
Оформление (`ThemePanel` из W1: тема, 8 пресетов, эффекты, фон), Профиль-JSON
(`TextAreaField` + прежняя валидация), Уведомления (`SwitchField`, тихие часы),
Яндекс.Диск, push; `<details class="token-fallback">` → `Collapse`. Секцию
«Модель» (`LlmSettingsForm`) не переписывать. Сохранить литералы, которые ищет
`test_web_build` (`yadiskDisconnect`, `get('yadisk')`, «Подключить
Яндекс.Диск»).

**WS-F2 (frontend, второй контур):** `pages/agents/**`,
`pages/notifications/**`, `pages/jobs/**`, `pages/search/**`,
`pages/space/**`, `app/SearchOverlay.tsx`. Списки `Panel`, статусы `Tag`,
Задания `Table` + `Progress`, результаты поиска `mark`, оверлей — общие
примитивы + `aria-live`.

**WS-F3 (lead, после F1/F2):** удалить `styles/base.css` и `styles/shell.css`,
`styles.css` = только `@import './styles/tokens.css'`; `rg` по разметке на
остатки `.panel/.field/.card/.badge/.cards-grid/.profile-menu/.accent-swatch`
(кроме `theme.tsx` — его классы перевести в Emotion перед удалением).

**Проверки:** полный профиль + e2e + a11y; A1 закрывается здесь.

---

## T-EAD5B055 — переименование `viewer/` → `web/`

**WS-RN (test-engineer + lead):** `git mv viewer web` отдельным коммитом;
`web/package.json` → `atlas-web` (+ lock, оба места); `devkit.yaml` (7 `cwd`,
`install-viewer` → `install-web`, имена проверок не трогать);
`.github/workflows/ci.yml` (`working-directory: web`, artifact `web-dist`);
`.pre-commit-config.yaml`, `pyproject.toml`; `app/backend/main.py`
(`ROOT / "web" / "dist"`, `name="web"`);
`tests/test_viewer_acceptance.py` → `tests/test_web_acceptance.py` (переименовать,
не удалять), пути в `test_web_build.py`, `test_growth.py`, `test_app_auth.py`,
`test_push.py`; `AGENTS.md`, `README.md`, `app/README.md`. Архив
`docs/coordination/archive/DEVKIT.md` не трогать.

**Проверки:** полный профиль (все 10 обязательных), e2e (сборка в `web/dist`),
`rg -i viewer repo/atlas` → только архив.
