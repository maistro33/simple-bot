"""ORM model for the ``reports`` table — final project summary reports."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from database.models.project import Project


class Report(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    A generated end-of-pipeline report summarising the strategy, research
    findings, quality scores and recommendations for a completed project.
    """

    __tablename__ = "reports"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    strengths: Mapped[list | None] = mapped_column(JSON, nullable=True)
    risks: Mapped[list | None] = mapped_column(JSON, nullable=True)
    recommendations: Mapped[list | None] = mapped_column(JSON, nullable=True)
    quality_score: Mapped[float | None] = mapped_column(nullable=True)
    stage_durations: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="reports")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Report id={self.id!r} project_id={self.project_id!r}>"
