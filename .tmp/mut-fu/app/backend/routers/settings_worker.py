"""Настройки воркера ПК (FR-4): выдача/отзыв токена и статус связи."""
from __future__ import annotations

import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, status as http_status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import current_user, hash_token
from ..deps import get_db
from ..models import User, WorkerToken

router = APIRouter(prefix="/api/settings", tags=["settings"])


class WorkerTokenOut(BaseModel):
    configured: bool
    created_at: datetime | None = None
    last_seen_at: datetime | None = None


class WorkerStatusOut(BaseModel):
    configured: bool
    last_seen_at: datetime | None = None


class WorkerTokenCreatedOut(BaseModel):
    token: str


def _current(db: Session, user: User) -> WorkerToken | None:
    return (
        db.query(WorkerToken)
        .filter_by(owner_id=user.id)
        .order_by(WorkerToken.created_at.desc(), WorkerToken.id.desc())
        .first()
    )


@router.get("/worker-token", response_model=WorkerTokenOut)
def get_worker_token(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> WorkerTokenOut:
    """Только факт наличия и даты: сам токен после выдачи не показывается."""
    token = _current(db, user)
    if token is None:
        return WorkerTokenOut(configured=False)
    return WorkerTokenOut(
        configured=True,
        created_at=token.created_at,
        last_seen_at=token.last_seen_at,
    )


@router.post(
    "/worker-token",
    response_model=WorkerTokenCreatedOut,
    status_code=http_status.HTTP_201_CREATED,
)
def create_worker_token(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> WorkerTokenCreatedOut:
    """Выдать токен: показывается один раз, в БД — только sha256, старый заменяется."""
    raw = secrets.token_urlsafe(32)
    db.query(WorkerToken).filter_by(owner_id=user.id).delete()
    db.add(WorkerToken(owner_id=user.id, token_hash=hash_token(raw)))
    db.commit()
    return WorkerTokenCreatedOut(token=raw)


@router.delete("/worker-token", status_code=http_status.HTTP_204_NO_CONTENT)
def delete_worker_token(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> None:
    db.query(WorkerToken).filter_by(owner_id=user.id).delete()
    db.commit()


@router.get("/worker-status", response_model=WorkerStatusOut)
def worker_status(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> WorkerStatusOut:
    token = _current(db, user)
    return WorkerStatusOut(
        configured=token is not None,
        last_seen_at=token.last_seen_at if token is not None else None,
    )
