"""Люди (FR-17): CRUD, карточка со связями, привязки, поиск."""
from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy.orm import Session

from ..auth import current_user
from ..deps import get_db
from ..models import (
    Event,
    EventParticipant,
    Person,
    PersonProject,
    PersonSphere,
    Project,
    Sphere,
    Task,
    TaskPerson,
    User,
)
from ..ownership import get_owned_or_404

router = APIRouter(prefix="/api/people", tags=["people"])


PersonName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]


class PersonBase(BaseModel):
    contacts: dict[str, Any] = Field(default_factory=dict)
    birth_date: date | None = None
    relation: str | None = Field(default=None, max_length=64)
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)


class PersonIn(PersonBase):
    name: PersonName


class PersonUpdate(PersonBase):
    name: PersonName | None = None


class PersonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    contacts: dict
    birth_date: date | None
    relation: str | None
    notes: str | None
    tags: list
    created_at: datetime
    updated_at: datetime


class SphereLink(BaseModel):
    id: int
    name: str
    role: str | None


class ProjectLink(BaseModel):
    id: int
    name: str
    role: str | None


class EventLink(BaseModel):
    id: int
    title: str
    start_at: datetime
    role: str | None


class TaskLink(BaseModel):
    id: int
    title: str
    status: str
    role: str | None


class Relations(BaseModel):
    spheres: list[SphereLink]
    projects: list[ProjectLink]
    events: list[EventLink]
    tasks: list[TaskLink]


class PersonCard(PersonOut):
    relations: Relations


class SphereLinkIn(BaseModel):
    sphere_id: int
    role: str | None = Field(default=None, max_length=64)


class ProjectLinkIn(BaseModel):
    project_id: int
    role: str | None = Field(default=None, max_length=64)


def _relations(db: Session, person: Person, user: User) -> Relations:
    """Связи человека, только в пределах владельца."""
    spheres = (
        db.query(Sphere, PersonSphere.role)
        .join(PersonSphere, PersonSphere.sphere_id == Sphere.id)
        .filter(
            PersonSphere.person_id == person.id,
            PersonSphere.owner_id == user.id,
            Sphere.owner_id == user.id,
        )
        .order_by(Sphere.name)
        .all()
    )
    projects = (
        db.query(Project, PersonProject.role)
        .join(PersonProject, PersonProject.project_id == Project.id)
        .filter(
            PersonProject.person_id == person.id,
            PersonProject.owner_id == user.id,
            Project.owner_id == user.id,
        )
        .order_by(Project.name)
        .all()
    )
    events = (
        db.query(Event, EventParticipant.role)
        .join(EventParticipant, EventParticipant.event_id == Event.id)
        .filter(
            EventParticipant.person_id == person.id,
            EventParticipant.owner_id == user.id,
            Event.owner_id == user.id,
        )
        .order_by(Event.start_at)
        .all()
    )
    tasks = (
        db.query(Task, TaskPerson.role)
        .join(TaskPerson, TaskPerson.task_id == Task.id)
        .filter(
            TaskPerson.person_id == person.id,
            TaskPerson.owner_id == user.id,
            Task.owner_id == user.id,
        )
        .order_by(Task.title)
        .all()
    )
    return Relations(
        spheres=[
            SphereLink(id=sphere.id, name=sphere.name, role=role)
            for sphere, role in spheres
        ],
        projects=[
            ProjectLink(id=project.id, name=project.name, role=role)
            for project, role in projects
        ],
        events=[
            EventLink(
                id=event.id,
                title=event.title,
                start_at=event.start_at,
                role=role,
            )
            for event, role in events
        ],
        tasks=[
            TaskLink(id=task.id, title=task.title, status=task.status, role=role)
            for task, role in tasks
        ],
    )


