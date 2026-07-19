"""ORM model for the ``voices`` table — generated voice-over audio tracks."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from database.models.project import Project


class Voice(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    A synthesised voice-over track generated from a project's full script,
    including provider metadata needed to reproduce or regenerate it.
    """

    __tablename__ = "voices"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    provider: Mapped[str] = mapped_column(String(64), default="elevenlabs", nullable=False)
    voice_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    voice_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    language: Mapped[str] = mapped_column(String(16), default="en", nullable=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    stability: Mapped[float | None] = mapped_column(Float, nullable=True)
    similarity_boost: Mapped[float | None] = mapped_column(Float, nullable=True)

    project: Mapped["Project"] = relationship(back_populates="voices")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Voice id={self.id!r} provider={self.provider!r}>"
