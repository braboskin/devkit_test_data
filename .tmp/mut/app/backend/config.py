"""Конфигурация chat-приложения Atlas."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_URL = os.environ.get(
    "ATLAS_DB_URL",
    "postgresql+psycopg://atlas:atlas@127.0.0.1:5432/atlas",
)
COOKIE_NAME = "atlas_session"
COOKIE_SECURE = os.environ.get("ATLAS_COOKIE_SECURE", "0") == "1"
SESSION_DAYS = int(os.environ.get("ATLAS_SESSION_DAYS", "30"))

# Оригиналы документов — вне web-root; каталог создаётся при первой записи.
STORAGE_DIR = Path(os.environ.get("ATLAS_STORAGE_DIR", str(DATA_DIR / "storage")))
MAX_UPLOAD_MB = int(os.environ.get("ATLAS_MAX_UPLOAD_MB", "100"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
FETCH_TIMEOUT_SECONDS = 10
CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "ATLAS_CORS_ORIGINS", "http://localhost:5173"
    ).split(",")
    if origin.strip()
]
