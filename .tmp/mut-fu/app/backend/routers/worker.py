"""API воркера ПК: claim → heartbeat → complete/fail, выдача оригинала.

Авторизация — `Authorization: Bearer <worker-token>` (не cookie-сессия):
токен хешируется sha256 и принадлежит одному владельцу, поэтому воркер
видит только задания своего владельца.
"""
from __future__ import annotations

import logging
import os
from datetime import timedelta
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
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from .. import yadisk
from ..auth import hash_token
from ..deps import get_db
from ..knowledge.annotate import annotate
from ..knowledge.chunking import chunk_text
from ..knowledge.indexer import index_document
from ..models import Chunk, Document, Job, User, WorkerToken, utcnow
from .jobs import payload_document

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/worker", tags=["worker"])

# ponytail: потолок пропуска «битых» заданий (нет документа) за один claim;
# при массовых битых payload-ах поднять или чистить задания фоновой задачей.
CLAIM_SKIP_LIMIT = 10
# F8: в БД пишем только категорию — произвольный текст от воркера не храним.
FAIL_CATEGORIES = frozenset(
    {"extract_failed", "unsupported_format", "too_large", "timeout", "cancelled"}
)
DEFAULT_FAIL_CATEGORY = "extract_failed"
# F12: `running` дольше lease возвращается в очередь (свежий воркер его возьмёт),
# после `MAX_ATTEMPTS` — `failed`; lease настраивается под скорость ПК-воркера.
LEASE_MINUTES = int(os.environ.get("ATLAS_WORKER_LEASE_MINUTES", "30"))
MAX_ATTEMPTS = 3
TIMEOUT_ERROR = "worker timeout"
JOB_FIELDS = (
    "id", "type", "status", "payload", "attempts",
    "created_at", "started_at", "finished_at", "error",
)


def _error_category(value: str) -> str:
    """Категория ошибки из allowlist; неизвестное → `extract_failed`."""
    return value if value in FAIL_CATEGORIES else DEFAULT_FAIL_CATEGORY


class CompleteIn(BaseModel):
    text: str
    attempts: int
    pages: int | None = None
    engine: str | None = None
    quality: str | None = None


class FailIn(BaseModel):
    error: str = ""
    attempts: int


class HeartbeatIn(BaseModel):
    attempts: int


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


def _running_job(
    db: Session, token: WorkerToken, job_id: int, attempts: int
) -> Job:
    """Своё `running` задание с текущим lease-generation (`attempts`).

    Иначе 404 (чужое/нет) или 409: задание завершено, перехвачено reclaim'ом
    или захвачено новым claim'ом (attempts не совпал) — старый воркер не должен
    дописывать чужой результат.
    """
    job = _owned_job(db, token, job_id)
    if job.status != "running" or job.attempts != attempts:
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
    """Индексация чанков: сбой виден в `document.error` (F9), ответ не ломаем."""
    try:
        index_document(db, document)
    except Exception as exc:  # noqa: BLE001 — Qdrant/эмбеддинги снаружи БД
        logger.warning(
            "indexing failed for document %s: %s",
            document.id,
            exc.__class__.__name__,
        )
        db.rollback()
        current = db.get(Document, document.id)
        if current is not None:
            current.error = "indexing failed"
            db.commit()


def _reclaim_stale(db: Session, owner_id: str, now) -> None:
    """Протухший lease: attempts<3 → `queued`, иначе `failed` («worker timeout»).

    Reclaim — per-job атомарный `UPDATE ... WHERE status='running' AND
    started_at < cutoff`: конкурентный complete/claim/reclaim не перетирается
    (rowcount=0 → чужую строку не трогаем). Документ обновляется отдельным
    условным UPDATE и только если reclaim выиграл (rowcount=1).
    `attempts` here не меняется: generation инкрементирует следующий claim.
    """
    cutoff = now - timedelta(minutes=LEASE_MINUTES)
    stale = (
        db.query(Job)
        .filter(
            Job.owner_id == owner_id,
            Job.status == "running",
            Job.started_at.is_not(None),
            Job.started_at < cutoff,
        )
        .all()
    )
    for job in stale:
        requeue = (job.attempts or 0) < MAX_ATTEMPTS
        job_values: dict = {"status": "queued" if requeue else "failed"}
        if requeue:
            job_values.update(
                {"started_at": None, "finished_at": None, "error": None}
            )
        else:
            job_values.update({"error": TIMEOUT_ERROR, "finished_at": now})
        updated = (
            db.query(Job)
            .filter(
                Job.id == job.id,
                Job.status == "running",
                Job.started_at.is_not(None),
                Job.started_at < cutoff,
            )
            .update(job_values, synchronize_session=False)
        )
        if updated != 1:
            continue  # конкурент уже завершил/перехватил это задание
        document_values: dict = {
            "status": "queued" if requeue else "failed",
            "updated_at": now,
        }
        if not requeue:
            document_values["error"] = TIMEOUT_ERROR
        if job.payload and (document_id := job.payload.get("document_id")):
            db.query(Document).filter(
                Document.id == document_id,
                Document.owner_id == owner_id,
                Document.status.in_(("processing", "queued")),
            ).update(document_values, synchronize_session=False)
    if stale:
        db.commit()


