---
title: Сессии эпика E-AA7F23F1 — волны и промпты запуска
status: draft
epic: E-AA7F23F1
tz: docs/tz/TZ-53B42870.md
plan: docs/plans/epic-E-AA7F23F1.md
updated: 2026-11-27
---

# Сессии эпика E-AA7F23F1

Одна сессия = одна задача. AgentTeam работает внутри сессии; между сессиями
переезжают только артефакты (ТЗ, план эпика, файл задачи, бриф, отчёт,
смёрженные коммиты), история чата не передаётся.

S0 (`T-C050AC16`) и S1 (`T-DD797EDB`) выполняются в текущей сессии — промпты
для них не нужны. Всё, что ниже, запускается отдельными сессиями.

## 1. Волны

| Волна | Задача | Сессия | Стартует, когда |
|---|---|---|---|
| S0 | T-C050AC16 shell | эта сессия | — |
| S1 | T-DD797EDB backend | эта сессия | — |
| S2a | T-AB4212F4 экраны | отдельная | S0 и S1 смёржены в main |
| S2b | T-7F821446 календарь | отдельная, можно параллельно S2a | S0 и S1 смёржены |
| S2c | T-AC2A5666 файлы, настройки, уведомления, задания, поиск | отдельная, можно параллельно S2a | S0 и S1 смёржены |
| S2d | T-6E58E324 онбординг | отдельная, после S2a или параллельно | S0 и S1 смёржены |
| S2e | T-170164DD чат и агенты | отдельная, можно параллельно | S0 смёржена |
| S3 | T-366AA68F проект, дерево/доска/гант + Задачи | отдельная | S2a смёржена |
| S4 | T-607A3128 качество, E2E и снос старого | отдельная | все задачи `done` |

Не больше трёх параллельных сессий: ревью и порядок мержей становятся узким
местом раньше, чем техника.

## 2. Как запускать

1. Новая сессия DSH, рабочий каталог — корень проекта.
2. Вставить промпт сессии целиком. Он самодостаточен: задача, ТЗ, план, scope,
   роли, проверки.
3. Сессия сначала делает план задачи и ждёт утверждения владельца в web.
4. После `done` — `devkit task ship` (мёрж в main), только потом стартует
   зависимая волна.
5. Независимая проверка — отдельная сессия с промптом из раздела 4.

## 3. Промпты сессий

### S2a — T-AB4212F4 «Главная, Развитие, Профиль, Интересы, Проекты, Люди»

```
Ты ведёшь задачу T-AB4212F4 эпика E-AA7F23F1 в режиме AgentTeam. Ты lead и
единственный автор кода этой задачи.

СНАЧАЛА ПРОЧИТАЙ
- devkit task show T-AB4212F4 --json (вместе с comments).
- ТЗ: docs/tz/TZ-53B42870.md, разделы 6.1, 6.4–6.6, 6.9–6.10, 6.13, 6.19, 8, 10.
- План эпика: docs/plans/epic-E-AA7F23F1.md.
- Навыки: devkit-task, devkit-team-run, devkit-team-brief, devkit-task-verify.

ПЛАН
- Сделай план задачи по devkit-task-plan (этапы по экранам, acceptance, проверки).
- Без утверждения плана владельцем в web код не пиши.

ГРАНИЦЫ
- Scope только: viewer/src/pages/{home,growth,profile,interests,projects,people},
  viewer/src/shared/widgets.
- Не трогай viewer/package.json, viewer/src/shared/ui (база принадлежит
  T-C050AC16), viewer/src/shared/api, routes в app.
- Ветка devkit/T-AB4212F4, worktree; минимальный diff; ноль eslint-disable,
  type ignore, noqa; проверки не ослаблять.
- Первый экран — проверка скина antd/SVAR/FullCalendar на одном файле токенов.
  Не сходится — эскалация (devkit-team-escalate), не локальные переопределения.

РАБОТА
- Разбей на непересекающиеся workstreams по экранам; субагентам (роли
  designer, frontend-engineer, test-engineer) дай брифы из .agents/prompts/<role>.md
  плюс разделы ТЗ; историю чата не передавай.
- Коммит и приёмка на каждый экран отдельно, иначе ревью не осилит.
- Состояния: скелетон, пусто с CTA, ошибка с повтором, тост.
- Проверки профиля: web-build, typecheck-web, lint-web, arch-web.

ФИНИШ
- devkit task report T-AB4212F4: что сделано / изменения / проверки (с exit code) /
  риски; статус needs_review.
- Верни факты: файлы, команды, коды возврата, что не проверено. Не пиши «готово».
```

