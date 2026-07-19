"""Dashboard handler mixin — the root panel showing overall system status."""
from __future__ import annotations

from config import get_settings
from config.constants import WorkflowStatus
from database.session import session_scope
from telegram_bot import keyboards
from telegram_bot.context import BotContext
from telegram_bot.formatters import escape_markdown, format_usd


class DashboardHandlers:
    """Renders the main dashboard panel with live system status counts."""

    def show_dashboard(self: BotContext, chat_id: int, message_id: int | None = None) -> None:
        """Render the root dashboard: project counts by status, active runs, and usage cost."""
        projects = self.project_manager.list_projects(limit=500)
        counts: dict[str, int] = {}
        for p in projects:
            counts[p.status.value] = counts.get(p.status.value, 0) + 1

        active_runs = self.workflow_controller.active_count
        max_conc = self.workflow_controller.max_concurrency
        usage = self.usage_tracker.get_summary()
        settings = get_settings()

        lines = [
            "🏭 *FACT DROP AI STUDIO*",
            "_Remote Control Panel_",
            "",
            f"📁 Total projects: *{len(projects)}*",
            f"⚙️ Running: *{counts.get(WorkflowStatus.RUNNING.value, 0)}*  "
            f"⏸️ Paused: *{counts.get(WorkflowStatus.PAUSED.value, 0)}*",
            f"✅ Completed: *{counts.get(WorkflowStatus.COMPLETED.value, 0)}*  "
            f"❌ Failed: *{counts.get(WorkflowStatus.FAILED.value, 0)}*",
            "",
            f"🧵 Active workers: *{active_runs}/{max_conc}*",
            f"💰 Total est\\. cost: *{escape_markdown(format_usd(usage.total_estimated_cost_usd))}*",
            "",
            f"🔑 OpenAI: {'✅' if settings.has_openai_credentials else '❌ not configured'}",
            f"🎙️ ElevenLabs: {'✅' if settings.has_elevenlabs_credentials else '❌ not configured'}",
        ]
        text = "\n".join(lines)
        self._render(chat_id, message_id, text, keyboards.main_menu())
