import pathlib
root = pathlib.Path(r"X:\devkit_projects\projects\atlas\repo\atlas\viewer\src")
bad = []
for p in list(root.rglob("*.ts")) + list(root.rglob("*.tsx")):
    t = p.read_text(encoding="utf-8")
    fffd = t.count("\ufffd")
    mojo = sum(t.count(m) for m in ("Р°", "РЎ", "Рµ", "С‚", "вЂ"))
    if fffd or mojo:
        bad.append((str(p.relative_to(root)), fffd, mojo))
print("files with damage:", len(bad))
for name, fffd, mojo in bad:
    print(f"  {name}: U+FFFD={fffd} mojibake={mojo}")
