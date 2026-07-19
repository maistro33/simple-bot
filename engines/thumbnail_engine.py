"""Thumbnail Engine — pipeline stage 13: thumbnail concepts and rendered images."""
from __future__ import annotations

from typing import Any

from config.constants import AssetType, WorkflowStage
from core.asset_manager import AssetManager
from core.exceptions import StageExecutionError
from database.repositories import ThumbnailRepository
from database.session import session_scope
from engines.base_engine import BaseEngine
from services.image_generation_service import ImageGenerationService

_THUMBNAIL_CONCEPT_SYSTEM_PROMPT = """You are a YouTube thumbnail strategist known for high-CTR \
designs. Given a product profile, hook and marketing strategy, propose exactly 3 distinct thumbnail \
concepts optimised for click-through-rate. Each needs a short punchy headline (max 5 words, ALL \
CAPS friendly), a clear visual focal point, a color scheme, and the primary emotion it should evoke. \
Respond only with JSON: {"concepts": [{"concept_title": str, "headline_text": str, \
"visual_description": str, "color_scheme": str, "emotion": str, "image_prompt": str}]}"""


class ThumbnailEngine(BaseEngine):
    """Generates multiple thumbnail concepts and renders the top concept as an image."""

    def __init__(self, *args, asset_manager: AssetManager | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._thumbnail_repo = ThumbnailRepository()
        self._asset_manager = asset_manager or AssetManager()
        self._image_service = ImageGenerationService()

    def execute(self, project_id: str, context: dict[str, Any]) -> dict[str, Any]:
        """Generate thumbnail concepts, render the top one, and persist all of them."""
        product_profile = context.get("product_profile")
        hook = context.get("hook")
        strategy = context.get("strategy")

        if not product_profile:
            raise StageExecutionError(
                WorkflowStage.THUMBNAIL_GENERATION.value, "Missing product_profile from prior stage.", recoverable=False
            )

        user_prompt = f"Product: {product_profile}\nHook: {hook}\nStrategy: {strategy}"
        try:
            result = self.ai.generate_json(_THUMBNAIL_CONCEPT_SYSTEM_PROMPT, user_prompt, temperature=0.8)
        except Exception as exc:
            raise StageExecutionError(WorkflowStage.THUMBNAIL_GENERATION.value, str(exc)) from exc

        concepts = result.get("concepts", [])
        if not concepts:
            raise StageExecutionError(WorkflowStage.THUMBNAIL_GENERATION.value, "AI returned zero thumbnail concepts.")

        persisted_concepts = []
        with session_scope() as session:
            existing = self._thumbnail_repo.list_by_project(session, project_id)
            for row in existing:
                session.delete(row)
            session.flush()

            for index, concept in enumerate(concepts):
                file_path = None
                if index == 0:
                    try:
                        image_bytes = self._image_service.generate_thumbnail(concept["image_prompt"])
                        asset = self._asset_manager.save_bytes(
                            project_id,
                            AssetType.THUMBNAIL,
                            "thumbnail_primary.png",
                            image_bytes,
                            source_stage=WorkflowStage.THUMBNAIL_GENERATION.value,
                        )
                        file_path = asset.file_path
                    except Exception as exc:
                        self.logger.warning("Thumbnail image render failed, keeping concept text-only: {}", exc)

                self._thumbnail_repo.create(
                    session,
                    project_id=project_id,
                    concept_title=concept["concept_title"],
                    headline_text=concept["headline_text"],
                    visual_description=concept["visual_description"],
                    color_scheme=concept.get("color_scheme"),
                    emotion=concept.get("emotion"),
                    file_path=file_path,
                    is_selected=(index == 0),
                )
                persisted_concepts.append({**concept, "file_path": file_path, "is_selected": index == 0})

        self.logger.info("Generated {} thumbnail concepts for project {}", len(concepts), project_id)
        return {"thumbnails": persisted_concepts}
