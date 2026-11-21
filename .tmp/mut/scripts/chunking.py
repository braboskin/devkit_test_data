"""Тонкая обёртка: логика в `app/backend/knowledge/chunking.py`."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.backend.knowledge.chunking import (  # noqa: E402,F401
    MAX_TOKENS,
    MIN_TOKENS,
    OVERLAP_RATIO,
    chunk_text,
    split_long_unit,
    split_units,
)
