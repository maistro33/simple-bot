"""ORM model for the ``scripts`` table — YouTube Shorts scripts and hooks."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from database.models.project import Project


class Script(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    A generated video script for a project, including the attention hook,
    the full body script broken into timed beats, and a call-to-action.
    """

    __tablename__ = "scripts"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    hook_text: Mapped[str] = mapped_column(Text, nullable=False)
    hook_style: Mapped[str | None] = mapped_column(String(128), nullable=True)
    full_script: Mapped[str] = mapped_column(Text, nullable=False)
    call_to_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    estimated_duration_seconds: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    beats: Mapped[list | None] = mapped_column(JSON, nullable=True)
    tone: Mapped[str | None] = mapped_column(String(128), nullable=True)
    word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    project: Mapped["Project"] = relationship(back_populates="scripts")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Script id={self.id!r} project_id={self.project_id!r} v={self.version}>"
