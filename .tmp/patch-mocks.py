import pathlib
p = pathlib.Path(r"X:\devkit_projects\projects\atlas\.tmp\design\w3-shots.mjs")
s = p.read_text(encoding="utf-8")
s = s.replace(
  "      { id: 1, role: 'user', content: 'Собери каркас чата: список диалогов, тред и композер.' },",
  "      { id: 1, role: 'user', content: 'Собери каркас чата: список диалогов, тред и композер.', citations: [] },",
)
s = s.replace(
  "        'Готово. Слева — список диалогов и выбор агента, в центре — лента сообщений, снизу — композер.',",
  "        'Готово. Слева — список диалогов и выбор агента, в центре — лента сообщений, снизу — композер.',\n        citations: [],",
)
p.write_text(s, encoding="utf-8")
print("mocks patched")
