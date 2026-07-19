"""ORM model for the ``cache`` table — persisted, TTL-aware key/value cache."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, String

from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Cache(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    A persisted cache entry. Backs the in-memory :class:`CacheManager` so
    expensive operations (competitor research API calls, AI completions)
    survive application restarts until their TTL expires.
    """

    __tablename__ = "cache"

    cache_key: Mapped[str] = mapped_column(String(512), unique=True, nullable=False, index=True)
    value: Mapped[dict] = mapped_column(JSON, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    namespace: Mapped[str] = mapped_column(String(128), default="default", nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Cache key={self.cache_key!r} namespace={self.namespace!r}>"
