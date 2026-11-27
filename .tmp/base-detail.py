import pathlib
p = pathlib.Path(r"X:\devkit_projects\projects\atlas\repo\atlas\viewer\src\app\styles\base.css")
t = p.read_text(encoding="utf-8")
markers = ("Р°", "РЎ", "Рµ", "С‚", "вЂ", "Рѕ", "Рё")
for m in markers:
    idx = t.find(m)
    if idx >= 0:
        print(repr(m), "at", idx, "context:", repr(t[max(0,idx-30):idx+30]))
