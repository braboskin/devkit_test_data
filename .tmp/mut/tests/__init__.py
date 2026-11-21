"""Тестовая среда по умолчанию: без сети и без загрузки BGE-M3.

`ATLAS_EMBEDDINGS=fake` — детерминированные векторы; `ATLAS_QDRANT_URL=:memory:`
— локальный Qdrant. Тесты, которым нужны реальный Qdrant/PostgreSQL, задают
env сами (например, `tests/test_search.py`).
"""
import os

os.environ.setdefault("ATLAS_EMBEDDINGS", "fake")
os.environ.setdefault("ATLAS_QDRANT_URL", ":memory:")
