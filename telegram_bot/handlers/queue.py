"""Queue handler mixin — shows running, paused and recently finished workflow runs."""
from __future__ import annotations

from telegram_bot import keyboards
from telegram_bot.context import BotContext
from telegram_bot.formatters import escape_markdown, format_duration, status_emoji, truncate


class QueueHandlers:
    """Renders the live job queue: running, queued, paused, completed and failed runs."""

    def show_queue(self: BotContext, chat_id: int, message_id: int | None) -> None:
        """Render every tracked workflow run in this process, grouped by status."""
        from datetime import datetime, timezone

        runs = self.workflow_controller.list_runs()
        if not runs:
            text = "📋 *Queue*\n\nNo workflow runs tracked yet in this session\\."
            self._render(chat_id, message_id, text, keyboards.queue_menu())
            return

        lines = [f"📋 *Queue* \\({self.workflow_controller.active_count}/{self.workflow_controller.max_concurrency} active\\)", ""]
        for run in runs[:20]:
            elapsed = ""
            if run.started_at:
                end = run.finished_at or datetime.now(timezone.utc)
                elapsed = f" · {escape_markdown(format_duration((end - run.started_at).total_seconds()))}"
            lines.append(
                f"{status_emoji(run.status.value)} {escape_markdown(truncate(run.project_name, 35))}{elapsed}"
            )
            if run.error:
                lines.append(f"   └ {escape_markdown(truncate(run.error, 80))}")

        text = "\n".join(lines)
        self._render(chat_id, message_id, text, keyboards.queue_menu())
