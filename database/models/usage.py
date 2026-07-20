"""ORM model for the ``usage_events`` table — tracks every billable API call."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Integer, String

from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from database.models.project import Project


class UsageEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    A single billable API call (OpenAI text/JSON completion, OpenAI image
    generation, or ElevenLabs voice synthesis), recorded for cost tracking
    and the Telegram bot's statistics/usage dashboard.
    """

    __tablename__ = "usage_events"

    project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    image_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    character_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    project: Mapped["Project | None"] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<UsageEvent provider={self.provider!r} op={self.operation!r} cost=${self.estimated_cost_usd:.4f}>"
