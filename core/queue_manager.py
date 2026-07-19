"""
Async job queue that bounds how many project workflows may run
concurrently, protecting rate-limited external AI APIs from being
overwhelmed when many projects are queued at once.
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable

from config import get_settings
from core.exceptions import QueueFullError
from core.logger import get_logger

logger = get_logger(__name__)


class JobStatus(str, Enum):
    """Lifecycle status of a single queued job."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(slots=True)
class Job:
    """A unit of work submitted to the :class:`QueueManager`."""

    id: str
    name: str
    coro_factory: Callable[[], Awaitable[Any]]
    status: JobStatus = JobStatus.QUEUED
    result: Any = None
    error: str | None = None
    submitted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    finished_at: datetime | None = None


class QueueManager:
    """
    Bounded-concurrency async job queue.

    Wraps an ``asyncio.Semaphore`` sized from ``MAX_CONCURRENT_WORKFLOWS``
    so at most N project workflows execute simultaneously; additional
    submissions queue until a slot frees up.
    """

    def __init__(self, max_queue_size: int = 100) -> None:
        settings = get_settings()
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_workflows)
        self._max_queue_size = max_queue_size
        self._jobs: dict[str, Job] = {}
        self._lock = asyncio.Lock()

    async def submit(self, name: str, coro_factory: Callable[[], Awaitable[Any]]) -> str:
        """
        Enqueue a new job for execution and return its job ID immediately.

        Args:
            name: A human-readable job name (e.g. a project name) for logging.
            coro_factory: A zero-argument callable returning the coroutine
                to execute. Using a factory (rather than a coroutine object)
                avoids "coroutine already awaited" pitfalls on retry.

        Raises:
            QueueFullError: If the number of tracked jobs exceeds capacity.
        """
        async with self._lock:
            active = sum(1 for j in self._jobs.values() if j.status in (JobStatus.QUEUED, JobStatus.RUNNING))
            if active >= self._max_queue_size:
                raise QueueFullError(f"Queue is full ({active}/{self._max_queue_size} active jobs).")
            job_id = str(uuid.uuid4())
            self._jobs[job_id] = Job(id=job_id, name=name, coro_factory=coro_factory)

        logger.info("Job '{}' queued with id={}", name, job_id)
        asyncio.create_task(self._run_job(job_id))
        return job_id

    async def _run_job(self, job_id: str) -> None:
        """Execute a single queued job under the concurrency semaphore."""
        job = self._jobs[job_id]
        async with self._semaphore:
            job.status = JobStatus.RUNNING
            job.started_at = datetime.now(timezone.utc)
            logger.info("Job '{}' (id={}) started.", job.name, job_id)
            try:
                job.result = await job.coro_factory()
                job.status = JobStatus.COMPLETED
                logger.info("Job '{}' (id={}) completed successfully.", job.name, job_id)
            except Exception as exc:  # noqa: BLE001 - deliberately broad at job boundary
                job.status = JobStatus.FAILED
                job.error = str(exc)
                logger.exception("Job '{}' (id={}) failed.", job.name, job_id)
            finally:
                job.finished_at = datetime.now(timezone.utc)

    def get_job(self, job_id: str) -> Job | None:
        """Return the tracked :class:`Job` for ``job_id``, or None if unknown."""
        return self._jobs.get(job_id)

    def list_jobs(self, status: JobStatus | None = None) -> list[Job]:
        """Return all tracked jobs, optionally filtered by status."""
        jobs = list(self._jobs.values())
        if status is not None:
            jobs = [j for j in jobs if j.status == status]
        return sorted(jobs, key=lambda j: j.submitted_at, reverse=True)

    async def wait_for(self, job_id: str, poll_interval: float = 0.5) -> Job:
        """Block (async) until the given job reaches a terminal status."""
        while True:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(f"Unknown job id: {job_id}")
            if job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
                return job
            await asyncio.sleep(poll_interval)


_queue_manager: QueueManager | None = None


def get_queue_manager() -> QueueManager:
    """Return the process-wide :class:`QueueManager` singleton."""
    global _queue_manager
    if _queue_manager is None:
        _queue_manager = QueueManager()
    return _queue_manager
