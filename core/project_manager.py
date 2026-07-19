"""
Project Manager — the public API for creating, listing, resuming,
deleting and undoing changes to projects. Sits above the repository
layer and coordinates the event bus, history snapshots and asset
cleanup so callers (CLI, workflow engine) never touch the database
directly.
"""
from __future__ import annotations

from typing import Any

from config.constants import WorkflowStage, WorkflowStatus
from core.asset_manager import AssetManager
from core.event_bus import get_event_bus
from core.exceptions import ProjectNotFoundError
from core.logger import get_logger
from database.models.project import Project
from database.repositories.domain_repositories import HistoryRepository
from database.repositories.project_repository import ProjectRepository
from database.session import session_scope

logger = get_logger(__name__)


class ProjectManager:
    """
    High-level façade over project persistence, following the Facade
    pattern to give the rest of the application (CLI, Workflow Engine)
    a single, simple entry point for all project lifecycle operations.
    """

    def __init__(self) -> None:
        self._repo = ProjectRepository()
        self._history_repo = HistoryRepository()
        self._asset_manager = AssetManager()
        self._event_bus = get_event_bus()

    def create_project(self, raw_input: str, name: str | None = None) -> Project:
        """
        Create a new project from raw user input (a URL, title, or free-form
        product description) and persist its initial snapshot to history.

        Args:
            raw_input: The exact text/URL the user provided.
            name: Optional human-friendly project name; derived from the
                input's first 60 characters when omitted.

        Returns:
            The newly created, fully persisted :class:`Project`.
        """
        display_name = name or self._derive_name(raw_input)

        with session_scope() as session:
            project = self._repo.create(
                session,
                name=display_name,
                raw_input=raw_input,
                current_stage=WorkflowStage.PRODUCT_ANALYSIS,
                status=WorkflowStatus.PENDING,
            )
            session.flush()
            project_id = project.id
            self._snapshot(session, project_id, action="project_created", stage=WorkflowStage.PRODUCT_ANALYSIS.value)

        logger.info("Created project '{}' (id={})", display_name, project_id)
        self._event_bus.publish("project.created", {"project_id": project_id, "name": display_name})

        with session_scope() as session:
            return self._repo.get_by_id(session, project_id)

    def get_project(self, project_id: str) -> Project:
        """Return a project by ID, raising if it does not exist."""
        with session_scope() as session:
            project = self._repo.get_by_id(session, project_id)
            if project is None:
                raise ProjectNotFoundError(f"No project found with id={project_id}")
            session.expunge(project)
            return project

    def list_projects(self, limit: int = 100) -> list[Project]:
        """Return the most recently updated projects, newest first."""
        with session_scope() as session:
            projects = self._repo.get_all(session, limit=limit)
            for p in projects:
                session.expunge(p)
            return list(projects)

    def list_resumable_projects(self) -> list[Project]:
        """Return every project left mid-pipeline (paused, failed, or running)."""
        with session_scope() as session:
            projects = self._repo.get_resumable(session)
            for p in projects:
                session.expunge(p)
            return list(projects)

    def update_stage(self, project_id: str, stage: WorkflowStage, status: WorkflowStatus | None = None) -> None:
        """Advance a project's ``current_stage`` and, optionally, its status."""
        fields: dict[str, Any] = {"current_stage": stage}
        if status is not None:
            fields["status"] = status

        with session_scope() as session:
            self._repo.update(session, project_id, **fields)
            self._snapshot(session, project_id, action="stage_advanced", stage=stage.value)

        self._event_bus.publish(
            "project.stage_changed", {"project_id": project_id, "stage": stage.value, "status": status.value if status else None}
        )

    def update_fields(self, project_id: str, **fields: Any) -> None:
        """Persist arbitrary field updates on a project (e.g. research_data, brand_name)."""
        with session_scope() as session:
            self._repo.update(session, project_id, **fields)

    def delete_project(self, project_id: str, delete_assets: bool = True) -> bool:
        """
        Permanently delete a project and (optionally) its on-disk assets.

        The database cascade handles all dependent rows (scripts,
        storyboards, prompts, etc.) automatically via ``ondelete=CASCADE``.
        """
        with session_scope() as session:
            deleted = self._repo.delete(session, project_id)

        if deleted and delete_assets:
            self._asset_manager.delete_project_assets(project_id)

        if deleted:
            logger.info("Deleted project {}", project_id)
            self._event_bus.publish("project.deleted", {"project_id": project_id})
        return deleted

    def undo_last_action(self, project_id: str) -> dict | None:
        """
        Revert a project to its most recent non-reverted history snapshot.

        Returns:
            The restored snapshot dict, or None if no history exists.
        """
        with session_scope() as session:
            entries = self._history_repo.list_by_project(session, project_id)
            candidates = [e for e in entries if not e.is_reverted]
            if not candidates:
                logger.warning("No history available to undo for project {}", project_id)
                return None

            latest = max(candidates, key=lambda e: e.sequence_number)
            snapshot = latest.snapshot
            latest.is_reverted = True

            stage_value = snapshot.get("current_stage")
            status_value = snapshot.get("status")
            update_fields: dict[str, Any] = {}
            if stage_value:
                update_fields["current_stage"] = WorkflowStage(stage_value)
            if status_value:
                update_fields["status"] = WorkflowStatus(status_value)
            if update_fields:
                self._repo.update(session, project_id, **update_fields)

        logger.info("Reverted project {} to snapshot seq={}", project_id, latest.sequence_number)
        return snapshot

    def _snapshot(self, session, project_id: str, action: str, stage: str) -> None:
        """Persist a history row capturing the current project state before/after a change."""
        project = self._repo.get_by_id(session, project_id)
        if project is None:
            return
        sequence_number = self._history_repo.get_next_sequence_number(session, project_id)
        snapshot = {
            "current_stage": project.current_stage.value,
            "status": project.status.value,
            "research_data": project.research_data,
            "strategy_data": project.strategy_data,
        }
        self._history_repo.create(
            session,
            project_id=project_id,
            sequence_number=sequence_number,
            action=action,
            stage=stage,
            snapshot=snapshot,
        )

    @staticmethod
    def _derive_name(raw_input: str) -> str:
        """Derive a short, human-friendly project name from raw input text."""
        cleaned = raw_input.strip().replace("\n", " ")
        return (cleaned[:60] + "…") if len(cleaned) > 60 else cleaned


_project_manager: ProjectManager | None = None


def get_project_manager() -> ProjectManager:
    """Return the process-wide :class:`ProjectManager` singleton."""
    global _project_manager
    if _project_manager is None:
        _project_manager = ProjectManager()
    return _project_manager
