---
name: devkit-team-run
description: Ведение задачи командой ролей AgentTeam — декомпозиция на непересекающиеся workstreams, брифы и субагенты, сбор результатов без правок автора за ролями.
user-invocable: true
---

# devkit-team-run — задача командой

## Когда

Задача L, затрагивает несколько слоёв/репозиториев, требует параллельных ролей
(backend + frontend + tests) или независимой проверки. Нужен утверждённый план
и настроенный профиль. Для S/M в одном слое дешевле solo.

## Инструменты

- `devkit task show|plan|status|run|comment|report|brief|check|token`
- `devkit profile show|test`, `devkit doc show`
- `devkit task gate` (для проверки статуса гейтов), git, grep/read
- graphify (опционально), ponytail
- субагенты DSH: `subagent`, `send_message`, `wait_agent`
- Полный CLI-набор devkit: 	ask plan, 	ask check, 	ask gate, 	ask report,
  doc, profile; применяй только относящиеся к навыку.

## Шаги

1. Предусловия: план `approved`, профиль `valid`, task-токен с `task:read` и
   `run:write`; у владельца получены токены для ролей с минимальными scopes
   (исполнителю — `task:write`,`check:write`,`comment:write`; проверяющему —
   `check:write`,`gate:write`,`comment:write`).
2. Раздели план на workstreams с **непересекающимся** scope (файлы/каталоги/
   репозитории). Для каждого определи роль, результат, проверки и зависимости.
   Пересечение возможно только последовательно, с записью в план.
3. Для каждого субагента собери бриф через `devkit-team-brief`: фрагмент
   плана, scope, acceptance, ограничения, токен/scopes, формат ответа. Никакой
   истории чата, никаких «сделай как в прошлый раз».
4. Запусти субагентов: прочитай `.agents/prompts/<role>.md` и подставь файл в
   `prompt` вместе с брифом. Роли: `backend-engineer`, `frontend-engineer`,
   `test-engineer`, `designer` (по потребности). Начни с независимых
   workstreams одновременно; зависимые — после результата предыдущего.
5. Веди run-записи (`devkit task run ...`): кто, роль, scope, старт/финиш,
   результат, commit sha. При steering — `send_message` с новым брифом, а не
   пересказом.
6. Собирай результаты фактами: изменённые файлы, коммиты, команды, exit code,
   что не проверено. Сам не переписывай работу ролей; интеграционные правки —
   минимальны и помечены.
7. Проверь каждый workstream `devkit-task-verify`, затем `devkit-team-sync`
   (план ↔ acceptance ↔ scope) и `devkit-team-check` независимыми ролями.
8. Отклонения от плана → `devkit-replan`; блокер → `devkit-team-escalate`.
   Финальный статус и выпуск — только после гейтов и санкции владельца.

## Промпты субагентов

- `.agents/prompts/backend-engineer.md` — сервер/API/БД/CLI;
- `.agents/prompts/frontend-engineer.md` — web/UI;
- `.agents/prompts/test-engineer.md` — тесты и независимое воспроизведение;
- `.agents/prompts/designer.md` — UX/UI-спецификация и состояния;
- `.agents/prompts/architect.md` — спорные технические решения.
Каждый промпт целиком подставляется в `prompt` ребёнка вместе с брифом;
ребёнок не видит родительский чат. Один workstream — один ребёнок, один scope.

## Если инструмент недоступен

- graphify нет → grep/read, `git log`, анализ каталогов.
- ponytail нет → правила `devkit-lifecycle` (минимальные workstreams и diff).
- Нет субагентов/лимит параллелизма → выполняй workstreams последовательно,
  сохраняя брифы и run-записи; это всё ещё AgentTeam-процесс.
- `devkit task run` не подключён → фиксируй роли/scope/результат в отчёте и
  комментариях; отметь деградацию.
- Нет токена на роль → не давай ребёнку owner-доступ; остановись и запроси.

## Доказательства

- План и карта workstreams со scope; брифы (или их hash) в run-записях.
- Run-записи: роль, старт/финиш, результат, коммиты.
- Проверки по каждому workstream (id, exit code, sha) и отчёт.
- Гейты независимых ролей; пустой `git status` перед сдачей.

## Если не получилось

Не смешивай роли и не позволяй проверяющему править код. Если две роли дают
конфликтующие изменения — останови запись, сведи конфликт в `devkit-team-sync`,
при необходимости `devkit-replan`. Если субагент не уложился в scope или
дважды провалил проверку — зафиксируй `blocked` через `devkit-team-escalate`,
приложи его вывод и решение, которое нужно от владельца.
