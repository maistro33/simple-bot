"""
Usage Tracker — records every billable AI provider call (OpenAI text/JSON
completions, OpenAI image generations, ElevenLabs voice synthesis) and
estimates USD cost from published per-model pricing, so the Telegram
bot's statistics dashboard can show real, running cost totals.

Pricing tables are approximate published rates (USD) and are meant for
budgeting/estimation, not exact billing reconciliation — actual invoices
should always be treated as the source of truth.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select

from core.logger import get_logger
from database.models.usage import UsageEvent
from database.session import session_scope

logger = get_logger(__name__)

# USD per 1,000,000 tokens (prompt, completion), approximate published rates.
_OPENAI_TEXT_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4-turbo": (10.00, 30.00),
}
_DEFAULT_TEXT_PRICING = (2.50, 10.00)

# USD per generated image, approximate, by model+quality tier.
_OPENAI_IMAGE_PRICING: dict[str, float] = {
    "gpt-image-1": 0.04,
    "dall-e-3": 0.04,
    "dall-e-2": 0.02,
}
_DEFAULT_IMAGE_PRICE = 0.04

# USD per 1,000 characters synthesised (ElevenLabs approximate rate).
_ELEVENLABS_PRICE_PER_1K_CHARS = 0.18


@dataclass(slots=True)
class UsageSummary:
    """Aggregated usage totals returned by :meth:`UsageTracker.get_summary`."""

    total_events: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_images: int = 0
    total_characters: int = 0
    total_estimated_cost_usd: float = 0.0


class UsageTracker:
    """Records and aggregates AI provider usage for cost estimation and reporting."""

    def log_text_completion(
        self, model: str, prompt_tokens: int, completion_tokens: int, project_id: str | None = None
    ) -> float:
        """Record a text/JSON completion call and return its estimated USD cost."""
        prompt_rate, completion_rate = _OPENAI_TEXT_PRICING.get(model, _DEFAULT_TEXT_PRICING)
        cost = (prompt_tokens / 1_000_000) * prompt_rate + (completion_tokens / 1_000_000) * completion_rate

        with session_scope() as session:
            session.add(
                UsageEvent(
                    project_id=project_id,
                    provider="openai",
                    operation="text_completion",
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    estimated_cost_usd=cost,
                )
            )
        return cost

    def log_image_generation(self, model: str, count: int = 1, project_id: str | None = None) -> float:
        """Record an image generation call and return its estimated USD cost."""
        price = _OPENAI_IMAGE_PRICING.get(model, _DEFAULT_IMAGE_PRICE)
        cost = price * count

        with session_scope() as session:
            session.add(
                UsageEvent(
                    project_id=project_id,
                    provider="openai",
                    operation="image_generation",
                    model=model,
                    image_count=count,
                    estimated_cost_usd=cost,
                )
            )
        return cost

    def log_voice_synthesis(self, character_count: int, project_id: str | None = None) -> float:
        """Record a voice synthesis call and return its estimated USD cost."""
        cost = (character_count / 1000) * _ELEVENLABS_PRICE_PER_1K_CHARS

        with session_scope() as session:
            session.add(
                UsageEvent(
                    project_id=project_id,
                    provider="elevenlabs",
                    operation="voice_synthesis",
                    character_count=character_count,
                    estimated_cost_usd=cost,
                )
            )
        return cost

    def get_summary(self, project_id: str | None = None) -> UsageSummary:
        """
        Return aggregated usage totals, optionally scoped to a single project.

        Args:
            project_id: If given, only aggregate events for this project;
                otherwise aggregate across the entire application lifetime.
        """
        with session_scope() as session:
            stmt = select(
                func.count(UsageEvent.id),
                func.coalesce(func.sum(UsageEvent.prompt_tokens), 0),
                func.coalesce(func.sum(UsageEvent.completion_tokens), 0),
                func.coalesce(func.sum(UsageEvent.image_count), 0),
                func.coalesce(func.sum(UsageEvent.character_count), 0),
                func.coalesce(func.sum(UsageEvent.estimated_cost_usd), 0.0),
            )
            if project_id:
                stmt = stmt.where(UsageEvent.project_id == project_id)

            row = session.execute(stmt).one()
            return UsageSummary(
                total_events=row[0],
                total_prompt_tokens=row[1],
                total_completion_tokens=row[2],
                total_images=row[3],
                total_characters=row[4],
                total_estimated_cost_usd=round(row[5], 4),
            )


_usage_tracker: UsageTracker | None = None


def get_usage_tracker() -> UsageTracker:
    """Return the process-wide :class:`UsageTracker` singleton."""
    global _usage_tracker
    if _usage_tracker is None:
        _usage_tracker = UsageTracker()
    return _usage_tracker
