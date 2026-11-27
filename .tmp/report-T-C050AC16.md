# T-C050AC16 — Shell: роутер, каркас, токены, тема, стекло

## Что сделано

- Поставлены зависимости плана S0: `antd` 6.7.2, `@ant-design/icons` 6.3.4,
  `lucide-react` 1.81.0, `react-router` 8.5.3, `@tanstack/react-query` 5.108.4,
  `dayjs`, `recharts` 3.11.1, SVAR Gantt/Kanban, FullCalendar 6.1.22 (все
  MIT/бесплатные). Реестр зависимостей в тестах обновлён явным allowlist.
- Роутер: `app/router.tsx` со всеми маршрутами ТЗ §2. Старые экраны подключены
  к своим адресам, новые (`/profile`, `/notifications`, `/space`) — заглушки.
  Редиректы: `/today` → `/`, `/documents` → `/files`, `/spheres` → `/interests`,
  `/projects` → `/interests` (до экрана S2). SPA-fallback проверен.
- Каркас `AppShell`: липкая шапка (логотип, поиск с `Ctrl/⌘K`, аватар с бейджем
  непрочитанных, меню профиля), левое меню из 9 пунктов со сворачиванием до
  иконок, нижние табы Home/Chat/Space/Profile с safe-area, `PageHeader`.
  Возврат после OAuth Яндекса (`?yadisk`) снова открывает настройки.
- Тема и токены: `styles/tokens.css` — один источник цветов, тёмная/светлая/
  системная, `--accent` из пикера по всей палитре, `--accent-contrast` по
  яркости, фокус-кольцо, фон-пресеты (аврора/дымка/ночь), тема в localStorage
  до первого кадра (inline-скрипт в `index.html`, без вспышки).
- LiquidGlass: слой на шапке, меню, нижних табах и стеклянных панелях;
  `@supports` fallback, `prefers-contrast: more`, выключатель «меньше эффектов»
  (`data-effects=off`), на теле таблиц стекла нет.
- Базовые примитивы в `shared/ui`: `PageHeader`, `EmptyState`, `Skeleton`,
  `Avatar` (фото/инициалы), `TreeList`, `WidgetHost` с реестром виджетов,
  `ThemePanel`, `useSession`.
- CSS разбит: `styles/base.css` (старое, классы сохранены), `tokens.css`,
  `shell.css`; `styles.css` — точка импорта.
- Тесты `test_web_build` и `test_growth` адаптированы под перенос навигации в
  `AppShell`/`router`: проверки не ослаблены, те же утверждения на новых
  файлах, allowlist зависимостей обновлён под утверждённый план S0.

## Изменения

Коммиты ветки `devkit/T-C050AC16`:

- `a21e066` — feat(viewer): shell, роутер, токены, тема, стекло.
- `2c79dd7` — fix(viewer,tests): OAuth-возврат в настройки, тесты следуют за
  роутером.

Файлы: `viewer/package.json` и `package-lock.json`, `viewer/index.html`,
`viewer/src/app/{App.tsx,main.tsx,AppShell.tsx,SearchOverlay.tsx,router.tsx}`,
`viewer/src/app/styles/{base,tokens,shell}.css` и `styles.css`,
`viewer/src/shared/{api,lib,ui}` (новые примитивы, тема, сессия, queryClient),
`viewer/src/pages/{profile,notifications,space}`, тесты
`tests/test_web_build.py`, `tests/test_growth.py`.

ТЗ обновлено: `React Router 7` → `React Router 8.5.3` (фактическая версия).

## Проверки

| Проверка | Команда | Результат |
|---|---|---|
| web-build | `npm run build` | exit 0; dist 1.01 MB JS / 311 KB gzip, CSS 19 KB |
| typecheck-web | `npx tsc --noEmit` | exit 0 |
| lint-web | `npx eslint .` | exit 0, 0 выключений |
| arch-web | `npx steiger ./src` | exit 0, «No problems found» |
| format-web | `npx prettier --check .` | exit 0, «All matched files use Prettier code style» |
| unit-tests | `python -m unittest discover -s tests` | exit 0, Ran 446 tests, OK |

Smoke: `vite preview` отдаёт `/` и SPA-fallback `/settings` (200), ассет
1 011 787 байт.

## Риски

- **Bundle 1.01 MB (311 KB gzip)** — начал предупреждать Vite о чанках >500 KB.
  Нужен route-level `lazy`/`import()`; предложу в S4 или отдельной chore.
- **Service worker** (`public/sw.js`) не проверялся в браузере на новых
  маршрутах: кэш навигации может отдавать старый shell. Проверить в S4 вместе
  с E2E.
- **Поиск в шапке** пока ищет только документы (`/api/search`); задачи, люди,
  проекты `scope=all` придут из S1 — до этого оверлей честно пишет об этом.
- **Загрузка фона и аватара** — эндпоинты в S1; в S0 только пресеты фона и
  инициалы.
- **`/projects` редиректит на `/interests`** до экрана S2; старая страница
  «Сферы и проекты» временно обслуживает «Интересы».
- `ThemePanel` пишет только в localStorage. Синхронизация с `UserProfile.data`
  не включена, чтобы не сломать проверку «пустой профиль → визард»; делать
  вместе с экраном профиля (S2).
