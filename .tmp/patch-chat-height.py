import pathlib

p = pathlib.Path(
    r"X:\devkit_projects\projects\atlas\repo\atlas\viewer\src\pages\chat\ui\Chat.tsx"
)
s = p.read_text(encoding="utf-8")

subs = [
    (
        "  gap: 16px;\n  align-items: start;\n  min-height: 0;\n\n  @media (max-width: 960px) {\n    grid-template-columns: minmax(0, 1fr);\n  }",
        "  gap: 16px;\n  align-items: stretch;\n  height: calc(100vh - 210px);\n  min-height: 420px;\n\n  @media (max-width: 960px) {\n    grid-template-columns: minmax(0, 1fr);\n    height: auto;\n  }",
    ),
    (
        "  min-height: 0;\n  max-height: calc(100vh - 220px);\n  padding: 16px;\n  overflow: hidden;",
        "  min-height: 0;\n  height: 100%;\n  padding: 16px;\n  overflow: hidden;",
    ),
    (
        "const Thread = styled(Column)`\n  max-height: calc(100vh - 220px);\n  padding: 0;\n  gap: 0;\n`;",
        "const Thread = styled(Column)`\n  padding: 0;\n  gap: 0;\n`;",
    ),
    (
        "const ChatList = styled.ul`\n  display: flex;\n  flex-direction: column;\n  gap: 4px;\n  margin: 0;\n  padding: 0;\n  list-style: none;\n  overflow-y: auto;\n`;",
        "const ChatList = styled.ul`\n  display: flex;\n  flex: 1;\n  flex-direction: column;\n  gap: 4px;\n  min-height: 0;\n  margin: 0;\n  padding: 0;\n  list-style: none;\n  overflow-y: auto;\n`;",
    ),
    (
        "const Messages = styled.ol`\n  display: flex;\n  flex-direction: column;\n  gap: 12px;\n  margin: 0;\n  padding: 16px;\n  overflow-y: auto;\n  list-style: none;\n`;",
        "const Messages = styled.ol`\n  display: flex;\n  flex: 1;\n  flex-direction: column;\n  gap: 12px;\n  min-height: 0;\n  margin: 0;\n  padding: 16px;\n  overflow-y: auto;\n  list-style: none;\n`;",
    ),
]

missing = []
for old, new in subs:
    if old not in s:
        missing.append(old.splitlines()[0])
        continue
    s = s.replace(old, new, 1)

p.write_text(s, encoding="utf-8")
print("patched", len(subs) - len(missing), "of", len(subs))
for item in missing:
    print("MISS:", item)
