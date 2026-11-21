"""События (FR-9): CRUD, участники, развёртывание повторений, `.ics`."""
from __future__ import annotations

from datetime import datetime, timezone

from dateutil.rrule import rrulestr
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ..auth import current_user
from ..deps import get_db
from ..ics import build_calendar
from ..models import Event, EventParticipant, Person, Project, Sphere, User
from ..ownership import get_owned_or_404

router = APIRouter(prefix="/api/events", tags=["events"])

EXPAND_LIMIT = 500


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


class EventIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    start_at: datetime
    end_at: datetime | None = None
    all_day: bool = False
    location: str | None = Field(default=None, max_length=300)
    description: str | None = None
    sphere_id: int | None = None
    project_id: int | None = None
    rrule: str | None = None
    remind_minutes: int | None = Field(default=None, ge=0)


class EventPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    start_at: datetime | None = None
    end_at: datetime | None = None
    all_day: bool | None = None
    location: str | None = Field(default=None, max_length=300)
    description: str | None = None
    sphere_id: int | None = None
    project_id: int | None = None
    rrule: str | None = None
    remind_minutes: int | None = Field(default=None, ge=0)


class EventOut(BaseModel):
    id: int
    title: str
    description: str | None = None
    start_at: datetime
    end_at: datetime | None = None
    all_day: bool = False
    location: str | None = None
    sphere_id: int | None = None
    project_id: int | None = None
    rrule: str | None = None
    remind_minutes: int | None = None
    created_at: datetime
    occurrence: bool = False
    series_start_at: datetime | None = None


class ParticipantIn(BaseModel):
    person_id: int
    role: str | None = Field(default=None, max_length=64)


class ParticipantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    person_id: int
    role: str | None


def _payload(
    event: Event,
    start_at: datetime,
    end_at: datetime | None,
    occurrence: bool = False,
) -> dict:
    return {
        "id": event.id,
        "title": event.title,
        "description": event.description,
        "start_at": start_at,
        "end_at": end_at,
        "all_day": event.all_day,
        "location": event.location,
        "sphere_id": event.sphere_id,
        "project_id": event.project_id,
        "rrule": event.rrule,
        "remind_minutes": event.remind_minutes,
        "created_at": event.created_at,
        "occurrence": occurrence,
        "series_start_at": event.start_at,
    }


def _check_scope(
    db: Session,
    user: User,
    sphere_id: int | None,
    project_id: int | None,
) -> None:
    if sphere_id is not None:
        get_owned_or_404(db, Sphere, sphere_id, user)
    if project_id is not None:
        get_owned_or_404(db, Project, project_id, user)


def _check_times(start_at: datetime, end_at: datetime | None) -> None:
    if end_at is not None and end_at < start_at:
        raise HTTPException(
            status_code=422,
            detail="end_at before start_at",
        )


def _normalize_rrule(value: str | None, start_at: datetime) -> str | None:
    """Trim, срезать ведущий `RRULE:` и проверить правило через dateutil."""
    if value is None:
        return None
    # Переводы строк в rrule — подделка/мусор: разрешаем одну строку только.
    if "\r" in value or "\n" in value:
        raise HTTPException(status_code=422, detail="invalid rrule")
    rule = value.strip()
    if rule.upper().startswith("RRULE:"):
        rule = rule[len("RRULE:"):].strip()
    if not rule:
        raise HTTPException(status_code=422, detail="invalid rrule")
    try:
        rrulestr(rule, dtstart=start_at)
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="invalid rrule")
    return rule


def _owned_event(db: Session, user: User, event_id: int) -> Event:
    return get_owned_or_404(db, Event, event_id, user)


@router.get("", response_model=list[EventOut])
def list_events(
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    sphere_id: int | None = None,
    project_id: int | None = None,
    expand: bool | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    _check_scope(db, user, sphere_id, project_id)

    query = db.query(Event).filter(Event.owner_id == user.id)
    if sphere_id is not None:
        query = query.filter(Event.sphere_id == sphere_id)
    if project_id is not None:
        query = query.filter(Event.project_id == project_id)
    events = query.order_by(Event.start_at, Event.id).all()

    if from_ is None and to is None:
        return [_payload(event, event.start_at, event.end_at) for event in events]

    if expand is None:
        expand = from_ is not None and to is not None
    if not expand:
        low = _naive_utc(from_) if from_ is not None else datetime.min
        high = _naive_utc(to) if to is not None else datetime.max
        return [
            _payload(event, event.start_at, event.end_at)
            for event in events
            if low <= event.start_at <= high
        ]
    if from_ is None or to is None:
        raise HTTPException(
            status_code=422,
            detail="from and to are required for expand",
        )

    low, high = _naive_utc(from_), _naive_utc(to)
    rows: list[dict] = []
    for event in events:
        if not event.rrule:
            if low <= event.start_at <= high:
                rows.append(_payload(event, event.start_at, event.end_at))
            continue
        try:
            rule = rrulestr(event.rrule, dtstart=event.start_at)
        except (ValueError, TypeError):
            continue
        duration = (
            event.end_at - event.start_at if event.end_at is not None else None
        )
        for occurrence_at in rule.between(low, high, inc=True):
            start_at = _naive_utc(occurrence_at)
            end_at = start_at + duration if duration is not None else None
            rows.append(_payload(event, start_at, end_at, occurrence=True))
    rows.sort(key=lambda row: row["start_at"])
    return rows[:EXPAND_LIMIT]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=EventOut)