### S2b — T-7F821446 «Календарь Apple Calendar»

```
Ты ведёшь задачу T-7F821446 эпика E-AA7F23F1 в режиме AgentTeam. Ты lead и
единственный автор кода этой задачи.

СНАЧАЛА ПРОЧИТАЙ
- devkit task show T-7F821446 --json (вместе с comments).
- ТЗ: docs/tz/TZ-53B42870.md, разделы 6.3, 7, 8, 9.
- План эпика: docs/plans/epic-E-AA7F23F1.md.
- Навыки: devkit-task, devkit-team-run, devkit-team-brief, devkit-task-verify.

ПЛАН
- План по devkit-task-plan: спайк года в первый день, виды Месяц/Неделя/День,
  сайдбар, поповер, создание/перенос/resize, повторы.
- Без утверждения плана владельцем код не пиши.

ГРАНИЦЫ
- Scope только: viewer/src/pages/calendar, viewer/src/shared/ui/calendar.tsx.
- Не трогай viewer/package.json (зависимости уже стоят из T-C050AC16),
  shared/ui вне calendar.tsx, shared/api, app.
- Ветка devkit/T-7F821446, worktree; минимальный diff; ноль подавлений.
- FullCalendar пиновать 6.1.22 (7 в переходном состоянии).

РАБОТА
- Спайк: @fullcalendar/multimonth против своего год-грида. Решение и причину
  зафиксируй в плане задачи, не меняя ТЗ.
- Механика FullCalendar (drag, resize, select, all-day, многодневные полосы);
  сайдбар, поповер, Apple-поведение и скин — свои, на токенах.
- Доступность: клавиатура по сетке, фокус, «сегодня», Esc закрывает поповер.
- Проверки профиля: web-build, typecheck-web, lint-web, arch-web.

ФИНИШ
- devkit task report T-7F821446 с проверками и exit code; статус needs_review.
- Верни факты: файлы, команды, коды возврата, что не проверено.
```

### S2c — T-AC2A5666 «Файлы, Настройки, уведомления, задания, поиск»

```
Ты ведёшь задачу T-AC2A5666 эпика E-AA7F23F1 в режиме AgentTeam. Ты lead и
единственный автор кода этой задачи.

СНАЧАЛА ПРОЧИТАЙ
- devkit task show T-AC2A5666 --json (вместе с comments).
- ТЗ: docs/tz/TZ-53B42870.md, разделы 6.11–6.12, 6.14–6.18, 7, 8.
- План эпика: docs/plans/epic-E-AA7F23F1.md.
- Навыки: devkit-task, devkit-team-run, devkit-team-brief, devkit-task-verify.

ПЛАН
- План по devkit-task-plan: файловое дерево, страница файла, настройки с темой и
  акцентом, уведомления, задания, поиск.
- Без утверждения плана владельцем код не пиши.

ГРАНИЦЫ
- Scope только: viewer/src/pages/{files,settings,notifications,jobs,search}.
- Файловое дерево — на базовом TreeList из T-C050AC16, задача T-366AA68F не
  ожидается. Не трогай viewer/package.json, shared/ui, shared/api, app.
- Ветка devkit/T-AC2A5666, worktree; минимальный diff; ноль подавлений.

РАБОТА
- Поиск: страница результатов по группам с «показать все»; сам эндпоинт
  scope=all приходит из T-DD797EDB, контракт сверяй по нему.
- Настройки: тема, акцент, фон, «меньше эффектов», интеграции, уведомления.
- Проверки профиля: web-build, typecheck-web, lint-web, arch-web.

ФИНИШ
- devkit task report T-AC2A5666 с проверками и exit code; статус needs_review.
- Верни факты: файлы, команды, коды возврата, что не проверено.
```

