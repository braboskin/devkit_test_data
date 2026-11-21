"""Изоляция данных: единственная точка фильтрации по `owner_id`."""
from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from .models import User


def get_owned_or_404(db: Session, model, obj_id, user: User):
    """Вернуть объект модели, принадлежащий user, иначе 404 (не 403 — без утечки)."""
    obj = (
        db.query(model)
        .filter_by(id=obj_id, owner_id=user.id)
        .first()
    )
    if obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="not found",
        )
    return obj
