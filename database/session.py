"""
Database engine and session factory management.

This module owns the single SQLAlchemy ``Engine`` for the process and
exposes a context-manager based session helper so the rest of the
codebase never has to worry about opening/closing/committing/rolling
back sessions manually and consistently.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from config import get_settings
from core.logger import get_logger

logger = get_logger(__name__)

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """
    Return the process-wide SQLAlchemy :class:`Engine` singleton.

    For SQLite URLs, ``check_same_thread`` is disabled (safe because we
    serialise access via short-lived sessions) and foreign key
    enforcement is turned on via a connection-level ``PRAGMA``.
    """
    global _engine
    if _engine is not None:
        return _engine

    settings = get_settings()
    connect_args: dict = {}
    if settings.database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    _engine = create_engine(
        settings.database_url,
        echo=settings.database_echo,
        future=True,
        connect_args=connect_args,
    )

    if settings.database_url.startswith("sqlite"):

        @event.listens_for(_engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
            """Enable SQLite foreign-key enforcement on every connection."""
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    logger.info("Database engine initialised for URL: {}", settings.database_url)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Return the process-wide :class:`sessionmaker` singleton."""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(),
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
    return _session_factory


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """
    Provide a transactional scope around a series of ORM operations.

    Commits on success, rolls back and re-raises on any exception, and
    always closes the session. Usage::

        with session_scope() as session:
            session.add(my_model)
    """
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Database session rolled back due to an error.")
        raise
    finally:
        session.close()


def init_database() -> None:
    """
    Create all tables declared on :class:`database.base.Base` metadata.

    Safe to call on every application startup — SQLAlchemy's
    ``create_all`` only creates tables that do not already exist.
    """
    from database.base import Base
    import database.models  # noqa: F401  (ensures all models are registered)

    Base.metadata.create_all(bind=get_engine())
    logger.info("Database schema verified/created successfully.")
