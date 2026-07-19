"""
Centralised logging configuration for FACT DROP AI STUDIO.

Every module in the application obtains its logger via
:func:`get_logger`, which returns a Loguru logger pre-bound with the
calling module's name. Sinks (console + rotating file) are configured
exactly once, the first time this module is imported.
"""
from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger as _loguru_logger

from config import get_settings

_CONFIGURED: bool = False


def _configure_logging() -> None:
    """
    Configure Loguru sinks exactly once for the entire process.

    Sets up:
      * A colourised console sink at the configured log level.
      * A rotating, retained file sink for ``INFO`` and above.
      * A dedicated file sink capturing only ``ERROR`` and above, so
        operators can tail failures without noise.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    settings = get_settings()
    log_dir: Path = settings.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    _loguru_logger.remove()

    _loguru_logger.add(
        sys.stderr,
        level=settings.log_level,
        colorize=True,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
        backtrace=settings.app_debug,
        diagnose=settings.app_debug,
    )

    _loguru_logger.add(
        log_dir / "fact_drop_{time:YYYY-MM-DD}.log",
        level="INFO",
        rotation=settings.log_rotation,
        retention=settings.log_retention,
        compression="zip",
        encoding="utf-8",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
            "{name}:{function}:{line} | {message}"
        ),
        enqueue=True,
        backtrace=True,
        diagnose=False,
    )

    _loguru_logger.add(
        log_dir / "errors_{time:YYYY-MM-DD}.log",
        level="ERROR",
        rotation=settings.log_rotation,
        retention=settings.log_retention,
        compression="zip",
        encoding="utf-8",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
            "{name}:{function}:{line} | {message}\n{exception}"
        ),
        enqueue=True,
        backtrace=True,
        diagnose=False,
    )

    _CONFIGURED = True
    _loguru_logger.debug("Logging subsystem configured.")


def get_logger(name: str):
    """
    Return a Loguru logger bound with ``name`` (typically ``__name__``).

    Args:
        name: The name to bind onto the logger, usually the calling
            module's ``__name__``, so log lines are traceable to their
            origin.

    Returns:
        A Loguru logger instance pre-bound with the ``module`` context.
    """
    _configure_logging()
    return _loguru_logger.bind(module=name)
