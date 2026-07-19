"""
SQLAlchemy declarative base and reusable model mixins.

Every ORM model in the application inherits from :class:`Base` and, in
almost all cases, from :class:`TimestampMixin` and :class:`UUIDPrimaryKeyMixin`
so that identity generation and auditing behaviour stays perfectly
consistent across all fourteen tables.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    """Return the current UTC time (used as a shared column default)."""
    return datetime.now(timezone.utc)


def generate_uuid() -> str:
    """Generate a URL-safe unique identifier string for primary keys."""
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    """Root declarative base class shared by every ORM model."""

    pass


class UUIDPrimaryKeyMixin:
    """Mixin providing a UUID4 string primary key column named ``id``."""

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid, nullable=False
    )


class TimestampMixin:
    """Mixin providing ``created_at`` / ``updated_at`` audit columns."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )
