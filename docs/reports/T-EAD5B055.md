---
id: R-f4e752ce0f
type: report
title: Отчёт T-EAD5B055
task: T-EAD5B055
status: final
created_at: 2026-11-27T20:54:33.430Z
updated_at: 2026-11-27T20:54:33.430Z
---

# Отчёт T-EAD5B055 — переименование `viewer/` в `web/`

## Что сделано

Каталог фронтенда переименован `repo/atlas/viewer` → `repo/atlas/web`, и все
живые ссылки на старое имя обновлены. Поведение приложения не менялось:
переименование подтверждено тем же профилем (e2e/a11y/SPA-fallback работают от
`web/dist`), а не только диффом.

**Переименование одним коммитом:** файловая система (`Move-Item`) + `git add -A`
— git увидел это как rename (**106 файлов**, 2 вставки: правки `.gitignore`),
а не delete+add, поэтому история файлов сохранилась.

**Конфиги и код:**
- `web/package.json` и `package-lock.json` → `"name": "atlas-web"`.
- `app/backend/main.py`: `dist = ROOT / "web" / "dist"`, mount `name="web"`.
- `.github/workflows/ci.yml`: `working-directory: web`, artifact `web-dist`,
  шаги `upload-web-dist`/`download-web-dist`, `path: web/dist`.
- `.pre-commit-config.yaml`: `node web/node_modules/...`, `files: ^web/src/...`.
- `pyproject.toml`: `exclude = [..., "web"]`.
- `.gitignore`: `viewer/node_modules/` → `web/node_modules/`,
  `viewer/dist/` → `web/dist/`.
- `.git-blame-ignore-revs`: комментарий про prettier указывает на `web`.

**Тесты:**
- `git mv tests/test_viewer_acceptance.py tests/test_web_acceptance.py`
  (переименование, не удаление; классы/переменные `Viewer*`/`VIEWER` → `Web*`/`WEB`).
- `test_web_build.py`, `test_spa_fallback.py`, `test_growth.py`,
  `test_app_auth.py`, `test_push.py` — пути `web/...`, тексты скипов,
  `test_root_json_without_web_build`.

**Документация app-репозитория:** `AGENTS.md` (команды, FSD-структура, hooks),
`app/README.md`, `docs/DESIGN-SYSTEM.md`. Исторический
`docs/coordination/archive/DEVKIT.md` не переписывался (ТЗ R4).

**Профиль devkit:** в `devkit.yaml` 8 путей `cwd` (`repo\atlas\web`) и setup
`install-viewer` → `install-web`; имена проверок не менялись.

**Инцидент, который поймали до пуша:** корневой `.gitignore` содержал
*литеральные* `viewer/node_modules/` и `viewer/dist/`. После переименования они
перестали совпадать, и первый прогон `git add -A` притянул в индекс
**12 475 файлов `node_modules`** (коммит `17da6216` был создан и тут же отменён
через `git reset --soft HEAD~1`). Игнор-правила обновлены, переименование
перезакоммичено чисто: `staged=106`, `node_modules_staged=0`. Ничего не ушло в
удалённый репозиторий — коммит не пушился.

## Изменения

**Переименовано:** `viewer/` → `web/` (106 файлов), `tests/test_viewer_acceptance.py`
→ `tests/test_web_acceptance.py`.

**Изменены:** `.gitignore`, `.git-blame-ignore-revs`, `.pre-commit-config.yaml`,
`.github/workflows/ci.yml`, `pyproject.toml`, `app/backend/main.py`,
`tests/{test_web_build,test_spa_fallback,test_growth,test_app_auth,test_push,
test_web_acceptance}.py`, `AGENTS.md`, `app/README.md`, `docs/DESIGN-SYSTEM.md`,
`web/package.json`, `web/package-lock.json`; в data-репозитории — `devkit.yaml`.

**Коммиты (ветка `devkit/T-EAD5B055`):**

- `4ae6ab78` refactor(web): Переименовать viewer в web
- `49a0d9e5` refactor(web): Обновить пути и имена после переименования

## Проверки

- `git grep -i viewer` по отслеживаемым файлам (без `node_modules` и
  `docs/coordination/archive`): **0 файлов** — живых ссылок не осталось.
- `npm ci` в `web/` → exit 0, `npm run build` → exit 0, `web/dist/index.html`
  на месте.
- Целевые тесты: `python -m unittest tests.test_spa_fallback tests.test_web_build
  tests.test_web_acceptance` → **22 теста, OK** (SPA-fallback читает `web/dist`).
- `devkit profile test` на `49a0d9e5` → exit 0, обязательные passed:
  `web-build` (2.0 с), `typecheck-web` (1.3 с), `lint-web` (6.5 с),
  `arch-web` (2.0 с), `e2e` (10.3 с), `a11y` (12.6 с, axe 0),
  `unit-tests` (285 с), `lint-python`, `typecheck-python`, `arch-python`,
  `format-web`. `schema-check` (required:false) — красный по среде, как на
  baseline.

## Риски

1. **Внешние ссылки на старое имя** (IDE-воркспейсы, закладки, сторонние
   инструкции, скрипты вне репозитория) не проверялись — в репозитории их нет.
2. **`devkit.yaml` в data-репозитории** обновлён в этой же задаче; если у кого-то
   остался старый профиль в кэше CLI — поможет повторный `devkit profile show`.
3. **Локальный стенд** (`start-atlas.ps1`) берёт пути от `repo/atlas`, на `web`
   ссылок не имел — но health после переименования стоит проверить на живом
   стенде, когда будет собран `web/dist` (сборка есть).
4. **CI artifact переименован** (`viewer-dist` → `web-dist`) — если в GitHub
   есть внешние workflow/фильтры по имени artifact, их надо обновить.
