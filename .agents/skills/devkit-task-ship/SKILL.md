---
name: devkit-task-ship
description: Выпуск задачи сразу после `done` — PR или локальный merge с фиксацией попытки и без обхода защиты.
user-invocable: true
---

# devkit-task-ship — выпуск задачи

## Когда

Только когда задача в `done` (это состояние ставит владелец): все обязательные
проверки зелёные и привязаны к текущему commit sha, отчёт и sync готовы,
рабочее дерево чистое. Выпуск запускается сразу после `done`, отдельного
подтверждения на выпуск не требуется. Для промежуточных коммитов, «посмотреть
CI» и черновиков этот навык не используется.

## Инструменты

- `devkit task show <id> --json`, `devkit task status`, `devkit task check`,
  `devkit task report`, `devkit task ship --mode pr|local`, `devkit task comment`
- `devkit profile show`, `devkit doc show`
- git (`status`, `log`, `diff`, `branch`, `push` только через ship), graphify
  (опционально), ponytail
- Полный CLI-набор devkit: `devkit task plan`, `devkit task check`, `devkit task report`, `devkit doc`, `devkit profile`; применяй только относящиеся к навыку.

## Шаги

1. Проверь предусловия по `devkit task show <id> --json`:
   - статус `done`;
   - все `required`-проверки профиля имеют `passed` для текущего commit sha и не
     помечены `invalidated`;
   - `devkit-team-sync` выполнен, отчёт актуален;
   - `git status --porcelain` пуст, ветка `devkit/<id>` запушена или готова к push.
2. Определи режим выпуска:
   - `pr` — push ветки и PR, merge-commit через GitHub; задача остаётся `done` до
     merge, в отчёте фиксируется `pr_url` и состояние CI;
   - `local` — локальный merge-commit в целевую ветку без PR и без защиты ветки.
   Если режим не задан в задаче, спроси владельца одним вопросом.
   Никаких force-push, обхода branch protection и прямых push в default branch.
3. Запусти `devkit task ship <id> --mode pr|local`. CLI сам фиксирует
   `ship_attempt` (commit, PR, CI, ошибка) и переводит `ship_state`. Не
   дублируй push вручную.
4. При ошибке CI/PR/merge: прочитай лог, исправь причину в ветке (новый коммит
   инвалидирует проверки — прогони их заново), повтори ship. Лимит — 3 попытки;
   дальше `blocked`.
5. После успеха приложи финальный commit sha, PR URL (для `pr`), id попытки и
   статус `shipped`. Без фактического merge `shipped` не ставится; для `pr` не
   закрывай задачу до merge.

## Промпты субагентов

Обычно не нужны. Для разбора упавшего CI можно поднять субагента с
`.agents/prompts/test-engineer.md` или `.agents/prompts/backend-engineer.md`:
в `prompt` передай только лог CI, diff, acceptance и scope; без истории чата.

## Если инструмент недоступен

- graphify нет → `git log`, `git diff`, grep/read; отметь деградацию.
- ponytail нет → правила `devkit-lifecycle`.
- `devkit task ship` не подключён → не эмулируй выпуск вручную: зафиксируй
  `blocked` и передай владельцу коммит/ветку/PR-ссылку для ручного merge.
- Нет доступа к remote → локальный коммит сохранён; сообщи владельцу, не
  переписывай историю.

## Доказательства

- id проверок с commit sha кандидата; `git status` пуст.
- Режим выпуска и подтверждение, что `done` поставил владелец.
- id `ship_attempt`, PR URL, состояние CI, финальный commit sha в отчёте.
- Для merge — коммит в целевой ветке и статус `shipped`.

## Если не получилось

Не обходи защиту и не выпускай частично: после третьей неудачной попытки
вызови `devkit-team-escalate`, статус `blocked`, с логом последней ошибки,
списком попыток и запросом решения (новый фикс, другая ветка, ручной выпуск).
Задача не становится `shipped` без фактического merge.
