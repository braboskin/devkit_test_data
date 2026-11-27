import pathlib
p = pathlib.Path(r"X:\devkit_projects\projects\atlas\.tmp\debug-chat-select.cjs")
s = p.read_text(encoding="utf-8")
s = s.replace("const { chromium } = require('@playwright/test');", "const { createRequire } = require('node:module');\nconst requireWeb = createRequire('X:/devkit_projects/projects/atlas/repo/atlas/web/package.json');\nconst { chromium } = requireWeb('@playwright/test');")
p.write_text(s, encoding="utf-8")
print("patched")
