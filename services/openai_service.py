"""
OpenAI Service — text/JSON completions and image generation.

Text completions automatically prefer Groq (free, OpenAI-compatible API)
when ``GROQ_API_KEY`` is configured, avoiding OpenAI text costs entirely.
Image generation always uses real OpenAI as a fallback for when Pexels
(the primary, free image source) has no match.
"""
from __future__ import annotations

import base64
import json
import os
from typing import Any

from openai import APIConnectionError, APIStatusError, OpenAI, RateLimitError

from config import get_settings
from core.exceptions import AIServiceError, ConfigurationError, TransientServiceError
from core.logger import get_logger
from core.settings_manager import get_settings_manager
from core.usage_tracker import get_usage_tracker

logger = get_logger(__name__)

_GROQ_BASE_URL = "https://api.groq.com/openai/v1"
_GROQ_DEFAULT_MODEL = "llama-3.3-70b-versatile"


class OpenAIService:
    """Thin, resilient wrapper around OpenAI-compatible chat/image APIs (OpenAI or Groq)."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._text_client: OpenAI | None = None
        self._image_client: OpenAI | None = None
        self._usage_tracker = get_usage_tracker()
        self._settings_manager = get_settings_manager()
        self._groq_api_key = os.environ.get("GROQ_API_KEY", "").strip()

    @property
    def _using_groq(self) -> bool:
        """Return True if text completions should be routed through Groq (free)."""
        return bool(self._groq_api_key)

    def _resolve_text_model(self) -> str:
        """Return the active text model, preferring a runtime override from SettingsManager."""
        override = self._settings_manager.get("openai.text_model")
        if override:
            return override
        return _GROQ_DEFAULT_MODEL if self._using_groq else self._settings.openai_text_model

    def _resolve_image_model(self) -> str:
        """Return the active image model, preferring a runtime override from SettingsManager."""
        override = self._settings_manager.get("openai.image_model")
        return override or self._settings.openai_image_model

    def _resolve_temperature(self, requested: float) -> float:
        """Return the temperature to use, honouring a global Settings override if set."""
        override = self._settings_manager.get("openai.temperature")
        if override is None:
            return requested
        try:
            return float(override)
        except (TypeError, ValueError):
            return requested

    def _get_text_client(self) -> OpenAI:
        """Lazily construct the text-completion client: Groq if configured, else real OpenAI."""
        if self._using_groq:
            if self._text_client is None:
                self._text_client = OpenAI(api_key=self._groq_api_key, base_url=_GROQ_BASE_URL)
            return self._text_client

        if not self._settings.has_openai_credentials:
            raise ConfigurationError(
                "Neither GROQ_API_KEY nor OPENAI_API_KEY is configured. Set at least one before running the pipeline."
            )
        if self._text_client is None:
            self._text_client = OpenAI(
                api_key=self._settings.openai_api_key,
                organization=self._settings.openai_org_id or None,
            )
        return self._text_client

    def _get_image_client(self) -> OpenAI:
        """Lazily construct the image-generation client (always real OpenAI)."""
        if not self._settings.has_openai_credentials:
            raise ConfigurationError(
                "OPENAI_API_KEY is not configured. It is required for image generation "
                "whenever Pexels (PEXELS_API_KEY) has no matching stock photo."
            )
        if self._image_client is None:
            self._image_client = OpenAI(
                api_key=self._settings.openai_api_key,
                organization=self._settings.openai_org_id or None,
            )
        return self._image_client

    def complete_text(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.8,
        max_tokens: int = 2000,
    ) -> str:
        """Request a free-form text completion (via Groq if configured, else OpenAI)."""
        client = self._get_text_client()
        model = self._resolve_text_model()
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self._resolve_temperature(temperature),
                max_tokens=max_tokens,
            )
            content = response.choices[0].message.content
            if not content:
                raise AIServiceError("Text completion returned empty content.")
            if response.usage and not self._using_groq:
                self._usage_tracker.log_text_completion(
                    model, response.usage.prompt_tokens, response.usage.completion_tokens
                )
            return content.strip()
        except RateLimitError as exc:
            raise TransientServiceError(f"Text completion rate limit hit: {exc}") from exc
        except APIConnectionError as exc:
            raise TransientServiceError(f"Text completion connection error: {exc}") from exc
        except APIStatusError as exc:
            raise AIServiceError(f"Text completion API returned status {exc.status_code}: {exc.message}") from exc

    def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 2500,
    ) -> dict[str, Any]:
        """Request a completion constrained to valid JSON output, parsed automatically."""
        client = self._get_text_client()
        model = self._resolve_text_model()
        json_instruction = (
            f"{system_prompt}\n\nYou MUST respond with a single valid JSON object only — "
            "no markdown code fences, no commentary, no leading or trailing text."
        )
        try:
            response_format = {"type": "json_object"}
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": json_instruction},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self._resolve_temperature(temperature),
                max_tokens=max_tokens,
                response_format=response_format,
            )
            content = response.choices[0].message.content
            if not content:
                raise AIServiceError("JSON completion returned empty content.")
            if response.usage and not self._using_groq:
                self._usage_tracker.log_text_completion(
                    model, response.usage.prompt_tokens, response.usage.completion_tokens
                )
            return json.loads(content)
        except RateLimitError as exc:
            raise TransientServiceError(f"JSON completion rate limit hit: {exc}") from exc
        except APIConnectionError as exc:
            raise TransientServiceError(f"JSON completion connection error: {exc}") from exc
        except APIStatusError as exc:
            raise AIServiceError(f"JSON completion API returned status {exc.status_code}: {exc.message}") from exc
        except json.JSONDecodeError as exc:
            raise AIServiceError(f"Model returned invalid JSON: {exc}") from exc

    def generate_image(
        self,
        prompt: str,
        size: str = "1024x1536",
        quality: str = "low",
    ) -> bytes:
        """Generate a single image via real OpenAI and return its raw PNG bytes."""
        client = self._get_image_client()
        model = self._resolve_image_model()
        try:
            response = client.images.generate(
                model=model,
                prompt=prompt,
                size=size,
                quality=quality,
                n=1,
            )
            image_item = response.data[0]
            self._usage_tracker.log_image_generation(model, count=1)
            if getattr(image_item, "b64_json", None):
                return base64.b64decode(image_item.b64_json)
            if getattr(image_item, "url", None):
                import requests

                image_response = requests.get(image_item.url, timeout=self._settings.http_timeout_seconds)
                image_response.raise_for_status()
                return image_response.content
            raise AIServiceError("OpenAI image response contained neither b64_json nor url.")
        except RateLimitError as exc:
            raise TransientServiceError(f"OpenAI image rate limit hit: {exc}") from exc
        except APIConnectionError as exc:
            raise TransientServiceError(f"OpenAI image connection error: {exc}") from exc
        except APIStatusError as exc:
            raise AIServiceError(f"OpenAI image API returned status {exc.status_code}: {exc.message}") from exc
