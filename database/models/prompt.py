"""ORM model for the ``prompts`` table — cinematic AI image/video prompts."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from database.models.project import Project


class Prompt(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    A single AI generation prompt (image or video) tied to one storyboard
    scene, ready to be sent to an image/video generation provider.
    """

    __tablename__ = "prompts"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scene_number: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt_type: Mapped[str] = mapped_column(String(32), default="image", nullable=False)
    positive_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    negative_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    style_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    aspect_ratio: Mapped[str] = mapped_column(String(16), default="9:16", nullable=False)
    camera_motion: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lighting: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="prompts")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Prompt id={self.id!r} scene={self.scene_number} type={self.prompt_type}>"
