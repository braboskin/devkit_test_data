"""API воркера ПК: claim → heartbeat → complete/fail, выдача оригинала.

Авторизация — `Authorization: Bearer <worker-token>` (не cookie-сессия):
токен хешируется sha256 и принадлежит одному владельцу, поэтому воркер
видит только задания своего владельца.
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Response,
    status as http_status,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import storage
from ..auth import hash_token
from ..deps import get_db
from ..knowledge.annotate import annotate
from ..knowledge.chunking import chunk_text
from ..models import Chunk, Document, Job, WorkerToken, utcnow
from .jobs import payload_document

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/worker", tags=["worker"])

# ponytail: потолок пропуска «битых» заданий (нет документа) за один claim;
# при массовых битых payload-ах поднять или чистить задания фоновой задачей.
CLAIM_SKIP_LIMIT = 10
JOB_FIELDS = (
    "id", "type", "status", "payload", "attempts",
    "created_at", "started_at", "finished_at", "error",
)


class CompleteIn(BaseModel):
    text: str
    pages: int | None = None
    engine: str | None = None
    quality: str | None = None


class FailIn(BaseModel):
    error: str = ""


def worker_token(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> WorkerToken:
    """Bearer worker-token; cookie-сессия и чужой/отозванный токен → 401."""
    scheme, _, value = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        raise HTTPException(
            http_status.HTTP_401_UNAUTHORIZED, "worker token required"
        )
    token = (
        db.query(WorkerToken)
        .filter_by(token_hash=hash_token(value.strip()))
        .first()
    )
    if token is None:
        raise HTTPException(
            http_status.HTTP_401_UNAUTHORIZED, "invalid worker token"
        )
    return token


def _job_out(job: Job) -> dict:
    return {field: getattr(job, field) for field in JOB_FIELDS}


def _owned_job(db: Session, token: WorkerToken, job_id: int) -> Job:
    job = db.query(Job).filter_by(id=job_id, owner_id=token.owner_id).first()
    if job is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "not found")
    return job


def _running_job(db: Session, token: WorkerToken, job_id: int) -> Job:
    """Своё и именно `running` задание: иначе 404 (чужое) или 409 (завершено)."""
    job = _owned_job(db, token, job_id)
    if job.status != "running":
        raise HTTPException(
            http_status.HTTP_409_CONFLICT, "job is not running"
        )
    return job


def _document(db: Session, job: Job, owner_id: str) -> Document:
    document = payload_document(db, job)
    if document is None or document.owner_id != owner_id:
        raise HTTPException(
            http_status.HTTP_404_NOT_FOUND, "document not found"
        )
    return document


def _touch(db: Session, token: WorkerToken) -> None:
    token.last_seen_at = utcnow()


def _index(db: Session, document: Document) -> None:
    """Опциональный хук поиска (WS-D): его отсутствие/сбой не ломает complete."""
    try:
        from ..knowledge import indexer
    except ImportError:
        return
    try:
        indexer.index_document(db, document)
    except Exception as exc:  # noqa: BLE001 — граница чужого модуля
        logger.warning("indexing failed: %s", exc.__class__.__name__)


@router.post("/claim")
def claim(
    db: Session = Depends(get_db),
    token: WorkerToken = Depends(worker_token),
):
    """Атомарно взять одно `queued` задание владельца; пустая очередь → 204.

    PostgreSQL: `FOR UPDATE SKIP LOCKED`; SQLite (тесты однопоточные) — select+update.
    """
    for _ in range(CLAIM_SKIP_LIMIT):
        query = (
            db.query(Job)
            .filter(Job.owner_id == token.owner_id, Job.status == "queued")
            .order_by(Job.created_at, Job.id)
        )
        if db.get_bind().dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)
        job = query.first()
        if job is None:
            break

        document = payload_document(db, job)
        if document is None or document.owner_id != token.owner_id:
            # Документ удалён/чужой: задание невыполнимо, не блокируем очередь.
            job.status = "failed"
            job.error = "document not found"
            job.finished_at = utcnow()
            db.commit()
            continue

        job.status = "running"
        job.started_at = utcnow()
        job.attempts = (job.attempts or 0) + 1
        _touch(db, token)
        db.commit()
        return {
            "job": _job_out(job),
            "document": {
                "id": document.id,
                "title": document.title,
                "mime": document.mime,
                "storage": document.storage,
                "storage_ref": document.storage_ref,
            },
        }

    _touch(db, token)
    db.commit()
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)


@router.post("/jobs/{job_id}/heartbeat")
def heartbeat(
    job_id: int,
    db: Session = Depends(get_db),
    token: WorkerToken = Depends(worker_token),
) -> dict:
    job = _running_job(db, token, job_id)
    _touch(db, token)
    db.commit()
    return {"status": job.status}


@router.get("/jobs/{job_id}/file")
def job_file(
    job_id: int,
    db: Session = Depends(get_db),
    token: WorkerToken = Depends(worker_token),
) -> FileResponse:
    job = _owned_job(db, token, job_id)
    document = _document(db, job, token.owner_id)
    path = storage.resolve(document.storage_ref) if document.storage_ref else None
    if document.storage != "local" or path is None or not path.is_file():
        raise HTTPException(
            http_status.HTTP_404_NOT_FOUND, "original is not stored locally"
        )
    return FileResponse(
        path, media_type=document.mime or "application/octet-stream"
    )


@router.post("/jobs/{job_id}/complete")
def complete(
    job_id: int,
    body: CompleteIn,
    db: Session = Depends(get_db),
    token: WorkerToken = Depends(worker_token),
) -> dict:
    """Результат распознавания: чанки + аннотация, документ `ready`/`needs_review`."""
    job = _running_job(db, token, job_id)
    document = _document(db, job, token.owner_id)
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(
            http_status.HTTP_422_UNPROCESSABLE_CONTENT, "text is required"
        )

    def count_tokens(value: str) -> int:
        # ponytail: те же «токены», что в documents._count_tokens (по словам).
        return len(value.split())

    db.query(Chunk).filter_by(document_id=document.id).delete()
    for ord_, part in enumerate(chunk_text(text, count_tokens)):
        db.add(
            Chunk(
                document_id=document.id,
                owner_id=document.owner_id,
                ord=ord_,
                text=part["text"],
                tokens=part["token_count"],
            )
        )

    quality = body.quality or "ok"
    # `engine` принимаем для протокола, но в `documents` его нет — не храним.
    result = annotate(
        text,
        {
            "format": Path(document.storage_ref or "").suffix.lstrip("."),
            "source_path": document.storage_ref or "",
            "quality": quality,
        },
    )
    document.annotation = result["annotation"]
    document.doc_class = result["doc_class"]
    document.tags = result["tags"]
    document.entities = result["entities"]
    if body.pages is not None:
        document.pages = body.pages
    document.status = "ready" if quality == "ok" else "needs_review"
    document.error = None
    document.updated_at = utcnow()

    job.status = "done"
    job.error = None
    job.finished_at = utcnow()
    db.commit()
    _index(db, document)
    return _job_out(job)


@router.post("/jobs/{job_id}/fail")
def fail(
    job_id: int,
    body: FailIn,
    db: Session = Depends(get_db),
    token: WorkerToken = Depends(worker_token),
) -> dict:
    job = _running_job(db, token, job_id)
    message = " ".join((body.error or "").split())[:500] or "worker failed"
    document = payload_document(db, job)
    if document is not None and document.owner_id == token.owner_id:
        document.status = "failed"
        document.error = message
        document.updated_at = utcnow()
    job.status = "failed"
    job.error = message
    job.finished_at = utcnow()
    db.commit()
    return _job_out(job)
