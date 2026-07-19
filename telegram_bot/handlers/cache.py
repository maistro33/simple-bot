"""Cache handler mixin — inspect and purge the persisted application cache."""
from __future__ import annotations

from core.cache_manager import CacheManager
from telegram_bot import keyboards
from telegram_bot.context import BotContext


class CacheHandlers:
    """Provides cache maintenance actions (expired-entry cleanup) from the panel."""

    def show_cache_menu(self: BotContext, chat_id: int, message_id: int | None) -> None:
        """Render the cache management menu."""
        text = (
            "🧹 *Cache*\n\n"
            "The application caches expensive lookups \\(competitor research, "
            "AI completions\\) with a time\\-to\\-live\\. Expired entries are swept "
            "automatically every hour, but you can force a cleanup now\\."
        )
        self._render(chat_id, message_id, text, keyboards.cache_menu())

    def clear_expired_cache(self: BotContext, chat_id: int, message_id: int | None) -> None:
        """Force an immediate purge of expired cache entries and report how many were removed."""
        removed = CacheManager.clear_all_expired()
        self.bot.send_message(chat_id, f"✅ Removed {removed} expired cache entr{'y' if removed == 1 else 'ies'}.")
        self.show_cache_menu(chat_id, message_id)
