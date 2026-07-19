"""
Research Engine — covers pipeline stages 1-5: product analysis, category
detection, brand detection, competitor research and target audience
analysis. This is the foundation every downstream engine builds on.
"""
from __future__ import annotations

from typing import Any

from config.constants import ProductCategory, WorkflowStage
from core.exceptions import StageExecutionError
from database.repositories.project_repository import ProjectRepository
from database.session import session_scope
from engines.base_engine import BaseEngine
from plugins.plugin_registry import get_plugin_registry
from services.youtube_service import YouTubeService

_PRODUCT_ANALYSIS_SYSTEM_PROMPT = """You are a senior e-commerce product analyst specialising in \
affiliate marketing content. Given raw product input (a URL, title, or description), extract a \
clean, structured product profile. Infer sensible values when information is incomplete, but never \
fabricate specific facts like exact prices if not given — use null instead. Respond only with JSON \
matching this schema: {"product_title": str, "product_description": str, "key_features": [str], \
"price_range": str|null, "unique_selling_points": [str], "target_use_cases": [str]}"""

_CATEGORY_BRAND_SYSTEM_PROMPT = """You are a product taxonomy and brand-detection specialist. Given a \
product profile, classify it into exactly one of these categories: electronics, home_and_kitchen, \
beauty_and_personal_care, fashion_and_apparel, health_and_wellness, toys_and_games, \
sports_and_outdoors, pet_supplies, automotive, tools_and_home_improvement, office_and_productivity, \
baby_and_kids, gadgets_and_novelty, unknown. Also detect the most likely brand name if one is \
identifiable from the title/description, else null. Respond only with JSON: \
{"category": str, "brand_name": str|null, "category_confidence": float}"""

_AUDIENCE_SYSTEM_PROMPT = """You are a consumer market research analyst. Given a product profile and \
category, define the primary target audience for short-form video marketing. Respond only with JSON: \
{"primary_demographic": str, "age_range": str, "pain_points": [str], "desires": [str], \
"buying_triggers": [str], "platforms": [str], "content_tone_recommendation": str}"""

_COMPETITOR_SYNTHESIS_SYSTEM_PROMPT = """You are a competitive content strategist. Given a list of \
real competitor video titles (or, if none were found, the product profile alone), identify recurring \
angles, hooks and gaps in the market. Respond only with JSON: {"common_angles": [str], \
"overused_hooks": [str], "content_gaps": [str], "differentiation_opportunities": [str]}"""


class ResearchEngine(BaseEngine):
    """Performs full upstream research: product, category, brand, competitors, audience."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._project_repo = ProjectRepository()
        self._youtube = YouTubeService()
        self._plugin_registry = get_plugin_registry()

    def execute(self, project_id: str, context: dict[str, Any]) -> dict[str, Any]:
        """Run every research sub-stage in sequence and persist the results onto the project."""
        raw_input = context.get("raw_input")
        if not raw_input:
            raise StageExecutionError(
                WorkflowStage.PRODUCT_ANALYSIS.value, "No raw_input available in context.", recoverable=False
            )

        product_profile = self._analyze_product(raw_input)
        category, brand_name = self._detect_category_and_brand(product_profile)
        competitors = self._research_competitors(product_profile)
        audience = self._analyze_audience(product_profile, category)

        research_data = {
            "product_profile": product_profile,
            "competitors": competitors,
        }

        with session_scope() as session:
            self._project_repo.update(
                session,
                project_id,
                product_title=product_profile.get("product_title"),
                product_description=product_profile.get("product_description"),
                product_price=product_profile.get("price_range"),
                brand_name=brand_name,
                category=ProductCategory(category),
                research_data=research_data,
                audience_data=audience,
            )

        self.logger.info("Research complete for project {} (category={})", project_id, category)
        return {
            "product_profile": product_profile,
            "category": category,
            "brand_name": brand_name,
            "competitors": competitors,
            "audience": audience,
        }

    def _analyze_product(self, raw_input: str) -> dict[str, Any]:
        """
        Stage 1: extract a structured product profile from raw input.

        If ``raw_input`` looks like a URL matched by a registered platform
        plugin, the plugin's scraped data (title/price/description/brand)
        is fetched first and passed to the AI as grounding context so it
        doesn't have to hallucinate facts it could instead read directly.
        """
        analysis_input = raw_input
        if raw_input.strip().lower().startswith("http"):
            try:
                scraped = self._plugin_registry.fetch_product_data(raw_input.strip())
                if scraped is not None:
                    analysis_input = (
                        f"Source URL: {raw_input}\n"
                        f"Scraped title: {scraped.title}\n"
                        f"Scraped description: {scraped.description}\n"
                        f"Scraped price: {scraped.price} {scraped.currency or ''}\n"
                        f"Scraped brand: {scraped.brand}"
                    )
            except Exception as exc:
                self.logger.warning("Plugin scraping failed for '{}', falling back to raw input: {}", raw_input, exc)

        try:
            return self.ai.generate_json(_PRODUCT_ANALYSIS_SYSTEM_PROMPT, analysis_input, temperature=0.4)
        except Exception as exc:
            raise StageExecutionError(WorkflowStage.PRODUCT_ANALYSIS.value, str(exc)) from exc

    def _detect_category_and_brand(self, product_profile: dict[str, Any]) -> tuple[str, str | None]:
        """Stages 2 & 3: classify the product category and detect its brand."""
        try:
            result = self.ai.generate_json(
                _CATEGORY_BRAND_SYSTEM_PROMPT, str(product_profile), temperature=0.2
            )
            category = result.get("category", "unknown")
            if category not in [c.value for c in ProductCategory]:
                category = "unknown"
            return category, result.get("brand_name")
        except Exception as exc:
            raise StageExecutionError(WorkflowStage.CATEGORY_DETECTION.value, str(exc)) from exc

    def _research_competitors(self, product_profile: dict[str, Any]) -> dict[str, Any]:
        """Stage 4: gather real competitor videos (if YouTube API configured) and synthesise insights."""
        query = product_profile.get("product_title") or ""
        competitor_videos: list[dict[str, Any]] = []

        if self._youtube.is_configured and query:
            try:
                competitor_videos = self._youtube.search_competitor_videos(query, max_results=10)
            except Exception as exc:
                self.logger.warning("YouTube competitor search failed, continuing without it: {}", exc)

        titles = [v["title"] for v in competitor_videos if v.get("title")]
        synthesis_input = (
            f"Competitor video titles: {titles}" if titles
            else f"No competitor videos found. Product profile: {product_profile}"
        )

        try:
            synthesis = self.ai.generate_json(
                _COMPETITOR_SYNTHESIS_SYSTEM_PROMPT, synthesis_input, temperature=0.6
            )
        except Exception as exc:
            raise StageExecutionError(WorkflowStage.COMPETITOR_RESEARCH.value, str(exc)) from exc

        return {"videos": competitor_videos, "synthesis": synthesis}

    def _analyze_audience(self, product_profile: dict[str, Any], category: str) -> dict[str, Any]:
        """Stage 5: define the target audience for this product/category."""
        try:
            return self.ai.generate_json(
                _AUDIENCE_SYSTEM_PROMPT,
                f"Product: {product_profile}\nCategory: {category}",
                temperature=0.5,
            )
        except Exception as exc:
            raise StageExecutionError(WorkflowStage.AUDIENCE_ANALYSIS.value, str(exc)) from exc
