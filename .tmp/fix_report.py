import pathlib

path = pathlib.Path(".tmp/report-m3-live.md")
text = path.read_text(encoding="utf-8")
start = text.index("## Live smoke")
end = text.index("## Что не проверено")
section = """## Live smoke (реальный DeepSeek)

Прогон владельца, 2026-11-21, `repo/atlas` HEAD `87094eb` (codeSha `c210681…`),
модель `deepseek-chat`, `https://api.deepseek.com/v1`, скрипт
`.tmp/smoke_agent_llm.py` (временная SQLite/хранилище, `.tmp` вне git).

**22/22 проверок PASS**:

| Что | Факт |
| --- | --- |
| `POST /api/settings/llm/check` | 200 `ok=true`, 0.76 с |
| Стрим чата (SSE) | ответ с цитатой из «Анализы» (1 citation); **первый токен 0.62 с** (≤ 8 с) |
| Предложение | `propose_create_task` → `pending` → apply 200, задача создана, `audit` записан |
| Тест агента «Врач» (только сфера «Здоровье») | ответ по документу; история чатов/сообщений не изменилась |
| Онбординг | 15 ответов → профиль (15 тем + сводка) сохранён |
| Секреты | ключ маскирован в API, в БД только шифр, в ответах API не встречается |

Ограничения прогона: эмбеддинги fake (поиск лексический на SQLite), поэтому
проверены LLM + API + tool-calling + цитаты, но не BGE-M3/Qdrant и не
прод-PostgreSQL; UI не проверялся (`T-CA6FF8E2`).

"""
path.write_text(text[:start] + section + text[end:], encoding="utf-8")
print("ok")
