import pathlib

root = pathlib.Path(r"X:\devkit_projects\projects\atlas\repo\atlas\viewer\src")
markers = ("Р°", "РЎ", "Рµ", "С‚", "П°", "вЂ")

corrupted = []
skipped = []

for path in sorted(root.rglob("*.ts")) + sorted(root.rglob("*.tsx")):
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        skipped.append((path, "not utf-8"))
        continue
    if "\ufeff" in text:
        text = text.replace("\ufeff", "")
    if not any(marker in text for marker in markers):
        continue
    try:
        fixed = text.encode("cp1251").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError) as exc:
        skipped.append((path, f"not reversible: {exc}"))
        continue
    has_cyrillic = any(
        "\u0400" <= ch <= "\u04ff" and ch not in "РС" for ch in fixed
    )
    if not has_cyrillic:
        skipped.append((path, "reversal gives no cyrillic"))
        continue
    path.write_text(fixed, encoding="utf-8")
    corrupted.append(str(path.relative_to(root)))

print("corrupted fixed:", len(corrupted))
for item in corrupted:
    print("  ", item)
print("skipped:", len(skipped))
for path, reason in skipped:
    print("  ", path.relative_to(root), "-", reason)
