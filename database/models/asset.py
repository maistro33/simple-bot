"""ORM model for the ``assets`` table — tracks every generated binary/file asset."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, Enum as SAEnum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from config.constants import AssetType
from database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from database.models.project import Project


class Asset(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    A single physical file (image, audio clip, video, subtitle file, ...)
    produced somewhere in the pipeline and persisted to disk under the
    ``assets/`` (or ``voices/``, ``exports/``) directory tree.
    """

    __tablename__ = "assets"

    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_type: Mapped[AssetType] = mapped_column(SAEnum(AssetType), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    extra_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    project: Mapped["Project"] = relationship(back_populates="assets")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Asset id={self.id!r} type={self.asset_type} path={self.file_path!r}>"
