"""Индексация чанков документов в Qdrant (dense + sparse).

Точка входа для API (`routers/documents.py`) и воркера: `index_document`,
`delete_document`. Коллекция — `ATLAS_COLLECTION` (default `kb_chunks`);
`ATLAS_QDRANT_URL=:memory:` — локальный клиент для тестов.
"""
from __future__ import annotations

import logging
import os
import threading
import uuid
import warnings

from qdrant_client import QdrantClient, models
from sqlalchemy.orm import Session

from ..models import Chunk, Document
from .embeddings import DENSE_SIZE, encode_texts, to_sparse

logger = logging.getLogger(__name__)

DEFAULT_URL = "http://127.0.0.1:6333"
DEFAULT_COLLECTION = "kb_chunks"
PAYLOAD_INDEXES = {
    "owner_id": models.PayloadSchemaType.KEYWORD,
    "document_id": models.PayloadSchemaType.INTEGER,
    "sphere_id": models.PayloadSchemaType.INTEGER,
    "project_id": models.PayloadSchemaType.INTEGER,
}

_client: QdrantClient | None = None
_client_lock = threading.Lock()


def collection_name() -> str:
    return os.environ.get("ATLAS_COLLECTION", DEFAULT_COLLECTION)


def get_client() -> QdrantClient:
    """Singleton; URL читается при первом обращении (тесты подменяют env)."""
    global _client
    with _client_lock:
        if _client is None:
            url = os.environ.get("ATLAS_QDRANT_URL", DEFAULT_URL)
            _client = (
                QdrantClient(":memory:") if url == ":memory:" else QdrantClient(url=url)
            )
        return _client


def reset_client() -> None:
    global _client
    with _client_lock:
        _client = None


def ensure_collection(client: QdrantClient | None = None) -> str:
    """Создать коллекцию и payload-индексы, если их ещё нет (идемпотентно)."""
    client = client or get_client()
    name = collection_name()
    if client.collection_exists(name):
        return name
    try:
        client.create_collection(
            name,
            vectors_config={
                "dense": models.VectorParams(
                    size=DENSE_SIZE, distance=models.Distance.COSINE
                )
            },
            sparse_vectors_config={"sparse": models.SparseVectorParams()},
        )
    except Exception:  # гонка двух процессов: коллекцию создал сосед
        if client.collection_exists(name):
            return name
        raise
    for field, schema in PAYLOAD_INDEXES.items():
        with warnings.catch_warnings():
            # ponytail: локальный Qdrant payload-индексы игнорирует и шумит —
            # глушим только это предупреждение; на сервере индексы реальные.
            warnings.simplefilter("ignore")
            client.create_payload_index(name, field_name=field, field_schema=schema)
    return name


def point_id(owner_id: str, document_id: int, ord_: int) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{owner_id}:{document_id}:{ord_}"))


def index_document(db: Session, document: Document) -> int:
    """Эмбеддинги чанков документа → Qdrant; вернуть число точек."""
    chunks = (
        db.query(Chunk)
        .filter_by(document_id=document.id, owner_id=document.owner_id)
        .order_by(Chunk.ord)
        .all()
    )
    if not chunks:
        delete_document(document.owner_id, document.id)
        return 0
    # Клиент и коллекция — до эмбеддингов: без Qdrant модель не грузим.
    client = get_client()
    name = ensure_collection(client)
    vectors = encode_texts([chunk.text for chunk in chunks])
    pairs = [
        (chunk, vector)
        for chunk, vector in zip(chunks, vectors)
        if vector["sparse"]
    ]
    if not pairs:
        delete_document(document.owner_id, document.id)
        return 0
    points = [
        models.PointStruct(
            id=point_id(document.owner_id, document.id, chunk.ord),
            vector={
                "dense": vector["dense"],
                "sparse": to_sparse(vector["sparse"]),
            },
            payload={
                "owner_id": document.owner_id,
                "document_id": document.id,
                "sphere_id": document.sphere_id,
                "project_id": document.project_id,
                "ord": chunk.ord,
                # ключ слияния лексики и векторов в RRF
                "chunk_id": chunk.id,
                "title": document.title,
                "text": chunk.text,
            },
        )
        for chunk, vector in pairs
    ]
    client.upsert(name, points=points, wait=True)
    for (chunk, _vector), point in zip(pairs, points):
        chunk.qdrant_point_id = str(point.id)
    db.commit()
    return len(points)


def delete_document(owner_id: str, document_id: int) -> None:
    """Удалить все точки документа; отсутствие Qdrant — ошибка вызывающего."""
    client = get_client()
    name = collection_name()
    if not client.collection_exists(name):
        return
    client.delete(
        name,
        points_selector=models.FilterSelector(
            filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="owner_id", match=models.MatchValue(value=owner_id)
                    ),
                    models.FieldCondition(
                        key="document_id", match=models.MatchValue(value=document_id)
                    ),
                ]
            )
        ),
        wait=True,
    )
