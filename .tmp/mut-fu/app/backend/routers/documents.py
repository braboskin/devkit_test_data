"""Документы (FR-4): загрузка файлом/URL, карточка, оригинал, переобработка."""
from __future__ import annotations

import hashlib
import logging
import mimetypes
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status as http_status,
)
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import config, storage, yadisk
from ..auth import current_user
from ..deps import get_db
from ..knowledge.annotate import annotate
from ..knowledge.chunking import chunk_text
from ..knowledge.extract import SUPPORTED
from ..knowledge.indexer import delete_document, index_document
from ..knowledge.pipeline import analyze_file, should_defer
from ..models import Chunk, Document, Job, Project, Sphere, User
from ..ownership import get_owned_or_404

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])

DocumentStatus = Literal[
    "uploaded", "processing", "queued", "ready", "needs_review", "failed"
]
# Плана/ТЗ: >20 МБ оригинал уходит в Яндекс.Диск (WS-E), иначе — локально.
YADISK_THRESHOLD = 20 * 1024 * 1024
# URL-приём: извлечённый текст режется по 2 МБ; сеть — через SSRF-safe http_fetch.
MAX_URL_TEXT_CHARS = 2 * 1024 * 1024
ACTIVE_JOB_STATUSES = ("queued", "running")


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: str
    sphere_id: int | None
    project_id: int | None
    title: str
    source_type: str
    sha256: str | None
    mime: str | None
    size_bytes: int
    pages: int | None
    storage: str
    storage_ref: str | None
    annotation: str | None
    doc_class: str | None
    tags: list[str]
    entities: dict
    status: str
    error: str | None
    created_at: datetime
    updated_at: datetime


class UploadOut(DocumentOut):
    duplicate: bool = False


# ---------- внешние сервисы: Яндекс.Диск и индексация ----------


def _safe_remote(action: str, call) -> None:
    """Сбой внешнего сервиса не должен ронять запрос: в лог без деталей."""
    try:
        call()
    except Exception as exc:  # noqa: BLE001 — граница Яндекс.Диска
        logger.warning("%s failed: %s", action, exc.__class__.__name__)


def _store_remote(db: Session, user: User, document: Document) -> None:
    if document.size_bytes <= YADISK_THRESHOLD or not document.storage_ref:
        return
    _safe_remote(
        "yandex upload",
        lambda: yadisk.store_original(
            db, user, document, storage.resolve(document.storage_ref)
        ),
    )


def _index(db: Session, document: Document) -> None:
    """Индексация чанков: сбой виден в `document.error` (F9), не молчим."""
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


def _drop_index(owner_id: str, document_id: int) -> None:
    """Точки удалённого документа: сбой Qdrant не отменяет уже сделанное удаление."""
    _safe_remote("index cleanup", lambda: delete_document(owner_id, document_id))


# ---------- разбор текста ----------


def _count_tokens(text: str) -> int:
    # ponytail: оценка по словам; токенизатор BGE-M3 в API не тянем.
    return len(text.split())


def _fetch_text(url: str) -> tuple[str, str]:
    """Скачать URL → (текст, title) через SSRF-safe `http_fetch` (WS-B2, F1).

    Импорт внутри функции: модуль соседнего WS может появиться позже.
    """
    from .. import http_fetch

    try:
        return http_fetch.fetch_text(
            url,
            max_bytes=config.MAX_UPLOAD_BYTES,
            max_chars=MAX_URL_TEXT_CHARS,
            timeout=config.FETCH_TIMEOUT_SECONDS,
        )
    except http_fetch.HttpFetchError as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc


# ---------- запись документа ----------


