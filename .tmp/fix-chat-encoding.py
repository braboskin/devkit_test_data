import pathlib

path = pathlib.Path(
    r"X:\devkit_projects\projects\atlas\repo\atlas\viewer\src\pages\chat\ui\Chat.tsx"
)
text = path.read_text(encoding="utf-8").replace("\ufeff", "")

out = bytearray()
fallbacks = 0
for ch in text:
    code = ord(ch)
    try:
        out += ch.encode("cp1251")
    except UnicodeEncodeError:
        if code < 256:
            out.append(code)
            fallbacks += 1
        else:
            raise SystemExit(f"cannot map U+{code:04X} at {len(out)}")

try:
    fixed = out.decode("utf-8")
except UnicodeDecodeError as exc:
    raise SystemExit(f"decode failed: {exc}")

assert "Новый чат" in fixed, "no expected russian string after reversal"
assert "Сообщение" in fixed or "сообщение" in fixed

path.write_text(fixed, encoding="utf-8")
print("fixed Chat.tsx, byte-fallbacks:", fallbacks, "len:", len(fixed))
