---
name: devkit-task-ship
description: Выпуск задачи после валидных гейтов и санкции владельца — PR или merge в целевую ветку с фиксацией попытки и без обхода защиты.
user-invocable: true
---

# devkit-task-ship — выпуск задачи

## Когда

Только когда задача в `done`: все обязательные проверки зелёные и не
инвалидированы, гейты валидны, отчёт и sync готовы, рабочее дерево чистое и
владелец выдал санкцию на выпуск в web. Для промежуточных коммитов, «посмотреть
CI» и черновиков этот навык не используется.

## Инструменты

- `devkit task show <id> --json`, `devkit task status`, `devkit task check`,
  `devkit task gate`, `devkit task report`, `devkit task ship`, `devkit task comment`
- `devkit profile show`, `devkit doc show`
- git (`status`, `log`, `diff`, `branch`, `push` только через ship), graphify
  (опционально), ponytail
- Полный CLI-набор devkit: 	ask plan, 	ask check, 	ask gate, 	ask report,
  doc, profile; применяй только относящиеся к навыку.

## Шаги

1. Проверь предусловия по `devkit task show <id> --json`:
   - статус `done`;
   - все `required`-проверки профиля имеют `ok` для текущего commit sha и не
     помечены `invalidated`;
   - гейты `pass`, не `superseded`/`invalidated`;
   - `devkit-team-sync` выполнен, отчёт актуален;
   - `git status --porcelain` пуст, ветка `devkit/<id>` запушена или готова к push.
2. Проверь активную санкцию владельца в статусе ship (`sanctioned_at`,
   `sanction_expires_at`). Санкция одноразовая и с TTL. Нет санкции — не
   выпускай: оставь комментарий, дождись решения владельца в web или
   эскалируй. Не проси и не подделывай подтверждение в чате.
3. Выбери режим, который разрешил владелец:
   - `pr` — push ветки и создание PR; задача остаётся `done` до merge,
     в отчёте фиксируется `pr_url` и состояние CI;
   - `merge` — только если владелец выбрал его и ветка не защищена от прямого
     merge; после успешного merge задача переходит в `done`.
   Никаких force-push, обхода branch protection и прямых push в default branch.
4. Убедись, что владелец выдал санкцию: `devkit task ship sanction <id>` (владелец).
   Затем запусти `devkit task ship <id> --mode <pr|local>`. CLI сам фиксирует
   `ship_attempt` (commit, PR, CI, ошибка) и переводит `ship_state`. Не
   дублируй push вручную.
5. При ошибке CI/PR: прочитай лог, исправь причину в ветке (это новая итерация
   проверок и гейтов), повтори ship. Лимит — 3 попытки; дальше `blocked`.
6. После успеха: убедись, что `done` выставлен только для merge/закрытого PR;
   приложи финальный commit sha, PR URL, id попытки и санкции. Для `pr` не
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

- id гейтов и проверок с commit sha кандидата; `git status` пуст.
- Время/срок санкции владельца и режим выпуска.
- id `ship_attempt`, PR URL, состояние CI, финальный commit sha в отчёте.
- Для merge — `done_at` и коммит в целевой ветке.

## Если не получилось

Не обходи защиту и не выпускай частично: после третьей неудачной попытки или
истёкшей санкции вызови `devkit-team-escalate`, статус `blocked`, с логом
последней ошибки, списком попыток и запросом решения (новый фикс, другая
ветка, ручной выпуск). Задача не становится `done` без фактического merge.