### S2d — T-6E58E324 «Онбординг: вход, модель, Яндекс.Диск, опрос из 9 шагов»

```
Ты ведёшь задачу T-6E58E324 эпика E-AA7F23F1 в режиме AgentTeam. Ты lead и
единственный автор кода этой задачи.

СНАЧАЛА ПРОЧИТАЙ
- devkit task show T-6E58E324 --json (вместе с comments).
- ТЗ: docs/tz/TZ-53B42870.md, разделы 3, 3.1, 7.
- План эпика: docs/plans/epic-E-AA7F23F1.md.
- Навыки: devkit-task, devkit-team-run, devkit-team-brief, devkit-task-verify.

ПЛАН
- План по devkit-task-plan: четыре шага визарда, опрос из 9 шагов, превью после
  каждого, идемпотентность, пропуск и возобновление.
- Без утверждения плана владельцем код не пиши.

ГРАНИЦЫ
- Scope только: viewer/src/pages/onboarding, viewer/src/pages/login.
- Не трогай viewer/package.json, shared/ui, shared/api, app.
- Ветка devkit/T-6E58E324, worktree; минимальный diff; ноль подавлений.

РАБОТА
- Состояние шага — OnboardingSession, защита от дублей по созданным id.
- PII шага «О тебе» (имя, возраст, город, профессия) — с тумблером «передавать
  агенту»; по умолчанию включён, отключается.
- После финиша — переход в `/` и тост; пропущенный опрос оставляет баннер.
- Проверки профиля: web-build, typecheck-web, lint-web, arch-web.

ФИНИШ
- devkit task report T-6E58E324 с проверками и exit code; статус needs_review.
- Верни факты: файлы, команды, коды возврата, что не проверено.
```

### S2e — T-170164DD «Чат и настройки агентов»

```
Ты ведёшь задачу T-170164DD эпика E-AA7F23F1 в режиме AgentTeam. Ты lead и
единственный автор кода этой задачи.

СНАЧАЛА ПРОЧИТАЙ
- devkit task show T-170164DD --json (вместе с comments).
- ТЗ: docs/tz/TZ-53B42870.md, разделы 6.2, 6.15, 7.
- План эпика: docs/plans/epic-E-AA7F23F1.md.
- Навыки: devkit-task, devkit-team-run, devkit-team-brief, devkit-task-verify.

ПЛАН
- План по devkit-task-plan: список чатов и тред, источники, инструменты, стоп,
  глубокий анализ, шестерёнка к агентам, мобильный переход.
- Без утверждения плана владельцем код не пиши.

ГРАНИЦЫ
- Scope только: viewer/src/pages/chat, viewer/src/pages/agents.
- Не трогай viewer/package.json, shared/ui, shared/api, app.
- Ветка devkit/T-170164DD, worktree; минимальный diff; ноль подавлений.

РАБОТА
- Поведение чата не меняем: только UI и навигация, API тот же.
- Мобильный: список → тред с back, composer липкий с safe-area.
- Проверки профиля: web-build, typecheck-web, lint-web, arch-web.

ФИНИШ
- devkit task report T-170164DD с проверками и exit code; статус needs_review.
- Верни факты: файлы, команды, коды возврата, что не проверено.
```

### S3 — T-366AA68F «Проект: дерево, доска, гант; экран Задачи»

