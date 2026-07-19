"""
Concrete repositories for every remaining domain model.

Each of these tables only needs generic CRUD plus a "list by project"
lookup, so rather than duplicating boilerplate we generate them here on
top of :class:`BaseRepository`, adding the one project-scoped query
method each engine actually needs.
"""
from __future__ import annotations

from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models.asset import Asset
from database.models.export import Export
from database.models.history import History
from database.models.log import Log
from database.models.prompt import Prompt
from database.models.report import Report
from database.models.script import Script
from database.models.seo import Seo
from database.models.storyboard import Storyboard
from database.models.subtitle import Subtitle
from database.models.thumbnail import Thumbnail
from database.models.voice import Voice
from database.repositories.base_repository import BaseRepository, ModelType


class ProjectScopedRepository(BaseRepository[ModelType]):
    """Base class for repositories of tables owned by a single project."""

    def list_by_project(self, session: Session, project_id: str) -> Sequence[ModelType]:
        """Return every row belonging to the given project, oldest first."""
        stmt = (
            select(self.model)
            .where(self.model.project_id == project_id)
            .order_by(self.model.created_at.asc())
        )
        return session.execute(stmt).scalars().all()


class AssetRepository(ProjectScopedRepository[Asset]):
    def __init__(self) -> None:
        super().__init__(Asset)


class ScriptRepository(ProjectScopedRepository[Script]):
    def __init__(self) -> None:
        super().__init__(Script)

    def get_latest(self, session: Session, project_id: str) -> Script | None:
        """Return the highest-version script for a project."""
        stmt = (
            select(Script)
            .where(Script.project_id == project_id)
            .order_by(Script.version.desc())
            .limit(1)
        )
        return session.execute(stmt).scalars().first()


class StoryboardRepository(ProjectScopedRepository[Storyboard]):
    def __init__(self) -> None:
        super().__init__(Storyboard)

    def list_ordered(self, session: Session, project_id: str) -> Sequence[Storyboard]:
        """Return storyboard scenes ordered by their scene number."""
        stmt = (
            select(Storyboard)
            .where(Storyboard.project_id == project_id)
            .order_by(Storyboard.scene_number.asc())
        )
        return session.execute(stmt).scalars().all()


class PromptRepository(ProjectScopedRepository[Prompt]):
    def __init__(self) -> None:
        super().__init__(Prompt)


class VoiceRepository(ProjectScopedRepository[Voice]):
    def __init__(self) -> None:
        super().__init__(Voice)


class SubtitleRepository(ProjectScopedRepository[Subtitle]):
    def __init__(self) -> None:
        super().__init__(Subtitle)


class ThumbnailRepository(ProjectScopedRepository[Thumbnail]):
    def __init__(self) -> None:
        super().__init__(Thumbnail)


class SeoRepository(ProjectScopedRepository[Seo]):
    def __init__(self) -> None:
        super().__init__(Seo)


class ReportRepository(ProjectScopedRepository[Report]):
    def __init__(self) -> None:
        super().__init__(Report)


class ExportRepository(ProjectScopedRepository[Export]):
    def __init__(self) -> None:
        super().__init__(Export)


class HistoryRepository(ProjectScopedRepository[History]):
    def __init__(self) -> None:
        super().__init__(History)

    def get_next_sequence_number(self, session: Session, project_id: str) -> int:
        """Compute the next monotonically increasing sequence number for a project."""
        rows = self.list_by_project(session, project_id)
        return (max((row.sequence_number for row in rows), default=0)) + 1


class LogRepository(BaseRepository[Log]):
    def __init__(self) -> None:
        super().__init__(Log)

    def list_recent(self, session: Session, limit: int = 200) -> Sequence[Log]:
        """Return the most recent log records, newest first."""
        stmt = select(Log).order_by(Log.created_at.desc()).limit(limit)
        return session.execute(stmt).scalars().all()
