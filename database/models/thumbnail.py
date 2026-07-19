"""ORM model for the ``thumbnails`` table — thumbnail concepts and renders."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from database.models.project import Project


class Thumbnail(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    A thumbnail concept for a project: the creative direction (headline
    text, visual focal point, colour scheme) plus the rendered image
    file path once generated.
    """

    __tablename__ = "thumbnails"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    concept_title: Mapped[str] = mapped_column(String(255), nullable=False)
    headline_text: Mapped[str] = mapped_column(String(255), nullable=False)
    visual_description: Mapped[str] = mapped_column(Text, nullable=False)
    color_scheme: Mapped[str | None] = mapped_column(String(255), nullable=True)
    emotion: Mapped[str | None] = mapped_column(String(128), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    is_selected: Mapped[bool] = mapped_column(default=False, nullable=False)

    project: Mapped["Project"] = relationship(back_populates="thumbnails")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Thumbnail id={self.id!r} concept={self.concept_title!r}>"
