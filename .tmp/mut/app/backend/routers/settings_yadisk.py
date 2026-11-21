"""Настройки Яндекс.Диска (FR-15): токен пользователя, шифр в БД, маска в API."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, StringConstraints
from sqlalchemy.orm import Session

from .. import yadisk
from ..auth import current_user
from ..deps import get_db
from ..models import Integration, User

router = APIRouter(prefix="/api/settings", tags=["settings"])


class YadiskSettingsOut(BaseModel):
    configured: bool
    masked: str | None = None


class YadiskSettingsIn(BaseModel):
    # Пустой/пробельный токен — 422 на границе доверия.
    token: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1024)
    ]


def _integration(db: Session, owner_id: str) -> Integration | None:
    return (
        db.query(Integration)
        .filter_by(owner_id=owner_id, kind=yadisk.KIND)
        .first()
    )


def _config_error(exc: yadisk.YadiskConfigError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
    )


@router.get("/yadisk", response_model=YadiskSettingsOut)
def get_yadisk_settings(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> YadiskSettingsOut:
    integration = _integration(db, user.id)
    if integration is None or not integration.token_enc:
        return YadiskSettingsOut(configured=False, masked=None)
    try:
        raw = yadisk.decrypt_token(integration.token_enc)
    except yadisk.YadiskConfigError as exc:
        raise _config_error(exc) from exc
    return YadiskSettingsOut(configured=True, masked=yadisk.mask_token(raw))


@router.put("/yadisk", response_model=YadiskSettingsOut)
def set_yadisk_settings(
    payload: YadiskSettingsIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> YadiskSettingsOut:
    try:
        encrypted = yadisk.encrypt_token(payload.token)
    except yadisk.YadiskConfigError as exc:
        raise _config_error(exc) from exc

    integration = _integration(db, user.id)
    if integration is None:
        integration = Integration(owner_id=user.id, kind=yadisk.KIND)
        db.add(integration)
    integration.token_enc = encrypted
    db.commit()
    return YadiskSettingsOut(
        configured=True, masked=yadisk.mask_token(payload.token)
    )


@router.delete("/yadisk", status_code=status.HTTP_204_NO_CONTENT)
def delete_yadisk_settings(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> None:
    db.query(Integration).filter_by(
        owner_id=user.id, kind=yadisk.KIND
    ).delete()
    db.commit()
