"""Единая точка knowledge core для API и воркера.

`analyze_file` — извлечение + аннотация; `should_defer` — решение быстрый путь
или отложенная job (`extract` / `extract-full`), без OCR внутри решения.
"""
from __future__ import annotations

import mimetypes
import re
from pathlib import Path

import pymupdf

from .annotate import annotate
from .extract import (
    IMAGE_EXT,
    PDF_EXT,
    SUPPORTED,
    extract_file,
    normalize_body,
)

PDF_FULL_MAX_PAGES = 20
PDF_FULL_MAX_BYTES = 20 * 1024 * 1024
TEXT_LAYER_MIN_CHARS = 40


def _suffix(path: Path, original_name: str | None, mime: str | None) -> str:
    for candidate in (path.suffix, Path(original_name or "").suffix):
        if candidate.lower() in SUPPORTED:
            return candidate.lower()
    guessed = mimetypes.guess_extension((mime or "").split(";")[0].strip())
    return (guessed or path.suffix or "").lower()


def should_defer(
    path: Path, mime: str | None = None, size_bytes: int = 0
) -> dict:
    path = Path(path)
    suffix = _suffix(path, None, mime)
    mime = (mime or "").lower()

    if suffix in IMAGE_EXT or mime.startswith("image/"):
        return {"defer": True, "kind": "extract", "reason": "image requires ocr"}
    if suffix not in PDF_EXT and mime != "application/pdf":
        return {"defer": False, "kind": None, "reason": "text format, inline"}

    if size_bytes > PDF_FULL_MAX_BYTES:
        return {"defer": True, "kind": "extract-full", "reason": "pdf too large"}

    try:
        document = pymupdf.open(str(path))
    except Exception as exc:  # битый/зашифрованный PDF — отдаём воркеру
        return {
            "defer": True,
            "kind": "extract-full",
            "reason": f"pdf unreadable: {exc}",
        }
    try:
        pages = document.page_count
        pages_with_text = sum(
            1
            for page in document
            if len(page.get_text("text").strip()) >= TEXT_LAYER_MIN_CHARS
        )
    finally:
        document.close()

    if pages > PDF_FULL_MAX_PAGES:
        return {
            "defer": True,
            "kind": "extract-full",
            "reason": "pdf too many pages",
        }
    if pages_with_text * 2 < pages:
        return {
            "defer": True,
            "kind": "extract",
            "reason": "pdf mostly without text layer",
        }
    return {"defer": False, "kind": None, "reason": "pdf fast path"}


def analyze_file(
    path: Path, original_name: str | None = None, mime: str | None = None
) -> dict:
    path = Path(path)
    name = original_name or path.name
    suffix = _suffix(path, original_name, mime)
    extracted = extract_file(path, suffix=suffix)

    text = normalize_body(extracted.get("text", ""))
    frontmatter = extracted.get("meta") or {}
    meta = {
        "source_path": name,
        "format": extracted.get("format") or suffix.lstrip("."),
        "quality": extracted.get("quality", "ok"),
        "word_count": len(re.findall(r"\w+", text, flags=re.UNICODE)),
        "frontmatter": frontmatter,
    }
    annotation = annotate(text, meta)
    quality = str(extracted.get("quality", "ok"))
    title = str(extracted.get("title") or frontmatter.get("title") or "").strip()
    if not title:
        title = Path(name).stem

    return {
        "text": text,
        "pages": extracted.get("pages"),
        "engine": extracted.get("engine", "unknown"),
        "quality": quality,
        "reason": extracted.get("reason", ""),
        "title": title,
        "doc_class": annotation["doc_class"],
        "annotation": annotation["annotation"],
        "tags": annotation["tags"],
        "entities": annotation["entities"],
        "needs_review": quality != "ok" or not text.strip(),
    }
