"""
Centralised, type-safe application settings.

All configuration is loaded from environment variables / a local ``.env``
file via ``pydantic-settings``. Nothing else in the codebase should call
``os.getenv`` directly — everything must flow through :func:`get_settings`
so that behaviour is consistent, validated and easily testable (tests can
monkeypatch environment variables and call ``get_settings.cache_clear()``).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from config.constants import (
    APP_ROOT,
    ASSETS_DIR,
    DATABASE_DIR,
    EXPORTS_DIR,
    LOGS_DIR,
    PROJECTS_DIR,
    VOICES_DIR,
)


class Settings(BaseSettings):
    """
    Strongly-typed application settings.

    Instances are immutable once constructed. Use :func:`get_settings` to
    obtain the process-wide singleton instance instead of instantiating
    this class directly.
    """

    model_config = SettingsConfigDict(
        env_file=str(APP_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application -----------------------------------------------------
    app_env: str = Field(default="development", alias="APP_ENV")
    app_debug: bool = Field(default=True, alias="APP_DEBUG")
    app_name: str = Field(default="Fact Drop AI Studio", alias="APP_NAME")
    app_timezone: str = Field(default="UTC", alias="APP_TIMEZONE")

    # --- Database ----------------------------------------------------------
    database_url: str = Field(
        default=f"sqlite:///{(DATABASE_DIR / 'fact_drop.db').as_posix()}",
        alias="DATABASE_URL",
    )
    database_echo: bool = Field(default=False, alias="DATABASE_ECHO")

    # --- Logging ----------------------------------------------------------
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_dir: Path = Field(default=LOGS_DIR, alias="LOG_DIR")
    log_rotation: str = Field(default="10 MB", alias="LOG_ROTATION")
    log_retention: str = Field(default="30 days", alias="LOG_RETENTION")

    # --- OpenAI -------------------------------------------------------------
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_text_model: str = Field(default="gpt-4o", alias="OPENAI_TEXT_MODEL")
    openai_image_model: str = Field(default="gpt-image-1", alias="OPENAI_IMAGE_MODEL")
    openai_org_id: str = Field(default="", alias="OPENAI_ORG_ID")

    # --- ElevenLabs ---------------------------------------------------------
    elevenlabs_api_key: str = Field(default="", alias="ELEVENLABS_API_KEY")
    elevenlabs_default_voice_id: str = Field(
        default="21m00Tcm4TlvDq8ikWAM", alias="ELEVENLABS_DEFAULT_VOICE_ID"
    )
    elevenlabs_model: str = Field(
        default="eleven_multilingual_v2", alias="ELEVENLABS_MODEL"
    )

    # --- YouTube --------------------------------------------------------------
    youtube_api_key: str = Field(default="", alias="YOUTUBE_API_KEY")
    youtube_client_id: str = Field(default="", alias="YOUTUBE_CLIENT_ID")
    youtube_client_secret: str = Field(default="", alias="YOUTUBE_CLIENT_SECRET")
    
    # --- Telegram Bot -----------------------------------------------------------
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_admin_ids: str = Field(default="", alias="TELEGRAM_ADMIN_IDS")


    # --- Video provider -------------------------------------------------------
    video_provider: str = Field(default="none", alias="VIDEO_PROVIDER")
    runway_api_key: str = Field(default="", alias="RUNWAY_API_KEY")
    pika_api_key: str = Field(default="", alias="PIKA_API_KEY")

    # --- Affiliate plugin credentials -----------------------------------------
    amazon_access_key: str = Field(default="", alias="AMAZON_ACCESS_KEY")
    amazon_secret_key: str = Field(default="", alias="AMAZON_SECRET_KEY")
    amazon_partner_tag: str = Field(default="", alias="AMAZON_PARTNER_TAG")
    aliexpress_app_key: str = Field(default="", alias="ALIEXPRESS_APP_KEY")
    aliexpress_app_secret: str = Field(default="", alias="ALIEXPRESS_APP_SECRET")
    ebay_app_id: str = Field(default="", alias="EBAY_APP_ID")
    shopify_api_key: str = Field(default="", alias="SHOPIFY_API_KEY")
    shopify_api_secret: str = Field(default="", alias="SHOPIFY_API_SECRET")

    # --- Runtime limits ---------------------------------------------------------
    max_concurrent_workflows: int = Field(default=3, alias="MAX_CONCURRENT_WORKFLOWS")
    http_timeout_seconds: int = Field(default=30, alias="HTTP_TIMEOUT_SECONDS")
    cache_ttl_seconds: int = Field(default=3600, alias="CACHE_TTL_SECONDS")

    # --- Derived filesystem paths (not env-configurable) -------------------------
    assets_dir: Path = ASSETS_DIR
    voices_dir: Path = VOICES_DIR
    projects_dir: Path = PROJECTS_DIR
    exports_dir: Path = EXPORTS_DIR

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        """Ensure the configured log level is one Loguru understands."""
        allowed = {"TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"}
        upper = value.upper()
        if upper not in allowed:
            raise ValueError(f"log_level must be one of {allowed}, got {value!r}")
        return upper

    @field_validator("video_provider")
    @classmethod
    def _validate_video_provider(cls, value: str) -> str:
        """Restrict video provider to known, supported backends."""
        allowed = {"none", "openai", "runway", "pika"}
        lower = value.lower()
        if lower not in allowed:
            raise ValueError(f"video_provider must be one of {allowed}, got {value!r}")
        return lower

    def ensure_directories(self) -> None:
        """Create every directory this application depends on, if missing."""
        for directory in (
            self.log_dir,
            self.assets_dir,
            self.voices_dir,
            self.projects_dir,
            self.exports_dir,
            DATABASE_DIR,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    @property
    def is_production(self) -> bool:
        """Return True when running under the production environment."""
        return self.app_env.lower() == "production"

    @property
    def has_openai_credentials(self) -> bool:
        """Return True if an OpenAI API key has been configured."""
        return bool(self.openai_api_key.strip())

    @property
    def has_elevenlabs_credentials(self) -> bool:
        """Return True if an ElevenLabs API key has been configured."""
        return bool(self.elevenlabs_api_key.strip())
        
    @property
    def has_telegram_credentials(self) -> bool:
        """Return True if a Telegram bot token has been configured."""
        return bool(self.telegram_bot_token.strip())

    @property
    def telegram_admin_id_list(self) -> list[int]:
        """Parse the comma-separated TELEGRAM_ADMIN_IDS into a list of integer user IDs."""
        if not self.telegram_admin_ids.strip():
            return []
        result: list[int] = []
        for chunk in self.telegram_admin_ids.split(","):
            chunk = chunk.strip()
            if chunk.isdigit() or (chunk.startswith("-") and chunk[1:].isdigit()):
                result.append(int(chunk))
        return result



@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return the process-wide singleton :class:`Settings` instance.

    The result is cached via ``lru_cache`` so repeated calls are cheap and
    every module in the application observes the exact same configuration.
    Tests that need to override environment variables should call
    ``get_settings.cache_clear()`` after monkeypatching the environment.
    """
    settings = Settings()
    settings.ensure_directories()
    return settings
