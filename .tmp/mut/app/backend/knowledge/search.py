"""Гибридный поиск по знаниям: PostgreSQL FTS + Qdrant (dense+sparse) → RRF.

`search` — лексика и векторы сливаются RRF (k=60), результат гидратируется из
БД (единственный источник истины и фильтра `owner_id`). `similar` — по векторам
чанков документа ищет похожие, агрегирует по документу.
"""
from __future__ import annotations

import logging
import math
import re
from datetime import datetime, timezone

from qdrant_client import models
from sqlalchemy import bindparam, case, func, text
from sqlalchemy.orm import Session

from ..models import Chunk, Document, User
from ..ownership import get_owned_or_404
from . import indexer
from .embeddings import encode_query, to_sparse

logger = logging.getLogger(__name__)

RRF_K = 60
MAX_LIMIT = 50
WORD_RE = re.compile(r"\w+", re.UNICODE)


def _naive_utc(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _rrf(hit_lists: list[list]) -> list[tuple]:
    """Reciprocal rank fusion: списки уже ранжированы, ключ — `hit[0]`."""
    fused: dict = {}
    for hits in hit_lists:
        for rank, hit in enumerate(hits, 1):
            fused[hit[0]] = fused.get(hit[0], 0.0) + 1.0 / (RRF_K + rank)
    return sorted(fused.items(), key=lambda item: item[1], reverse=True)


def _result(document: Document, chunk: Chunk, score: float) -> dict:
    return {
        "score": round(float(score), 6),
        "document_id": document.id,
        "title": document.title,
        "chunk_id": chunk.id,
        "ord": chunk.ord,
        "text": chunk.text,
        "sphere_id": document.sphere_id,
        "project_id": document.project_id,
        "doc_class": document.doc_class,
        "status": document.status,
        "tags": document.tags or [],
    }


def _hydrate(db: Session, user: User, scored: list[tuple]) -> list[dict]:
    """`[(chunk_id, score)]` → результаты; чанки вне БД/владения отбрасываются."""
    chunk_ids = [chunk_id for chunk_id, _ in scored]
    if not chunk_ids:
        return []
    rows = (
        db.query(Chunk, Document)
        .join(Document, Document.id == Chunk.document_id)
        .filter(
            Chunk.owner_id == user.id,
            Document.owner_id == user.id,
            Chunk.id.in_(chunk_ids),
        )
        .all()
    )
    found = {chunk.id: (chunk, document) for chunk, document in rows}
    results = []
    for chunk_id, score in scored:
        pair = found.get(chunk_id)
        if pair is not None:
            results.append(_result(pair[1], pair[0], score))
    return results


# ---------- фильтры ----------


def _allowed_ids(
    db: Session,
    user: User,
    *,
    sphere_id: int | None,
    project_id: int | None,
    doc_type: str | None,
    doc_class: str | None,
    status: str | None,
    tags: list[str] | None,
    date_from: datetime | None,
    date_to: datetime | None,
) -> list[int]:
    """Документы владельца, прошедшие фильтры; затем семантикой/лексикой."""
    query = db.query(Document.id, Document.tags).filter(Document.owner_id == user.id)
    if sphere_id is not None:
        query = query.filter(Document.sphere_id == sphere_id)
    if project_id is not None:
        query = query.filter(Document.project_id == project_id)
    if doc_type is not None:
        query = query.filter(Document.source_type == doc_type)
    if doc_class is not None:
        query = query.filter(Document.doc_class == doc_class)
    if status is not None:
        query = query.filter(Document.status == status)
    if date_from is not None:
        query = query.filter(Document.created_at >= _naive_utc(date_from))
    if date_to is not None:
        query = query.filter(Document.created_at <= _naive_utc(date_to))
    rows = query.all()
    if not tags:
        return [document_id for document_id, _ in rows]
    wanted = set(tags)
    # ponytail: тег сравнивается в Python (JSONB `@>` — если корпус станет большим).
    return [
        document_id
        for document_id, document_tags in rows
        if wanted & set(document_tags or [])
    ]


# ---------- лексика ----------


def _lexical_chunks(
    db: Session, owner_id: str, q: str, document_ids: list[int], limit: int
) -> list[tuple]:
    if not document_ids:
        return []
    if db.get_bind().dialect.name == "postgresql":
        statement = text(
            "SELECT chunks.id AS chunk_id, "
            "ts_rank(to_tsvector('russian', chunks.text), "
            "plainto_tsquery('russian', :q)) AS rank "
            "FROM chunks JOIN documents ON documents.id = chunks.document_id "
            "WHERE chunks.owner_id = :owner_id "
            "AND chunks.document_id IN :document_ids "
            "AND to_tsvector('russian', chunks.text) @@ "
            "plainto_tsquery('russian', :q) "
            "ORDER BY rank DESC LIMIT :limit"
        ).bindparams(bindparam("document_ids", expanding=True))
        rows = db.execute(
            statement,
            {
                "q": q,
                "owner_id": owner_id,
                "document_ids": document_ids,
                "limit": limit,
            },
        ).all()
        return [(row.chunk_id, float(row.rank)) for row in rows]

    # SQLite (тесты): нет FTS-конфигурации «russian» — LIKE по словам запроса.
    words = WORD_RE.findall(q)[:16]
    if not words:
        return []
    matches = [Chunk.text.ilike(f"%{word}%") for word in words]
    rank = func.sum(case(*[(match, 1) for match in matches], else_=0))
    query = (
        db.query(Chunk.id, rank.label("rank"))
        .filter(
            Chunk.owner_id == owner_id,
            Chunk.document_id.in_(document_ids),
            *matches,
        )
        .group_by(Chunk.id)
        .order_by(rank.desc(), Chunk.id)
        .limit(limit)
    )
    return [(chunk_id, float(score or 0.0)) for chunk_id, score in query.all()]


# ---------- семантика ----------


def _hit_chunk_id(hit) -> int | None:
    payload = hit.payload or {}
    chunk_id = payload.get("chunk_id")
    return int(chunk_id) if chunk_id is not None else None


def _semantic_chunks(
    owner_id: str, document_ids: list[int], q: str, limit: int
) -> list[tuple]:
    if not document_ids:
        return []
    try:
        vector = encode_query(q)
        client = indexer.get_client()
        name = indexer.collection_name()
        if not client.collection_exists(name):
            return []
        query_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="owner_id", match=models.MatchValue(value=owner_id)
                ),
                models.FieldCondition(
                    key="document_id", match=models.MatchAny(any=document_ids)
                ),
            ]
        )
        hit_lists: list[list[tuple]] = []
        query_values = [("dense", vector["dense"])]
        if vector["sparse"]:
            query_values.append(("sparse", to_sparse(vector["sparse"])))
        for using, query_value in query_values:
            points = client.query_points(
                name,
                query=query_value,
                using=using,
                limit=limit,
                query_filter=query_filter,
                with_payload=True,
            ).points
            hit_lists.append(
                [
                    (chunk_id, float(point.score))
                    for point in points
                    if (chunk_id := _hit_chunk_id(point)) is not None
                ]
            )
        return _rrf(hit_lists)
    except Exception as exc:  # noqa: BLE001 — деградация до лексики, без секретов
        logger.warning("vector search unavailable: %s", exc.__class__.__name__)
        return []


