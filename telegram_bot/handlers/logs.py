"""Log handler mixin — displays recent persisted log records from the database."""
from __future__ import annotations

from database.repositories.domain_repositories import LogRepository
from database.session import session_scope
from telegram_bot import keyboards
from telegram_bot.formatters import escape_markdown, truncate

_LEVEL_EMOJI = {"INFO": "ℹ️", "WARNING": "⚠️", "ERROR": "❌", "DEBUG": "🐛", "CRITICAL": "🔥"}


class LogHandlers:
    """Renders the most recent structured log records for quick remote diagnostics."""

    def show_logs(self, chat_id: int, message_id: int | None, level_filter: str | None = None) -> None:
        """Render the most recent log entries, optionally filtered to a single level."""
        repo = LogRepository()
        with session_scope() as session:
            entries = list(repo.list_recent(session, limit=200))

        if level_filter:
            entries = [e for e in entries if e.level == level_filter]
        entries = entries[:15]

        if not entries:
            text = "📜 *Logs*\n\nNo log records found\\."
        else:
            lines = ["📜 *Recent Logs* \\(last 15\\)", ""]
            for entry in entries:
                emoji = _LEVEL_EMOJI.get(entry.level, "•")
                ts = entry.created_at.strftime("%m-%d %H:%M")
                lines.append(
                    f"{emoji} `{ts}` {escape_markdown(entry.source)}\n"
                    f"   {escape_markdown(truncate(entry.message, 100))}"
                )
            text = "\n".join(lines)

        self._render(chat_id, message_id, text, keyboards.back_to_dashboard())
