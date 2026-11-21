"""Эмбеддинги BGE-M3 (ленивый импорт) и детерминированный fake для тестов.

Реальный режим: `encode_texts` грузит `BGEM3FlagModel` только при первом вызове.
Fake (`ATLAS_EMBEDDINGS=fake`): векторы из sha256 текста, без сети и модели —
dense строится по 3-граммам слов (грубая морфологическая близость), sparse —
по словам. Так тесты видят и лексический, и «смысловой» сигнал.
"""
from __future__ import annotations

import hashlib
import math
import os
import re
import threading

from qdrant_client import models

from ..config import ROOT

MODEL_NAME = "BAAI/bge-m3"
DENSE_SIZE = 1024
CACHE_DIR = ROOT / ".cache" / "huggingface"
WORD_RE = re.compile(r"\w+", re.UNICODE)

_model = None
_model_lock = threading.RLock()


def use_fake() -> bool:
    return os.environ.get("ATLAS_EMBEDDINGS", "").strip().lower() == "fake"


def _model_load():
    """Модель BGE-M3: импорт FlagEmbedding и кэш HF — только здесь."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(CACHE_DIR))
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    from FlagEmbedding import BGEM3FlagModel

    return BGEM3FlagModel(MODEL_NAME, use_fp16=False)


def _model():
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                _model = _model_load()
    return _model


# ---------- fake-режим ----------


def _fake_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for word in WORD_RE.findall(text.lower()):
        if len(word) <= 3:
            tokens.append(word)
        else:
            tokens.extend(word[index : index + 3] for index in range(len(word) - 2))
    return tokens


def _fake_dense(text: str) -> list[float]:
    """Хеш-трюк: 3-граммы слов → нормализованный вектор 1024."""
    vector = [0.0] * DENSE_SIZE
    for token in _fake_tokens(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % DENSE_SIZE
        vector[index] += 1.0 if digest[4] & 1 else -1.0
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        vector[0] = 1.0
        return vector
    return [value / norm for value in vector]


def _fake_sparse(text: str) -> dict[str, float]:
    """Слова текста → веса вида `{token_id: tf}`; пустой результат невозможен."""
    weights: dict[str, float] = {}
    for word in WORD_RE.findall(text.lower()):
        digest = hashlib.sha256(word.encode("utf-8")).digest()
        key = str(int.from_bytes(digest[:4], "big"))
        weights[key] = weights.get(key, 0.0) + 1.0
    return weights


# ---------- публичный API ----------


def encode_texts(texts: list[str]) -> list[dict]:
    """`[{"dense": [1024 float], "sparse": {token_id: weight}}]`."""
    texts = list(texts)
    if not texts:
        return []
    if use_fake():
        return [
            {"dense": _fake_dense(text), "sparse": _fake_sparse(text)}
            for text in texts
        ]

    model = _model()
    with _model_lock:
        output = model.encode(
            texts,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False,
        )
    return [
        {
            "dense": [float(value) for value in dense],
            "sparse": {str(key): float(value) for key, value in sparse.items()},
        }
        for dense, sparse in zip(output["dense_vecs"], output["lexical_weights"])
    ]


def encode_query(text: str) -> dict:
    return encode_texts([text])[0]


def to_sparse(weights: dict) -> models.SparseVector:
    items = sorted(
        (int(key), float(value))
        for key, value in weights.items()
        if float(value) > 0
    )
    if not items:
        raise ValueError("empty sparse vector")
    return models.SparseVector(
        indices=[index for index, _ in items],
        values=[value for _, value in items],
    )
