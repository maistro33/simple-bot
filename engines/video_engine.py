"""
Video Engine — renders every scene's visual (via the configured video
provider) and assembles them, together with the voice-over track and
burned-in subtitles, into the final MP4 deliverable. Runs just before
export, since the finished video is the centrepiece of the export bundle.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from config import get_settings
from config.constants import AssetType, WorkflowStage
from core.asset_manager import AssetManager
from core.exceptions import StageExecutionError
from engines.base_engine import BaseEngine
from services.video_generation_service import VideoGenerationService


class VideoEngine(BaseEngine):
    """Renders per-scene visuals and assembles the final vertical video file."""

    def __init__(self, *args, asset_manager: AssetManager | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._asset_manager = asset_manager or AssetManager()
        self._video_service = VideoGenerationService()
        self._settings = get_settings()

    def execute(self, project_id: str, context: dict[str, Any]) -> dict[str, Any]:
        """Render scene visuals and assemble them into the final video, if prompts are available."""
        prompts = context.get("prompts")
        storyboard = context.get("storyboard")

        if not prompts or not storyboard:
            self.logger.warning(
                "No prompts/storyboard available for project {}; skipping final video assembly.", project_id
            )
            return {"final_video_path": None}

        scene_paths: list[Path] = []
        scene_durations: list[float] = []

        try:
            for scene, prompt in zip(storyboard, prompts):
                image_bytes = self._video_service.generate_scene_visual(prompt["positive_prompt"])
                asset = self._asset_manager.save_bytes(
                    project_id,
                    AssetType.IMAGE,
                    f"scene_{scene['scene_number']:02d}.png",
                    image_bytes,
                    source_stage=WorkflowStage.PROMPT_GENERATION.value,
                )
                scene_paths.append(Path(asset.file_path))
                scene_durations.append(float(scene.get("duration_seconds", 5)))
        except Exception as exc:
            raise StageExecutionError("video_assembly", f"Scene visual generation failed: {exc}") from exc

        voice_over_path = context.get("voice_over_path")
        subtitle_cues = context.get("subtitle_cues")
        output_path = self._settings.assets_dir / project_id / "video" / "final_video.mp4"

        try:
            final_path = self._video_service.assemble_video(
                scene_image_paths=scene_paths,
                scene_durations=scene_durations,
                voice_over_path=Path(voice_over_path) if voice_over_path else None,
                subtitle_cues=subtitle_cues,
                output_path=output_path,
            )
        except Exception as exc:
            raise StageExecutionError("video_assembly", str(exc)) from exc

        asset = self._asset_manager.copy_external_file(
            project_id, AssetType.VIDEO, final_path, source_stage="video_assembly"
        )

        self.logger.info("Final video assembled for project {} at {}", project_id, asset.file_path)
        return {"final_video_path": asset.file_path}
