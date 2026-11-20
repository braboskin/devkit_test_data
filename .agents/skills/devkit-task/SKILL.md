---
name: devkit-task
description: Точка входа для любой задачи devkit — классифицирует задачу и направляет в solo- или AgentTeam-навык, не выполняя работу сам.
user-invocable: true
---

# devkit-task — маршрутизация задачи

## Когда

Загружай этот навык в начале любой работы над задачей devkit, когда режим не
очевиден или задачу передали без указания навыка. Не используй его для
профиля проекта и эпиков — там сразу `devkit-profile-setup` / `devkit-epic-plan`.

## Инструменты

- `devkit task show <id> --json`, `devkit task list --json`, `devkit task status`
- `devkit task plan`, `devkit task check`, `devkit task gate`, `devkit task report`,
  `devkit task brief`, `devkit task ship`, `devkit task token`
- `devkit doc ...`, `devkit profile show|test`
- файлы задачи: `tasks/<id>.md`, `plans/<id>/`, `docs/`, `AGENTS.md`, `.agents/`
- git (`log`, `diff`, `status`), grep/read, graphify (опционально), ponytail
- Полный CLI-набор devkit: 	ask plan, 	ask check, 	ask gate, 	ask report,
  doc, profile; применяй только относящиеся к навыку.

## Шаги

1. Прочитай задачу и её окружение:
   `devkit task show <id> --json`; затем `tasks/<id>.md`, связанный эпик
   (`epics/<id>.md`), профиль `devkit profile show --json`, `AGENTS.md`.
2. Проверь готовность: есть ли task-токен в `DEVKIT_TOKEN` и нужные scopes,
   установлен ли слой `.agents`, настроен ли профиль (`missing`/`pending` →
   `devkit-profile-setup`).
3. Классифицируй:
   - **Размер**: S — 1–2 файла, без миграций/auth/денег/новых зависимостей;
     M — несколько файлов или один слой; L — несколько слоёв/репозиториев,
     миграции, безопасность, неясные требования.
   - **Тип**: `feature` (новая функциональность), `bug` (дефект, нужен root
     cause), `chore` (обслуживание, docs, зависимости).
   - **Риск**: цена ошибки, обратимость, внешние интеграции.
4. Выбери ровно один основной навык:
   - S + ясный acceptance → `devkit-just-do`;
   - M/L, новый функционал, неясность → `devkit-task-plan`;
   - план провален или устарел → `devkit-replan`;
   - эпик без плана → `devkit-epic-plan`;
   - L + несколько ролей/репозиториев → `devkit-team-run`;
   - нужна только независимая проверка → `devkit-team-check`;
   - профиль не настроен → `devkit-profile-setup`.
5. Загрузи выбранный навык и следуй ему. Не дублируй его шаги здесь и не
   выполняй несколько основных навыков параллельно в одном агенте.
6. После реализации обязательно `devkit-task-verify` (проверки), затем
   `devkit-team-sync` и `devkit-team-check`; выпуск — `devkit-task-ship`.

## Промпты субагентов

Маршрутизатор субагентов не запускает. Если задача уходит в AgentTeam, роль и
промпт выбирает `devkit-team-run` из `.agents/prompts/<role>.md`.

## Если инструмент недоступен

- graphify нет → `grep`/`rg`, чтение файлов, `git log -S`, `git grep`; пометь в отчёте.
- ponytail нет → правила `devkit-lifecycle` (минимальный diff, stdlib/native,
  одна runnable проверка).
- Нет task-токена → остановись и запроси у владельца; не используй owner-сессию.
- `devkit task show` не работает → читай `tasks/<id>.md` и `plans/<id>/`
  напрямую, зафиксируй деградацию.

## Доказательства

- `devkit task show <id> --json` до и после выбора режима.
- Решение о режиме с обоснованием (S/M/L, тип, риск) — в комментарии или отчёте.
- Список загруженных навыков и ролей.

## Если не получилось

Не угадывай режим по названию задачи: если данных для классификации не хватает
(нет acceptance, scope, профиля), задай владельцу один блокирующий вопрос.
Нет ответа в разумное время → `devkit-team-escalate`: статус `blocked`, что
именно неизвестно и какой ответ нужен. Не начинай реализацию «наугад».
