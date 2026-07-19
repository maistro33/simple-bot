"""ORM model for the ``subtitles`` table — generated subtitle/caption files."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from database.models.project import Project


class Subtitle(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    A subtitle/caption track for a project, stored both as a rendered
    file (SRT/VTT on disk) and as structured cue data for programmatic
    reuse (e.g. burning captions into video with MoviePy).
    """

    __tablename__ = "subtitles"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    format: Mapped[str] = mapped_column(String(16), default="srt", nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    raw_content: Mapped[str] = mapped_column(Text, nullable=False)
    cues: Mapped[list | None] = mapped_column(JSON, nullable=True)
    language: Mapped[str] = mapped_column(String(16), default="en", nullable=False)

    project: Mapped["Project"] = relationship(back_populates="subtitles")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Subtitle id={self.id!r} format={self.format!r}>"
