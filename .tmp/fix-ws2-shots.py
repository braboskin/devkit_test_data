import pathlib
p = pathlib.Path(r"X:\devkit_projects\projects\atlas\.tmp\design\ws2-shots.mjs")
s = p.read_text(encoding="utf-8")
s = s.replace("  '/api/profile': PROFILE,", "  '/api/profile': { data: PROFILE, summary: null, updated_at: null },")
p.write_text(s, encoding="utf-8")
print("mock fixed")
