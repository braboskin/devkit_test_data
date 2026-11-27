# План T-28C2A79F — экраны: Сферы, Проекты, Проект, Люди, Профиль, Развитие

## Контекст

- Шесть экранов на классовых стилях `base.css` и без обёрток:
  `pages/spheres` (сетка карточек, прогресс — `div` с шириной),
  `pages/projects` (список + карточка проекта), `pages/people` (карточки,
  2 `<input type="file">` для фото), `pages/profile` (фото, контекст,
  `type="file"`), `pages/growth` (5 нативных `<select>`, 19 `<input>`,
  1 `<textarea>`, 15 `<button>`).
- antd-first: прогресс — `Progress`, загрузка фото — `Upload`, таблицы —
  `Table`, статусы — `Tag`, даты — `DateField`, формы — `TextField`/
  `NumberField`/`SelectField`/`TextAreaField`.
- Примитивы W1: `Panel`, `PageFrame`, `PageHeader` (eyebrow), `Empty`,
  `Skeleton`, `ErrorNote`, `Tag`, `Table`, `Progress` (antd).
- API фото: `POST` upload в профиль/человека уже существует (эпик `E-AA7F23F1`,
  `UserProfile.data.avatar_ref`/`Person.photo_ref`) — контракт не меняем.

## Шаги

1. **Сферы и Проекты.** Сетка карточек — `Panel` + `PageFrame`; прогресс —
   antd `Progress` (`percent`, `size="small"`, `showInfo`), счётчики —
   `tabular-nums`; список проектов — `Table` (колонки: название, сфера,
   прогресс, даты, статус `Tag`); пусто/загрузка/ошибка — `EmptyState`/
   `Skeleton`/`ErrorNote`.
2. **Проект.** `PageHeader` с прогресс-кольцом (antd `Progress type="circle"`),
   дашборд — `Panel`; задачи — существующие `TreeList`/`TaskBoard`/
   `TaskGantt` (обёртки antd/SVAR), не переписывать их API.
3. **Люди и Профиль.** Карточки — `Panel`, фото — antd `Upload`
   (`showUploadList`, `beforeUpload` проверяет тип/размер, `customRequest` на
   существующий эндпоинт), фолбэк — `Avatar`; поля — обёртки; контекст
   «передавать агенту» — `SwitchField`.
4. **Развитие.** Нативные контролы → обёртки (цели/привычки/метрики/дневник),
   habit-стрики — `Tag`/`Progress`, метрики — Recharts (не менять), табы —
   `Tabs` (antd), историю обзоров — `Collapse` при необходимости.
5. **Проверки.** `tsc/eslint/steiger/prettier/build`; `a11y` (`/spheres`,
   `/profile` уже в списке) + ручная сверка; e2e оболочки.

## Acceptance

- A3 (часть): шесть экранов на примитивах, обе темы читаемы, нет светлых
  островов, фокус виден.
- A11 (часть): `Progress` вместо div-баров, `Upload` вместо `<input type=file>`,
  нативных `<select>/<input>/<textarea>` в этих экранах нет.
- Загрузка фото работает (успех/ошибка/пусто), контракт API не изменён.
- `a11y` (axe serious/critical = 0) на маршрутах из `a11y.spec.ts`.

## Проверки

`web-build`, `typecheck-web`, `lint-web`, `arch-web`, `e2e`, `a11y`,
`format-web`.

## Scope

`viewer/src/pages/spheres/**`, `viewer/src/pages/projects/**`,
`viewer/src/pages/people/**`, `viewer/src/pages/profile/**`,
`viewer/src/pages/growth/**`.

Вне scope: `shared/ui/**`, бэкенд загрузки (используем существующие
эндпоинты), `base.css`.

## Риски

1. **Upload** меняет UX загрузки: нужен явный прогресс и ошибка типа/размера;
   существующие ограничения сервера не ослаблять.
2. **Growth** — самый большой экран (≈1100 строк), правки по секциям; следить
   за `react-hooks/exhaustive-deps` без подавлений.
3. **Recharts** не на Emotion: цвета осей/сетки — через `vendor.ts`/пропсы,
   не перекрашивать внутренние классы.
4. **Progress** в карточках сфер: не потерять `aria`-семантику и подписи процентов.
