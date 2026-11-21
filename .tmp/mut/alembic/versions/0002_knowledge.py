"""M2: знания — документы, чанки, задания, воркер-токены, интеграции §7.

Revision ID: 0002_knowledge
Revises: 0001_m1
Create Date: 2026-11-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_knowledge"
down_revision = "0001_m1"
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
        "documents",
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
        sa.Column("source_type", sa.String(16), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("mime", sa.String(255), nullable=True),
        sa.Column("size_bytes", bigint(), nullable=False),
        sa.Column("pages", sa.Integer(), nullable=True),
        sa.Column("storage", sa.String(16), nullable=False),
        sa.Column("storage_ref", sa.Text(), nullable=True),
        sa.Column("annotation", sa.Text(), nullable=True),
        sa.Column("doc_class", sa.String(32), nullable=True),
        sa.Column("tags", jsonb(), nullable=False),
        sa.Column("entities", jsonb(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_documents_owner_created", "documents", ["owner_id", "created_at"]
    )
    op.create_index(
        "ix_documents_owner_status", "documents", ["owner_id", "status"]
    )
    # Дедуп в рамках владельца: partial unique на PostgreSQL; на SQLite NULL-ы
    # в unique-индексе не конфликтуют, поэтому обычный unique-индекс.
    op.create_index(
        "uq_documents_owner_sha256",
        "documents",
        ["owner_id", "sha256"],
        unique=True,
        postgresql_where=sa.text("sha256 IS NOT NULL"),
    )

    op.create_table(
        "chunks",
        sa.Column("id", bigint(), primary_key=True, autoincrement=True),
        sa.Column(
            "document_id",
            bigint(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ord", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("tokens", sa.Integer(), nullable=False),
        sa.Column("qdrant_point_id", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_chunks_owner_document_ord", "chunks", ["owner_id", "document_id", "ord"]
    )
    if op.get_bind().dialect.name == "postgresql":
        # Полнотекстовый поиск FR-5; на SQLite FTS нет — там lexical fallback.
        op.execute(
            "CREATE INDEX ix_chunks_text_fts ON chunks "
            "USING GIN (to_tsvector('russian', text))"
        )

    op.create_table(
        "jobs",
        sa.Column("id", bigint(), primary_key=True, autoincrement=True),
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("payload", jsonb(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("ix_jobs_owner_status", "jobs", ["owner_id", "status"])
    op.create_index("ix_jobs_status_created", "jobs", ["status", "created_at"])

    op.create_table(
        "worker_tokens",
        sa.Column("id", bigint(), primary_key=True, autoincrement=True),
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_worker_tokens_owner_id", "worker_tokens", ["owner_id"]
    )
    op.create_index(
        "ix_worker_tokens_token_hash",
        "worker_tokens",
        ["token_hash"],
        unique=True,
    )

    op.create_table(
        "integrations",
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("token_enc", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("owner_id", "kind"),
    )


def downgrade() -> None:
    op.drop_table("integrations")
    op.drop_index("ix_worker_tokens_token_hash", table_name="worker_tokens")
    op.drop_index("ix_worker_tokens_owner_id", table_name="worker_tokens")
    op.drop_table("worker_tokens")
    op.drop_index("ix_jobs_status_created", table_name="jobs")
    op.drop_index("ix_jobs_owner_status", table_name="jobs")
    op.drop_table("jobs")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_chunks_text_fts")
    op.drop_index("ix_chunks_owner_document_ord", table_name="chunks")
    op.drop_table("chunks")
    op.drop_index("uq_documents_owner_sha256", table_name="documents")
    op.drop_index("ix_documents_owner_status", table_name="documents")
    op.drop_index("ix_documents_owner_created", table_name="documents")
    op.drop_table("documents")
