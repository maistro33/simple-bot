"""
Runtime, user-adjustable settings manager (distinct from the ``.env``
environment configuration handled by :mod:`config.settings`).

Backed by the ``settings`` database table so preferences like the
active UI theme or default export format persist across restarts.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select

from core.logger import get_logger
from database.models.setting import Setting
from database.session import session_scope

logger = get_logger(__name__)

_DEFAULTS: dict[str, Any] = {
    "ui.theme": "dark",
    "export.default_format": "zip",
    "voice.default_provider": "elevenlabs",
    "video.default_provider": "none",
    "workflow.auto_advance": True,
    "workflow.max_retries": 3,
}


class SettingsManager:
    """Provides typed get/set access to persisted, user-adjustable settings."""

    def get(self, key: str, default: Any = None) -> Any:
        """Return the stored value for ``key``, falling back to built-in defaults."""
        with session_scope() as session:
            stmt = select(Setting).where(Setting.key == key)
            row = session.execute(stmt).scalars().first()
            if row is not None:
                return row.value
        if key in _DEFAULTS:
            return _DEFAULTS[key]
        return default

    def set(self, key: str, value: Any, category: str = "general", description: str | None = None) -> None:
        """Create or update a persisted setting."""
        with session_scope() as session:
            stmt = select(Setting).where(Setting.key == key)
            row = session.execute(stmt).scalars().first()
            if row is None:
                session.add(Setting(key=key, value=value, category=category, description=description))
            else:
                row.value = value
                if description:
                    row.description = description
        logger.debug("Setting '{}' updated.", key)

    def get_all(self, category: str | None = None) -> dict[str, Any]:
        """Return every persisted setting, optionally filtered by category, merged with defaults."""
        merged = dict(_DEFAULTS)
        with session_scope() as session:
            stmt = select(Setting)
            if category:
                stmt = stmt.where(Setting.category == category)
            for row in session.execute(stmt).scalars().all():
                merged[row.key] = row.value
        return merged

    def reset(self, key: str) -> None:
        """Delete a persisted override, causing subsequent reads to fall back to defaults."""
        with session_scope() as session:
            stmt = select(Setting).where(Setting.key == key)
            row = session.execute(stmt).scalars().first()
            if row is not None:
                session.delete(row)
                logger.info("Setting '{}' reset to default.", key)


_settings_manager: SettingsManager | None = None


def get_settings_manager() -> SettingsManager:
    """Return the process-wide :class:`SettingsManager` singleton."""
    global _settings_manager
    if _settings_manager is None:
        _settings_manager = SettingsManager()
    return _settings_manager