def create_event(
    payload: EventIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    start_at = _naive_utc(payload.start_at)
    end_at = _naive_utc(payload.end_at) if payload.end_at is not None else None
    _check_times(start_at, end_at)
    _check_scope(db, user, payload.sphere_id, payload.project_id)
    rrule = _normalize_rrule(payload.rrule, start_at)
    event = Event(
        owner_id=user.id,
        title=payload.title,
        description=payload.description,
        start_at=start_at,
        end_at=end_at,
        all_day=payload.all_day,
        location=payload.location,
        sphere_id=payload.sphere_id,
        project_id=payload.project_id,
        rrule=rrule,
        remind_minutes=payload.remind_minutes,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return _payload(event, event.start_at, event.end_at)


# `.ics` объявлен до `/{event_id}`, иначе путь `1.ics` попадёт в int-параметр.
@router.get("/{event_id}.ics")
def event_ics(
    event_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    event = _owned_event(db, user, event_id)
    return Response(
        content=build_calendar([event]),
        media_type="text/calendar; charset=utf-8",
    )


@router.get("/{event_id}", response_model=EventOut)
def get_event(
    event_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    event = _owned_event(db, user, event_id)
    return _payload(event, event.start_at, event.end_at)


@router.patch("/{event_id}", response_model=EventOut)
def update_event(
    event_id: int,
    payload: EventPatch,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    event = _owned_event(db, user, event_id)
    data = payload.model_dump(exclude_unset=True)

    if data.get("start_at") is not None:
        event.start_at = _naive_utc(data["start_at"])
    if "end_at" in data:
        event.end_at = (
            _naive_utc(data["end_at"]) if data["end_at"] is not None else None
        )
    _check_times(event.start_at, event.end_at)
    if data.get("title") is not None:
        event.title = data["title"]
    if data.get("all_day") is not None:
        event.all_day = data["all_day"]
    for field in ("location", "description"):
        if field in data:
            setattr(event, field, data[field])
    _check_scope(db, user, data.get("sphere_id"), data.get("project_id"))
    for field in ("sphere_id", "project_id"):
        if field in data:
            setattr(event, field, data[field])
    if "rrule" in data:
        event.rrule = _normalize_rrule(data["rrule"], event.start_at)
    if "remind_minutes" in data:
        event.remind_minutes = data["remind_minutes"]
    db.commit()
    db.refresh(event)
    return _payload(event, event.start_at, event.end_at)


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(
    event_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    event = _owned_event(db, user, event_id)
    db.delete(event)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{event_id}/participants", response_model=list[ParticipantOut])
def list_participants(
    event_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[EventParticipant]:
    event = _owned_event(db, user, event_id)
    return (
        db.query(EventParticipant)
        .filter_by(event_id=event.id)
        .order_by(EventParticipant.person_id)
        .all()
    )


@router.post(
    "/{event_id}/participants",
    status_code=status.HTTP_201_CREATED,
    response_model=ParticipantOut,
)
def add_participant(
    event_id: int,
    payload: ParticipantIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> EventParticipant:
    event = _owned_event(db, user, event_id)
    person = get_owned_or_404(db, Person, payload.person_id, user)
    participant = (
        db.query(EventParticipant)
        .filter_by(event_id=event.id, person_id=person.id)
        .first()
    )
    if participant is None:
        participant = EventParticipant(
            event_id=event.id,
            person_id=person.id,
            owner_id=user.id,
            role=payload.role,
        )
        db.add(participant)
    else:
        participant.role = payload.role
    db.commit()
    db.refresh(participant)
    return participant


@router.delete(
    "/{event_id}/participants/{person_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_participant(
    event_id: int,
    person_id: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    event = _owned_event(db, user, event_id)
    deleted = (
        db.query(EventParticipant)
        .filter_by(event_id=event.id, person_id=person_id)
        .delete()
    )
    db.commit()
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="not found",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
