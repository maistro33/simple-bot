"""
Stock Image Service — free alternative to AI-generated images, backed by
the Pexels API. Used automatically by :class:`ImageGenerationService`
whenever ``PEXELS_API_KEY`` is configured, avoiding OpenAI image-generation
costs entirely while still producing relevant, professional-looking visuals.
"""
from __future__ import annotations

import os
import re

import requests

from core.exceptions import AIServiceError, ConfigurationError, TransientServiceError
from core.logger import get_logger

logger = get_logger(__name__)

_PEXELS_SEARCH_URL = "https://api.pexels.com/v1/search"
_STOPWORDS = {
    "a", "an", "the", "and", "or", "with", "of", "on", "in", "at", "to", "for",
    "photorealistic", "cinematic", "shot", "shallow", "depth", "field", "lens",
    "mm", "grade", "color", "lighting", "camera", "angle", "commercial",
    "product", "photography", "style", "reference", "close-up", "closeup",
}


class StockImageService:
    """Fetches a single relevant stock photo from Pexels for a given text prompt."""

    def __init__(self) -> None:
        self._api_key = os.environ.get("PEXELS_API_KEY", "").strip()

    @property
    def is_configured(self) -> bool:
        """Return True if a Pexels API key is available in the environment."""
        return bool(self._api_key)

    def search_and_download(self, prompt: str, aspect_ratio: str = "9:16") -> bytes:
        """
        Search Pexels for a photo matching ``prompt`` and return its raw
        image bytes at a high-resolution size closest to ``aspect_ratio``.
        """
        if not self.is_configured:
            raise ConfigurationError("PEXELS_API_KEY is not configured.")

        orientation = {"9:16": "portrait", "16:9": "landscape", "1:1": "square"}.get(
            aspect_ratio, "portrait"
        )
        query = self._extract_query(prompt)

        try:
            response = requests.get(
                _PEXELS_SEARCH_URL,
                headers={"Authorization": self._api_key},
                params={"query": query, "per_page": 5, "orientation": orientation},
                timeout=20,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.exceptions.Timeout as exc:
            raise TransientServiceError(f"Pexels search timed out: {exc}") from exc
        except requests.exceptions.ConnectionError as exc:
            raise TransientServiceError(f"Pexels connection error: {exc}") from exc
        except requests.exceptions.HTTPError as exc:
            raise AIServiceError(f"Pexels API error: {exc}") from exc

        photos = payload.get("photos", [])
        if not photos:
            broad_query = query.split(" ")[0] if query else "product"
            try:
                response = requests.get(
                    _PEXELS_SEARCH_URL,
                    headers={"Authorization": self._api_key},
                    params={"query": broad_query, "per_page": 5, "orientation": orientation},
                    timeout=20,
                )
                response.raise_for_status()
                photos = response.json().get("photos", [])
            except Exception:  # noqa: BLE001
                photos = []

        if not photos:
            raise AIServiceError(f"Pexels returned no photos for query: '{query}'")

        image_url = self._select_image_url(photos[0], aspect_ratio)
        try:
            image_response = requests.get(image_url, timeout=30)
            image_response.raise_for_status()
        except requests.exceptions.Timeout as exc:
            raise TransientServiceError(f"Pexels image download timed out: {exc}") from exc
        except requests.exceptions.ConnectionError as exc:
            raise TransientServiceError(f"Pexels image download connection error: {exc}") from exc

        logger.debug("Fetched Pexels stock image for query '{}'", query)
        return image_response.content

    @staticmethod
    def _select_image_url(photo: dict, aspect_ratio: str) -> str:
        """Pick the best pre-sized image variant from a Pexels photo object."""
        src = photo.get("src", {})
        preferred_key = {"9:16": "portrait", "16:9": "landscape", "1:1": "square"}.get(
            aspect_ratio, "large2x"
        )
        return src.get(preferred_key) or src.get("large2x") or src.get("original")

    @staticmethod
    def _extract_query(prompt: str) -> str:
        """
        Reduce a verbose cinematic AI prompt down to a short, Pexels-friendly
        keyword query by stripping punctuation, technical photography jargon,
        and keeping only the first handful of meaningful words.
        """
        cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", prompt.lower())
        words = [w for w in cleaned.split() if w not in _STOPWORDS and len(w) > 2]
        return " ".join(words[:6]) if words else "product"
