import pathlib
p = pathlib.Path(r"X:\devkit_projects\projects\atlas\repo\atlas\web\e2e\chat-features.spec.ts")
s = p.read_text(encoding="utf-8")
s = s.replace("Ѐлка и ёж", "Ёлка и ёж")
p.write_text(s, encoding="utf-8")
print("title fixed:", "Ёлка и ёж" in s)
