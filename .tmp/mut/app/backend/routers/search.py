"""Поиск (FR-5): гибридный поиск по знаниям и похожие документы."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..auth import current_user
from ..deps import get_db
from ..knowledge.search import search, similar
from ..models import Project, Sphere, User
from ..ownership import get_owned_or_404

router = APIRouter(tags=["search"])


def _tags(values: list[str] | None) -> list[str]:
    tags: list[str] = []
    for value in values or []:
        tags.extend(part.strip() for part in value.split(",") if part.strip())
    return tags


@router.get("/api/search")
def api_search(
    q: str = Query(..., description="поисковый запрос"),
    limit: int = Query(default=10, ge=1, le=50),
    sphere_id: int | None = None,
    project_id: int | None = None,
    doc_type: str | None = Query(default=None, alias="type"),
    doc_class: str | None = Query(default=None, alias="class"),
    status_: str | None = Query(default=None, alias="status"),
    tags: list[str] | None = Query(default=None),
    date_from: datetime | None = Query(default=None, alias="from"),
    date_to: datetime | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[dict]:
    """Гибридный поиск только по своим документам."""
    if not q.strip():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "query must not be empty"
        )
    if sphere_id is not None:
        get_owned_or_404(db, Sphere, sphere_id, user)
    if project_id is not None:
        get_owned_or_404(db, Project, project_id, user)
    return search(
        db,
        user,
        q,
        sphere_id=sphere_id,
        project_id=project_id,
        doc_type=doc_type,
        doc_class=doc_class,
        status=status_,
        tags=_tags(tags),
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )


@router.get("/api/documents/{document_id}/similar")
def api_similar(
    document_id: int,
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[dict]:
    """Похожие документы; чужой или несуществующий → 404."""
    return similar(db, user, document_id, limit=limit)
