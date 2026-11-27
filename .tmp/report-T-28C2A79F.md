# Отчёт T-28C2A79F — экраны: Сферы, Проекты, Проект, Люди, Профиль, Развитие

## Что сделано

Шесть экранов переведены на примитивы Graphite; загрузка фото пошла через
antd `Upload`, интерактивные подтверждения — через `useConfirm`/`useToast`
вместо `window.*`, а нечитаемый активный таб исправлен системно в обёртке.

**Сферы и Проекты (WS-S1).** `PageFrame`/`PageHeader`, формы создания и
редактирования на `Panel` и обёртках (`TextField`, `TextAreaField`,
`ColorField`, `SelectField`), карточки сфер — доступная сетка `<ul>` со ссылками
и цветовой точкой, состояния `Skeleton`/`EmptyState`/`ErrorNote`. Детальная
страница сферы: `Progress type="circle"` с процентом из `tasks_done/tasks`,
плитки метрик, проекты на `TreeList`, задачи без проекта с `Badge`. Проекты —
`Table` (название, сфера, статус, срок); страница проекта: сводка с
`Progress type="circle"`, вкладки «Список/Доска/Гант» через существующий `Tabs`,
`TreeList`/`TaskBoard`/`TaskGantt` не переписаны. `window.alert` →
`useToast().error`.

**Люди, Профиль, Развитие (WS-S2).** Люди: `PageFrame`/`Panel`, список с
`Avatar` (инициалы как фолбэк), `aria-pressed`, теги `Badge`, связи через
`SelectField`; фото — antd `Upload` через обёртку на существующий
`POST /api/people/{id}/photo` (`beforeUpload`: `image/*`, ≤10 МБ,
`showUploadList={false}`, ошибка → `ErrorNote`). Профиль: секции `Panel`
(аккаунт с `POST /api/profile/avatar`, фон `uploadBackground`/`deleteBackground`,
контекст, «Внешний вид» — `ThemePanel`). Развитие: antd `Tabs` (Цели, Привычки,
Метрики, Дневник, Обзоры, Ритм) вместо текстовых ссылок, **все** нативные
контролы (19 input / 5 select / 1 textarea / 15 button) заменены обёртками,
цели и недельные привычки — `Progress`, инлайн-SVG график сохранён с
`role="img"`, Recharts не тронут.

**Системные правки (лид):**
- В публичный API добавлены `Progress` и `Upload` (чтобы страницы не импортировали
  antd), плюс `Segmented`/`Tooltip`/`Collapse` из прошлых волн.
- **Обёртка `Tabs`**: активный таб был окрашен в `colorPrimary` (графит на
  графите — нечитаемо). Исправлено в `shared/ui/surface.tsx` для всех экранов:
  текст активного таба — `var(--text)`, состояние несёт акцентный инкбар.

**Дефекты, найденные WS и исправленные:**
1. Кнопка в antd `Input.Search` была белой из-за legacy `button[type='button']`
   в `base.css` — обёрнута в styled с `&&` (в проекте это повторяющаяся
   проблема, окончательно уйдёт с legacy-слоем в T-7E446096).
2. Форма контекста в профиле с `defaultValue` оставалась пустой до перезагрузки
   — починено через `key` на форме.
3. `window.confirm`/`window.alert` в людях/проекте заменены на `useConfirm`/
   `useToast`.

## Изменения

**Новые файлы:** `viewer/src/pages/spheres/ui/layout.tsx`,
`viewer/src/pages/projects/ui/layout.tsx` (styled-слой слайсов).

**Изменены:** `pages/spheres/{Spheres,SphereDetail}.tsx`,
`pages/projects/{Projects,ProjectPage}.tsx`,
`pages/people/ui/People.tsx`, `pages/profile/ui/Profile.tsx`,
`pages/growth/ui/Growth.tsx`, `shared/ui/{controls,surface,index}`.

**Коммиты (ветка `devkit/T-28C2A79F`):**

- `5b3c650` feat(web): Progress и Upload в public API, читаемый активный таб
- `200c57f` feat(web): Сферы, Проекты и Проект на примитивах
- `c38d325` feat(web): Люди, Профиль и Развитие на примитивах, фото через Upload

**Отклонения от плана:** прогресс в карточках сфер и в таблице проектов не
показан — в API у `Sphere`/`Project` нет поля прогресса, а тянуть summary на
каждую карточку было бы N+1. Процент показывается там, где данные уже есть —
на детальных страницах. Если нужен в списках — потребуется поле в API или
отдельное решение.

## Проверки

`devkit profile test` на `c38d325` → exit 0; обязательные passed: `web-build`
(2.1 с), `typecheck-web` (1.4 с), `lint-web` (6.5 с), `arch-web` (1.9 с),
`e2e` (14.2 с), `a11y` (13.0 с, axe serious/critical = 0 — включая `/spheres`
и `/profile`), `unit-tests` (305 с), `lint-python`, `typecheck-python`,
`arch-python`, `format-web`.

`schema-check` (required:false) — красный по среде, как на baseline.

WS-агенты дополнительно: ручной смоук `/spheres`, `/spheres/1`, `/projects`,
`/projects/1`, `/people`, `/profile`, `/growth` (вкладка «Привычки») — 0
`pageerror`; скриншоты dark/light приложены.

Скриншоты «после»: `.tmp/design/out/after-w5-{spheres,projects,people,profile,growth}-{dark,light}.png`;
«до»: `before-w5-*`.

## Риски

1. **Загрузка фото не прогнана на живом API**: `beforeUpload` вызывает загрузку
   вручную, поэтому нет полосы прогресса — только успех/ошибка. Если нужен
   прогресс, переделать на `customRequest` с локальным состоянием.
2. **Клиентский лимит 10 МБ** — выбран WS; серверные ограничения остаются
   главными, проверка их не ослабляет.
3. **Прогресс в списках** отсутствует (см. отклонения) — при требовании нужен
   `progress`/`summary` в API.
4. **`Typography`/`Tabs`-фикс** затронул общий `shared/ui` — проверены
   профилем все экраны, но если на других страницах табы выглядели иначе, это
   стоит глянуть глазами.
5. **Мобильная ширина** проверена только скриншотами на 1440×960.
