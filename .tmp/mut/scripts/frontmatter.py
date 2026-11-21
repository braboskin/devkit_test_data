"""Минимальный парсер YAML-подобного frontmatter без внешних зависимостей.

Поддерживает: скаляры, числа, bool, null, списки в [a, b] и блочные списки
через "- item". Формат держим простым — вложенные объекты не нужны.
"""
from __future__ import annotations

import re
from pathlib import Path

FM_RE = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n?(.*)$", re.S)


def parse_scalar(raw: str):
    s = raw.strip()
    if not s:
        return None
    if (s.startswith('"') and s.endswith('"')) or (
        s.startswith("'") and s.endswith("'")
    ):
        return s[1:-1]
    low = s.lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("null", "none", "~"):
        return None
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    if re.fullmatch(r"-?\d+\.\d+", s):
        return float(s)
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        if not inner:
            return []
        return [parse_scalar(x) for x in inner.split(",")]
    return s


def parse_frontmatter(text: str):
    m = FM_RE.match(text)
    if not m:
        return {}, text
    raw, body = m.group(1), m.group(2)
    meta: dict = {}
    current = None
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if re.match(r"^\s+-\s+", line):
            if current is None:
                continue
            item = re.sub(r"^\s+-\s+", "", line).strip()
            if not isinstance(meta.get(current), list):
                meta[current] = []
            meta[current].append(parse_scalar(item))
            continue
        m2 = re.match(r"^([A-Za-z0-9_]+):\s*(.*)$", line)
        if m2:
            key, rest = m2.group(1), m2.group(2)
            current = key
            meta[key] = [] if rest.strip() == "" else parse_scalar(rest)
    return meta, body


def read(path: Path):
    return parse_frontmatter(path.read_text(encoding="utf-8"))


def set_field(path: Path, key: str, value: str) -> None:
    text = path.read_text(encoding="utf-8")
    m = FM_RE.match(text)
    if not m:
        raise ValueError(f"no frontmatter: {path}")
    raw, body = m.group(1), m.group(2)
    lines = raw.splitlines()
    found = False
    for i, line in enumerate(lines):
        if re.match(rf"^{re.escape(key)}:\s*", line):
            lines[i] = f"{key}: {value}"
            found = True
            break
    if not found:
        lines.append(f"{key}: {value}")
    new_text = "---\n" + "\n".join(lines) + "\n---\n" + body
    path.write_text(new_text, encoding="utf-8")
