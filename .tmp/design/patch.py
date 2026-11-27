import pathlib

p = pathlib.Path(__file__).with_name("mockup.html")
s = p.read_text(encoding="utf-8")

pairs = [
    (".content { flex: 1; overflow: hidden; padding: 22px 24px; }",
     ".content { flex: 1; overflow: hidden; padding: 18px 22px; }"),
    (".page-head { display: flex; align-items: flex-end; gap: 16px; margin-bottom: 20px; }",
     ".page-head { display: flex; align-items: flex-end; gap: 16px; margin-bottom: 16px; }"),
    (".page-head h1 { font-size: 30px; font-weight: 500; }",
     ".page-head h1 { font-size: 28px; font-weight: 500; }"),
    (".stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 16px; }",
     ".stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 14px; }"),
    (".stat { padding: 14px 16px; display: flex; flex-direction: column; gap: 8px; }",
     ".stat { padding: 12px 14px; display: flex; flex-direction: column; gap: 6px; }"),
    (".stat-value { font-size: 26px;", ".stat-value { font-size: 24px;"),
    (".grid { display: grid; grid-template-columns: 1.55fr 1fr; gap: 16px; align-items: start; }",
     ".grid { display: grid; grid-template-columns: 1.55fr 1fr; gap: 14px; align-items: start; }"),
    (".col { display: flex; flex-direction: column; gap: 16px; }",
     ".col { display: flex; flex-direction: column; gap: 14px; }"),
    ("padding: 14px 16px; border-bottom: 1px solid var(--border);",
     "padding: 11px 15px; border-bottom: 1px solid var(--border);"),
    (".panel-body { padding: 14px 16px; }", ".panel-body { padding: 12px 15px; }"),
    ("    padding: 10px 0;\n    border-bottom: 1px solid var(--border);\n    transition: background",
     "    padding: 8px 0;\n    border-bottom: 1px solid var(--border);\n    transition: background"),
    (".doc { display: flex; align-items: center; gap: 12px; padding: 10px 0;",
     ".doc { display: flex; align-items: center; gap: 12px; padding: 8px 0;"),
    (".habit { display: flex; align-items: center; gap: 10px; padding: 9px 0; }",
     ".habit { display: flex; align-items: center; gap: 10px; padding: 7px 0; }"),
    (".sphere { padding: 9px 0; }", ".sphere { padding: 7px 0; }"),
    (".agent-card { padding: 16px; display: flex; flex-direction: column; gap: 10px; }",
     ".agent-card { padding: 14px 15px; display: flex; flex-direction: column; gap: 8px; }"),
    ("  .toast {\n    position: fixed; right: 22px; bottom: 22px;\n    display: flex; align-items: center; gap: 10px;",
     "  .toast {\n    position: fixed; right: 22px; bottom: 108px;\n    display: none; align-items: center; gap: 10px;"),
    ("  .toast svg { width: 16px; height: 16px; color: var(--ok); }",
     "  .toast svg { width: 16px; height: 16px; color: var(--ok); }\n  body[data-screen=\"chat\"] .toast { display: flex; }"),
    ('<span class="hint">Enter — отправить, Shift+Enter — новая строка</span>',
     '<span class="hint">Enter — отправить</span>'),
    ("  document.body.dataset.palette = palette;\n  document.body.dataset.screen = screen;",
     "  document.body.dataset.palette = palette;\n  document.body.dataset.screen = screen;\n"
     "  const items = document.querySelectorAll('.nav .nav-item');\n"
     "  items.forEach((item) => item.removeAttribute('aria-current'));\n"
     "  const active = screen === 'chat' ? items[2] : items[0];\n"
     "  if (active) active.setAttribute('aria-current', 'page');"),
]

missing = []
for old, new in pairs:
    if old not in s:
        missing.append(old[:60])
        continue
    s = s.replace(old, new, 1)

p.write_text(s, encoding="utf-8")
print("patched", len(pairs) - len(missing), "of", len(pairs))
for item in missing:
    print("MISS:", item)
