import pathlib
p = pathlib.Path(r"X:\devkit_projects\projects\atlas\repo\atlas\.git-blame-ignore-revs")
s = p.read_text(encoding="utf-8")
s = s.replace("prettier (viewer,", "prettier (web,")
p.write_text(s, encoding="utf-8")
print("blame comment updated")
