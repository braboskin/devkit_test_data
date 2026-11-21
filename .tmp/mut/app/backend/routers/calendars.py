"""Подписка на календарь (FR-9): токены scope и `.ics` без cookie-сессии."""
from __future__ import annotations

import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from ..auth import current_user, hash_token
from ..deps import get_db
from ..ics import build_calendar
from ..models import CalendarToken, Event, Project, Sphere, User
from ..ownership import get_owned_or_404

router = APIRouter(prefix="/api/calendars", tags=["calendars"])

_SCOPE = re.compile(r"^(all|sphere-(\d+)|project-(\d+))$")


def _parse_scope(scope: str) -> tuple[str, int | None]:
    match = _SCOPE.match(scope)
    if match is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="not found",
        )
    if match.group(1) == "all":
        return "all", None
    if match.group(2) is not None:
        return "sphere", int(match.group(2))
    return "project", int(match.group(3))


def _owned_scope(db: Session, user: User, scope: str) -> tuple[str, int | None]:
    kind, ident = _parse_scope(scope)
    if kind == "sphere":
        get_owned_or_404(db, Sphere, ident, user)
    elif kind == "project":
        get_owned_or_404(db, Project, ident, user)
    return kind, ident


def _scope_events(
    db: Session,
    owner_id: str,
    kind: str,
    ident: int | None,
) -> list[Event]:
    query = db.query(Event).filter(Event.owner_id == owner_id)
    if kind == "sphere":
        query = query.filter(Event.sphere_id == ident)
    elif kind == "project":
        query = query.filter(Event.project_id == ident)
    return query.order_by(Event.start_at, Event.id).all()


def _calendar_response(events: list[Event]) -> Response:
    return Response(
        content=build_calendar(events),
        media_type="text/calendar; charset=utf-8",
    )


@router.post("/{scope}/token", status_code=status.HTTP_201_CREATED)
def create_token(
    scope: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    _owned_scope(db, user, scope)
    token = secrets.token_urlsafe(24)
    # Старый токен этого scope заменяется: в БД остаётся только его хеш.
    db.query(CalendarToken).filter_by(owner_id=user.id, scope=scope).delete()
    db.add(
        CalendarToken(
            owner_id=user.id,
            scope=scope,
            token_hash=hash_token(token),
        )
    )
    db.commit()
    return {
        "token": token,
        "url": f"/api/calendars/{scope}.ics?token={token}",
    }


@router.delete("/{scope}/token", status_code=status.HTTP_204_NO_CONTENT)
def revoke_token(
    scope: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    _owned_scope(db, user, scope)
    db.query(CalendarToken).filter_by(owner_id=user.id, scope=scope).delete()
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{scope}.ics")
def calendar_ics(
    scope: str,
    token: str | None = None,
    db: Session = Depends(get_db),
) -> Response:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="not found"
        )
    row = (
        db.query(CalendarToken)
        .filter_by(token_hash=hash_token(token))
        .first()
    )
    if row is None or row.scope != scope:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="not found"
        )
    kind, ident = _parse_scope(scope)
    return _calendar_response(_scope_events(db, row.owner_id, kind, ident))
