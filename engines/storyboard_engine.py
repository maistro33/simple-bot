"""Storyboard Engine — pipeline stage 9: breaks the script into timed visual scenes."""
from __future__ import annotations

from typing import Any

from config.constants import DEFAULT_STORYBOARD_SCENES, WorkflowStage
from core.exceptions import StageExecutionError
from database.repositories import StoryboardRepository
from database.session import session_scope
from engines.base_engine import BaseEngine

_STORYBOARD_SYSTEM_PROMPT = """You are a professional video director for short-form affiliate \
content. Given a full video script (with beats) and a product profile, break it down into a \
scene-by-scene storyboard of approximately {scene_count} scenes. Each scene must map to a portion \
of the narration, and specify concrete, filmable visual direction — not vague ideas. Respond only \
with JSON matching this schema: {{"scenes": [{{"scene_number": int, "scene_title": str, \
"narration_text": str, "visual_description": str, "camera_angle": str, "duration_seconds": number, \
"on_screen_text": str|null, "transition": str, "sound_effect": str|null}}]}}"""


class StoryboardEngine(BaseEngine):
    """Converts the finished script into a concrete, filmable scene-by-scene storyboard."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._storyboard_repo = StoryboardRepository()

    def execute(self, project_id: str, context: dict[str, Any]) -> dict[str, Any]:
        """Generate and persist the full ordered storyboard for a project."""
        script = context.get("script")
        product_profile = context.get("product_profile")

        if not script:
            raise StageExecutionError(
                WorkflowStage.STORYBOARD_GENERATION.value, "Missing script from prior stage.", recoverable=False
            )

        beat_count = len(script.get("beats", [])) or DEFAULT_STORYBOARD_SCENES
        scene_count = max(beat_count, DEFAULT_STORYBOARD_SCENES // 2)
        system_prompt = _STORYBOARD_SYSTEM_PROMPT.format(scene_count=scene_count)
        user_prompt = f"Script: {script}\nProduct: {product_profile}"

        try:
            result = self.ai.generate_json(system_prompt, user_prompt, temperature=0.6)
        except Exception as exc:
            raise StageExecutionError(WorkflowStage.STORYBOARD_GENERATION.value, str(exc)) from exc

        scenes = result.get("scenes", [])
        if not scenes:
            raise StageExecutionError(WorkflowStage.STORYBOARD_GENERATION.value, "AI returned zero scenes.")

        with session_scope() as session:
            existing = self._storyboard_repo.list_by_project(session, project_id)
            for row in existing:
                session.delete(row)
            session.flush()

            for scene in scenes:
                self._storyboard_repo.create(
                    session,
                    project_id=project_id,
                    scene_number=scene["scene_number"],
                    scene_title=scene["scene_title"],
                    narration_text=scene["narration_text"],
                    visual_description=scene["visual_description"],
                    camera_angle=scene.get("camera_angle"),
                    duration_seconds=scene.get("duration_seconds", 5),
                    on_screen_text=scene.get("on_screen_text"),
                    transition=scene.get("transition"),
                    sound_effect=scene.get("sound_effect"),
                )

        self.logger.info("Storyboard generated for project {} ({} scenes)", project_id, len(scenes))
        return {"storyboard": scenes}
