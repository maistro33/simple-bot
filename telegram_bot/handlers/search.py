"""Search handler mixin — find projects by name or ID substring."""
from __future__ import annotations

from telebot.types import Message

from database.repositories.project_repository import ProjectRepository
from database.session import session_scope
from telegram_bot import keyboards
from telegram_bot.context import BotContext
from telegram_bot.formatters import escape_markdown
from telegram_bot.state import PendingInputKind


class SearchHandlers:
    """Handles the search prompt and renders matching projects as a tappable list."""

    def prompt_search(self: BotContext, chat_id: int, message_id: int | None) -> None:
        """Ask the user for a search query as their next free-text message."""
        self.chat_states.set_pending_input(chat_id, PendingInputKind.SEARCH_QUERY)
        text = "🔎 *Search Projects*\n\nSend a project name \\(or part of it\\) to search for\\."
        self._render(chat_id, message_id, text, keyboards.back_to_dashboard())

    def handle_search_query(self: BotContext, message: Message) -> None:
        """Consume the free-text search query and render matching projects."""
        chat_id = message.chat.id
        query = message.text.strip()
        self.chat_states.clear_pending_input(chat_id)

        repo = ProjectRepository()
        with session_scope() as session:
            matches = list(repo.search_by_name(session, query, limit=20))

        if not matches:
            text = f"🔎 No projects found matching *{escape_markdown(query)}*\\."
            self.bot.send_message(chat_id, text, parse_mode="MarkdownV2", reply_markup=keyboards.back_to_dashboard())
            return

        text = f"🔎 *Search Results* \\({len(matches)} found\\)"
        sent = self.bot.send_message(
            chat_id, text, parse_mode="MarkdownV2", reply_markup=keyboards.project_list(matches, 0, 1)
        )
        self.chat_states.set_panel_message(chat_id, sent.message_id)