# ---------- публичный API ----------


def search(
    db: Session,
    user: User,
    q: str,
    *,
    sphere_id: int | None = None,
    project_id: int | None = None,
    doc_type: str | None = None,
    doc_class: str | None = None,
    status: str | None = None,
    tags: list[str] | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = 10,
) -> list[dict]:
    q = (q or "").strip()
    if not q:
        return []
    limit = max(1, min(int(limit), MAX_LIMIT))
    candidates = max(limit * 3, 20)
    document_ids = _allowed_ids(
        db,
        user,
        sphere_id=sphere_id,
        project_id=project_id,
        doc_type=doc_type,
        doc_class=doc_class,
        status=status,
        tags=tags,
        date_from=date_from,
        date_to=date_to,
    )
    if not document_ids:
        return []
    lexical = _lexical_chunks(db, user.id, q, document_ids, candidates)
    semantic = _semantic_chunks(user.id, document_ids, q, candidates)
    fused = _rrf([lexical, semantic])
    return _hydrate(db, user, fused[:limit])


def _mean_dense(vectors: list) -> list[float]:
    vectors = [vector for vector in vectors if vector]
    if not vectors:
        return []
    size = len(vectors[0])
    mean = [0.0] * size
    for vector in vectors:
        if len(vector) != size:
            continue
        for index, value in enumerate(vector):
            mean[index] += float(value)
    norm = math.sqrt(sum(value * value for value in mean))
    if norm == 0.0:
        return []
    return [value / norm for value in mean]


