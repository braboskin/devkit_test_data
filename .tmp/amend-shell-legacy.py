import pathlib
from pathlib import Path

root = Path(__file__).resolve().parents[1]

tz_path = root / "docs" / "tz" / "TZ-2F2279C9.md"
tz = tz_path.read_text(encoding="utf-8", newline="").replace("\r\n", "\n")
old = (
    "Удаляются `styles/shell.css`, `shared/ui/ui.css`,\n"
    "`pages/calendar/ui/calendar.css`, `pages/files/ui/files.css`.\n"
    "`styles/base.css` — legacy-слой для ещё не переведённых экранов: он удаляется\n"
    "последней экранной задачей (T-7E446096), а не фундаментом, иначе экраны\n"
    "остаются без стилей и e2e/a11y падают. К концу эпика `styles.css` содержит\n"
    "только импорт `tokens.css`."
)
new = (
    "Удаляются `shared/ui/ui.css`, `pages/calendar/ui/calendar.css`,\n"
    "`pages/files/ui/files.css`. `styles/base.css` и `styles/shell.css` —\n"
    "legacy-слой для ещё не переведённых экранов (`.panel`, `.field`, `.card`,\n"
    "`.cards-grid`, `.profile-menu`, `.accent-swatch*`): они удаляются последней\n"
    "экранной задачей (T-7E446096), а не фундаментом, иначе экраны остаются без\n"
    "стилей и e2e/a11y падают. К концу эпика `styles.css` содержит только импорт\n"
    "`tokens.css`."
)
if old not in tz:
    raise SystemExit("TZ css paragraph not found")
tz = tz.replace(old, new, 1)
tz_path.write_text(tz, encoding="utf-8", newline="")

notes = {
    "T-4FC8A97B": "shell.css остаётся legacy до T-7E446096: классы .cards-grid/"
    ".profile-menu/.accent-swatch ещё используются экранами и панелью темы; "
    "каркас при этом полностью на Emotion.",
    "T-7E446096": "После перевода экранов удалить оба legacy-файла — base.css и "
    "shell.css; styles.css оставляет только tokens.css.",
}
for task_id, note in notes.items():
    path = root / "tasks" / f"{task_id}.md"
    text = path.read_text(encoding="utf-8", newline="").replace("\r\n", "\n")
    if note[:35] in text:
        continue
    path.write_text(text.rstrip("\n") + "\n" + note + "\n", encoding="utf-8", newline="")

print("ok")
