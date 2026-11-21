"""Общий слой retrieval: BGE-M3 + Qdrant + чтение документов."""
from __future__ import annotations

import json
import os
import re
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache" / "huggingface"
CACHE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("HF_HOME", str(CACHE))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

from qdrant_client import QdrantClient, models  # noqa: E402

MODEL_NAME = "BAAI/bge-m3"
RERANK_MODEL = "BAAI/bge-reranker-v2-m3"
DEFAULT_COLLECTION = os.environ.get("ATLAS_COLLECTION", "kb_chunks")
DEFAULT_QDRANT = os.environ.get("ATLAS_QDRANT_URL", "http://127.0.0.1:6333")
PROCESSED = ROOT / "data" / "processed"
META = ROOT / "data" / "meta"
LOG_PATH = Path(os.environ.get("ATLAS_LOG", str(ROOT / "logs" / "queries.jsonl")))

_model = None
_client = None
_reranker = None
_lock = threading.RLock()

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def get_model():
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                from FlagEmbedding import BGEM3FlagModel

                _model = BGEM3FlagModel(MODEL_NAME, use_fp16=False)
    return _model


def get_client(url: str = DEFAULT_QDRANT) -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(url=url)
    return _client


def get_reranker():
    global _reranker
    if _reranker is None:
        with _lock:
            if _reranker is None:
                from FlagEmbedding import FlagReranker

                _reranker = FlagReranker(RERANK_MODEL, use_fp16=False)
    return _reranker


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


def rrf_merge(hit_lists: list[list], k: int = 60) -> list[dict]:
    fused: dict[str, dict] = {}
    for hits in hit_lists:
        for rank, hit in enumerate(hits, 1):
            entry = fused.setdefault(hit.id, {"hit": hit, "score": 0.0})
            entry["score"] += 1.0 / (k + rank)
    return sorted(fused.values(), key=lambda item: item["score"], reverse=True)


def rerank_results(
    query: str, results: list[dict], top_n: int = 20
) -> list[dict]:
    candidates = results[:top_n]
    if not candidates:
        return candidates
    reranker = get_reranker()
    pairs = [[query, result["text"]] for result in candidates]
    with _lock:
        scores = reranker.compute_score(
            pairs,
            batch_size=8,
            max_length=1024,
        )
    if isinstance(scores, (int, float)):
        scores = [scores]
    else:
        scores = list(scores)
    for result, score in zip(candidates, scores):
        result["rerank_score"] = float(score)
    return sorted(
        candidates,
        key=lambda result: result.get("rerank_score", -1e9),
        reverse=True,
    )


def search(
    query: str,
    limit: int = 5,
    collection: str = DEFAULT_COLLECTION,
    qdrant: str = DEFAULT_QDRANT,
    rerank: bool = False,
    candidate_limit: int = 20,
) -> list[dict]:
    query = query.strip()
    if not query:
        raise ValueError("empty query")
    candidate_limit = max(candidate_limit, limit)
    model = get_model()
    with _lock:
        output = model.encode(
            [query],
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False,
        )
    dense = output["dense_vecs"][0].tolist()
    sparse = to_sparse(output["lexical_weights"][0])

    client = get_client(qdrant)
    hits_limit = max(limit * 3, candidate_limit if rerank else 0, 10)
    dense_hits = client.query_points(
        collection_name=collection,
        query=dense,
        using="dense",
        limit=hits_limit,
        with_payload=True,
    ).points
    sparse_hits = client.query_points(
        collection_name=collection,
        query=sparse,
        using="sparse",
        limit=hits_limit,
        with_payload=True,
    ).points

    take = candidate_limit if rerank else limit
    results = []
    for entry in rrf_merge([dense_hits, sparse_hits])[:take]:
        payload = entry["hit"].payload or {}
        results.append(
            {
                "score": round(entry["score"], 6),
                "doc_id": payload.get("doc_id"),
                "chunk_id": payload.get("chunk_id"),
                "title": payload.get("title"),
                "chunk_index": payload.get("chunk_index"),
                "token_count": payload.get("token_count"),
                "source_path": payload.get("source_path"),
                "content_hash": payload.get("content_hash"),
                "type": payload.get("type"),
                "sphere": payload.get("sphere"),
                "project": payload.get("project"),
                "summary": payload.get("summary"),
                "text": payload.get("text", ""),
            }
        )

    if rerank:
        results = rerank_results(query, results, top_n=candidate_limit)

    return results[:limit]


def get_document(
    doc_id: str,
    max_chars: int = 20000,
    processed: Path = PROCESSED,
    meta: Path = META,
) -> dict:
    doc_id = doc_id.strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", doc_id):
        return {"ok": False, "doc_id": doc_id, "error": "invalid doc_id"}

    path = processed / f"{doc_id}.md"
    meta_path = meta / f"{doc_id}.json"
    if not path.exists():
        return {"ok": False, "doc_id": doc_id, "error": "document not found"}

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "doc_id": doc_id, "error": str(exc)}

    record: dict = {}
    if meta_path.exists():
        try:
            record = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            record = {}

    truncated = len(text) > max_chars
    return {
        "ok": True,
        "doc_id": doc_id,
        "title": record.get("title", doc_id),
        "source_path": record.get("source_path", ""),
        "content_hash": record.get("content_hash", ""),
        "text": text[:max_chars],
        "truncated": truncated,
        "metadata": record,
    }


def log_event(
    tool: str,
    payload: dict,
    result_count: int,
    latency_ms: int,
    status: str = "ok",
    error: str | None = None,
) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "ts": now_iso(),
        "tool": tool,
        "payload": payload,
        "results": result_count,
        "latency_ms": latency_ms,
        "status": status,
    }
    if error:
        event["error"] = error
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
