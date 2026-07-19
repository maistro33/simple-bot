"""Prompt Engine — pipeline stage 10: turns each storyboard scene into a cinematic AI prompt."""
from __future__ import annotations

from typing import Any

from config import get_settings
from config.constants import WorkflowStage
from core.exceptions import StageExecutionError
from database.repositories import PromptRepository
from database.session import session_scope
from engines.base_engine import BaseEngine

_PROMPT_SYSTEM_PROMPT = """You are a cinematic AI image/video prompt engineer specialising in \
photorealistic product marketing visuals. Given one storyboard scene and the product profile, write \
a single highly-detailed positive prompt suitable for a text-to-image/video model (subject, setting, \
lighting, camera lens/angle, mood, color grade) plus a negative prompt to avoid common artifacts. \
Respond only with JSON: {"positive_prompt": str, "negative_prompt": str, "lighting": str, \
"camera_motion": str, "style_reference": str}"""


class PromptEngine(BaseEngine):
    """Generates one cinematic AI generation prompt per storyboard scene."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._prompt_repo = PromptRepository()
        self._settings = get_settings()

    def execute(self, project_id: str, context: dict[str, Any]) -> dict[str, Any]:
        """Generate and persist a cinematic prompt for every scene in the storyboard."""
        storyboard = context.get("storyboard")
        product_profile = context.get("product_profile")

        if not storyboard:
            raise StageExecutionError(
                WorkflowStage.PROMPT_GENERATION.value, "Missing storyboard from prior stage.", recoverable=False
            )

        prompts: list[dict[str, Any]] = []
        with session_scope() as session:
            existing = self._prompt_repo.list_by_project(session, project_id)
            for row in existing:
                session.delete(row)
            session.flush()

            for scene in storyboard:
                generated = self._generate_scene_prompt(scene, product_profile)
                prompts.append({**generated, "scene_number": scene["scene_number"]})
                self._prompt_repo.create(
                    session,
                    project_id=project_id,
                    scene_number=scene["scene_number"],
                    prompt_type="image" if self._settings.video_provider in ("none", "openai") else "video",
                    positive_prompt=generated["positive_prompt"],
                    negative_prompt=generated.get("negative_prompt"),
                    style_reference=generated.get("style_reference"),
                    aspect_ratio="9:16",
                    camera_motion=generated.get("camera_motion"),
                    lighting=generated.get("lighting"),
                    provider=self._settings.video_provider,
                )

        self.logger.info("Generated {} cinematic prompts for project {}", len(prompts), project_id)
        return {"prompts": prompts}

    def _generate_scene_prompt(self, scene: dict, product_profile: dict | None) -> dict[str, Any]:
        """Generate a single scene's cinematic prompt via the AI manager."""
        user_prompt = f"Scene: {scene}\nProduct: {product_profile}"
        try:
            return self.ai.generate_json(_PROMPT_SYSTEM_PROMPT, user_prompt, temperature=0.65)
        except Exception as exc:
            raise StageExecutionError(WorkflowStage.PROMPT_GENERATION.value, str(exc)) from exc