def _merge_sparse(vectors: list) -> models.SparseVector | None:
    weights: dict[int, float] = {}
    for vector in vectors:
        for index, value in zip(vector.indices, vector.values):
            if float(value) > weights.get(index, 0.0):
                weights[index] = float(value)
    if not weights:
        return None
    items = sorted(weights.items())
    return models.SparseVector(
        indices=[index for index, _ in items],
        values=[value for _, value in items],
    )


def _similar_hits(
    client,
    name: str,
    query_value,
    using: str,
    owner_id: str,
    document_id: int,
    limit: int,
) -> list[tuple]:
    points = client.query_points(
        name,
        query=query_value,
        using=using,
        limit=limit,
        query_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="owner_id", match=models.MatchValue(value=owner_id)
                )
            ],
            must_not=[
                models.FieldCondition(
                    key="document_id", match=models.MatchValue(value=document_id)
                )
            ],
        ),
        with_payload=True,
    ).points
    hits = []
    for point in points:
        payload = point.payload or {}
        chunk_id = payload.get("chunk_id")
        hit_document_id = payload.get("document_id")
        if chunk_id is None or hit_document_id is None:
            continue
        hits.append((int(chunk_id), int(hit_document_id), float(point.score)))
    return hits


def similar(
    db: Session, user: User, document_id: int, limit: int = 10
) -> list[dict]:
    """Похожие документы по векторам чанков; чужой/несуществующий → 404."""
    document = get_owned_or_404(db, Document, document_id, user)
    limit = max(1, min(int(limit), MAX_LIMIT))
    point_ids = [
        chunk.qdrant_point_id
        for chunk in db.query(Chunk)
        .filter(
            Chunk.owner_id == user.id,
            Chunk.document_id == document.id,
            Chunk.qdrant_point_id.isnot(None),
        )
        .all()
    ]
    if not point_ids:
        return []
    try:
        client = indexer.get_client()
        name = indexer.collection_name()
        if not client.collection_exists(name):
            return []
        records = client.retrieve(name, ids=point_ids, with_vectors=True)
        vectors = [
            record.vector
            for record in records
            if isinstance(record.vector, dict)
        ]
        hit_lists: list[list[tuple]] = []
        dense = _mean_dense([vector.get("dense") for vector in vectors])
        if dense:
            hit_lists.append(
                _similar_hits(client, name, dense, "dense", user.id, document.id, limit * 3)
            )
        sparse = _merge_sparse(
            [vector["sparse"] for vector in vectors if vector.get("sparse")]
        )
        if sparse is not None:
            hit_lists.append(
                _similar_hits(
                    client, name, sparse, "sparse", user.id, document.id, limit * 3
                )
            )
        fused = _rrf(hit_lists)
    except Exception as exc:  # noqa: BLE001 — деградация, без секретов
        logger.warning("similar unavailable: %s", exc.__class__.__name__)
        return []

    chunk_documents = {
        hit[0]: hit[1] for hits in hit_lists for hit in hits
    }
    by_document: dict[int, tuple] = {}
    for chunk_id, score in fused:
        hit_document_id = chunk_documents.get(chunk_id)
        if hit_document_id is None:
            continue
        # fused отсортирован → первым у документа идёт его лучший чанк
        by_document.setdefault(hit_document_id, (chunk_id, score))
    return _hydrate(db, user, list(by_document.values())[:limit])
