"""Тонкая обёртка: логика в `app/backend/knowledge/triage.py`."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.backend.knowledge.triage import (  # noqa: E402,F401
    DEFAULT_META,
    DEFAULT_PROCESSED,
    POLICIES,
    PRIORITY,
    SENSITIVE_TAGS,
    SPHERE_MAP,
    classify,
    detect_language,
    main,
    make_summary,
    now_iso,
    run,
    save_json,
)

if __name__ == "__main__":
    raise SystemExit(main())
