"""
Settings handler mixin — lets the admin adjust runtime-tunable behaviour
(model choice, temperature, voice/video providers, retries, concurrency)
directly from Telegram. Values are persisted via SettingsManager and
consulted live by the services layer (see ``OpenAIService._resolve_*``).
"""
from __future__ import annotations

from telebot.types import Message

from telegram_bot import keyboards
from telegram_bot.context import BotContext
from telegram_bot.formatters import escape_markdown
from telegram_bot.state import PendingInputKind

_PRESET_OPTIONS: dict[str, list[str]] = {
    "openai.text_model": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
    "openai.image_model": ["gpt-image-1", "dall-e-3", "dall-e-2"],
    "voice.default_provider": ["elevenlabs"],
    "video.default_provider": ["none", "openai", "runway", "pika"],
    "video.aspect_ratio": ["9:16", "16:9", "1:1"],
    "video.duration_seconds": ["30", "45", "60", "90"],
    "workflow.max_retries": ["1", "2", "3", "5"],
    "workflow.max_concurrency": ["1", "2", "3", "5"],
    "language": ["en", "tr"],
}

_FREE_TEXT_KEYS = {"openai.temperature"}


class SettingsHandlers:
    """Renders the settings menu and applies changes to persisted runtime settings."""

    def show_settings(self: BotContext, chat_id: int, message_id: int | None) -> None:
        """Render the settings menu with each key's current effective value."""
        current = self.settings_manager.get_all()
        text = "⚙️ *Settings*\n\nTap a setting to change it\\."
        self._render(chat_id, message_id, text, keyboards.settings_menu(current))

    def prompt_edit_setting(self: BotContext, chat_id: int, message_id: int | None, key: str) -> None:
        """Show preset options for a setting, or prompt free-text input for numeric ones."""
        if key in _PRESET_OPTIONS:
            current = self.settings_manager.get(key, "—")
            text = f"⚙️ *{escape_markdown(key)}*\n\nCurrent: `{escape_markdown(str(current))}`\n\nChoose a new value:"
            self._render(chat_id, message_id, text, keyboards.settings_value_options(key, _PRESET_OPTIONS[key]))
            return

        if key in _FREE_TEXT_KEYS:
            self.chat_states.set_pending_input(chat_id, PendingInputKind.SETTINGS_VALUE, {"key": key})
            current = self.settings_manager.get(key, "0.7")
            text = (
                f"⚙️ *{escape_markdown(key)}*\n\nCurrent: `{escape_markdown(str(current))}`\n\n"
                "Send a new numeric value \\(e\\.g\\. `0\\.7`\\)\\."
            )
            self._render(chat_id, message_id, text, keyboards.back_to_dashboard())
            return

        self._render(chat_id, message_id, "⚠️ Unknown setting\\.", keyboards.back_to_dashboard())

    def apply_setting(self: BotContext, chat_id: int, message_id: int | None, raw_arg: str) -> None:
        """Apply a ``key=value`` setting change selected from the preset options keyboard."""
        if "=" not in raw_arg:
            return
        key, value = raw_arg.split("=", 1)
        self.settings_manager.set(key, value)
        self.show_settings(chat_id, message_id)

    def handle_settings_free_text(self: BotContext, message: Message) -> None:
        """Consume a free-text settings value (e.g. temperature) sent after a prompt."""
        chat_id = message.chat.id
        state = self.chat_states.get(chat_id)
        key = state.pending_context.get("key")
        self.chat_states.clear_pending_input(chat_id)
        if not key:
            return

        try:
            value = float(message.text.strip())
        except ValueError:
            self.bot.send_message(chat_id, "⚠️ Please send a valid number.")
            return

        self.settings_manager.set(key, value)
        self.bot.send_message(chat_id, f"✅ {key} updated to {value}.")
        self.show_settings(chat_id, None)
