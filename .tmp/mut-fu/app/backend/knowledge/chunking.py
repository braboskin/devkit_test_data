"""Markdown-aware чанкинг: 300–800 токенов, overlap ~15%."""
from __future__ import annotations

import re

MIN_TOKENS = 300
MAX_TOKENS = 800
OVERLAP_RATIO = 0.15
SENTENCE_RE = re.compile(r"(?<=[.!?…])\s+")


def split_units(text: str) -> list[str]:
    units: list[str] = []
    for block in re.split(r"\n{2,}", text):
        block = block.strip()
        if not block:
            continue
        if block.startswith("#"):
            lines = block.splitlines()
            heading = lines[0].strip()
            if heading:
                units.append(heading)
            rest = "\n".join(lines[1:]).strip()
            if rest:
                for sentence in SENTENCE_RE.split(rest):
                    sentence = sentence.strip()
                    if sentence:
                        units.append(sentence)
        else:
            for sentence in SENTENCE_RE.split(block):
                sentence = sentence.strip()
                if sentence:
                    units.append(sentence)
    return units


def split_long_unit(unit: str, count_tokens, max_tokens: int) -> list[str]:
    words = unit.split()
    parts: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join(current + [word])
        if current and count_tokens(candidate) > max_tokens:
            parts.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        parts.append(" ".join(current))
    return parts


def chunk_text(
    text: str,
    count_tokens,
    min_tokens: int = MIN_TOKENS,
    max_tokens: int = MAX_TOKENS,
    overlap_ratio: float = OVERLAP_RATIO,
) -> list[dict]:
    units = split_units(text)
    expanded: list[str] = []
    for unit in units:
        if count_tokens(unit) > max_tokens:
            expanded.extend(split_long_unit(unit, count_tokens, max_tokens))
        else:
            expanded.append(unit)

    chunks: list[list[str]] = []
    current: list[str] = []
    current_tokens = 0

    for unit in expanded:
        unit_tokens = count_tokens(unit)
        if current and current_tokens + unit_tokens > max_tokens:
            chunks.append(current)
            target = max(1, int(current_tokens * overlap_ratio))
            overlap: list[str] = []
            overlap_tokens = 0
            for previous in reversed(current):
                previous_tokens = count_tokens(previous)
                if overlap and overlap_tokens + previous_tokens > target:
                    break
                overlap.insert(0, previous)
                overlap_tokens += previous_tokens
                if overlap_tokens >= target:
                    break
            current = overlap
            current_tokens = overlap_tokens

        while current and current_tokens + unit_tokens > max_tokens:
            dropped = current.pop(0)
            current_tokens -= count_tokens(dropped)

        current.append(unit)
        current_tokens += unit_tokens

    if current:
        chunks.append(current)

    result: list[dict] = []
    for chunk in chunks:
        chunk_text_value = "\n\n".join(chunk).strip()
        if not chunk_text_value:
            continue
        result.append(
            {
                "text": chunk_text_value,
                "token_count": count_tokens(chunk_text_value),
            }
        )
    return result
