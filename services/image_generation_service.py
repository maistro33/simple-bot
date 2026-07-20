"""
Image Generation Service — the high-level interface engines use to turn
a cinematic prompt into a rendered image.

Automatically prefers the free StockImageService (Pexels) when
PEXELS_API_KEY is configured, avoiding OpenAI image-generation costs
entirely. Falls back to OpenAI's image model otherwise.
"""
from __future__ import annotations

from core.exceptions import AIServiceError
from core.logger import get_logger
from services.openai_service import OpenAIService
from services.stock_image_service import StockImageService

logger = get_logger(__name__)

_ASPECT_RATIO_TO_SIZE = {
    "9:16": "1024x1536",
    "16:9": "1536x1024",
    "1:1": "1024x1024",
}


class ImageGenerationService:
    """Provider-agnostic facade for generating still images from text prompts."""

    def __init__(
        self,
        openai_service: OpenAIService | None = None,
        stock_service: StockImageService | None = None,
    ) -> None:
        self._openai_service = openai_service or OpenAIService()
        self._stock_service = stock_service or StockImageService()

    def generate(self, prompt: str, aspect_ratio: str = "9:16", quality: str = "low") -> bytes:
        """
        Generate a single image for the given cinematic prompt.

        Prefers free Pexels stock photos when configured; falls back to
        OpenAI image generation (paid) otherwise.
        """
        if self._stock_service.is_configured:
            try:
                return self._stock_service.search_and_download(prompt, aspect_ratio=aspect_ratio)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Pexels stock image lookup failed ({}); falling back to OpenAI image generation.", exc
                )

        size = _ASPECT_RATIO_TO_SIZE.get(aspect_ratio, "1024x1536")
        logger.debug("Generating OpenAI image ({}, {}): {}", size, quality, prompt[:80])
        return self._openai_service.generate_image(prompt, size=size, quality=quality)

    def generate_thumbnail(self, prompt: str, quality: str = "medium") -> bytes:
        """Generate a 16:9 landscape thumbnail image (YouTube's preferred ratio)."""
        return self.generate(prompt, aspect_ratio="16:9", quality=quality)
