"""Задания воркера (FR-4): список своих заданий и отмена."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status as http_status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ..auth import current_user
from ..deps import get_db
from ..models import Document, Job, User, utcnow
from ..ownership import get_owned_or_404

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

JobStatus = Literal["queued", "running", "done", "failed", "cancelled"]
# Отмена допустима только до завершения; документ при этом уходит в `failed`.
CANCELLABLE = ("queued", "running")
# Документ «в работе»: `queued` в очереди или `processing` после claim (F13).
DOCUMENT_ACTIVE = ("queued", "processing")


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    status: str
    payload: dict
    attempts: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None


def payload_document(db: Session, job: Job) -> Document | None:
    """Документ задания из `payload`; None — если поля нет или документ удалён."""
    document_id = (job.payload or {}).get("document_id")
    if not isinstance(document_id, int):
        return None
    return db.get(Document, document_id)


@router.get("", response_model=list[JobOut])
def list_jobs(
    status: JobStatus | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[Job]:
    query = db.query(Job).filter(Job.owner_id == user.id)
    if status is not None:
        query = query.filter(Job.status == status)
    return query.order_by(Job.created_at.desc(), Job.id.desc()).all()


@router.post("/{job_id}/cancel", response_model=JobOut)
def cancel_job(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Job:
    """Отменить своё незавершённое задание; документ из payload → `failed`."""
    job = get_owned_or_404(db, Job, job_id, user)
    if job.status not in CANCELLABLE:
        raise HTTPException(
            http_status.HTTP_409_CONFLICT, "job is already finished"
        )

    job.status = "cancelled"
    job.finished_at = utcnow()
    document = payload_document(db, job)
    if (
        document is not None
        and document.owner_id == user.id
        and document.status in DOCUMENT_ACTIVE
    ):
        document.status = "failed"
        document.error = "cancelled"
        document.updated_at = utcnow()
    db.commit()
    return job
