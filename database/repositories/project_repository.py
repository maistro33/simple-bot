"""Repository for the ``Project`` aggregate root, with domain-specific queries."""
from __future__ import annotations

from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from config.constants import WorkflowStatus
from database.models.project import Project
from database.repositories.base_repository import BaseRepository


class ProjectRepository(BaseRepository[Project]):
    """Adds project-specific lookups (by status, resumable projects, ...) on top of CRUD."""

    def __init__(self) -> None:
        super().__init__(Project)

    def get_by_status(
        self, session: Session, status: WorkflowStatus, limit: int = 100
    ) -> Sequence[Project]:
        """Return projects currently in the given lifecycle status."""
        stmt = (
            select(Project)
            .where(Project.status == status)
            .order_by(Project.updated_at.desc())
            .limit(limit)
        )
        return session.execute(stmt).scalars().all()

    def get_resumable(self, session: Session) -> Sequence[Project]:
        """Return projects that were interrupted mid-pipeline and can be resumed."""
        stmt = select(Project).where(
            Project.status.in_(
                [WorkflowStatus.PAUSED, WorkflowStatus.FAILED, WorkflowStatus.RUNNING]
            )
        ).order_by(Project.updated_at.desc())
        return session.execute(stmt).scalars().all()

    def search_by_name(self, session: Session, query: str, limit: int = 50) -> Sequence[Project]:
        """Case-insensitive substring search over project names."""
        stmt = (
            select(Project)
            .where(Project.name.ilike(f"%{query}%"))
            .order_by(Project.updated_at.desc())
            .limit(limit)
        )
        return session.execute(stmt).scalars().all()
