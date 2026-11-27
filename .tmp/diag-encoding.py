import pathlib

root = pathlib.Path(
    r"X:\devkit_projects\projects\atlas\repo\atlas\viewer\src"
)
files = [
    root / "pages" / "chat" / "ui" / "Chat.tsx",
    root / "app" / "AppShell.tsx",
    root / "pages" / "home" / "ui" / "Home.tsx",
    root / "shared" / "ui" / "controls.tsx",
    root / "shared" / "ui" / "PageHeader.tsx",
    root / "pages" / "not-found" / "ui" / "NotFound.tsx",
]

for path in files:
    text = path.read_text(encoding="utf-8")
    proper = "Новый чат" in text or "Главная" in text or "Страница не найдена" in text
    moji = "РќРѕРІС‹Р№" in text or "Р“Р»Р°РІРЅР°СЏ" in text or "РЎС‚СЂР°РЅРёС†Р°" in text
    print(path.name, "proper=", proper, "mojibake=", moji)
    if moji and not proper:
        try:
            fixed = text.encode("cp1251").decode("utf-8")
            ok_proper = "Новый чат" in fixed or "Главная" in fixed
            print("  reversible:", ok_proper, "len", len(text), "->", len(fixed))
        except (UnicodeEncodeError, UnicodeDecodeError) as exc:
            print("  not reversible:", exc)