```
Ты ведёшь задачу T-366AA68F эпика E-AA7F23F1 в режиме AgentTeam. Ты lead и
единственный автор кода этой задачи.

СНАЧАЛА ПРОЧИТАЙ
- devkit task show T-366AA68F --json (вместе с comments).
- ТЗ: docs/tz/TZ-53B42870.md, разделы 6.7–6.8, 8, 9, 11.
- План эпика: docs/plans/epic-E-AA7F23F1.md.
- Навыки: devkit-task, devkit-team-run, devkit-team-brief, devkit-task-verify.

ПЛАН
- План по devkit-task-plan: три представления в проекте, экран Задачи, скины
  SVAR под токены, вид в URL.
- Без утверждения плана владельцем код не пиши.

ГРАНИЦЫ
- Scope только: viewer/src/pages/project, viewer/src/pages/tasks,
  viewer/src/shared/ui/{tree,board,gantt}.tsx.
- Базовый TreeList уже есть из T-C050AC16 — не переписывай, используй.
- Не трогай viewer/package.json, shared/ui вне трёх файлов, shared/api, app.
- Ветка devkit/T-366AA68F, worktree; минимальный diff; ноль подавлений.

РАБОТА
- Дерево: группировки по статусу/исполнителю/тегу, поиск, фильтры, свёртка.
- Доска: SVAR Kanban, drag между колонками, свои карточки; swimlanes — PRO, не
  используем.
- Гант: SVAR Gantt, зависимости task_dependencies, прогресс, drag/resize, зум.
- Задачи: дефолтный фильтр «без интереса и проекта», дерево, свайп на мобильном.
- Проверки профиля: web-build, typecheck-web, lint-web, arch-web.

ФИНИШ
- devkit task report T-366AA68F с проверками и exit code; статус needs_review.
- Верни факты: файлы, команды, коды возврата, что не проверено.
```

### S4 — T-607A3128 «Качество: Playwright и axe, снос старых экранов»

```
Ты ведёшь задачу T-607A3128 эпика E-AA7F23F1 в режиме AgentTeam. Ты lead и
единственный автор кода этой задачи.

СНАЧАЛА ПРОЧИТАЙ
- devkit task show T-607A3128 --json (вместе с comments).
- ТЗ: docs/tz/TZ-53B42870.md, разделы 10 (A11, A12), 12.
- План эпика: docs/plans/epic-E-AA7F23F1.md.
- Навыки: devkit-task, devkit-team-run, devkit-team-brief, devkit-task-verify,
  devkit-code-quality.

ПЛАН
- План по devkit-task-plan: E2E-набор, axe, проверки профиля, редиректы,
  удаление старых страниц и табов.
- Без утверждения плана владельцем код не пиши.

ГРАНИЦЫ
- Scope только: viewer/e2e, viewer/package.json, viewer/eslint.config.js,
  .github/workflows, devkit.yaml.
- Удаление старых файлов — только после того, как все задачи эпика в done.
- Ветка devkit/T-607A3128, worktree; ноль подавлений; проверки не ослаблять.

РАБОТА
- E2E на критические пути: вход, онбординг, создание задачи, проект с тремя
  видами, создание события в календаре, файлы.
- axe на ключевые экраны, без новых нарушений уровня serious/critical.
- Проверки профиля: Playwright и axe добавить в devkit.yaml и CI тем же PR;
  прогнать web-build, typecheck-web, lint-web, arch-web, unit-tests,
  lint-python, typecheck-python, arch-python, schema-check.
- Редиректы с прежних адресов (`/today`, `/documents`, `/spheres` и т. п.),
  старые табы удалить, мёртвый код не оставлять.

ФИНИШ
- devkit task report T-607A3128 с проверками и exit code; статус needs_review.
- Верни факты: файлы, команды, коды возврата, что не проверено.
```

## 4. Промпт независимой проверки (после каждой задачи)

```
Ты проверяешь задачу T-XXXXXXXX эпика E-AA7F23F1. Ты не автор кода и не правишь
его. Режим — devkit-team-check, роли skeptic и test-engineer.

ПРОЧИТАЙ
- devkit task show T-XXXXXXXX --json, отчёт docs/reports/T-XXXXXXXX.md, план задачи.
- ТЗ: docs/tz/TZ-53B42870.md (раздел, относящийся к задаче) и Acceptance.
- Diff задачи и ветку devkit/T-XXXXXXXX.

ПРОВЕРЬ
- Acceptance задачи и соответствующие пункты A1–A12 ТЗ.
- Scope: не вылез ли диф за объявленные пути, не ослаблены ли проверки, нет ли
  eslint-disable / type ignore / noqa.
- Провайдерские проверки: имена из профиля, вывод с exit code.
- Accessibility: фокус, таргеты 44px, контраст на стекле и акценте.
- Мобильный: ничего не уезжает, safe-area, табы и поиск на месте.

ВЕРНИ
- Находки с file:line, severity (blocker/major/minor), рекомендация.
- Вердикт: можно сдавать или нужен реwork. В devkit вердикт не пиши.
```
