"""
OpenAI Service — the sole module that talks to the OpenAI SDK directly.

Wraps chat completions (including strict-JSON structured output) and
image generation behind a small, mockable interface so every engine
depends on this abstraction rather than the raw SDK, satisfying the
Dependency Inversion Principle and making unit testing trivial.
"""
from __future__ import annotations

import base64
import json
from typing import Any

from openai import APIConnectionError, APIStatusError, OpenAI, RateLimitError

from config import get_settings
from core.exceptions import AIServiceError, ConfigurationError, TransientServiceError
from core.logger import get_logger

logger = get_logger(__name__)


class OpenAIService:
    """
    Thin, resilient wrapper around the OpenAI Python SDK.

    Every public method translates SDK-level exceptions into the
    application's own exception hierarchy so callers (engines) never
    need to import ``openai`` directly.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._client: OpenAI | None = None

    def _get_client(self) -> OpenAI:
        """Lazily construct the OpenAI client, validating credentials first."""
        if not self._settings.has_openai_credentials:
            raise ConfigurationError(
                "OPENAI_API_KEY is not configured. Set it in your .env file before running the pipeline."
            )
        if self._client is None:
            self._client = OpenAI(
                api_key=self._settings.openai_api_key,
                organization=self._settings.openai_org_id or None,
            )
        return self._client

    def complete_text(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.8,
        max_tokens: int = 2000,
    ) -> str:
        """
        Request a free-form text completion.

        Args:
            system_prompt: The system-role instructions defining the AI's role.
            user_prompt: The user-role message containing the actual task.
            temperature: Sampling temperature (higher = more creative).
            max_tokens: Maximum tokens to generate in the response.

        Returns:
            The generated text content.

        Raises:
            TransientServiceError: On rate limits or connection failures (retryable).
            AIServiceError: On any other non-retryable API failure.
        """
        client = self._get_client()
        try:
            response = client.chat.completions.create(
                model=self._settings.openai_text_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = response.choices[0].message.content
            if not content:
                raise AIServiceError("OpenAI returned an empty completion.")
            return content.strip()
        except RateLimitError as exc:
            raise TransientServiceError(f"OpenAI rate limit hit: {exc}") from exc
        except APIConnectionError as exc:
            raise TransientServiceError(f"OpenAI connection error: {exc}") from exc
        except APIStatusError as exc:
            raise AIServiceError(f"OpenAI API returned status {exc.status_code}: {exc.message}") from exc

    def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 2500,
    ) -> dict[str, Any]:
        """
        Request a completion constrained to valid JSON output, parsed
        automatically. Engines use this for every structured-data stage
        (research findings, strategy plans, storyboard scenes, SEO packages).

        Raises:
            AIServiceError: If the model's response cannot be parsed as JSON.
        """
        client = self._get_client()
        json_instruction = (
            f"{system_prompt}\n\nYou MUST respond with a single valid JSON object only — "
            "no markdown code fences, no commentary, no leading or trailing text."
        )
        try:
            response = client.chat.completions.create(
                model=self._settings.openai_text_model,
                messages=[
                    {"role": "system", "content": json_instruction},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            if not content:
                raise AIServiceError("OpenAI returned an empty JSON completion.")
            return json.loads(content)
        except RateLimitError as exc:
            raise TransientServiceError(f"OpenAI rate limit hit: {exc}") from exc
        except APIConnectionError as exc:
            raise TransientServiceError(f"OpenAI connection error: {exc}") from exc
        except APIStatusError as exc:
            raise AIServiceError(f"OpenAI API returned status {exc.status_code}: {exc.message}") from exc
        except json.JSONDecodeError as exc:
            raise AIServiceError(f"OpenAI returned invalid JSON: {exc}") from exc

    def generate_image(
        self,
        prompt: str,
        size: str = "1024x1792",
        quality: str = "standard",
    ) -> bytes:
        """
        Generate a single image and return its raw PNG bytes.

        Args:
            prompt: The full descriptive image generation prompt.
            size: Output resolution string accepted by the configured model.
            quality: Quality tier accepted by the configured model.

        Raises:
            TransientServiceError: On rate limits or connection failures.
            AIServiceError: On any other failure, including missing image data.
        """
        client = self._get_client()
        try:
            response = client.images.generate(
                model=self._settings.openai_image_model,
                prompt=prompt,
                size=size,
                quality=quality,
                n=1,
            )
            image_item = response.data[0]
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
