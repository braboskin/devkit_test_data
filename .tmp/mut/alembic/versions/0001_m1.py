"""M1: фундамент §7 ТЗ — пользователи, сессии и доменные таблицы.

Revision ID: 0001_m1
Revises:
Create Date: 2026-11-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_m1"
down_revision = None
branch_labels = None
depends_on = None


def bigint() -> sa.BigInteger:
    """bigint identity на PostgreSQL, INTEGER на SQLite."""
    return sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def jsonb() -> sa.JSON:
    """JSONB на PostgreSQL, JSON на SQLite."""
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_token_hash", "sessions", ["token_hash"], unique=True)

    op.create_table(
        "spheres",
        sa.Column("id", bigint(), primary_key=True, autoincrement=True),
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_spheres_owner_id", "spheres", ["owner_id"])

    op.create_table(
        "projects",
        sa.Column("id", bigint(), primary_key=True, autoincrement=True),
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "sphere_id",
            bigint(),
            sa.ForeignKey("spheres.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("due_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_projects_owner_id", "projects", ["owner_id"])

    op.create_table(
        "people",
        sa.Column("id", bigint(), primary_key=True, autoincrement=True),
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("contacts", jsonb(), nullable=False),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("relation", sa.String(64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("tags", jsonb(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_people_owner_id", "people", ["owner_id"])

    op.create_table(
        "person_spheres",
        sa.Column(
            "person_id",
            bigint(),
            sa.ForeignKey("people.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "sphere_id",
            bigint(),
            sa.ForeignKey("spheres.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(64), nullable=True),
        sa.PrimaryKeyConstraint("person_id", "sphere_id"),
    )
    op.create_index("ix_person_spheres_owner_id", "person_spheres", ["owner_id"])

    op.create_table(
        "person_projects",
        sa.Column(
            "person_id",
            bigint(),
            sa.ForeignKey("people.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            bigint(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(64), nullable=True),
        sa.PrimaryKeyConstraint("person_id", "project_id"),
    )
    op.create_index("ix_person_projects_owner_id", "person_projects", ["owner_id"])

    op.create_table(
        "tasks",
        sa.Column("id", bigint(), primary_key=True, autoincrement=True),
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sphere_id", bigint(), sa.ForeignKey("spheres.id"), nullable=True),
        sa.Column("project_id", bigint(), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column(
            "parent_id",
            bigint(),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("priority", sa.String(16), nullable=False),
        sa.Column("due_at", sa.DateTime(), nullable=True),
        sa.Column("rrule", sa.Text(), nullable=True),
        sa.Column("tags", jsonb(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_tasks_owner_id", "tasks", ["owner_id"])

    op.create_table(
        "task_dependencies",
        sa.Column(
            "task_id",
            bigint(),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "blocked_by_id",
            bigint(),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("task_id", "blocked_by_id"),
    )

    op.create_table(
        "task_people",
        sa.Column(
            "task_id",
            bigint(),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "person_id",
            bigint(),
            sa.ForeignKey("people.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(64), nullable=True),
        sa.PrimaryKeyConstraint("task_id", "person_id"),
    )
    op.create_index("ix_task_people_owner_id", "task_people", ["owner_id"])

    op.create_table(
        "events",
        sa.Column("id", bigint(), primary_key=True, autoincrement=True),
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sphere_id", bigint(), sa.ForeignKey("spheres.id"), nullable=True),
        sa.Column("project_id", bigint(), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("start_at", sa.DateTime(), nullable=False),
        sa.Column("end_at", sa.DateTime(), nullable=True),
        sa.Column("all_day", sa.Boolean(), nullable=False),
        sa.Column("location", sa.String(300), nullable=True),
        sa.Column("rrule", sa.Text(), nullable=True),
        sa.Column("remind_minutes", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_events_owner_id", "events", ["owner_id"])

    op.create_table(
        "event_participants",
        sa.Column(
            "event_id",
            bigint(),
            sa.ForeignKey("events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "person_id",
            bigint(),
            sa.ForeignKey("people.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(64), nullable=True),
        sa.PrimaryKeyConstraint("event_id", "person_id"),
    )
    op.create_index(
        "ix_event_participants_owner_id", "event_participants", ["owner_id"]
    )

    op.create_table(
        "calendar_tokens",
        sa.Column("id", bigint(), primary_key=True, autoincrement=True),
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scope", sa.String(32), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_calendar_tokens_owner_id", "calendar_tokens", ["owner_id"])
    op.create_index(
        "ix_calendar_tokens_token_hash",
        "calendar_tokens",
        ["token_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("calendar_tokens")
    op.drop_table("event_participants")
    op.drop_table("events")
    op.drop_table("task_people")
    op.drop_table("task_dependencies")
    op.drop_table("tasks")
    op.drop_table("person_projects")
    op.drop_table("person_spheres")
    op.drop_table("people")
    op.drop_table("projects")
    op.drop_table("spheres")
    op.drop_table("sessions")
    op.drop_table("users")
