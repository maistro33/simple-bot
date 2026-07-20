"""Voice Engine — pipeline stage 11: synthesises the narrated voice-over track."""
from __future__ import annotations

from typing import Any

from config import get_settings
from config.constants import AssetType, WorkflowStage
from core.asset_manager import AssetManager
from core.exceptions import ConfigurationError, StageExecutionError
from database.repositories import VoiceRepository
from database.session import session_scope
from engines.base_engine import BaseEngine
from services.voice_generation_service import VoiceGenerationService


class VoiceEngine(BaseEngine):
    """Synthesises the full script into a single narrated voice-over audio file."""

    def __init__(self, *args, asset_manager: AssetManager | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._voice_repo = VoiceRepository()
        self._asset_manager = asset_manager or AssetManager()
        self._settings = get_settings()

    def execute(self, project_id: str, context: dict[str, Any]) -> dict[str, Any]:
        """Generate and persist the voice-over audio for the project's full script."""
        script = context.get("script")
        if not script or not script.get("full_script"):
            raise StageExecutionError(
                WorkflowStage.VOICE_GENERATION.value, "Missing full_script from prior stage.", recoverable=False
            )

        narration_text = script["full_script"]
        voice_service = VoiceGenerationService()
        estimated_duration = voice_service.estimate_duration_seconds(narration_text)

        file_path = None
        actual_duration = estimated_duration

        if not self._settings.has_elevenlabs_credentials:
            self.logger.warning(
                "ELEVENLABS_API_KEY not configured; skipping audio synthesis and recording a text-only voice entry."
            )
        else:
            try:
                audio_bytes = voice_service.synthesize(narration_text)
                asset = self._asset_manager.save_bytes(
                    project_id,
                    AssetType.AUDIO,
                    "voice_over.mp3",
                    audio_bytes,
                    source_stage=WorkflowStage.VOICE_GENERATION.value,
                )
                file_path = asset.file_path
            except Exception as exc:
                # Any ElevenLabs failure (payment required, rate limit, plan
                # restriction, etc.) degrades gracefully to a silent video
                # rather than failing the whole project — voice-over is a
                # nice-to-have, not a hard requirement for the pipeline.
                self.logger.warning(
                    "Voice synthesis failed ({}); continuing without audio for project {}.", exc, project_id
                )

        with session_scope() as session:
            self._voice_repo.create(
                session,
                project_id=project_id,
                source_text=narration_text,
                file_path=file_path,
                provider="elevenlabs",
                voice_id=self._settings.elevenlabs_default_voice_id,
                language="en",
                duration_seconds=actual_duration,
                stability=0.5,
                similarity_boost=0.75,
            )

        self.logger.info("Voice-over generated for project {} (~{}s)", project_id, actual_duration)
        return {"voice_over_path": file_path, "voice_duration_seconds": actual_duration}
