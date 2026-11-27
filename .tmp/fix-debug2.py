import pathlib
p = pathlib.Path(r"X:\devkit_projects\projects\atlas\.tmp\debug-chat-flow.cjs")
s = p.read_text(encoding="utf-8")
s = s.replace("    (window as unknown as { __chat: typeof chatState }).__chat = chatState;", "    window.__chat = chatState;")
s = s.replace("      return original(input as RequestInfo, init);", "      return original(input, init);")
p.write_text(s, encoding="utf-8")
print("ts syntax removed")
