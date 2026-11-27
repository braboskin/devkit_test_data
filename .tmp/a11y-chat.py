import pathlib
p = pathlib.Path(r"X:\devkit_projects\projects\atlas\repo\atlas\web\e2e\a11y.spec.ts")
s = p.read_text(encoding="utf-8")
old = "  { path: '/jobs', name: 'Задания' },\n];"
new = "  { path: '/jobs', name: 'Задания' },\n  { path: '/chat', name: 'Чат' },\n];"
assert old in s, "route list pattern not found"
s = s.replace(old, new, 1)
p.write_text(s, encoding="utf-8")
print("chat route added to a11y")