@router.post("/claim")
def claim(
    db: Session = Depends(get_db),
    token: WorkerToken = Depends(worker_token),
):
    """Атомарно взять одно `queued` задание владельца; пустая очередь → 204.

    Single-flight: пока у владельца есть `running` задание, новый claim → 204
    (условие в запросе + частичный unique index `(owner_id) WHERE running`).
    Захват — атомарным `UPDATE ... WHERE status='queued'` с проверкой rowcount
    (SQLite и PG), плюс `FOR UPDATE SKIP LOCKED` на PG.
    """
    now = utcnow()
    # Протухшие running-задания не должны блокировать очередь навсегда.
    _reclaim_stale(db, token.owner_id, now)

    # `NOT EXISTS running`: второй воркер/поток того же владельца ничего не берёт.
    running = (
        db.query(Job.id)
        .filter(Job.owner_id == token.owner_id, Job.status == "running")
        .exists()
    )
    for _ in range(CLAIM_SKIP_LIMIT):
        query = (
            db.query(Job)
            .filter(
                Job.owner_id == token.owner_id,
                Job.status == "queued",
                ~running,
            )
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

        # Атомарный захват: только тот, кто реально перевёл queued → running,
        # отдаёт задание (rowcount=0 — его перехватил параллельный claim).
        try:
            taken = (
                db.query(Job)
                .filter(Job.id == job.id, Job.status == "queued")
                .update(
                    {
                        "status": "running",
                        "started_at": now,
                        "attempts": Job.attempts + 1,
                    },
                    synchronize_session=False,
                )
            )
        except IntegrityError:
            # PG: partial unique index отбил второй running-job того же владельца.
            db.rollback()
            _touch(db, token)
            db.commit()
            return Response(status_code=http_status.HTTP_204_NO_CONTENT)
        except OperationalError:
            # SQLite: параллельный writer держит БД — задание не наше, позже.
            db.rollback()
            _touch(db, token)
            db.commit()
            return Response(status_code=http_status.HTTP_204_NO_CONTENT)
        if not taken:
            db.rollback()
            continue

        document.status = "processing"
        document.updated_at = now
        _touch(db, token)
        try:
            db.commit()
        except IntegrityError:
            # Гонка на PG: другой claim того же владельца успел раньше —
            # partial unique index не даёт второму running-заданию.
            db.rollback()
            _touch(db, token)
            db.commit()
            return Response(status_code=http_status.HTTP_204_NO_CONTENT)
        db.refresh(job)
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
    body: HeartbeatIn,
    db: Session = Depends(get_db),
    token: WorkerToken = Depends(worker_token),
) -> dict:
    """Продлить lease: `started_at=now`; чужой/устаревший attempts → 409."""
    job = _running_job(db, token, job_id, body.attempts)
    job.started_at = utcnow()
    _touch(db, token)
    db.commit()
    return {"status": job.status, "attempts": job.attempts}


@router.get("/jobs/{job_id}/file")
def job_file(
    job_id: int,
    db: Session = Depends(get_db),
    token: WorkerToken = Depends(worker_token),
) -> FileResponse:
    job = _owned_job(db, token, job_id)
    document = _document(db, job, token.owner_id)
    # Локальной копии может не быть: облачный оригинал (F4) скачиваем в storage.
    user = db.get(User, token.owner_id)
    path = (
        yadisk.ensure_local_original(db, user, document)
        if user is not None
        else None
    )
    if path is None:
        raise HTTPException(
            http_status.HTTP_409_CONFLICT,
            "original is not stored locally and cannot be downloaded",
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
    job = _running_job(db, token, job_id, body.attempts)
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
    """Сбой воркера: в БД — только категория (F8), детали остаются у воркера."""
    job = _running_job(db, token, job_id, body.attempts)
    message = _error_category(body.error.strip())
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
