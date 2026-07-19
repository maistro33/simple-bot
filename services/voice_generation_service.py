"""
Voice Generation Service — wraps the ElevenLabs SDK for text-to-speech
voice-over generation, isolated behind a small interface so the Voice
Engine never imports the ElevenLabs SDK directly.
"""
from __future__ import annotations

from elevenlabs import VoiceSettings
from elevenlabs.client import ElevenLabs

from config import get_settings
from core.exceptions import AIServiceError, ConfigurationError, TransientServiceError
from core.logger import get_logger

logger = get_logger(__name__)


class VoiceGenerationService:
    """Thin, resilient wrapper around the ElevenLabs text-to-speech API."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._client: ElevenLabs | None = None

    def _get_client(self) -> ElevenLabs:
        """Lazily construct the ElevenLabs client, validating credentials first."""
        if not self._settings.has_elevenlabs_credentials:
            raise ConfigurationError(
                "ELEVENLABS_API_KEY is not configured. Set it in your .env file before generating voice-overs."
            )
        if self._client is None:
            self._client = ElevenLabs(api_key=self._settings.elevenlabs_api_key)
        return self._client

    def synthesize(
        self,
        text: str,
        voice_id: str | None = None,
        stability: float = 0.5,
        similarity_boost: float = 0.75,
    ) -> bytes:
        """
        Convert ``text`` into speech audio and return the raw MP3 bytes.

        Args:
            text: The full narration script to synthesise.
            voice_id: ElevenLabs voice ID; defaults to the configured default voice.
            stability: Voice stability parameter (0.0-1.0); lower is more expressive.
            similarity_boost: How closely to match the reference voice (0.0-1.0).

        Raises:
            AIServiceError: If synthesis fails for a non-retryable reason.
            TransientServiceError: On rate limits or transient network failures.
        """
        client = self._get_client()
        resolved_voice_id = voice_id or self._settings.elevenlabs_default_voice_id

        try:
            audio_stream = client.text_to_speech.convert(
                voice_id=resolved_voice_id,
                model_id=self._settings.elevenlabs_model,
                text=text,
                voice_settings=VoiceSettings(stability=stability, similarity_boost=similarity_boost),
            )
            audio_bytes = b"".join(chunk for chunk in audio_stream if chunk)
            if not audio_bytes:
                raise AIServiceError("ElevenLabs returned an empty audio stream.")
            return audio_bytes
        except AIServiceError:
            raise
        except Exception as exc:  # noqa: BLE001 - SDK raises assorted transport errors
            message = str(exc).lower()
            if "rate limit" in message or "timeout" in message or "connection" in message:
                raise TransientServiceError(f"ElevenLabs transient failure: {exc}") from exc
            raise AIServiceError(f"ElevenLabs synthesis failed: {exc}") from exc

    def list_available_voices(self) -> list[dict]:
        """Return the account's available voices as simple dicts (id, name, category)."""
        client = self._get_client()
        try:
            response = client.voices.get_all()
            return [
                {"voice_id": v.voice_id, "name": v.name, "category": getattr(v, "category", None)}
                for v in response.voices
            ]
        except Exception as exc:  # noqa: BLE001
            raise AIServiceError(f"Failed to list ElevenLabs voices: {exc}") from exc

    @staticmethod
    def estimate_duration_seconds(text: str, words_per_minute: int = 150) -> float:
        """Estimate spoken duration from word count, used before actual synthesis runs."""
        word_count = max(len(text.split()), 1)
        return round((word_count / words_per_minute) * 60, 2)
