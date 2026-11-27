import pathlib
p = pathlib.Path(r"X:\devkit_projects\projects\atlas\repo\atlas\.gitignore")
s = p.read_text(encoding="utf-8")
s = s.replace("viewer/node_modules/", "web/node_modules/").replace("viewer/dist/", "web/dist/")
p.write_text(s, encoding="utf-8")
print("gitignore updated")
