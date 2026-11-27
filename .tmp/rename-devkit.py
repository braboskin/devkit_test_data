import pathlib

p = pathlib.Path(r"X:\devkit_projects\projects\atlas\devkit.yaml")
s = p.read_text(encoding="utf-8")
before = s.count("repo\\atlas\\viewer")
s = s.replace(r"repo\atlas\viewer", r"repo\atlas\web")
s = s.replace("install-viewer", "install-web")
p.write_text(s, encoding="utf-8")
print("cwd replaced:", before, "install-viewer left:", s.count("install-viewer"))
