"""
Workflow Controller — a threading-based orchestration layer sitting above
:class:`core.workflow_engine.WorkflowEngine`, purpose-built for the
Telegram control panel (and any future synchronous UI).

Responsibilities:
  * Launch a project's pipeline run on a background thread so the
    Telegram bot's polling loop never blocks.
  * Bound overall concurrency with a semaphore (mirrors
    ``MAX_CONCURRENT_WORKFLOWS`` from settings).
  * Support cooperative pause/stop via a per-run ``threading.Event``,
    checked by :meth:`WorkflowEngine.run` between stages.
  * Track a live in-memory registry of running/queued/finished jobs for
    the "queue view" feature.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from config import get_settings
from core.logger import get_logger
from core.recovery_manager import RecoveryManager
from core.workflow_engine import WorkflowEngine

logger = get_logger(__name__)


class RunStatus(str, Enum):
    """Lifecycle status of a single controller-managed run."""

    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(slots=True)
class Run:
    """A single tracked execution of a project's pipeline."""

    id: str
    project_id: str
    project_name: str
    status: RunStatus = RunStatus.QUEUED
    error: str | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class WorkflowController:
    """
    Manages threaded, cancellable pipeline executions keyed by project ID.

    This is the single entry point the Telegram bot (or any other
    synchronous front-end) uses to start, pause, resume, stop and query
    project workflows, without ever touching :class:`WorkflowEngine`
    directly or worrying about thread management.
    """

    def __init__(self, workflow_engine: WorkflowEngine | None = None) -> None:
        self._engine = workflow_engine or WorkflowEngine()
        self._recovery = RecoveryManager()
        self._settings = get_settings()
        self._semaphore = threading.BoundedSemaphore(self._settings.max_concurrent_workflows)
        self._runs: dict[str, Run] = {}
        self._lock = threading.Lock()

    def start(self, project_id: str, project_name: str, resume: bool = False) -> Run:
        """
        Launch a project's pipeline on a background thread.

        Args:
            project_id: The project to run.
            project_name: Human-readable name, cached for display purposes.
            resume: Whether to resume from the project's last recorded stage
                (True) or start fresh from the beginning (False).

        Returns:
            The newly created :class:`Run` tracking object.
        """
        run = Run(id=str(uuid.uuid4()), project_id=project_id, project_name=project_name)
        with self._lock:
            self._runs[project_id] = run

        thread = threading.Thread(
            target=self._execute, args=(run, resume), name=f"workflow-{project_id[:8]}", daemon=True
        )
        run.thread = thread
        thread.start()
        logger.info("Started workflow run {} for project {} (resume={})", run.id, project_id, resume)
        return run

    def _execute(self, run: Run, resume: bool) -> None:
        """Thread target: acquires the concurrency slot and drives the engine run."""
        with self._semaphore:
            run.status = RunStatus.RUNNING
            run.started_at = datetime.now(timezone.utc)
            try:
                self._engine.run(run.project_id, resume=resume, cancel_event=run.cancel_event)
                if run.cancel_event.is_set():
                    run.status = RunStatus.PAUSED
                else:
                    run.status = RunStatus.COMPLETED
            except Exception as exc:  # noqa: BLE001 - run boundary; failure is recorded, not re-raised
                run.status = RunStatus.FAILED
                run.error = str(exc)
                logger.exception("Workflow run {} for project {} failed.", run.id, run.project_id)
            finally:
                run.finished_at = datetime.now(timezone.utc)

    def pause(self, project_id: str) -> bool:
        """
        Request cooperative cancellation of a running project.

        The run stops before its *next* stage boundary (not mid-stage),
        and the project is persisted as ``PAUSED`` so it can be resumed
        later via :meth:`start` with ``resume=True``.

        Returns:
            True if a running job was found and signalled, else False.
        """
        run = self._runs.get(project_id)
        if run is None or run.status != RunStatus.RUNNING:
            return False
        run.cancel_event.set()
        logger.info("Pause requested for project {}", project_id)
        return True

    def resume(self, project_id: str, project_name: str) -> Run:
        """Resume a paused or failed project from its last completed stage."""
        return self.start(project_id, project_name, resume=True)

    def retry(self, project_id: str, project_name: str) -> Run:
        """Retry a failed project — semantically identical to resume for this pipeline."""
        return self.start(project_id, project_name, resume=True)

    def stop(self, project_id: str) -> bool:
        """Alias for :meth:`pause` — stops a running job cooperatively (same mechanism)."""
        return self.pause(project_id)

    def get_run(self, project_id: str) -> Run | None:
        """Return the tracked :class:`Run` for a project, if one exists in this process."""
        return self._runs.get(project_id)

    def list_runs(self, status: RunStatus | None = None) -> list[Run]:
        """Return every tracked run, optionally filtered by status, most recent first."""
        runs = list(self._runs.values())
        if status is not None:
            runs = [r for r in runs if r.status == status]
        return sorted(runs, key=lambda r: r.started_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    def is_running(self, project_id: str) -> bool:
        """Return True if the given project currently has an active run in this process."""
        run = self._runs.get(project_id)
        return run is not None and run.status == RunStatus.RUNNING

    @property
    def active_count(self) -> int:
        """Number of runs currently executing (holding a concurrency slot)."""
        return sum(1 for r in self._runs.values() if r.status == RunStatus.RUNNING)

    @property
    def max_concurrency(self) -> int:
        """The configured maximum number of concurrent workflow runs."""
        return self._settings.max_concurrent_workflows


_workflow_controller: WorkflowController | None = None


def get_workflow_controller() -> WorkflowController:
    """Return the process-wide :class:`WorkflowController` singleton."""
    global _workflow_controller
    if _workflow_controller is None:
        _workflow_controller = WorkflowController()
    return _workflow_controller
