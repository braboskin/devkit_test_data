import re
import pathlib

path = pathlib.Path(
    r"X:\devkit_projects\projects\atlas\repo\atlas\viewer\src\pages\chat\ui\Chat.tsx"
)
text = path.read_text(encoding="utf-8").replace("\ufeff", "")

match = re.search(r"<Collapse[\s\S]*?\n\s*/>", text)
if not match:
    raise SystemExit("Collapse block not found")
block = match.group(0)
placeholder = "/*__COLLAPSE_BLOCK__*/"
text = text[: match.start()] + placeholder + text[match.end():]

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
            raise SystemExit(f"cannot map U+{code:04X} at {len(out)}: {ch!r}")

fixed = out.decode("utf-8", errors="strict")
fixed = fixed.replace(placeholder, block)

assert "Новый чат" in fixed, "no 'Новый чат' after reversal"
assert "Сообщение" in fixed or "сообщение" in fixed
assert "РЎ" not in fixed and "Р°" not in fixed, "mojibake leftovers"

path.write_text(fixed, encoding="utf-8")
print("fixed Chat.tsx, byte-fallbacks:", fallbacks, "len:", len(fixed))
