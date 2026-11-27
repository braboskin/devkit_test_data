import pathlib, re
p = pathlib.Path(r"X:\devkit_projects\projects\atlas\repo\atlas\viewer\src\app\styles\base.css")
t = p.read_text(encoding="utf-8")
for i, line in enumerate(t.splitlines(), 1):
    if any(m in line for m in ("Р°", "РЎ", "Рµ", "С‚", "вЂ", "Рѕ", "Рё")):
        print(i, line.strip()[:120])
