# Atlas Graphite — спецификация токенов и правил (источник истины для W1)

Согласовано с владельцем. Макеты: `.tmp/design/out/graphite-*.png`, исходник
`.tmp/design/mockup.html`. Значения ниже — перенос из макетов; менять только с
согласованием.

## Цвета

### Тёмная тема (по умолчанию)

| Токен | Значение |
|---|---|
| `--bg0` | `#07080a` |
| `--bg1` | `#171a20` |
| `--glow-accent` | `color-mix(in srgb, var(--accent) 26%, transparent)` |
| `--glow-neutral` | `rgba(148, 163, 184, .14)` |
| `--surface` | `rgba(24, 27, 33, .52)` |
| `--raised` | `rgba(30, 34, 41, .80)` |
| `--menu-bg` | `rgba(26, 30, 36, .97)` |
| `--sunken` | `rgba(9, 10, 12, .88)` |
| `--hover` | `rgba(255, 255, 255, .05)` |
| `--text` | `#eef1f5` |
| `--muted` | `#a4abb6` |
| `--faint` | `#7d858f` |
| `--border` | `rgba(255, 255, 255, .085)` |
| `--border-strong` | `rgba(255, 255, 255, .14)` |
| `--ok` | `#34d399` |
| `--warn` | `#fbbf24` |
| `--danger` | `#f87171` |
| `--shadow` | `0 24px 60px -28px rgba(0, 0, 0, .9)` |

### Светлая тема (`body[data-theme="light"]`)

| Токен | Значение |
|---|---|
| `--bg0` | `#f7f8fa` |
| `--bg1` | `#e7ebf1` |
| `--glow-accent` | `color-mix(in srgb, var(--accent) 14%, transparent)` |
| `--glow-neutral` | `rgba(148, 163, 184, .22)` |
| `--surface` | `rgba(255, 255, 255, .62)` |
| `--raised` | `rgba(255, 255, 255, .90)` |
| `--menu-bg` | `rgba(255, 255, 255, .985)` |
| `--sunken` | `rgba(255, 255, 255, .95)` |
| `--hover` | `rgba(15, 23, 42, .05)` |
| `--text` | `#12161c` |
| `--muted` | `#4b5563` |
| `--faint` | `#6b7280` |
| `--border` | `rgba(15, 23, 42, .10)` |
| `--border-strong` | `rgba(15, 23, 42, .18)` |
| `--ok` | `#047857` |
| `--warn` | `#b45309` |
| `--danger` | `#b91c1c` |
| `--shadow` | `0 20px 44px -28px rgba(15, 23, 42, .38)` |

### Акцент

- `--accent` задаётся рантаймом (`shared/lib/theme.ts` → `documentElement`),
  дефолт `#334155` (решение владельца).
- `--accent-soft`: `color-mix(in srgb, var(--accent) 16%, transparent)` (тёмная),
  12% (светлая) — вычислять через `var`, не хардкодить.
- `--on-accent`: `#ffffff` (все 8 пресетов из `theme.ts` достаточно тёмные).
- `--accent-contrast` уже пишет `theme.ts` — не дублировать.
- 8 пресетов `ACCENT_PRESETS` не менять, только дефолт.

## Стекло и плотность

- `--blur: 30px`, `--blur-raised: 40px`.
- Слои: S0 canvas (градиент + 2 радиальных glow), S1 shell (`--surface`,
  blur), S2 panel (`--surface`), S3 overlay (`--raised`/`--menu-bg`, blur-raised).
- Поля ввода, textarea, таблицы — `--sunken` (не стекло).
- `body[data-effects="off"]`: `--surface`/`--raised`/`--menu-bg`/`--sunken` —
  непрозрачные эквиваленты (тёмная: `#14171c`/`#1d2128`/`#1a1e24`/`#0b0d10`;
  светлая: `#ffffff`/`#ffffff`/`#ffffff`/`#f4f6f9`), `--blur: 0`,
  `--blur-raised: 0`.

## Типографика

- Шрифт: `"Roboto Condensed", "Roboto", system-ui, -apple-system, "Segoe UI",
  "Helvetica Neue", Arial, sans-serif`.
- Файлы: `public/fonts/roboto-condensed-{cyrillic,latin}-{400,500,700}-normal.woff2`
  (из `@fontsource/roboto-condensed@5.3.0`), `@font-face` с
  `font-display: swap`, preload только 400/cyrillic.
- Шкала: 12 (label, uppercase, tracking .08em), 13 (secondary), 14 (body),
  16 (subtitle), 20 (h3), 24 (h2), 28 (h1). line-height: 1.45 тело, 1.2
  заголовки, letter-spacing .007em тело / -.01em заголовки.
- `font-variant-numeric: tabular-nums` для чисел, дат, метрик.
- Компактная плотность: строка таблицы ~32px, контролы 32px, отступы 4/8/12/16/24/32.

## Геометрия и движение

- Радиусы: 8 (контролы), 12 (мелкие поверхности), 18 (панели), 24 (оверлеи),
  999 (pill).
- Motion: 120ms hover/press, 180ms enter, 260ms route; easing
  `cubic-bezier(.2, .8, .2, 1)`; `prefers-reduced-motion: reduce` и
  `data-effects="off"` → 0ms, без transform-анимаций.
- z-index: base 0, sticky 10, drawer 40, overlay 100, modal 200, toast 300.

## Emotion: только `styled` (обязательное правило реализации)

`css`-prop и `jsxImportSource` **не используем**: Vite 8 + React 19 + TS 7 в этом
проекте не настроены на babel-плагин Emotion, и `css={{...}}` молча превратится
в пустой класс. Все компонентные стили — `styled.div`/`styled.button`/…
из `@emotion/styled`; динамика — через пропсы и `var(--*)`, сложные варианты —
через массив классов `styled` (`styled('div', {...})` не нужен).

Глобальные стили — `Global` из `@emotion/react` (единственное использование
`@emotion/react` напрямую), провайдер темы — `ThemeProvider` из `@emotion/react`
с объектом отступов/радиусов/длительностей (без палитры).



## Правила

1. Цвета — только через `var(--*)`; в TS-тему Emotion идут только отступы,
   радиусы, длительности, z-index (без дублирования палитры).
2. Стекло — только на shell/панелях/оверлеях; тело таблиц и длинных списков
   непрозрачное.
3. antd: цвета через `ConfigProvider` (см. brief WS-A), внутренности antd не
   перекрашиваем точечными селекторами — только обёртками.
4. Текст ≥ 4.5:1, крупный ≥ 3:1, focus-ring ≥ 3:1 к соседнему фону.
5. `--accent` пользовательский: любой из 8 пресетов должен давать читаемый
   контраст — `on-accent` белый, статусные цвета фиксированные.