def _naive_utc(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _check_targets(
    db: Session, user: User, sphere_id: int | None, project_id: int | None
) -> None:
    if sphere_id is not None:
        get_owned_or_404(db, Sphere, sphere_id, user)
    if project_id is not None:
        get_owned_or_404(db, Project, project_id, user)


def _resolve_ext(name: str, content_type: str | None) -> str:
    suffix = Path(name).suffix.lower()
    if suffix in SUPPORTED:
        return suffix
    mime = (content_type or "").split(";")[0].strip().lower()
    guessed = mimetypes.guess_extension(mime) if mime else None
    if guessed and guessed in SUPPORTED:
        return guessed
    raise HTTPException(
        http_status.HTTP_422_UNPROCESSABLE_CONTENT, "unsupported file type"
    )


def _find_duplicate(db: Session, owner_id: str, sha256: str) -> Document | None:
    return (
        db.query(Document)
        .filter_by(owner_id=owner_id, sha256=sha256)
        .first()
    )


def _active_job(db: Session, user: User, document_id: int) -> Job | None:
    """Незавершённое задание документа: повторная постановка дала бы дубли."""
    jobs = (
        db.query(Job)
        .filter(Job.owner_id == user.id, Job.status.in_(ACTIVE_JOB_STATUSES))
        .all()
    )
    return next(
        (
            job
            for job in jobs
            if (job.payload or {}).get("document_id") == document_id
        ),
        None,
    )


def _apply(
    db: Session,
    document: Document,
    *,
    text: str,
    pages: int | None,
    title: str,
    doc_class: str,
    annotation: str,
    tags: list,
    entities: dict,
    needs_review: bool,
) -> None:
    if title and not document.title:
        document.title = title[:300]
    document.pages = pages
    document.doc_class = doc_class
    document.annotation = annotation
    document.tags = tags
    document.entities = entities
    document.status = "needs_review" if needs_review else "ready"
    document.error = None
    db.query(Chunk).filter_by(document_id=document.id).delete()
    for ord_, part in enumerate(chunk_text(text, _count_tokens)):
        db.add(
            Chunk(
                document_id=document.id,
                owner_id=document.owner_id,
                ord=ord_,
                text=part["text"],
                tokens=part["token_count"],
            )
        )


def _run_fast(db: Session, document: Document, path: Path, original_name: str) -> None:
    analyzed = analyze_file(path, original_name, document.mime)
    _apply(
        db,
        document,
        text=analyzed["text"],
        pages=analyzed["pages"],
        title=analyzed["title"],
        doc_class=analyzed["doc_class"],
        annotation=analyzed["annotation"],
        tags=analyzed["tags"],
        entities=analyzed["entities"],
        needs_review=analyzed["needs_review"],
    )


def _run_url(db: Session, document: Document, text: str, title: str) -> None:
    result = annotate(
        text,
        {
            "format": "html",
            "source_path": document.storage_ref or "",
            "quality": "ok",
        },
    )
    _apply(
        db,
        document,
        text=text,
        pages=None,
        title=title,
        doc_class=result["doc_class"],
        annotation=result["annotation"],
        tags=result["tags"],
        entities=result["entities"],
        needs_review=not text.strip(),
    )


def _queue(db: Session, document: Document, kind: str) -> None:
    document.status = "queued"
    document.error = None
    db.add(
        Job(
            owner_id=document.owner_id,
            type=kind,
            payload={
                "document_id": document.id,
                "storage_ref": document.storage_ref,
                "kind": kind,
            },
        )
    )


ERROR_TOO_LARGE = "too large"
ERROR_UNSUPPORTED_FORMAT = "unsupported format"
ERROR_EXTRACT = "extract failed"


def _error_category(exc: Exception) -> str:
    """Категория вместо `str(exc)`: текст исключения может содержать путь/URL."""
    if isinstance(exc, storage.StorageLimitExceeded):
        return ERROR_TOO_LARGE
    if isinstance(exc, ValueError) and str(exc).startswith("unsupported format"):
        return ERROR_UNSUPPORTED_FORMAT
    return ERROR_EXTRACT


def _fail(db: Session, document: Document, exc: Exception) -> None:
    """Ошибка обработки: статус `failed` и только категория, без деталей."""
    document.status = "failed"
    document.error = _error_category(exc)


def _duplicate_after_race(
    db: Session, owner_id: str, sha256: str, cleanup=None
) -> UploadOut | None:
    """F7: конкурент успел вставить тот же файл — вернуть его документ."""
    db.rollback()
    if cleanup is not None:
        cleanup()
    duplicate = _find_duplicate(db, owner_id, sha256)
    return None if duplicate is None else _out(duplicate, duplicate=True)


def _out(document: Document, duplicate: bool = False) -> UploadOut:
    result = UploadOut.model_validate(document)
    result.duplicate = duplicate
    return result


def _upload_file(
    db: Session,
    user: User,
    upload: UploadFile,
    sphere_id: int | None,
    project_id: int | None,
    title: str | None,
) -> UploadOut:
    name = Path(upload.filename or "").name
    ext = _resolve_ext(name, upload.content_type)
    # owner_id/остальное — заранее: после сбоя flush сессия инвалидируется.
    owner_id = user.id
    try:
        tmp, size, sha256 = storage.save_stream(
            upload.file, owner_id, config.MAX_UPLOAD_BYTES
        )
    except storage.StorageLimitExceeded as exc:
        raise HTTPException(
            http_status.HTTP_413_CONTENT_TOO_LARGE,
            f"file exceeds {config.MAX_UPLOAD_MB} MB",
        ) from exc

    duplicate = _find_duplicate(db, owner_id, sha256)
    if duplicate is not None:
        tmp.unlink(missing_ok=True)
        return _out(duplicate, duplicate=True)

    document = Document(
        owner_id=owner_id,
        sphere_id=sphere_id,
        project_id=project_id,
        title=(title or "").strip()[:300],
        source_type="file",
        sha256=sha256,
        mime=(upload.content_type or mimetypes.guess_type(name)[0] or "")[:255],
        size_bytes=size,
        storage="local",
        status="processing",
        tags=[],
        entities={},
    )
    db.add(document)
    try:
        db.flush()
    except IntegrityError:
        # F7: пока шла проверка, тот же файл вставил конкурент.
        raced = _duplicate_after_race(
            db, owner_id, sha256, lambda: tmp.unlink(missing_ok=True)
        )
        if raced is None:
            raise
        return raced
    document.storage_ref = storage.finalize(tmp, owner_id, document.id, ext)
    path = storage.resolve(document.storage_ref)
    try:
        decision = should_defer(path, document.mime, size)
        if decision["defer"]:
            document.title = document.title or Path(name).stem[:300] or "document"
            _queue(db, document, decision["kind"])
        else:
            _run_fast(db, document, path, name)
    except Exception as exc:  # noqa: BLE001 — любой сбой извлечения → `failed`
        _fail(db, document, exc)
        db.commit()
        storage.delete(document.storage_ref)
        raise HTTPException(
            http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            "document processing failed",
        ) from exc
    db.commit()
    _store_remote(db, user, document)
    _index(db, document)
    return _out(document)


def _upload_url(
    db: Session,
    user: User,
    url: str,
    sphere_id: int | None,
    project_id: int | None,
    title: str | None,
) -> UploadOut:
    text, page_title = _fetch_text(url)
    sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    owner_id = user.id
    duplicate = _find_duplicate(db, owner_id, sha256)
    if duplicate is not None:
        return _out(duplicate, duplicate=True)

    document = Document(
        owner_id=owner_id,
        sphere_id=sphere_id,
        project_id=project_id,
        title=((title or "").strip() or page_title or urlparse(url).hostname or "url")[:300],
        source_type="url",
        sha256=sha256,
        mime="text/html",
        size_bytes=len(text.encode("utf-8")),
        storage="none",
        storage_ref=url,
        status="processing",
        tags=[],
        entities={},
    )
    db.add(document)
    try:
        db.flush()
    except IntegrityError:
        # F7: тот же URL-текст уже вставлен конкурентом.
        raced = _duplicate_after_race(db, owner_id, sha256)
        if raced is None:
            raise
        return raced
    try:
        _run_url(db, document, text, page_title)
    except Exception as exc:  # noqa: BLE001
        _fail(db, document, exc)
        db.commit()
        raise HTTPException(
            http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            "document processing failed",
        ) from exc
    db.commit()
    _index(db, document)
    return _out(document)


# ---------- маршруты ----------


@router.post("", response_model=UploadOut)
def upload_document(
    file: UploadFile | None = File(default=None),
    url: str | None = Form(default=None),
    sphere_id: int | None = Form(default=None),
    project_id: int | None = Form(default=None),
    title: str | None = Form(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> UploadOut:
    """Загрузить файл или URL-страницу; ровно одно из полей `file`/`url`."""
    if (file is None) == (url is None):
        raise HTTPException(
            http_status.HTTP_422_UNPROCESSABLE_CONTENT,
            "exactly one of file or url is required",
        )
    _check_targets(db, user, sphere_id, project_id)
    if url is not None:
        return _upload_url(db, user, url.strip(), sphere_id, project_id, title)
    return _upload_file(db, user, file, sphere_id, project_id, title)


@router.get("", response_model=list[DocumentOut])
def list_documents(
    sphere_id: int | None = None,
    project_id: int | None = None,
    status_: DocumentStatus | None = Query(default=None, alias="status"),
    doc_class: str | None = None,
    tag: str | None = None,
    q: str | None = None,
    date_from: datetime | None = Query(default=None, alias="from"),
    date_to: datetime | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[Document]:
    if sphere_id is not None:
        get_owned_or_404(db, Sphere, sphere_id, user)
    if project_id is not None:
        get_owned_or_404(db, Project, project_id, user)

    query = db.query(Document).filter(Document.owner_id == user.id)
    if sphere_id is not None:
        query = query.filter(Document.sphere_id == sphere_id)
    if project_id is not None:
        query = query.filter(Document.project_id == project_id)
    if status_ is not None:
        query = query.filter(Document.status == status_)
    if doc_class is not None:
        query = query.filter(Document.doc_class == doc_class)
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(Document.title.ilike(like), Document.annotation.ilike(like))
        )
    if date_from is not None:
        query = query.filter(Document.created_at >= _naive_utc(date_from))
    if date_to is not None:
        query = query.filter(Document.created_at <= _naive_utc(date_to))

    documents = query.order_by(
        Document.created_at.desc(), Document.id.desc()
    ).all()
    if tag is not None:
        # ponytail: тег фильтруется в Python; JSONB @> — если документов много.
        documents = [doc for doc in documents if tag in (doc.tags or [])]
    return documents


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Document:
    return get_owned_or_404(db, Document, document_id, user)


@router.get("/{document_id}/content", response_class=PlainTextResponse)
def get_document_content(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> PlainTextResponse:
    document = get_owned_or_404(db, Document, document_id, user)
    chunks = (
        db.query(Chunk)
        .filter_by(document_id=document.id, owner_id=user.id)
        .order_by(Chunk.ord)
        .all()
    )
    return PlainTextResponse(
        "\n\n".join(chunk.text for chunk in chunks),
        media_type="text/markdown",
    )


def _download_name(document: Document, suffix: str) -> str:
    safe = re.sub(r"[^\w\-. ]+", "_", document.title, flags=re.UNICODE).strip()
    return f"{safe[:80] or f'document-{document.id}'}{suffix}"


@router.get("/{document_id}/file")
def get_document_file(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> FileResponse:
    document = get_owned_or_404(db, Document, document_id, user)
    path = yadisk.ensure_local_original(db, user, document)
    if path is None:
        raise HTTPException(
            http_status.HTTP_409_CONFLICT,
            "local copy is missing: cannot download the original "
            "from the external storage",
        )
    return FileResponse(
        path,
        filename=_download_name(document, path.suffix),
        media_type=document.mime or "application/octet-stream",
    )


def _local_original(document: Document) -> Path | None:
    """Локальная копия оригинала (для `yandex` — тоже, пока она на месте)."""
    return storage.local_original(
        document.owner_id, document.id, document.storage, document.storage_ref
    )


@router.post("/{document_id}/reprocess", response_model=DocumentOut)
def reprocess_document(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Document:
    """Сбросить результат и повторить быстрый/отложенный путь."""
    document = get_owned_or_404(db, Document, document_id, user)
    if _active_job(db, user, document.id) is not None:
        raise HTTPException(
            http_status.HTTP_409_CONFLICT,
            "document has an active job: cancel it before reprocessing",
        )
    db.query(Chunk).filter_by(document_id=document.id).delete()
    document.status = "processing"
    document.error = None
    document.annotation = None
    document.doc_class = None
    document.tags = []
    document.entities = {}

    try:
        if document.storage == "none" and (document.storage_ref or "").startswith(
            "http"
        ):
            text, page_title = _fetch_text(document.storage_ref)
            _run_url(db, document, text, document.title or page_title)
        else:
            path = yadisk.ensure_local_original(db, user, document)
            if path is None:
                raise HTTPException(
                    http_status.HTTP_409_CONFLICT,
                    "local copy is missing: cannot download the original "
                    "from the external storage",
                )
            decision = should_defer(path, document.mime, document.size_bytes)
            if decision["defer"]:
                _queue(db, document, decision["kind"])
            else:
                _run_fast(db, document, path, path.name)
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:  # noqa: BLE001 — переобработка не теряет документ
        _fail(db, document, exc)
        db.commit()
        raise HTTPException(
            http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            "document processing failed",
        ) from exc
    db.commit()
    _index(db, document)
    return document


@router.post("/{document_id}/reindex", response_model=DocumentOut)
def reindex_document(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Document:
    """Повторить индексацию чанков (F9): сбой Qdrant виден в `error`, не молчит."""
    document = get_owned_or_404(db, Document, document_id, user)
    try:
        index_document(db, document)
    except Exception as exc:  # noqa: BLE001 — Qdrant/эмбеддинги снаружи БД
        logger.warning(
            "indexing failed for document %s: %s",
            document.id,
            exc.__class__.__name__,
        )
        db.rollback()
        stored = db.get(Document, document.id)
        if stored is not None:
            stored.error = "indexing failed"
            db.commit()
        raise HTTPException(
            http_status.HTTP_502_BAD_GATEWAY, "indexing failed"
        ) from exc
    if document.error == "indexing failed":
        document.error = None
        db.commit()
    return document


@router.delete("/{document_id}", status_code=http_status.HTTP_204_NO_CONTENT)
def remove_document(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> None:
    document = get_owned_or_404(db, Document, document_id, user)
    owner_id, removed_id = document.owner_id, document.id
    local = _local_original(document)

    _safe_remote(
        "yandex delete", lambda: yadisk.delete_original(db, user, document)
    )
    # Локальную копию убираем при любом `storage`: даже если облако недоступно,
    # оригинал удалённого документа на диске оставаться не должен.
    if local is not None:
        local.unlink(missing_ok=True)

    db.delete(document)
    db.commit()
    _drop_index(owner_id, removed_id)
