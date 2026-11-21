"""Задачи (FR-8): CRUD, подзадачи, зависимости, RRULE, фильтры."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import case
from sqlalchemy.orm import Session

from ..auth import current_user
from ..deps import get_db
from ..models import (
    Person,
    Project,
    Sphere,
    Task,
    TaskDependency,
    TaskPerson,
    User,
    utcnow,
)
from ..ownership import get_owned_or_404
from ..pm import blockers_open, next_occurrence, validate_rrule

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

TaskStatus = Literal["todo", "doing", "done", "cancelled"]
TaskPriority = Literal["low", "medium", "high"]
TaskSort = Literal["due_at", "priority", "updated_at"]

CLOSED_STATUSES = ("done", "cancelled")
PRIORITY_ORDER = case(
    {"high": 0, "medium": 1, "low": 2}, value=Task.priority
)


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    sphere_id: int | None = None
    project_id: int | None = None
    parent_id: int | None = None
    status: TaskStatus = "todo"
    priority: TaskPriority = "medium"
    due_at: datetime | None = None
    rrule: str | None = None
    tags: list[str] = Field(default_factory=list)
    blocked_by: list[int] = Field(default_factory=list)


class TaskPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    sphere_id: int | None = None
    project_id: int | None = None
    parent_id: int | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    due_at: datetime | None = None
    rrule: str | None = None
    tags: list[str] | None = None
    blocked_by: list[int] | None = None


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: str
    sphere_id: int | None
    project_id: int | None
    parent_id: int | None
    title: str
    description: str | None
    status: str
    priority: str
    due_at: datetime | None
    rrule: str | None
    tags: list[str]
    created_at: datetime
    updated_at: datetime


class BlockerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    status: str


class PersonLinkOut(BaseModel):
    person_id: int
    name: str
    role: str | None


class TaskCardOut(TaskOut):
    subtasks: list[TaskOut] = Field(default_factory=list)
    blocked_by: list[BlockerOut] = Field(default_factory=list)
    people: list[PersonLinkOut] = Field(default_factory=list)


class TaskUpdateOut(TaskOut):
    next_task: TaskOut | None = None


class TaskPersonIn(BaseModel):
    person_id: int
    role: str | None = Field(default=None, max_length=64)


def _naive_utc(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _check_targets(db: Session, user: User, data: dict) -> None:
    """Связанные sphere/project/parent — только свои; иначе 404."""
    if data.get("sphere_id") is not None:
        get_owned_or_404(db, Sphere, data["sphere_id"], user)
    if data.get("project_id") is not None:
        get_owned_or_404(db, Project, data["project_id"], user)
    if data.get("parent_id") is not None:
        get_owned_or_404(db, Task, data["parent_id"], user)


def _check_rrule(data: dict) -> None:
    """Нормализованное правило сохраняем (без префикса `RRULE:`)."""
    rrule = data.get("rrule")
    if rrule is not None:
        data["rrule"] = validate_rrule(rrule)


def _resolve_blockers(
    db: Session, user: User, task_id: int | None, ids: list[int]
) -> list[Task]:
    """Свои блокеры; минимальная проверка циклов: self и прямые циклы."""
    unique = list(dict.fromkeys(ids))
    if task_id is not None and task_id in unique:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="task cannot block itself",
        )
    blockers: list[Task] = []
    for blocker_id in unique:
        blocker = get_owned_or_404(db, Task, blocker_id, user)
        if task_id is not None and db.get(TaskDependency, (blocker_id, task_id)):
            raise HTTPException(
                status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="dependency cycle",
            )
        blockers.append(blocker)
    return blockers


def _set_blockers(db: Session, task: Task, blockers: list[Task]) -> None:
    db.query(TaskDependency).filter_by(task_id=task.id).delete()
    for blocker in blockers:
        db.add(TaskDependency(task_id=task.id, blocked_by_id=blocker.id))


def _ensure_doing_allowed(db: Session, task: Task, user: User) -> None:
    open_blockers = blockers_open(db, task, user)
    if open_blockers:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail={
                "message": "task is blocked",
                "blockers": [
                    {"id": t.id, "title": t.title, "status": t.status}
                    for t in open_blockers
                ],
            },
        )


def _spawn_next(db: Session, task: Task) -> Task | None:
    """Следующий экземпляр повторяющейся задачи (без blocked_by)."""
    after = task.due_at or utcnow()
    due_at = next_occurrence(task.rrule, after)
    if due_at is None:
        return None
    nxt = Task(
        owner_id=task.owner_id,
        sphere_id=task.sphere_id,
        project_id=task.project_id,
        parent_id=task.parent_id,
        title=task.title,
        description=task.description,
        status="todo",
        priority=task.priority,
        due_at=due_at,
        rrule=task.rrule,
        tags=list(task.tags or []),
    )
    db.add(nxt)
    db.flush()
    return nxt


def _person_links(db: Session, task: Task, user: User) -> list[PersonLinkOut]:
    rows = (
        db.query(TaskPerson, Person)
        .join(Person, Person.id == TaskPerson.person_id)
        .filter(TaskPerson.task_id == task.id, TaskPerson.owner_id == user.id)
        .order_by(Person.name, Person.id)
        .all()
    )
    return [
        PersonLinkOut(person_id=person.id, name=person.name, role=link.role)
        for link, person in rows
    ]


def _blockers_out(db: Session, task: Task, user: User) -> list[BlockerOut]:
    rows = (
        db.query(Task)
        .join(TaskDependency, TaskDependency.blocked_by_id == Task.id)
        .filter(TaskDependency.task_id == task.id, Task.owner_id == user.id)
        .order_by(Task.id)
        .all()
    )
    return [BlockerOut.model_validate(row) for row in rows]


def _card(db: Session, task: Task, user: User) -> TaskCardOut:
    card = TaskCardOut.model_validate(task)
    card.subtasks = [
        TaskOut.model_validate(row)
        for row in db.query(Task)
        .filter_by(parent_id=task.id, owner_id=user.id)
        .order_by(Task.id)
        .all()
    ]
    card.blocked_by = _blockers_out(db, task, user)
    card.people = _person_links(db, task, user)
    return card


@router.get("", response_model=list[TaskOut])
def list_tasks(
    status_: TaskStatus | None = Query(default=None, alias="status"),
    project_id: int | None = None,
    sphere_id: int | None = None,
    priority: TaskPriority | None = None,
    tag: str | None = None,
    overdue: bool | None = None,
    stale_days: int | None = Query(default=None, ge=0),
    due_before: datetime | None = None,
    due_after: datetime | None = None,
    sort: TaskSort = "due_at",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[Task]:
    if sphere_id is not None:
        get_owned_or_404(db, Sphere, sphere_id, user)
    if project_id is not None:
        get_owned_or_404(db, Project, project_id, user)

    now = utcnow()
    query = db.query(Task).filter(Task.owner_id == user.id)
    if status_ is not None:
        query = query.filter(Task.status == status_)
    if project_id is not None:
        query = query.filter(Task.project_id == project_id)
    if sphere_id is not None:
        query = query.filter(Task.sphere_id == sphere_id)
    if priority is not None:
        query = query.filter(Task.priority == priority)
    if overdue:
        query = query.filter(
            Task.due_at.isnot(None),
            Task.due_at < now,
            Task.status.notin_(CLOSED_STATUSES),
        )
    if stale_days is not None:
        query = query.filter(
            Task.updated_at < now - timedelta(days=stale_days),
            Task.status.notin_(CLOSED_STATUSES),
        )
    if due_before is not None:
        query = query.filter(Task.due_at <= _naive_utc(due_before))
    if due_after is not None:
        query = query.filter(Task.due_at >= _naive_utc(due_after))

    if sort == "priority":
        query = query.order_by(PRIORITY_ORDER, Task.due_at.is_(None), Task.due_at)
    elif sort == "updated_at":
        query = query.order_by(Task.updated_at.desc(), Task.id)
    else:
        query = query.order_by(Task.due_at.is_(None), Task.due_at, Task.id)
    tasks = query.all()
    if tag is not None:
        # ponytail: тег фильтруется в Python; JSONB @> — если задач станет много.
        tasks = [task for task in tasks if tag in (task.tags or [])]
    return tasks


@router.get("/{task_id}", response_model=TaskCardOut)
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> TaskCardOut:
    return _card(db, get_owned_or_404(db, Task, task_id, user), user)


@router.post("", response_model=TaskOut, status_code=http_status.HTTP_201_CREATED)
def create_task(
    payload: TaskIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Task:
    data = payload.model_dump(exclude={"blocked_by"})
    data["due_at"] = _naive_utc(data["due_at"])
    _check_rrule(data)
    _check_targets(db, user, data)
    blockers = _resolve_blockers(db, user, None, payload.blocked_by)

    task = Task(owner_id=user.id, **data)
    db.add(task)
    db.flush()
    _set_blockers(db, task, blockers)
    db.flush()
    if task.status == "doing":
        _ensure_doing_allowed(db, task, user)
    db.commit()
    return task


@router.patch("/{task_id}", response_model=TaskUpdateOut)
def update_task(
    task_id: int,
    payload: TaskPatch,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> TaskUpdateOut:
    task = get_owned_or_404(db, Task, task_id, user)
    data = payload.model_dump(exclude_unset=True)
    for field in ("title", "status", "priority", "tags", "blocked_by"):
        if field in data and data[field] is None:
            raise HTTPException(
                status_code=http_status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"{field} cannot be null",
            )
    if "due_at" in data:
        data["due_at"] = _naive_utc(data["due_at"])
    _check_rrule(data)
    _check_targets(db, user, data)

    blockers = None
    if "blocked_by" in data:
        blockers = _resolve_blockers(db, user, task.id, data.pop("blocked_by"))

    was_done = task.status in CLOSED_STATUSES
    for key, value in data.items():
        setattr(task, key, value)
    db.flush()
    if blockers is not None:
        _set_blockers(db, task, blockers)
        db.flush()
    if data.get("status") == "doing":
        _ensure_doing_allowed(db, task, user)

    next_task = None
    if not was_done and task.status == "done" and task.rrule:
        next_task = _spawn_next(db, task)
    db.commit()

    result = TaskUpdateOut.model_validate(task)
    result.next_task = (
        TaskOut.model_validate(next_task) if next_task is not None else None
    )
    return result


@router.delete("/{task_id}", status_code=http_status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> None:
    db.delete(get_owned_or_404(db, Task, task_id, user))
    db.commit()


@router.get("/{task_id}/people", response_model=list[PersonLinkOut])
def list_task_people(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[PersonLinkOut]:
    task = get_owned_or_404(db, Task, task_id, user)
    return _person_links(db, task, user)


@router.post("/{task_id}/people", response_model=PersonLinkOut)
def add_task_person(
    task_id: int,
    payload: TaskPersonIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> PersonLinkOut:
    task = get_owned_or_404(db, Task, task_id, user)
    person = get_owned_or_404(db, Person, payload.person_id, user)
    link = (
        db.query(TaskPerson)
        .filter_by(task_id=task.id, person_id=person.id, owner_id=user.id)
        .first()
    )
    if link is None:
        link = TaskPerson(task_id=task.id, person_id=person.id, owner_id=user.id)
        db.add(link)
    link.role = payload.role
    db.commit()
    return PersonLinkOut(person_id=person.id, name=person.name, role=link.role)


@router.delete(
    "/{task_id}/people/{person_id}", status_code=http_status.HTTP_204_NO_CONTENT
)
def remove_task_person(
    task_id: int,
    person_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> None:
    task = get_owned_or_404(db, Task, task_id, user)
    get_owned_or_404(db, Person, person_id, user)
    db.query(TaskPerson).filter_by(
        task_id=task.id, person_id=person_id, owner_id=user.id
    ).delete()
    db.commit()
