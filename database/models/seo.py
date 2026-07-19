"""ORM model for the ``seo`` table — titles, descriptions, tags, hashtags."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from database.models.project import Project


class Seo(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    The full SEO metadata package generated for a project: optimised
    titles, description, tags, hashtags and target keywords for
    YouTube/TikTok discoverability.
    """

    __tablename__ = "seo"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    titles: Mapped[list] = mapped_column(JSON, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list] = mapped_column(JSON, nullable=False)
    hashtags: Mapped[list] = mapped_column(JSON, nullable=False)
    primary_keyword: Mapped[str | None] = mapped_column(String(255), nullable=True)
    secondary_keywords: Mapped[list | None] = mapped_column(JSON, nullable=True)
    pinned_comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped["Project"] = relationship(back_populates="seo_entries")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Seo id={self.id!r} project_id={self.project_id!r}>"
