import pathlib
p = pathlib.Path(r"X:\devkit_projects\projects\atlas\repo\atlas\web\src\pages\settings\ui\Settings.tsx")
s = p.read_text(encoding="utf-8")
s = s.replace("    let data: Record<string, unknown> = {};\n", "    let data: Record<string, unknown>;\n", 1)
p.write_text(s, encoding="utf-8")
print("patched")
