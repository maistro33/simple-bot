"""ORM model for the ``exports`` table — bundled/exported project archives."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Enum as SAEnum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from config.constants import ExportFormat
from database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from database.models.project import Project


class Export(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Records a single export/bundle operation for a project, capturing
    the resulting archive location and format so it can be re-downloaded
    or audited later.
    """

    __tablename__ = "exports"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    export_format: Mapped[ExportFormat] = mapped_column(
        SAEnum(ExportFormat), default=ExportFormat.ZIP, nullable=False
    )
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    included_assets_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    project: Mapped["Project"] = relationship(back_populates="exports")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Export id={self.id!r} format={self.export_format}>"
