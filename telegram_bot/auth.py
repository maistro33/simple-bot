"""
Admin authentication for the Telegram control panel.

Every incoming message and callback is checked against a whitelist of
Telegram numeric user IDs (``TELEGRAM_ADMIN_IDS``) before any handler
runs. This is a single-tenant admin panel by design — anyone not on the
whitelist is silently ignored (no information leakage about the bot's
existence or capabilities).
"""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from telebot.types import CallbackQuery, Message

from config import get_settings
from core.logger import get_logger

logger = get_logger(__name__)


def is_authorized(user_id: int) -> bool:
    """Return True if ``user_id`` appears in the configured admin whitelist."""
    settings = get_settings()
    admin_ids = settings.telegram_admin_id_list
    if not admin_ids:
        # Fail closed: an empty whitelist means nobody is authorized, so a
        # misconfiguration never accidentally exposes the bot to everyone.
        logger.warning("TELEGRAM_ADMIN_IDS is empty — rejecting all users until configured.")
        return False
    return user_id in admin_ids


def admin_only(handler: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator for message/callback handlers that restricts execution to
    whitelisted admin user IDs. Accepts either a :class:`Message` or a
    :class:`CallbackQuery` as the first positional argument after ``self``.
    """

    @wraps(handler)
    def wrapper(self, update: "Message | CallbackQuery", *args, **kwargs) -> Any:
        user = update.from_user
        if user is None or not is_authorized(user.id):
            logger.warning(
                "Unauthorized access attempt from user_id={} username={}",
                getattr(user, "id", None),
                getattr(user, "username", None),
            )
            return None
        return handler(self, update, *args, **kwargs)

    return wrapper
