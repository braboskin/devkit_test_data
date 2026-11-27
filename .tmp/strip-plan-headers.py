import pathlib
import re

root = pathlib.Path(r"X:\devkit_projects\projects\atlas\plans")
tasks = [
    "T-12FFB688",
    "T-EBDB7D0F",
    "T-20ECAACF",
    "T-E12FC73C",
    "T-C36A88F7",
    "T-7B422390",
    "T-6BD45D6E",
]

for task in tasks:
    path = root / task / "v1.md"
    text = path.read_text(encoding="utf-8")
    stripped = re.sub(r"^---\r?\n[\s\S]*?\r?\n---\r?\n", "", text, count=1)
    if stripped == text:
        print(task, "no frontmatter")
        continue
    path.write_text(stripped.lstrip("\r\n"), encoding="utf-8")
    print(task, "stripped", len(text), "->", len(stripped))
