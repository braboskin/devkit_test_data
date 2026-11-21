"""Экстрактивная аннотация: 1–3 предложения, класс документа, теги, сущности."""
from __future__ import annotations

import re

from . import triage
from .entities import extract_entities

SENTENCE_RE = re.compile(r"(?<=[.!?…])\s+")
MAX_SENTENCES = 3
MAX_CHARS = 600


def annotation_from_summary(summary: str) -> str:
    text = " ".join((summary or "").split())
    if not text:
        return ""
    sentences = [part.strip() for part in SENTENCE_RE.split(text) if part.strip()]
    annotation = " ".join(sentences[:MAX_SENTENCES])[:MAX_CHARS].strip()
    if annotation and annotation[-1] not in ".!?…":
        annotation += "."
    return annotation


def annotate(text: str, meta: dict | None = None) -> dict:
    """meta: {format, source_path, quality, word_count, frontmatter} или сам frontmatter."""
    meta = dict(meta or {})
    frontmatter = meta.get("frontmatter")
    if not isinstance(frontmatter, dict):
        frontmatter = meta
    record = {
        "frontmatter": frontmatter,
        "source_path": meta.get("source_path") or "",
        "format": meta.get("format") or "",
        "quality": meta.get("quality") or "ok",
        "word_count": meta.get("word_count") or len((text or "").split()),
    }
    classified = triage.classify(record, text or "")
    entities = extract_entities(text or "", frontmatter=frontmatter)
    return {
        "annotation": annotation_from_summary(classified["summary"]),
        "doc_class": classified["type"],
        "tags": entities["tags"],
        "entities": entities,
    }
