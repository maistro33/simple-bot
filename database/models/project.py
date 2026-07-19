"""ORM model for the ``projects`` table — the central entity of the pipeline."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, Enum as SAEnum, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from config.constants import ProductCategory, WorkflowStage, WorkflowStatus
from database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from database.models.asset import Asset
    from database.models.export import Export
    from database.models.history import History
    from database.models.prompt import Prompt
    from database.models.report import Report
    from database.models.script import Script
    from database.models.seo import Seo
    from database.models.storyboard import Storyboard
    from database.models.subtitle import Subtitle
    from database.models.thumbnail import Thumbnail
    from database.models.voice import Voice


class Project(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Represents a single affiliate-content generation project.

    A project is created from raw input (a product URL, title, or free-form
    description) and progresses through every :class:`WorkflowStage` until
    it reaches :class:`WorkflowStatus.COMPLETED`. All other domain tables
    (scripts, storyboards, prompts, voices, ...) hang off a project via a
    foreign key, so deleting a project cascades through the whole tree.
    """

    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_input: Mapped[str] = mapped_column(Text, nullable=False)
    product_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    product_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    product_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_price: Mapped[str | None] = mapped_column(String(64), nullable=True)
    brand_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[ProductCategory] = mapped_column(
        SAEnum(ProductCategory), default=ProductCategory.UNKNOWN, nullable=False
    )
    platform: Mapped[str | None] = mapped_column(String(64), nullable=True)

    current_stage: Mapped[WorkflowStage] = mapped_column(
        SAEnum(WorkflowStage), default=WorkflowStage.PRODUCT_ANALYSIS, nullable=False
    )
    status: Mapped[WorkflowStatus] = mapped_column(
        SAEnum(WorkflowStatus), default=WorkflowStatus.PENDING, nullable=False
    )

    research_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    audience_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    strategy_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # --- Relationships (cascade delete-orphan: a project owns its children) --
    assets: Mapped[list["Asset"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    scripts: Mapped[list["Script"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    storyboards: Mapped[list["Storyboard"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    prompts: Mapped[list["Prompt"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    voices: Mapped[list["Voice"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    subtitles: Mapped[list["Subtitle"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    thumbnails: Mapped[list["Thumbnail"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    seo_entries: Mapped[list["Seo"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    reports: Mapped[list["Report"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    exports: Mapped[list["Export"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    history_entries: Mapped[list["History"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper only
        return f"<Project id={self.id!r} name={self.name!r} stage={self.current_stage}>"
