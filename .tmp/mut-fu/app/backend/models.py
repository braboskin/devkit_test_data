"""Модели данных: пользователи, сессии и доменные сущности §7 ТЗ.

Схема — `public`; доменные таблицы несут `owner_id` и фильтруются по нему.
Схема создаётся только миграциями Alembic: `0001_m1` (M1) и `0002_knowledge`
(документы, чанки, задания, воркер-токены, интеграции).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def bigint() -> BigInteger:
    """bigint на PostgreSQL, INTEGER на SQLite (rowid) — тесты идут на SQLite."""
    return BigInteger().with_variant(Integer, "sqlite")


def json_type() -> JSON:
    """JSONB на PostgreSQL, JSON на SQLite."""
    return JSON().with_variant(postgresql.JSONB, "postgresql")


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    sessions: Mapped[list["UserSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class UserSession(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)

    user: Mapped[User] = relationship(back_populates="sessions")


class Sphere(Base):
    __tablename__ = "spheres"

    id: Mapped[int] = mapped_column(bigint(), primary_key=True)
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(bigint(), primary_key=True)
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    sphere_id: Mapped[int] = mapped_column(
        bigint(), ForeignKey("spheres.id")
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="active")
    due_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Person(Base):
    __tablename__ = "people"

    id: Mapped[int] = mapped_column(bigint(), primary_key=True)
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    contacts: Mapped[dict] = mapped_column(json_type(), default=dict)
    birth_date: Mapped[date | None] = mapped_column(Date)
    relation: Mapped[str | None] = mapped_column(String(64))
    notes: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list] = mapped_column(json_type(), default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )


class PersonSphere(Base):
    __tablename__ = "person_spheres"

    person_id: Mapped[int] = mapped_column(
        bigint(), ForeignKey("people.id", ondelete="CASCADE"), primary_key=True
    )
    sphere_id: Mapped[int] = mapped_column(
        bigint(), ForeignKey("spheres.id", ondelete="CASCADE"), primary_key=True
    )
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str | None] = mapped_column(String(64))


class PersonProject(Base):
    __tablename__ = "person_projects"

    person_id: Mapped[int] = mapped_column(
        bigint(), ForeignKey("people.id", ondelete="CASCADE"), primary_key=True
    )
    project_id: Mapped[int] = mapped_column(
        bigint(), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str | None] = mapped_column(String(64))


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(bigint(), primary_key=True)
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    sphere_id: Mapped[int | None] = mapped_column(bigint(), ForeignKey("spheres.id"))
    project_id: Mapped[int | None] = mapped_column(
        bigint(), ForeignKey("projects.id")
    )
    parent_id: Mapped[int | None] = mapped_column(
        bigint(), ForeignKey("tasks.id", ondelete="CASCADE")
    )
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="todo")
    priority: Mapped[str] = mapped_column(String(16), default="medium")
    due_at: Mapped[datetime | None] = mapped_column(DateTime)
    rrule: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list] = mapped_column(json_type(), default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )


class TaskDependency(Base):
    __tablename__ = "task_dependencies"

    task_id: Mapped[int] = mapped_column(
        bigint(), ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    blocked_by_id: Mapped[int] = mapped_column(
        bigint(), ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )


class TaskPerson(Base):
    __tablename__ = "task_people"

    task_id: Mapped[int] = mapped_column(
        bigint(), ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    person_id: Mapped[int] = mapped_column(
        bigint(), ForeignKey("people.id", ondelete="CASCADE"), primary_key=True
    )
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str | None] = mapped_column(String(64))


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(bigint(), primary_key=True)
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    sphere_id: Mapped[int | None] = mapped_column(bigint(), ForeignKey("spheres.id"))
    project_id: Mapped[int | None] = mapped_column(
        bigint(), ForeignKey("projects.id")
    )
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    start_at: Mapped[datetime] = mapped_column(DateTime)
    end_at: Mapped[datetime | None] = mapped_column(DateTime)
    all_day: Mapped[bool] = mapped_column(Boolean, default=False)
    location: Mapped[str | None] = mapped_column(String(300))
    rrule: Mapped[str | None] = mapped_column(Text)
    remind_minutes: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class EventParticipant(Base):
    __tablename__ = "event_participants"

    event_id: Mapped[int] = mapped_column(
        bigint(), ForeignKey("events.id", ondelete="CASCADE"), primary_key=True
    )
    person_id: Mapped[int] = mapped_column(
        bigint(), ForeignKey("people.id", ondelete="CASCADE"), primary_key=True
    )
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str | None] = mapped_column(String(64))


class CalendarToken(Base):
    __tablename__ = "calendar_tokens"

    id: Mapped[int] = mapped_column(bigint(), primary_key=True)
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    scope: Mapped[str] = mapped_column(String(32))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Document(Base):
    """Документ знания (§7): оригинал в storage, текст — в `chunks`."""

    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_owner_created", "owner_id", "created_at"),
        Index("ix_documents_owner_status", "owner_id", "status"),
        # Дедуп в рамках владельца: partial unique на PostgreSQL; на SQLite
        # обычный unique — NULL-ы там не конфликтуют между собой.
        Index(
            "uq_documents_owner_sha256",
            "owner_id",
            "sha256",
            unique=True,
            postgresql_where=text("sha256 IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(bigint(), primary_key=True)
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE")
    )
    sphere_id: Mapped[int | None] = mapped_column(bigint(), ForeignKey("spheres.id"))
    project_id: Mapped[int | None] = mapped_column(
        bigint(), ForeignKey("projects.id")
    )
    title: Mapped[str] = mapped_column(String(300))
    source_type: Mapped[str] = mapped_column(String(16), default="file")
    sha256: Mapped[str | None] = mapped_column(String(64))
    mime: Mapped[str | None] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(bigint(), default=0)
    pages: Mapped[int | None] = mapped_column(Integer)
    storage: Mapped[str] = mapped_column(String(16), default="local")
    storage_ref: Mapped[str | None] = mapped_column(Text)
    annotation: Mapped[str | None] = mapped_column(Text)
    doc_class: Mapped[str | None] = mapped_column(String(32))
    tags: Mapped[list] = mapped_column(json_type(), default=list)
    entities: Mapped[dict] = mapped_column(json_type(), default=dict)
    status: Mapped[str] = mapped_column(String(16), default="uploaded")
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )


class Chunk(Base):
    """Фрагмент текста документа; `qdrant_point_id` заполняет поиск (WS-D)."""

    __tablename__ = "chunks"
    __table_args__ = (
        Index("ix_chunks_owner_document_ord", "owner_id", "document_id", "ord"),
    )

    id: Mapped[int] = mapped_column(bigint(), primary_key=True)
    document_id: Mapped[int] = mapped_column(
        bigint(), ForeignKey("documents.id", ondelete="CASCADE")
    )
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE")
    )
    ord: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text)
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    qdrant_point_id: Mapped[str | None] = mapped_column(String(64))


class Job(Base):
    """Задание воркера: отложенная обработка оригинала."""

    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_owner_status", "owner_id", "status"),
        Index("ix_jobs_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(bigint(), primary_key=True)
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE")
    )
    type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="queued")
    payload: Mapped[dict] = mapped_column(json_type(), default=dict)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    error: Mapped[str | None] = mapped_column(Text)


class WorkerToken(Base):
    __tablename__ = "worker_tokens"

    id: Mapped[int] = mapped_column(bigint(), primary_key=True)
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE")
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime)


class Integration(Base):
    """Внешняя интеграция пользователя (например, `yadisk`), токен — шифром."""

    __tablename__ = "integrations"

    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    kind: Mapped[str] = mapped_column(String(32), primary_key=True)
    token_enc: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow
    )
