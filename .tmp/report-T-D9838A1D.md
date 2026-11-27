# T-D9838A1D — Профиль: удаление фона и приоритет пресетов

## Что сделано

- `DELETE /api/profile/background` (в `features/agent/routers/onboarding.py`):
  берёт текущую ссылку, очищает `ui.background_ref` через
  `service.clear_background` (идемпотентно, остальные ключи `data` сохраняются),
  удаляет файл с диска, если он есть; отвечает `ProfileOut`.
- `shared/api.deleteBackground()`.
- `pages/profile`: кнопка «Убрать фон» (только если фон загружен) с
  подтверждением (`useConfirm`); после удаления — перезагрузка профиля и событие
  `atlas:background-changed`.
- `AppShell`: фон применяется через общую функцию; при отсутствии
  `background_ref` инлайн-переменная `--bg-image` **снимается**
  (`removeProperty`), поэтому пресеты темы снова работают; слушатель события
  обновляет фон без перезагрузки.
- Тест в `test_app_auth`: загрузка → удаление (`background_ref` исчезает,
  GET 404) → повторное удаление 200.

## Изменения

Общая ветка/PR с T-E4E99EF8; коммит `0ef60ff`.

Файлы: `app/backend/features/agent/{service.py,routers/onboarding.py}`,
`viewer/src/shared/api/index.ts`, `viewer/src/pages/profile/ui/Profile.tsx`,
`viewer/src/app/AppShell.tsx`, `tests/test_app_auth.py`.

## Проверки

| Проверка | Результат |
|---|---|
| unit-tests | exit 0 (полный прогон) |
| lint-python / typecheck-python / arch-python | exit 0 |
| web-build | exit 0, index 160.0 kB + lazy-чанки |
| typecheck-web / lint-web / arch-web / format-web | exit 0 |
| e2e / a11y | exit 0, 8 / 5 passed |
| web-тесты Python | 17 OK |

## Риски

- Удаление файла выполняется в роутере (файловый IO, не БД) — arch-тест
  проходит; при ошибке unlink (нет прав) остаётся 500 — файл-сирота, ссылка уже
  очищена. Можно сделать best-effort unlink в сервисе — follow-up.
- Если фон удалён из другой вкладки, текущая обновится только по событию
  (его шлёт страница профиля этой же вкладки); между вкладками — при следующей
  навигации.
