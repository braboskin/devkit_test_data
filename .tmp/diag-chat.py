import pathlib, re
path = pathlib.Path(r"X:\devkit_projects\projects\atlas\repo\atlas\viewer\src\pages\chat\ui\Chat.tsx")
text = path.read_text(encoding="utf-8").replace("\ufeff", "")
match = re.search(r"<Collapse[\s\S]*?\n\s*/>", text)
block = match.group(0)
text2 = text[:match.start()] + "X" * len(block) + text[match.end():]
out = bytearray()
for ch in text2:
    code = ord(ch)
    try:
        out += ch.encode("cp1251")
    except UnicodeEncodeError:
        out.append(code & 0xFF)
try:
    fixed = out.decode("utf-8")
    print("OK")
except UnicodeDecodeError as exc:
    pos = exc.start
    print("fail at", pos, "byte", hex(out[pos]))
    print("orig context:", repr(text2[max(0, pos-60):pos+60]))
