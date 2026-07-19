"""SEO Engine — pipeline stage 14: titles, description, tags, hashtags, keywords."""
from __future__ import annotations

from typing import Any

from config.constants import WorkflowStage
from core.exceptions import StageExecutionError
from database.repositories import SeoRepository
from database.session import session_scope
from engines.base_engine import BaseEngine

_SEO_SYSTEM_PROMPT = """You are a YouTube Shorts / TikTok SEO specialist. Given a product profile, \
script, hook and target audience, generate a full discoverability package. Respond only with JSON \
matching this schema: {"titles": [str], "description": str, "tags": [str], "hashtags": [str], \
"primary_keyword": str, "secondary_keywords": [str], "pinned_comment": str}. Provide exactly 5 \
title variants under 60 characters each, a description under 500 characters with a natural keyword \
density, 15-20 tags, and 8-12 relevant hashtags (including the '#' symbol)."""


class SeoEngine(BaseEngine):
    """Generates the full SEO metadata package for a project's finished video."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._seo_repo = SeoRepository()

    def execute(self, project_id: str, context: dict[str, Any]) -> dict[str, Any]:
        """Generate and persist the SEO package for a project."""
        product_profile = context.get("product_profile")
        script = context.get("script")
        hook = context.get("hook")
        audience = context.get("audience")

        if not product_profile or not script:
            raise StageExecutionError(
                WorkflowStage.SEO_GENERATION.value, "Missing product_profile or script from prior stages.", recoverable=False
            )

        user_prompt = f"Product: {product_profile}\nScript: {script}\nHook: {hook}\nAudience: {audience}"
        try:
            seo_package = self.ai.generate_json(_SEO_SYSTEM_PROMPT, user_prompt, temperature=0.7)
        except Exception as exc:
            raise StageExecutionError(WorkflowStage.SEO_GENERATION.value, str(exc)) from exc

        with session_scope() as session:
            self._seo_repo.create(
                session,
                project_id=project_id,
                titles=seo_package.get("titles", []),
                description=seo_package.get("description", ""),
                tags=seo_package.get("tags", []),
                hashtags=seo_package.get("hashtags", []),
                primary_keyword=seo_package.get("primary_keyword"),
                secondary_keywords=seo_package.get("secondary_keywords"),
                pinned_comment=seo_package.get("pinned_comment"),
            )

        self.logger.info("SEO package generated for project {}", project_id)
        return {"seo": seo_package}
