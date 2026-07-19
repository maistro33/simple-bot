"""ORM model for the ``settings`` table — persisted key/value user settings."""
from __future__ import annotations

from sqlalchemy import JSON, String

from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Setting(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    A single persisted application setting, distinct from ``.env``
    environment configuration: these are user/runtime-adjustable
    preferences such as UI theme, default voice, default export format.
    """

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    value: Mapped[dict] = mapped_column(JSON, nullable=False)
    category: Mapped[str] = mapped_column(String(64), default="general", nullable=False)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Setting key={self.key!r}>"
