"""
Image Generation Service — the high-level interface engines use to turn
a cinematic prompt into a rendered image, currently backed by
:class:`services.openai_service.OpenAIService` but designed so an
additional provider (Stability, Midjourney API, etc.) could be plugged
in behind the same interface (Strategy pattern) without touching engine code.
"""
from __future__ import annotations

from core.logger import get_logger
from services.openai_service import OpenAIService

logger = get_logger(__name__)

_ASPECT_RATIO_TO_SIZE = {
    "9:16": "1024x1792",
    "16:9": "1792x1024",
    "1:1": "1024x1024",
}


class ImageGenerationService:
    """Provider-agnostic facade for generating still images from text prompts."""

    def __init__(self, openai_service: OpenAIService | None = None) -> None:
        self._openai_service = openai_service or OpenAIService()

    def generate(self, prompt: str, aspect_ratio: str = "9:16", quality: str = "standard") -> bytes:
        """
        Generate a single image for the given cinematic prompt.

        Args:
            prompt: The full positive image prompt, including style/lighting cues.
            aspect_ratio: One of ``"9:16"`` (vertical/Shorts), ``"16:9"`` or ``"1:1"``.
            quality: Provider-specific quality tier (``"standard"`` or ``"hd"``).

        Returns:
            Raw PNG image bytes.
        """
        size = _ASPECT_RATIO_TO_SIZE.get(aspect_ratio, "1024x1792")
        logger.debug("Generating image ({}, {}): {}", size, quality, prompt[:80])
        return self._openai_service.generate_image(prompt, size=size, quality=quality)

    def generate_thumbnail(self, prompt: str, quality: str = "hd") -> bytes:
        """Generate a 16:9 landscape thumbnail image (YouTube's preferred ratio)."""
        return self.generate(prompt, aspect_ratio="16:9", quality=quality)
