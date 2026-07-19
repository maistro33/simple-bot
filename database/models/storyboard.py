"""ORM model for the ``storyboards`` table — scene-by-scene visual breakdown."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from database.models.project import Project


class Storyboard(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Represents one scene of the storyboard derived from a project's script.

    Each row is a single scene; a project typically has several ordered
    ``Storyboard`` rows distinguished by ``scene_number``.
    """

    __tablename__ = "storyboards"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scene_number: Mapped[int] = mapped_column(Integer, nullable=False)
    scene_title: Mapped[str] = mapped_column(String(255), nullable=False)
    narration_text: Mapped[str] = mapped_column(Text, nullable=False)
    visual_description: Mapped[str] = mapped_column(Text, nullable=False)
    camera_angle: Mapped[str | None] = mapped_column(String(128), nullable=True)
    duration_seconds: Mapped[float] = mapped_column(Integer, default=5, nullable=False)
    on_screen_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    transition: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sound_effect: Mapped[str | None] = mapped_column(String(255), nullable=True)
    extra_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    project: Mapped["Project"] = relationship(back_populates="storyboards")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Storyboard id={self.id!r} scene={self.scene_number}>"
