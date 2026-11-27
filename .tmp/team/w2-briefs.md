# W2 — брифы: роутинг/404 (T-59D31937) и LLM (T-D24FD0BF)

Общие правила те же, что в `w1-briefs.md`: роль `frontend-engineer` /
`backend-engineer` (промпт роли читать из `.agents/prompts/`), только свой scope,
git и devkit не трогать, `console`/`any`/подавлений нет, стили — только
`@emotion/styled`, цвета — `var(--*)`, публичный API `shared/ui` заморожен,
перед ответом — проверки из брифа и exit codes.

Ветки: `lead` поднимает `devkit/<task-id>` от актуального `main`. Каждый WS
работает в общем дереве, файлы не пересекаются.

---

## T-59D31937 — WS-R1 (backend-engineer): SPA-fallback

**Scope:** `repo/atlas/app/backend/main.py`, `repo/atlas/tests/test_spa_fallback.py`,
`repo/atlas/tests/test_app_auth.py` (только если надо поправить ожидание).

**Сделать:**
1. Класс `SPAStaticFiles(StaticFiles)` в `main.py`: при `HTTPException(404)` и
   пути вне `/api/**` и `/health` отдать `index.html`; для API/health — 404 JSON.
   Монтирование как сейчас (`name="viewer"`, `dist = ROOT / "viewer" / "dist"`).
2. `tests/test_spa_fallback.py` (класс `SpaFallbackTests`): если
   `viewer/dist/index.html` нет — `skipTest` с текстом про сборку; иначе
   `GET /settings` и `/nope` → 200 `text/html` с `<div id="root">`;
   `GET /api/nope` → 404 JSON с `detail`; `GET /health` → 200 JSON.
3. Не менять существующие тесты, кроме случая, когда они прямо противоречат
   новому поведению (тогда пояснить в ответе).

**Проверки:** `.venv\Scripts\python.exe -m unittest tests.test_spa_fallback
tests.test_app_auth tests.test_web_build`; `ruff check .`; `mypy`.

**Готово когда:** на собранном фронте `GET /settings`, `/nope` отдают оболочку,
`/api/nope` — JSON 404, `/health` — JSON, тесты зелёные.

---

## T-59D31937 — WS-R2 (frontend-engineer): слайс 404

**Scope:** `repo/atlas/viewer/src/app/router.tsx`,
`repo/atlas/viewer/src/pages/not-found/**` (новый слайс),
`repo/atlas/viewer/e2e/not-found.spec.ts`.

**Сделать:**
1. Слайс `pages/not-found/`: `index.ts` (публичный API) + `ui/NotFound.tsx` —
   antd `Result status="404"`, заголовок «Страница не найдена», показ текущего
   `pathname` (из `useLocation`), кнопка «На главную» (`Button` из `shared/ui` +
   `useNavigate('/')`), внутри `AppShell` (маршрут в `children`).
2. `router.tsx`: wildcard `{ path: '*' }` → `<NotFound />`; легаси-редиректы
   (`today`, `documents`, `interests`) не трогать.
3. `e2e/not-found.spec.ts`: `goto('/nope')` → видим «Страница не найдена» и
   `/nope`; клик «На главную» → URL `/`; без ослаблений селекторов.
4. FSD: импорт только через `pages/not-found/index.ts`, `shared/ui` — через его
   `index.tsx`.

**Проверки (из `viewer`):** `npx tsc --noEmit`, `npx eslint .`,
`npx steiger ./src`, `npx prettier --check .`, `npm run build`;
e2e — `lead` после сборки (или `npx playwright test not-found.spec.ts` при уже
собранном `dist`).

**Готово когда:** `/nope` показывает страницу 404 в оболочке, сборка и
typecheck зелёные, e2e-спека описывает сценарий.

---

## T-D24FD0BF — WS-L1 (backend-engineer): эндпоинт списка моделей

**Scope:** `repo/atlas/app/backend/features/agent/llm.py`,
`repo/atlas/app/backend/features/settings/{service.py,routers/settings_llm.py}`,
`repo/atlas/tests/test_settings_models.py`, `tests/test_isolation.py`.

