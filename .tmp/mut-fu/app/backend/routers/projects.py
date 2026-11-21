"""Проекты (FR-3): CRUD проектов внутри своих сфер."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import JSONResponse
from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints
from sqlalchemy.orm import Session

from ..auth import current_user
from ..deps import get_db
from ..models import Event, Project, Sphere, Task, User
from ..ownership import get_owned_or_404

router = APIRouter(prefix="/api/projects", tags=["projects"])

ProjectStatus = Literal["idea", "planned", "active", "paused", "done", "archived"]

ProjectName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]


def _as_utc_naive(value: datetime | None) -> datetime | None:
    """В БД — наивный UTC (см. models.utcnow); смещение из ISO приводим к UTC."""
    if value is not None and value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


DueAt = Annotated[datetime | None, AfterValidator(_as_utc_naive)]


class ProjectIn(BaseModel):
    sphere_id: int
    name: ProjectName
    description: str | None = None
    status: ProjectStatus = "active"
    due_at: DueAt = None


class ProjectPatch(BaseModel):
    sphere_id: int | None = None
    name: ProjectName | None = None
    description: str | None = None
    status: ProjectStatus | None = None
    due_at: DueAt = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sphere_id: int
    name: str
    description: str | None
    status: str
    due_at: datetime | None
    created_at: datetime


@router.get("", response_model=list[ProjectOut])
def list_projects(
    sphere_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[Project]:
    query = db.query(Project).filter_by(owner_id=user.id)
    if sphere_id is not None:
        get_owned_or_404(db, Sphere, sphere_id, user)
        query = query.filter_by(sphere_id=sphere_id)
    return query.order_by(Project.id).all()


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Project:
    return get_owned_or_404(db, Project, project_id, user)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ProjectOut)
def create_project(
    payload: ProjectIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Project:
    get_owned_or_404(db, Sphere, payload.sphere_id, user)
    project = Project(
        owner_id=user.id,
        sphere_id=payload.sphere_id,
        name=payload.name,
        description=payload.description,
        status=payload.status,
        due_at=payload.due_at,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: int,
    payload: ProjectPatch,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Project:
    project = get_owned_or_404(db, Project, project_id, user)
    changes = payload.model_dump(exclude_unset=True)
    for field in ("sphere_id", "name", "status"):
        if field in changes and changes[field] is None:
            raise HTTPException(
                status_code=422,
                detail=f"{field}: null not allowed",
            )
    if "sphere_id" in changes:
        get_owned_or_404(db, Sphere, changes["sphere_id"], user)
    for field, value in changes.items():
        setattr(project, field, value)
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    project = get_owned_or_404(db, Project, project_id, user)
    # Связанные задачи и события не удаляем: сначала пользователь решит их судьбу.
    # Считаем только свои строки (M1-minor).
    tasks = (
        db.query(Task).filter_by(project_id=project.id, owner_id=user.id).count()
    )
    events = (
        db.query(Event).filter_by(project_id=project.id, owner_id=user.id).count()
    )
    if tasks or events:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": "project is in use",
                "tasks": tasks,
                "events": events,
            },
        )
    db.delete(project)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
