"""
Background task scheduler, built on APScheduler, used for periodic
maintenance work: expired-cache purges, automatic project backups and
autosave snapshots.
"""
from __future__ import annotations

from typing import Any, Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from core.logger import get_logger

logger = get_logger(__name__)


class SchedulerManager:
    """
    Thin, application-specific wrapper around :class:`BackgroundScheduler`.

    Centralising scheduler access here (rather than letting every module
    instantiate its own APScheduler) guarantees there is exactly one
    background thread pool managing all periodic jobs.
    """

    def __init__(self) -> None:
        self._scheduler = BackgroundScheduler(daemon=True)
        self._started = False

    def start(self) -> None:
        """Start the underlying APScheduler thread, if not already running."""
        if not self._started:
            self._scheduler.start()
            self._started = True
            logger.info("Background scheduler started.")

    def shutdown(self, wait: bool = True) -> None:
        """Stop the scheduler and cancel all pending jobs."""
        if self._started:
            self._scheduler.shutdown(wait=wait)
            self._started = False
            logger.info("Background scheduler shut down.")

    def add_interval_job(
        self,
        func: Callable[..., Any],
        *,
        seconds: int = 0,
        minutes: int = 0,
        hours: int = 0,
        job_id: str | None = None,
        replace_existing: bool = True,
        args: tuple = (),
        kwargs: dict | None = None,
    ) -> str:
        """
        Register a function to run repeatedly at a fixed interval.

        Args:
            func: The callable to invoke on each tick.
            seconds/minutes/hours: Interval components (combined).
            job_id: Optional explicit job identifier for later removal.
            replace_existing: Whether to replace a job already registered
                under the same ``job_id``.
            args/kwargs: Arguments forwarded to ``func`` on each invocation.

        Returns:
            The APScheduler job ID.
        """
        trigger = IntervalTrigger(seconds=seconds, minutes=minutes, hours=hours)
        job = self._scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            replace_existing=replace_existing,
            args=args,
            kwargs=kwargs or {},
        )
        logger.info("Scheduled interval job '{}' every {}h{}m{}s", job.id, hours, minutes, seconds)
        return job.id

    def remove_job(self, job_id: str) -> None:
        """Cancel and remove a previously scheduled job."""
        try:
            self._scheduler.remove_job(job_id)
            logger.info("Removed scheduled job '{}'.", job_id)
        except Exception:
            logger.warning("Attempted to remove unknown job '{}'.", job_id)

    def list_jobs(self) -> list[str]:
        """Return the IDs of all currently scheduled jobs."""
        return [job.id for job in self._scheduler.get_jobs()]


_scheduler_manager: SchedulerManager | None = None


def get_scheduler_manager() -> SchedulerManager:
    """Return the process-wide :class:`SchedulerManager` singleton."""
    global _scheduler_manager
    if _scheduler_manager is None:
        _scheduler_manager = SchedulerManager()
    return _scheduler_manager
