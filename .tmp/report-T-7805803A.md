# Отчёт T-7805803A — экраны: Календарь, Задачи, Файлы

## Что сделано

Три «тяжёлых» экрана переведены с классов на примитивы Graphite; вендорные
виджеты (FullCalendar, SVAR) перестали быть светлыми островами в тёмной теме.

**Календарь.** `PageFrame` + `PageHeader`; тулбар: навигация `‹ / Сегодня / ›`
на `IconButton`/`Button`, переключение вида — antd `Segmented` (обёртка добавлена
в публичный API `shared/ui`); сайдбар с мини-календарём и фильтром сфер и сетка —
две `Panel`; агенда — карточки. Тема FullCalendar — через `--fc-*` и минимальные
`.fc`-правила в `vendor.ts`. Исправлены дефекты «до»: сетка больше не сжимается
(виноват был legacy-класс `.calendar-grid` из `base.css`, а не FullCalendar),
номера недель не рисуются поверх числа дня (в месяце/годе скрыты, в неделе — в
оси с `min-width`), кнопки видов не белые-на-белом, длинные названия событий с
ellipsis, цвет текста на плашках сфер считается по яркости (`textOn()`).

**Задачи.** `PageFrame`/`PageHeader`, фильтры и форма на `Panel` и обёртках:
`TextField`, `DateField withTime` вместо `<input type="datetime-local">`,
`SelectField`, `SelectField mode="multiple"` для блокировок, `CheckboxField`,
`Button`. Доска — четыре `Panel`-колонки со счётчиками-`Badge`, карточки на
`--sunken` со статусами `Tag`; сохранена детальная карточка (связи с людьми,
блокировки, подзадачи). Нативных контролов не осталось.

**Файлы.** `PageFrame`, фильтры в `Panel`, дерево «сфера → проект → файлы» на
непрозрачной `--sunken` поверхности (стекла на теле списка нет — по правилу
дизайн-системы), статусы `DocBadge`/`Tag`, пустые состояния, сортировка, поиск.
`FilePage` также переведён на примитивы.

**SVAR (доска и гант).** Находка WS-C2 опровергла мою вводную: у библиотеки
**есть** CSS-переменные `--wx-*`, но тема включается классом
`wx-willow-theme` / `wx-willow-dark-theme` на контейнере. Достаточно навесить
класс по `useTheme()` в обёртках `board.tsx`/`gantt.tsx` и переопределить
переменные в `vendor.ts` внутри `.ui-board`/`.ui-gantt` — точечные перекраски
`.wx-*` не понадобились. Классы `.ui-board`/`.ui-gantt` сохранены (их ищет e2e).

**Интеграционные правки (лид):**
- `Segmented` добавлен в публичный API `shared/ui` и применён в календаре
  вместо временной группы кнопок (ТЗ R1.9: 3–5 вариантов — `Segmented`).
- Подключена русская локаль antd (`antd/locale/ru_RU`) и `dayjs.locale('ru')` в
  `ThemeProvider` — из-за её отсутствия датапикер показывал «Select date».
- После параллельной работы двух WS над `vendor.ts` прогнаны `tsc`, `eslint`,
  `prettier --check` — файл собран и отформатирован.

## Изменения

**Удалены:** `viewer/src/pages/calendar/ui/calendar.css`,
`viewer/src/pages/files/ui/files.css`.

**Новые:** `viewer/src/pages/calendar/ui/layout.tsx` (styled-слой слайса).

**Изменены:** `pages/calendar/ui/Calendar.tsx`, `pages/tasks/ui/Tasks.tsx`,
`pages/files/ui/{Files,FilePage}.tsx`, `shared/ui/calendar.tsx`,
`shared/ui/board.tsx`, `shared/ui/gantt.tsx`, `shared/ui/vendor.ts` (блоки
FullCalendar и SVAR), `shared/ui/controls.tsx` (+`Segmented`, `Tooltip`),
`shared/ui/index.tsx`, `shared/ui/theme.tsx` (локаль ru).

**Отклонения от плана (осознанные):**
1. Файлы остаются деревом, а не antd `Table`: группировка «сфера → проект →
   файлы» — требование исходного ТЗ; `TreeList` уже на antd `Tree`.
2. Пагинация — «Показать ещё» + строка «Показано N, начиная с M», а не antd
   `Pagination`: API `documents` отдаёт только `limit/offset`, `total` нет.
3. Поиск — `TextField` + «Найти», а не `SearchField`: у antd-поиска кнопка
   рендерилась белой из-за legacy `button[type='button']` в `base.css`.
4. На `/tasks` доска собственная (4 колонки на `Panel`), SVAR-канбан живёт на
   странице проекта — так было и раньше.

**Коммиты (ветка `devkit/T-7805803A`):**

- `9215884` feat(web): Календарь на примитивах, Segmented, тема FullCalendar
- `a4ac23f` feat(web): Задачи и Файлы на примитивах, тёмная тема SVAR
- `301439b` feat(web): Segmented в public API и русская локаль antd

## Проверки

`devkit profile test` на `301439b` → exit 0; обязательные passed: `web-build`
(2.2 с), `typecheck-web` (1.4 с), `lint-web` (6.3 с), `arch-web` (1.8 с),
`e2e` (11.6 с), `a11y` (13.4 с, axe serious/critical = 0), `unit-tests` (303 с),
`lint-python`, `typecheck-python`, `arch-python`, `format-web`.

`schema-check` (required:false) — красный по среде, как на baseline.

WS-агенты дополнительно: ручной смоук `/calendar` (все 5 видов), `/tasks`,
`/files`, `/projects/1?view=board|gantt` — 0 `pageerror`; axe на своих экранах в
dark и light — 0 blocking.

Скриншоты «после»: `.tmp/design/out/after-w4-{calendar,tasks,files}-{dark,light}.png`;
«до»: `before-w4-*` (в календаре было наложение номеров недель и белые кнопки, в
задачах — белые колонки канбана и нативные даты, в файлах — legacy-дерево).

## Риски

1. **Гант визуально не проверен на реальных данных**: в мок-данных не было
   `start_at`, полосы не рендерились; переменные темы применились (проверено
   вычисленными стилями), но бары стоит глянуть на живом проекте.
2. **Мобильная ширина <900px** для календаря/файлов не проверялась (сайдбар
   переезжает вниз) — проверить на устройстве.
3. **Legacy `base.css`** ещё влияет на нативные кнопки в непереведённых экранах;
   в этих экранах всё через обёртки, окончательно legacy уйдёт в T-7E446096.
4. **`window.alert/confirm`** в обработчиках календаря оставлены как были — вне
   рамок дизайн-перевода; заменить на `useToast`/`useConfirm` можно отдельно.
5. **Поиск в файлах** отправляется кнопкой «Найти», а не по паузе — поведение
   изменилось по сравнению с `SearchField`-версией; тесты это не ловят.