**Сделать:**
1. `llm.list_models(base_url, api_key) -> list[str]`: `client(...).get("models")`,
   не-200 → `LlmError("LLM model list failed: HTTP <code>")`, парсинг `data[].id`,
   дедуп, порядок провайдера; `httpx.HTTPError` → `LlmError`.
2. `service.list_models(db, user, base_url, api_key: str | None)`:
   `normalize_base_url` (ValueError → 422); пустой ключ → взять сохранённый, нет
   ключа → 400 «LLM key is not configured»; делегирование в `llm.list_models`.
3. `service.set_llm(..., api_key: str | None)`: пустой/None → сохранить прежний
   `api_key_enc` (записи нет → 400); `base_url`/`model` обновляются всегда.
4. Роутер: `POST /api/settings/llm/models` (`LlmModelsIn{base_url, api_key?}` →
   `LlmModelsOut{models, detail}`), `LlmError` → 200 `{models: [], detail}`;
   `PUT /api/settings/llm` — `api_key` необязателен, ответ прежний (маска).
5. Тесты `tests/test_settings_models.py` на `MockTransport` (успех, отказ
   провайдера → detail, ключ из хранилища, PUT без ключа сохраняет прежний,
   PUT без ключа без записи → 400, изоляция пользователей) + строка в матрицу
   `tests/test_isolation.py`.

**Проверки:** `unittest tests.test_settings_models tests.test_agent_llm
tests.test_isolation`; `ruff check .`; `mypy`.

**Готово когда:** список моделей приходит с провайдера, ключ нигде не
возвращается, `PUT` без ключа не затирает сохранённый, тесты зелёные.

---

## T-D24FD0BF — WS-L2 (frontend-engineer): форма модели

**Scope:** `repo/atlas/viewer/src/shared/ui/LlmSettingsForm.tsx` (новый) +
экспорт в `shared/ui/index.tsx`, `viewer/src/shared/lib/llmProviders.ts`,
`viewer/src/shared/api/index.ts`, `viewer/src/pages/settings/ui/Settings.tsx`
(только секция «Модель»), `viewer/src/app/SetupWizard.tsx` (только `ModelStep`),
`viewer/e2e/settings-llm.spec.ts`, `viewer/e2e/mockApi.ts` (новый маршрут).

**Сделать:**
1. `llmProviders.ts`: `providerByBaseUrl(baseUrl)` (trim slash; нет совпадения →
   `custom`).
2. `shared/api/index.ts`: `LlmModels {models: string[]; detail: string | null}`,
   `fetchLlmModels(baseUrl, apiKey?)`.
3. `LlmSettingsForm`: провайдер (`SelectField`), URL (`TextField`, только
   `custom`, иначе read-only подсказка), ключ (`TextField type="password"`,
   `placeholder="sk-..."`, `autoComplete="off"`), модель — antd `AutoComplete`
   (options из API + свободный ввод); кнопка «Загрузить модели» + авто-запрос
   через 500 мс после изменения ключа/URL (последний ответ выигрывает по
   счётчику); ошибка → `Alert kind="warning"` с `detail` + фолбэк на каталог;
   `variant="wizard"` (`Проверить`/`Сохранить`/`Позже`) и `variant="settings"`
   (статус, `Удалить ключ` с confirm); сохранение без повторного ввода ключа,
   если `configured`.
4. `SetupWizard.ModelStep` → `<LlmSettingsForm variant="wizard" …/>` с прежними
   колбэками; `Settings` — `<LlmSettingsForm variant="settings" …/>` вместо
   текущих полей (`base_url`, `model`, `api_key`, datalist).
5. E2E: `/settings` — провайдер виден; «Свой» показывает URL; моки отдают
   `/api/settings/llm/models`; поле модели предлагает id из списка.

**Проверки (из `viewer`):** `tsc`, `eslint`, `steiger`, `prettier`, `build`.

**Готово когда:** один компонент используется в онбординге и настройках,
список моделей грузится, ручной ввод работает, смена модели не требует ключа.
