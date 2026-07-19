"""
Recovery Manager — detects interrupted/failed projects and coordinates
resuming them from the last successfully completed workflow stage,
using bounded exponential-backoff retries for transient failures.
"""
from __future__ import annotations

import time
from typing import Callable, TypeVar

from config.constants import MAX_RETRY_ATTEMPTS, RETRY_BACKOFF_SECONDS, WorkflowStatus
from core.exceptions import ConfigurationError, StageExecutionError, TransientServiceError
from core.logger import get_logger
from database.models.project import Project
from database.repositories.project_repository import ProjectRepository
from database.session import session_scope

logger = get_logger(__name__)

T = TypeVar("T")


class RecoveryManager:
    """
    Provides retry-with-backoff execution for individual pipeline stages
    and discovery of projects that need to be resumed after a crash or
    manual pause.
    """

    def __init__(self) -> None:
        self._project_repo = ProjectRepository()

    def find_resumable_projects(self) -> list[Project]:
        """Return every project left in a non-terminal state, oldest-updated first."""
        with session_scope() as session:
            projects = self._project_repo.get_resumable(session)
            # Detach-safe: read fields we need while session is open.
            return [
                Project(
                    id=p.id,
                    name=p.name,
                    raw_input=p.raw_input,
                    current_stage=p.current_stage,
                    status=p.status,
                )
                for p in projects
            ]

    def execute_with_retry(
        self,
        stage_name: str,
        func: Callable[[], T],
        max_attempts: int = MAX_RETRY_ATTEMPTS,
        backoff_seconds: float = RETRY_BACKOFF_SECONDS,
    ) -> T:
        """
        Execute ``func`` with exponential-backoff retries on transient errors.

        Non-transient :class:`StageExecutionError` with ``recoverable=False``
        (or any other unexpected exception) is raised immediately without
        retrying, since retrying a deterministic bug would just waste time
        and API quota.

        Args:
            stage_name: The workflow stage name, used purely for logging.
            func: A zero-argument callable performing the actual work.
            max_attempts: Maximum number of attempts before giving up.
            backoff_seconds: Base delay multiplied by ``2 ** attempt``.

        Raises:
            StageExecutionError: If every retry attempt is exhausted.
        """
        last_exception: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                return func()
            except TransientServiceError as exc:
                last_exception = exc
                delay = backoff_seconds * (2 ** (attempt - 1))
                logger.warning(
                    "Stage '{}' attempt {}/{} failed transiently: {}. Retrying in {:.1f}s.",
                    stage_name, attempt, max_attempts, exc, delay,
                )
                if attempt < max_attempts:
                    time.sleep(delay)
            except StageExecutionError as exc:
                if not exc.recoverable or isinstance(exc.__cause__, ConfigurationError):
                    logger.error("Stage '{}' failed non-recoverably: {}", stage_name, exc)
                    raise
                last_exception = exc
                delay = backoff_seconds * (2 ** (attempt - 1))
                logger.warning(
                    "Stage '{}' attempt {}/{} failed: {}. Retrying in {:.1f}s.",
                    stage_name, attempt, max_attempts, exc, delay,
                )
                if attempt < max_attempts:
                    time.sleep(delay)

        raise StageExecutionError(
            stage_name, f"Exhausted {max_attempts} attempts. Last error: {last_exception}"
        )

    def mark_project_failed(self, project_id: str, error_message: str) -> None:
        """Persist a failure state on a project so it surfaces in resumable listings."""
        with session_scope() as session:
            self._project_repo.update(
                session, project_id, status=WorkflowStatus.FAILED, error_message=error_message
            )
        logger.error("Project {} marked as FAILED: {}", project_id, error_message)

    def mark_project_paused(self, project_id: str) -> None:
        """Persist a paused state, e.g. when the user explicitly interrupts a run."""
        with session_scope() as session:
            self._project_repo.update(session, project_id, status=WorkflowStatus.PAUSED)
        logger.info("Project {} marked as PAUSED.", project_id)
