"""ORM model for the ``history`` table — version history and undo support."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, Integer, String

from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from database.models.project import Project


class History(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    A single point-in-time snapshot of a project's mutable state, captured
    before each destructive or stage-advancing operation, enabling the
    Project Manager's undo/version-history feature.
    """

    __tablename__ = "history"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    is_reverted: Mapped[bool] = mapped_column(default=False, nullable=False)

    project: Mapped["Project"] = relationship(back_populates="history_entries")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<History id={self.id!r} seq={self.sequence_number} action={self.action!r}>"
