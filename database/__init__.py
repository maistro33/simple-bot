"""
Database package for FACT DROP AI STUDIO.

Exposes the engine/session helpers and the declarative base. Models are
intentionally NOT imported here (to avoid import-order issues); import
``database.models`` explicitly, or rely on ``init_database()`` which
does so internally.
"""
from database.base import Base
from database.session import get_engine, get_session_factory, init_database, session_scope

__all__ = [
    "Base",
    "get_engine",
    "get_session_factory",
    "init_database",
    "session_scope",
]
