"""Тонкая обёртка: логика в `app/backend/knowledge/extract.py`."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.backend.knowledge.extract import (  # noqa: E402,F401
    LANG,
    MIN_TEXT,
    OCR_DPI,
    SUPPORTED,
    extract_docx,
    extract_file,
    extract_image,
    extract_markdown,
    extract_pdf,
    normalize_body,
    ocr_image,
    parse_frontmatter,
    read_text,
    run_tesseract,
    tesseract_binary,
    tesseract_env,
)
