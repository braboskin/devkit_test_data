"""Сферы (FR-3): CRUD сфер владельца."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, StringConstraints
from sqlalchemy.orm import Session

from ..auth import current_user
from ..deps import get_db
from ..models import Event, Project, Sphere, Task, User
from ..ownership import get_owned_or_404

router = APIRouter(prefix="/api/spheres", tags=["spheres"])

SphereName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]


class SphereIn(BaseModel):
    name: SphereName


class SphereOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime


@router.get("", response_model=list[SphereOut])
def list_spheres(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[Sphere]:
    return (
        db.query(Sphere)
        .filter_by(owner_id=user.id)
        .order_by(Sphere.name)
        .all()
    )


@router.get("/{sphere_id}", response_model=SphereOut)
def get_sphere(
    sphere_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Sphere:
    return get_owned_or_404(db, Sphere, sphere_id, user)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=SphereOut)
def create_sphere(
    payload: SphereIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Sphere:
    sphere = Sphere(owner_id=user.id, name=payload.name)
    db.add(sphere)
    db.commit()
    db.refresh(sphere)
    return sphere


@router.patch("/{sphere_id}", response_model=SphereOut)
def update_sphere(
    sphere_id: int,
    payload: SphereIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Sphere:
    sphere = get_owned_or_404(db, Sphere, sphere_id, user)
    sphere.name = payload.name
    db.commit()
    db.refresh(sphere)
    return sphere


@router.delete("/{sphere_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sphere(
    sphere_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    sphere = get_owned_or_404(db, Sphere, sphere_id, user)
    # Сферу с привязанными сущностями не удаляем: FK из projects/tasks/events
    # не каскадный, иначе на PostgreSQL получим 500.
    projects = db.query(Project).filter_by(sphere_id=sphere.id).count()
    tasks = db.query(Task).filter_by(sphere_id=sphere.id).count()
    events = db.query(Event).filter_by(sphere_id=sphere.id).count()
    if projects or tasks or events:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": "sphere is in use",
                "projects": projects,
                "tasks": tasks,
                "events": events,
            },
        )
    db.delete(sphere)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
