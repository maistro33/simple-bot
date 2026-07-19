"""Strategy Engine — pipeline stage 6: builds the full marketing strategy."""
from __future__ import annotations

from typing import Any

from config.constants import WorkflowStage
from core.exceptions import StageExecutionError
from database.repositories.project_repository import ProjectRepository
from database.session import session_scope
from engines.base_engine import BaseEngine

_STRATEGY_SYSTEM_PROMPT = """You are a senior affiliate marketing strategist for short-form video \
content (YouTube Shorts / TikTok). Given a product profile, its category, competitor research and \
target audience data, build a complete marketing strategy. Respond only with JSON matching this \
schema: {"core_angle": str, "emotional_driver": str, "content_pillars": [str], \
"recommended_hook_styles": [str], "recommended_video_length_seconds": int, \
"call_to_action_strategy": str, "posting_strategy": str, "differentiation_statement": str}"""


class StrategyEngine(BaseEngine):
    """Synthesises research + audience data into an actionable content strategy."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._project_repo = ProjectRepository()

    def execute(self, project_id: str, context: dict[str, Any]) -> dict[str, Any]:
        """Generate and persist the marketing strategy for a project."""
        product_profile = context.get("product_profile")
        competitors = context.get("competitors")
        audience = context.get("audience")

        if not product_profile or not audience:
            raise StageExecutionError(
                WorkflowStage.MARKETING_STRATEGY.value,
                "Missing product_profile or audience data from research stage.",
                recoverable=False,
            )

        user_prompt = (
            f"Product profile: {product_profile}\n"
            f"Competitor insights: {competitors}\n"
            f"Target audience: {audience}"
        )

        try:
            strategy = self.ai.generate_json(_STRATEGY_SYSTEM_PROMPT, user_prompt, temperature=0.7)
        except Exception as exc:
            raise StageExecutionError(WorkflowStage.MARKETING_STRATEGY.value, str(exc)) from exc

        with session_scope() as session:
            self._project_repo.update(session, project_id, strategy_data=strategy)

        self.logger.info("Strategy generated for project {}: angle='{}'", project_id, strategy.get("core_angle"))
        return {"strategy": strategy}
