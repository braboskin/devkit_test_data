import pathlib
root = pathlib.Path(r"X:\devkit_projects\projects\atlas\repo\atlas\viewer")
skip = {"node_modules", "dist", "test-results", ".cache", ".tmp"}
bad = []
for p in root.rglob("*"):
    if not p.is_file() or p.suffix not in {".ts", ".tsx", ".js", ".json", ".html", ".css"}:
        continue
    if any(part in skip or part.startswith(".") for part in p.relative_to(root).parts):
        continue
    try:
        t = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        bad.append((str(p.relative_to(root)), "not-utf8", 0))
        continue
    mojo = sum(t.count(m) for m in ("Р°", "РЎ", "Рµ", "С‚", "вЂ", "Рѕ", "Рё"))
    fffd = t.count("\ufffd")
    if mojo or fffd:
        bad.append((str(p.relative_to(root)), fffd, mojo))
print("damaged files:", len(bad))
for row in bad:
    print("  ", row)
