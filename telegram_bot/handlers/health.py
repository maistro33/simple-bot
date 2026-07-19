"""System health handler mixin — CPU, RAM and disk usage via psutil."""
from __future__ import annotations

import psutil

from config import get_settings
from telegram_bot import keyboards
from telegram_bot.context import BotContext
from telegram_bot.formatters import escape_markdown, format_bytes, progress_bar


class HealthHandlers:
    """Renders live host resource usage — useful when this runs as a Railway worker."""

    def show_health(self: BotContext, chat_id: int, message_id: int | None) -> None:
        """Render current CPU, RAM and disk usage for the host running the bot."""
        cpu_percent = psutil.cpu_percent(interval=0.3)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage(str(get_settings().assets_dir.anchor or "/"))

        lines = [
            "🩺 *System Health*",
            "",
            f"🖥️ CPU: {escape_markdown(progress_bar(cpu_percent / 100))}",
            f"🧠 RAM: {escape_markdown(progress_bar(memory.percent / 100))}",
            f"   {escape_markdown(format_bytes(memory.used))} / {escape_markdown(format_bytes(memory.total))}",
            f"💽 Disk: {escape_markdown(progress_bar(disk.percent / 100))}",
            f"   {escape_markdown(format_bytes(disk.used))} / {escape_markdown(format_bytes(disk.total))}",
            "",
            f"🧵 Workflow workers: *{self.workflow_controller.active_count}/{self.workflow_controller.max_concurrency}*",
        ]
        text = "\n".join(lines)
        self._render(chat_id, message_id, text, keyboards.back_to_dashboard())
