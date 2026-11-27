import pathlib
import re

root = pathlib.Path(r"X:\devkit_projects\projects\atlas\repo\atlas")

simple = [
    "web/package.json",
    "web/package-lock.json",
    "pyproject.toml",
    ".pre-commit-config.yaml",
    ".github/workflows/ci.yml",
    "app/backend/main.py",
    "tests/test_growth.py",
    "tests/test_app_auth.py",
    "tests/test_push.py",
    "tests/test_web_build.py",
    "tests/test_spa_fallback.py",
    "tests/test_viewer_acceptance.py",
    "AGENTS.md",
    "README.md",
    "app/README.md",
    "docs/DESIGN-SYSTEM.md",
]

for rel in simple:
    path = root / rel
    text = path.read_text(encoding="utf-8")
    count = len(re.findall(r"(?i)viewer", text))
    if count == 0:
        print(f"skip {rel}: no viewer")
        continue
    text = re.sub(r"viewer", "web", text)
    text = re.sub(r"Viewer", "Web", text)
    text = re.sub(r"VIEWER", "WEB", text)
    path.write_text(text, encoding="utf-8")
    print(f"{rel}: {count} replaced")
