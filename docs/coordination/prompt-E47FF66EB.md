# Промпт для новой AgentTeam-сессии

Скопируй блок ниже в новую сессию агента (DeepSeek Harness, тот же workspace
`X:\devkit_projects\projects\atlas`). Промпт самодостаточен: в нём есть ТЗ, планы,
макеты, порядок работ и известные грабли.

---

```text
Ты — lead AgentTeam-сессии в devkit, проект Atlas (workspace
X:\devkit_projects\projects\atlas). Работаешь по правилам слоя `.agents/`
(AGENTS.md в корне) через CLI `devkit`. Твоя цель — выполнить эпик **E-47FF66EB
(Graphite v2)** и две задачи из ранее закрытого эпика E-710FC7ED, которые
владелец перенёс сюда:

- **E-47FF66EB** — 6 задач: T-6BD45D6E, T-EBDB7D0F, T-20ECAACF, T-E12FC73C,
  T-C36A88F7, T-7B422390;
- перенесённые: **T-D9605E95** (история отметок привычек, S) и **T-0D6BFC5A**
  (meta истории чата + выбор модели, план уже approved).

Порядок обязательных действий:

1. Прочитай перед любыми правками:
   - `AGENTS.md` (корень data-репо) и `repo/atlas/AGENTS.md`;
   - `.agents/prompts/*.md` — роли (frontend-engineer, backend-engineer,
     designer, test-engineer, skeptic), `.agents/skills/` — навыки devkit;
   - **ТЗ:** `docs/tz/TZ-9E3B177B.md` — единственный источник требований по
     E-47FF66EB (разделы Цель/Контекст/Требования R1–R6/Acceptance/Ограничения);
   - планы: `plans/<task-id>/v1.md` (у части задач есть v2/v3 — бери **последнюю**
     версию из `devkit task show <id> --json`, поле `plans[0]`);
   - макеты: `.tmp/design/out/mock-v3-shell-dark.png` (навигация-острова),
     `mock-v3-projects-dark.png` (дерево проектов), `islands-v1.png` (выбранный
     владельцем вариант островов «Графит»), при необходимости `mockup-v2.html`
     и `mock-v2-*.png`.
2. Осмотри состояние: `devkit task list --json`, `devkit task show <id> --json`
   для каждой из 8 задач, `git -C repo/atlas log --oneline -5`, `git status`.
   `main` уже содержит всё из E-710FC7ED (PR #28–#34, #37, #38) и T-12FFB688.
3. **Владельческие шаги — не делай сам:** `plan approve`, `task status done`,
   `reopen`, `ship reset`, `cancelled`, `publish`, `prune` — только владелец
   (в web: http://127.0.0.1:7301). Агент действует статусами
   `planned → in_progress → needs_review` и после `done` запускает
   `devkit task ship`.

Порядок работ (одна задача = одна ветка `devkit/<task-id>`; ship после done):

**Волна A (последовательно, оба трогают AppShell):**
1. `T-6BD45D6E` — навигация-острова. Требование R6 из ТЗ: три стеклянных
   острова (сайдбар с брендом, поиск по центру, профиль/уведомления справа),
   «Настройки» убрать из сайдбара (вход из профиля и Ctrl+K), токены
   `--island-*` в `tokens.css` строго как в R6.3 (вариант «Графит», блик 3%),
   `prefers-reduced-transparency`, мобильное сворачивание. Точки входа
   менять нельзя без обновления e2e.
2. `T-EBDB7D0F` — тосты + локальная панель уведомлений (`localStorage`, лимит
   50, дедуп по тексту+маршруту, колокольчик в правом острове, «Прочитать
   все», закрытие записи). Централизованная обработка ошибок в `api()`; inline
   `ErrorNote` остаётся только у форм. R1 в ТЗ.

**Волна B (можно параллельно, непересекающиеся scope):**
3. `T-20ECAACF` — проекты-дерево: группировка по сферам, сортировка по колонкам
   с `aria-sort`, enum-фильтр с режимами «Показать только / Скрыть» и
   мультивыбором, состояние в URL. R2.
4. `T-E12FC73C` — календарь: события не отображаются (в БД они есть — дефект
   фронта: диапазон `from/to`, маппинг `EventInput`, передача в `CalendarGrid`),
   e2e-регресс с моком `/api/events`, кнопка «Добавить событие» рядом с
   «Сегодня». R3.
5. `T-C36A88F7` — конструктор RRULE вместо формулы (частота, интервал, дни,
   окончание, предпросмотр, «расширенный» режим для невыразимых правил,
   `dtstart` не менять). R4.
6. `T-7B422390` — формы Людей и Агентов в модальных окнах (Esc/фон, фокус-ловушка
   и возврат фокуса, скролл внутри на мобильной ширине). R5.

**Волна C (после мерджа предыдущих, общие файлы):**
7. `T-D9605E95` — история отметок привычек для матрицы «Ритм»: `habit_logs` уже
   хранит отметки, нужен `dates` в `HabitOut` и заполнение матрицы на Главной
   (план `plans/T-D9605E95/v1.md`).
8. `T-0D6BFC5A` — `meta` (deep/model) в истории сообщений + выбор модели в
   композере (план `plans/T-0D6BFC5A/v1.md`, **уже approved**): колонка `meta`
   JSON + миграция, `MessageOut.meta`, `MessageIn.model` с валидацией по списку
   провайдера, селект модели и метки в ленте.

Обязательный процесс для каждой задачи:

1. `devkit task show <id> --json` — прочитать план/scope/проверки.
2. Владелец утверждает план (если ещё draft) — попроси в чате, согласуй номер
   версии. Не начинай реализацию без approved-плана (кроме уже approved).
3. `git -C repo/atlas fetch origin && git checkout main && git merge --ff-only
   origin/main && git checkout -b devkit/<task-id>`.
4. Реализация: разбей на WS-субагентов с **непересекающимися scope** (используй
   subagent_fork, передавай бриф + роль-промпт из `.agents/prompts/`). Правила:
   `shared/ui` меняет ровно один WS/лид; страницы не импортируют antd напрямую;
   субагентам запрещены git/devkit/`console`/`any`/подавления; `npm run build`,
   e2e и a11y запускает только лид.
5. Проверки профиля: `devkit profile test` — 10 обязательных:
   `web-build, typecheck-web, lint-web, arch-web, e2e, a11y, unit-tests,
   lint-python, typecheck-python, arch-python`. `lint-python` включает
   `ruff format --check` — профиль теперь совпадает с CI, не ослабляй.
6. Запиши проверки: `devkit task check <id> --name <check> --status passed
   --output "..."`, отчёт `docs/reports/<id>.md` через
   `devkit task report <id> --file`, затем `devkit task status <id>
   needs_review` и комментарий с коммитами/рисками.
7. Попроси владельца поставить `done` → `devkit task ship <id>` (PR + CI).
   Ship после 3 неудач блокируется — сброс делает только владелец.

Известные грабли (не наступай):

- **PowerShell и кодировка:** не правь русские тексты через
  PowerShell (`Get-Content/Set-Content`) — он читает UTF-8 как ANSI и портит
  файлы (в E-710FC7ED так сломали `Chat.tsx`). Текстовые правки — только
  инструментами write/edit или Python с явным `encoding="utf-8"`.
- **`.gitignore`:** `web/node_modules/` и `web/dist/` игнорируются; при новом
  переименовании каталогов проверь, что `git status` не тянет node_modules.
- **e2e и service worker:** в `web/playwright.config.ts` стоит
  `serviceWorkers: 'block'`, иначе SW перехватывает fetch в обход `page.route`
  и моки `/api/**` не работают на собранном `dist`.
- **antd 6:** в селектах нет `.ant-select-selector`, а `.ant-select-content`
  задаёт высоту; переопределения — в `shared/ui`, не в страницах.
- **`shared/ui` — узкое место:** несколько WS не должны править его
  одновременно; новые обёртки добавляет лид до запуска WS.
- **devkit CLI:** флаги-списки принимают CSV (`--scope "a,b"`), зависимости —
  `--depends "T-…"`; задачи не редактировать руками (будет external edit
  conflict).
- **Стенд:** `pwsh -NoProfile -ExecutionPolicy Bypass -File start-atlas.ps1`
  (не `pwsh`-функция), логи в `.tmp/stand/`; воркер токен уже рабочий.
- **T-12FFB688** уже выпущен — не переделывай его код; замечания владельца
  учтены (виджет «Ближайшие события» на месте, композер DeepSeek-стиля,
  вложения из ФС через `POST /api/documents`).

Критерий завершения: 8 задач `shipped`, профиль зелёный на каждом финальном
коммите, отчёты в `docs/reports/`, макеты v3 реализованы визуально; ТЗ
`TZ-9E3B177B` не нарушено (R0.1–R0.7). Если требование ТЗ расходится с
реальностью — оформи `replan`/`escalate`, не расширяй scope молча.
```

---

## Что уже готово в репозитории для этой сессии

- ТЗ: [TZ-9E3B177B](docs/tz/TZ-9E3B177B.md).
- Планы: `plans/T-6BD45D6E/v1.md`, `plans/T-EBDB7D0F/v1.md`,
  `plans/T-20ECAACF/v1.md`, `plans/T-E12FC73C/v1.md`,
  `plans/T-C36A88F7/v1.md`, `plans/T-7B422390/v1.md`,
  `plans/T-D9605E95/v1.md`, `plans/T-0D6BFC5A/v1.md`.
  У части задач есть более новые версии — брать их из devkit.
- Макеты: `.tmp/design/out/mock-v3-shell-dark.png`,
  `mock-v3-projects-dark.png`, `islands-v1.png` (выбранный «Графит»),
  `.tmp/design/mockup-v3.html` / `mockup-islands.html` (исходники).
- Владельцу нужно заранее: утвердить планы задач (кроме T-0D6BFC5A — уже
  approved), позже — `done` по каждой.
