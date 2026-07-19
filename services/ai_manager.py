"""
AI Manager — the single façade every engine depends on for AI
capabilities. Internally composes :class:`OpenAIService`,
:class:`VoiceGenerationService`, :class:`ImageGenerationService` and
:class:`VideoGenerationService`, so engines never instantiate provider
SDKs themselves (Dependency Inversion + Facade patterns combined).
"""
from __future__ import annotations

from core.logger import get_logger
from services.image_generation_service import ImageGenerationService
from services.openai_service import OpenAIService
from services.video_generation_service import VideoGenerationService
from services.voice_generation_service import VoiceGenerationService

logger = get_logger(__name__)


class AIManager:
    """
    Central access point for every AI capability used across the pipeline:
    text/JSON generation, image generation, voice synthesis and video
    prompt/asset handling. Engines receive an ``AIManager`` instance via
    constructor injection, making them trivially unit-testable with a
    mock manager.
    """

    def __init__(self) -> None:
        self.openai = OpenAIService()
        self.voice = VoiceGenerationService()
        self.image = ImageGenerationService(openai_service=self.openai)
        self.video = VideoGenerationService(image_service=self.image)

    def generate_text(self, system_prompt: str, user_prompt: str, temperature: float = 0.8) -> str:
        """Delegate to the OpenAI service for a free-form text completion."""
        return self.openai.complete_text(system_prompt, user_prompt, temperature=temperature)

    def generate_json(self, system_prompt: str, user_prompt: str, temperature: float = 0.7) -> dict:
        """Delegate to the OpenAI service for a structured JSON completion."""
        return self.openai.complete_json(system_prompt, user_prompt, temperature=temperature)

    def generate_image(self, prompt: str, aspect_ratio: str = "9:16") -> bytes:
        """Delegate to the image generation service."""
        return self.image.generate(prompt, aspect_ratio=aspect_ratio)

    def synthesize_voice(self, text: str, voice_id: str | None = None) -> bytes:
        """Delegate to the voice generation service."""
        return self.voice.synthesize(text, voice_id=voice_id)


_ai_manager: AIManager | None = None


def get_ai_manager() -> AIManager:
    """Return the process-wide :class:`AIManager` singleton."""
    global _ai_manager
    if _ai_manager is None:
        _ai_manager = AIManager()
    return _ai_manager
