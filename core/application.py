"""
Application — the top-level composition root for FACT DROP AI STUDIO.

Responsible for one-time startup (database schema, logging, scheduled
maintenance jobs) and exposing a single, simple facade
(``create_and_run_project``, ``resume_project``, etc.) that both the
CLI and any future GUI can call without knowing about the underlying
subsystem wiring.
"""
from __future__ import annotations

from typing import Any

from config import get_settings
from config.constants import ExportFormat
from core.backup_manager import BackupManager
from core.cache_manager import CacheManager
from core.export_manager import ExportManager
from core.logger import get_logger
from core.project_manager import ProjectManager, get_project_manager
from core.recovery_manager import RecoveryManager
from core.scheduler import get_scheduler_manager
from core.workflow_engine import WorkflowEngine
from database.session import init_database

logger = get_logger(__name__)


class Application:
    """
    Composition root and public facade for the entire application.

    Construct exactly one instance per process (typically inside
    ``main.py``), call :meth:`bootstrap` once, then drive projects
    through the pipeline via :meth:`create_and_run_project`.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._project_manager: ProjectManager = get_project_manager()
        self._workflow_engine = WorkflowEngine()
        self._backup_manager = BackupManager()
        self._recovery_manager = RecoveryManager()
        self._export_manager = ExportManager()
        self._scheduler = get_scheduler_manager()
        self._bootstrapped = False

    def bootstrap(self) -> None:
        """
        Perform one-time application startup: verify the database schema,
        ensure filesystem directories exist, and register background
        maintenance jobs (expired cache purges, periodic backups).
        """
        if self._bootstrapped:
            return

        logger.info("Bootstrapping {} (env={})", self._settings.app_name, self._settings.app_env)
        self._settings.ensure_directories()
        init_database()

        self._scheduler.add_interval_job(
            CacheManager.clear_all_expired, hours=1, job_id="cache_expiry_sweep"
        )
        self._scheduler.start()

        self._bootstrapped = True
        logger.info("Application bootstrap complete.")

    def shutdown(self) -> None:
        """Gracefully stop background services before process exit."""
        self._scheduler.shutdown(wait=False)
        logger.info("Application shutdown complete.")

    def create_and_run_project(self, raw_input: str, name: str | None = None) -> dict[str, Any]:
        """
        Create a new project from raw input and run it through the entire
        pipeline synchronously, returning the final accumulated context.
        """
        project = self._project_manager.create_project(raw_input, name=name)
        logger.info("Starting full pipeline run for project '{}' (id={})", project.name, project.id)
        try:
            context = self._workflow_engine.run(project.id, resume=False)
        finally:
            self._backup_manager.create_backup(project.id)
            self._backup_manager.prune_old_backups(project.id)
        return context

    def resume_project(self, project_id: str) -> dict[str, Any]:
        """Resume a previously interrupted project from its last recorded stage."""
        logger.info("Resuming project {}", project_id)
        context = self._workflow_engine.run(project_id, resume=True)
        self._backup_manager.create_backup(project_id)
        return context

    def list_resumable_projects(self) -> list:
        """Return every project left mid-pipeline, for CLI/GUI display."""
        return self._recovery_manager.find_resumable_projects()

    def export_project(self, project_id: str, export_format: ExportFormat = ExportFormat.ZIP):
        """Bundle a completed project into a delivery archive."""
        return self._export_manager.export_project(project_id, export_format=export_format)

    def undo_last_action(self, project_id: str):
        """Revert a project's most recent recorded change."""
        return self._project_manager.undo_last_action(project_id)

    @property
    def project_manager(self) -> ProjectManager:
        """Expose the Project Manager for direct read-only queries (list/get)."""
        return self._project_manager


_application: Application | None = None


def get_application() -> Application:
    """Return the process-wide :class:`Application` singleton, bootstrapping it if needed."""
    global _application
    if _application is None:
        _application = Application()
        _application.bootstrap()
    return _application
