"""PM-правила (FR-8): RRULE и зависимости задач."""
from __future__ import annotations

from datetime import datetime, timezone

from dateutil.rrule import rrulestr
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from .models import Task, TaskDependency, User

CLOSED_STATUSES = ("done", "cancelled")


def _naive_utc(value: datetime) -> datetime:
    """Модели хранят UTC naive; aware-вход приводим к UTC без tzinfo."""
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _invalid_rrule(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=f"invalid rrule: {detail}",
    )


def validate_rrule(rrule: str) -> str:
    """Нормализовать и проверить RFC 5545; вернуть правило для хранения.

    Срезаем префикс `RRULE:` (ICS сам его добавляет), запрещаем переводы строк
    (инъекция второй строки в `.ics`). Невалидное правило — 422.
    """
    if "\r" in rrule or "\n" in rrule:
        raise _invalid_rrule("rrule must be a single line")
    value = rrule.strip()
    while value[:6].lower() == "rrule:":
        value = value[6:].strip()
    if not value:
        raise _invalid_rrule("rrule is empty")
    try:
        rrulestr(value)
    except (ValueError, TypeError) as exc:
        raise _invalid_rrule(str(exc)) from exc
    return value


def next_occurrence(rrule: str, after: datetime) -> datetime | None:
    """Следующее вхождение строго после `after`; None, если правило исчерпано."""
    after = _naive_utc(after)
    rule = rrulestr(rrule, dtstart=after)
    occurrence = rule.after(after, inc=False)
    return None if occurrence is None else _naive_utc(occurrence)


def blockers_open(db: Session, task: Task, user: User) -> list[Task]:
    """Незакрытые блокеры задачи (свои; `blocked_by` — чужие невозможны)."""
    return (
        db.query(Task)
        .join(TaskDependency, TaskDependency.blocked_by_id == Task.id)
        .filter(
            TaskDependency.task_id == task.id,
            Task.owner_id == user.id,
            Task.status.notin_(CLOSED_STATUSES),
        )
        .order_by(Task.id)
        .all()
    )
