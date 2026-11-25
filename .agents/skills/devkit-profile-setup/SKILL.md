---
name: devkit-profile-setup
description: Настройка профиля проекта — реальные команды проверок и setup для платформ, документация и инструменты; без фиктивных проверок.
user-invocable: true
---

# devkit-profile-setup — профиль проекта

## Когда

Новый проект; `devkit profile show` возвращает `missing`/`pending`/`invalid`;
проверки профиля не соответствуют репозиториям; изменились команды сборки или
платформы. Профиль — предпосылка планирования и выпуска: без него задача не
может закрыться.

## Инструменты

- `devkit profile show|set|test`, `devkit project show|profile|doctor`
- `devkit doc list|show`, `devkit task` (для проверки доступности задачи)
- git, grep/read, оболочка проекта (npm/pnpm/cargo/go/etc. — только чтение),
  graphify (опционально), ponytail
- Полный CLI-набор devkit: `devkit task plan`, `devkit task check`, `devkit task report`, `devkit doc`, `devkit profile`; применяй только относящиеся к навыку.

## Шаги

1. Собери факты: `devkit project show <slug> --json` (репозитории и ветки),
   `repo/<name>/` (наличие проектов, lock-файлов, скриптов), существующий
   `devkit.yaml` проекта.
2. Определи стек и реальные команды для каждой платформы (`windows`, `darwin`,
   `linux`): установка зависимостей (setup), `lint`, `typecheck`, `arch`
   (границы слоёв и импортов), unit/integration tests, build. Для линта, типов
   и архитектуры — отдельные проверки, а не одна общая; выбор инструментов —
   `devkit-code-quality` и `devkit-architecture`. Смотри
   `package.json`/`Makefile`/`Cargo.toml`/CI-конфиги, не придумывай команды.
3. Проверь каждую команду вручную из указанного `cwd` и зафиксируй exit code.
   Требования: хотя бы одна `required: true` проверка; `lint`, `typecheck` и
   `arch` присутствуют, если стек и объявленная структура это позволяют; у
   каждой проверки есть команда для текущей платформы; `cwd` внутри рабочего
   каталога проекта; `timeoutSec` 1–3600. Запрещены пустышки (`echo`, `true`,
   `exit 0`).
4. Опиши профиль в YAML:
   `profile.app` (name, stack), `profile.commands.verification`,
   `profile.commands.setup` (опционально), `profile.docs` (ссылки внутри
   проекта), `profile.tools` (только `graphify` и/или `ponytail`).
   Пример:
   ```yaml
   profile:
     app: { name: web, stack: [typescript, react] }
     commands:
       verification:
         - name: typecheck
           required: true
           run: { windows: "npm run typecheck", linux: "npm run typecheck", darwin: "npm run typecheck" }
           cwd: repo/web
           timeoutSec: 600
       setup:
         - name: install
           required: true
           run: { windows: "npm ci", linux: "npm ci", darwin: "npm ci" }
           cwd: repo/web
           timeoutSec: 900
     tools: [graphify, ponytail]
   ```
5. Запиши профиль: `devkit project profile set <slug> --file <file>` (или
   `devkit profile set`), затем `devkit profile test --json`. Статус должен
   стать `valid`; при ошибке исправь команду/`cwd` и повтори, не отключай
   проверку.
6. Закоммить `devkit.yaml` в data-репозиторий, приложи вывод `profile test`,
   попроси владельца подтвердить профиль в web.

## Промпты субагентов

- `.agents/prompts/backend-engineer.md` / `frontend-engineer.md` — определить
  команды конкретного приложения и проверить их;
- `.agents/prompts/test-engineer.md` — выбрать осмысленные проверки и пороги;
- `.agents/prompts/architect.md` — границы репозиториев и `cwd`.
Промпт роли подставляется в `prompt` вместе со списком репозиториев и выводом
пробных команд. Историю чата не передавай.

## Если инструмент недоступен

- graphify нет → анализ `package.json`, lock-файлов, CI-конфигов, grep/read,
  `git log` по истории команд.
- ponytail нет → правила `devkit-lifecycle`.
- `devkit profile test` не подключён → выполни команды вручную, сохрани вывод
  и exit code; отметь деградацию и не ставь `valid` без фактического прогона.
- Нет доступа к репозиторию/сети для установки зависимостей → профиль не
  выдумывай; зафиксируй `invalid`/`pending` и эскалируй.

## Доказательства

- `devkit profile test --json` с exit code каждой команды и итоговым статусом.
- `devkit.yaml` и его commit sha; список платформ, для которых проверено.
- Запись в отчёте: какие проверки обязательные, почему, что не проверено.

## Если не получилось

Если команда не воспроизводится (нет зависимостей, нет прав, платформа не
поддерживается), не подменяй её фиктивной. Оставь профиль в `pending`/`invalid`,
приложи лог и вызови `devkit-team-escalate` с конкретным запросом: доступ,
секрет, установка окружения или исключение платформы.