@router.get("", response_model=list[PersonOut])
def list_people(
    q: str | None = None,
    sphere_id: int | None = None,
    project_id: int | None = None,
    tag: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[Person]:
    query = db.query(Person).filter(Person.owner_id == user.id)
    if sphere_id is not None:
        get_owned_or_404(db, Sphere, sphere_id, user)
        query = query.filter(
            Person.id.in_(
                db.query(PersonSphere.person_id).filter(
                    PersonSphere.sphere_id == sphere_id,
                    PersonSphere.owner_id == user.id,
                )
            )
        )
    if project_id is not None:
        get_owned_or_404(db, Project, project_id, user)
        query = query.filter(
            Person.id.in_(
                db.query(PersonProject.person_id).filter(
                    PersonProject.project_id == project_id,
                    PersonProject.owner_id == user.id,
                )
            )
        )
    people = query.order_by(Person.id).all()
    if q:
        needle = q.casefold()
        people = [person for person in people if needle in person.name.casefold()]
    if tag:
        people = [person for person in people if tag in (person.tags or [])]
    return people


@router.post("", response_model=PersonOut, status_code=status.HTTP_201_CREATED)
def create_person(
    payload: PersonIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Person:
    person = Person(owner_id=user.id, **payload.model_dump())
    db.add(person)
    db.commit()
    db.refresh(person)
    return person


@router.get("/{person_id}", response_model=PersonCard)
def get_person(
    person_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> PersonCard:
    person = get_owned_or_404(db, Person, person_id, user)
    return PersonCard(
        **PersonOut.model_validate(person).model_dump(),
        relations=_relations(db, person, user),
    )


@router.patch("/{person_id}", response_model=PersonOut)
def update_person(
    person_id: int,
    payload: PersonUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Person:
    person = get_owned_or_404(db, Person, person_id, user)
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="name must not be null",
        )
    for field, value in data.items():
        setattr(person, field, value)
    db.commit()
    db.refresh(person)
    return person


@router.delete("/{person_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_person(
    person_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    person = get_owned_or_404(db, Person, person_id, user)
    db.delete(person)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{person_id}/relations", response_model=Relations)
def get_relations(
    person_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Relations:
    person = get_owned_or_404(db, Person, person_id, user)
    return _relations(db, person, user)


@router.post(
    "/{person_id}/spheres",
    status_code=status.HTTP_201_CREATED,
)
def link_sphere(
    person_id: int,
    payload: SphereLinkIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    person = get_owned_or_404(db, Person, person_id, user)
    get_owned_or_404(db, Sphere, payload.sphere_id, user)
    link = db.get(PersonSphere, (person.id, payload.sphere_id))
    if link is None:
        link = PersonSphere(
            person_id=person.id,
            sphere_id=payload.sphere_id,
            owner_id=user.id,
        )
        db.add(link)
    link.role = payload.role
    db.commit()
    return {"person_id": person.id, "sphere_id": payload.sphere_id, "role": link.role}


@router.delete(
    "/{person_id}/spheres/{sphere_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def unlink_sphere(
    person_id: int,
    sphere_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    person = get_owned_or_404(db, Person, person_id, user)
    deleted = (
        db.query(PersonSphere)
        .filter(
            PersonSphere.person_id == person.id,
            PersonSphere.sphere_id == sphere_id,
            PersonSphere.owner_id == user.id,
        )
        .delete()
    )
    db.commit()
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="not found"
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{person_id}/projects",
    status_code=status.HTTP_201_CREATED,
)
def link_project(
    person_id: int,
    payload: ProjectLinkIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    person = get_owned_or_404(db, Person, person_id, user)
    get_owned_or_404(db, Project, payload.project_id, user)
    link = db.get(PersonProject, (person.id, payload.project_id))
    if link is None:
        link = PersonProject(
            person_id=person.id,
            project_id=payload.project_id,
            owner_id=user.id,
        )
        db.add(link)
    link.role = payload.role
    db.commit()
    return {
        "person_id": person.id,
        "project_id": payload.project_id,
        "role": link.role,
    }


@router.delete(
    "/{person_id}/projects/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def unlink_project(
    person_id: int,
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    person = get_owned_or_404(db, Person, person_id, user)
    deleted = (
        db.query(PersonProject)
        .filter(
            PersonProject.person_id == person.id,
            PersonProject.project_id == project_id,
            PersonProject.owner_id == user.id,
        )
        .delete()
    )
    db.commit()
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="not found"
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
