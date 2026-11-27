import pathlib
from pathlib import Path

root = Path(__file__).resolve().parents[1]

# 1. ТЗ: base.css остаётся legacy до последней экранной задачи.
tz_path = root / "docs" / "tz" / "TZ-2F2279C9.md"
tz = tz_path.read_text(encoding="utf-8", newline="").replace("\r\n", "\n")
old_css = (
    "Удаляются `styles.css`, `styles/base.css`,\n"
    "`styles/shell.css`, `shared/ui/ui.css`, `pages/calendar/ui/calendar.css`,\n"
    "`pages/files/ui/files.css`. В `main.tsx` остаётся только импорт `tokens.css`."
)
new_css = (
    "Удаляются `styles/shell.css`, `shared/ui/ui.css`,\n"
    "`pages/calendar/ui/calendar.css`, `pages/files/ui/files.css`.\n"
    "`styles/base.css` — legacy-слой для ещё не переведённых экранов: он удаляется\n"
    "последней экранной задачей (T-7E446096), а не фундаментом, иначе экраны\n"
    "остаются без стилей и e2e/a11y падают. К концу эпика `styles.css` содержит\n"
    "только импорт `tokens.css`."
)
if old_css not in tz:
    raise SystemExit("TZ: css paragraph not found")
tz = tz.replace(old_css, new_css, 1)

old_a1 = "A1. Один `.css` (`tokens.css`); компонентных стилей в файлах нет; `steiger`,"
new_a1 = "A1. К концу эпика один `.css` (`tokens.css`); компонентных стилей в файлах нет; `steiger`,"
if old_a1 not in tz:
    raise SystemExit("TZ: A1 not found")
tz = tz.replace(old_a1, new_a1, 1)
tz_path.write_text(tz, encoding="utf-8", newline="")

# 2. Брифы: уточнение про legacy base.css.
briefs = {
    "T-4FC8A97B": "base.css остаётся legacy-слоем для ещё не переведённых экранов; "
    "удаляются только shell.css и ui.css, styles.css сводится к tokens.css.",
    "T-7E446096": "После перевода экранов удалить legacy base.css и последние "
    "классовые стили; styles.css оставляет только tokens.css.",
}
for task_id, note in briefs.items():
    path = root / "tasks" / f"{task_id}.md"
    text = path.read_text(encoding="utf-8", newline="").replace("\r\n", "\n")
    if note[:35] in text:
        continue
    path.write_text(text.rstrip("\n") + "\n" + note + "\n", encoding="utf-8", newline="")

print("ok")
