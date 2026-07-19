"""ORM model for the ``logs`` table — persisted structured log/event records."""
from __future__ import annotations

from sqlalchemy import JSON, ForeignKey, String, Text

from sqlalchemy.orm import Mapped, mapped_column

from database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Log(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    A structured log record persisted to the database, complementing the
    Loguru file sinks. Used primarily so the (future) GUI can query and
    display recent events/errors without tailing log files.
    """

    __tablename__ = "logs"

    project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    level: Mapped[str] = mapped_column(String(16), default="INFO", nullable=False)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Log id={self.id!r} level={self.level!r} source={self.source!r}>"
