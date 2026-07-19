"""
Workflow handler mixin — start/pause/resume/retry actions plus the
EventBus subscribers that push live per-stage progress into the same
Telegram panel message for the chat that owns each project.
"""
from __future__ import annotations

from core.event_bus import Event
from core.exceptions import ProjectNotFoundError
from telegram_bot import keyboards
from telegram_bot.context import BotContext
from telegram_bot.formatters import (
    escape_markdown,
    progress_bar,
    stage_emoji,
    stage_label,
    stage_progress_fraction,
)


class WorkflowHandlers:
    """Handles workflow start/pause/resume/retry and renders live progress updates."""

    def start_workflow(self: BotContext, chat_id: int, message_id: int | None, project_id: str) -> None:
        """Start a pending project's pipeline from stage 1."""
        try:
            project = self.project_manager.get_project(project_id)
        except ProjectNotFoundError:
            self._render(chat_id, message_id, "⚠️ Project not found\\.", keyboards.back_to_dashboard())
            return

        self.project_chat_map[project_id] = chat_id
        self.workflow_controller.start(project_id, project.name, resume=False)
        self._render_progress(chat_id, message_id, project_id, project.name, "product_analysis", "started")

    def pause_workflow(self: BotContext, chat_id: int, message_id: int | None, project_id: str) -> None:
        """Request a running project to pause before its next stage."""
        ok = self.workflow_controller.pause(project_id)
        note = "⏸️ Pause requested — will stop before the next stage\\." if ok else "⚠️ This project isn't currently running\\."
        self.bot.send_message(chat_id, note, parse_mode="MarkdownV2")
        self.show_project_detail(chat_id, message_id, project_id)

    def resume_workflow(self: BotContext, chat_id: int, message_id: int | None, project_id: str) -> None:
        """Resume a paused project from its last completed stage."""
        project = self.project_manager.get_project(project_id)
        self.project_chat_map[project_id] = chat_id
        self.workflow_controller.resume(project_id, project.name)
        self._render_progress(chat_id, message_id, project_id, project.name, project.current_stage.value, "started")

    def retry_workflow(self: BotContext, chat_id: int, message_id: int | None, project_id: str) -> None:
        """Retry a failed project from its last completed stage."""
        project = self.project_manager.get_project(project_id)
        self.project_chat_map[project_id] = chat_id
        self.workflow_controller.retry(project_id, project.name)
        self._render_progress(chat_id, message_id, project_id, project.name, project.current_stage.value, "started")

    def _render_progress(
        self: BotContext,
        chat_id: int,
        message_id: int | None,
        project_id: str,
        project_name: str,
        stage_value: str,
        phase: str,
    ) -> None:
        """Render a live progress panel for a project's currently executing stage."""
        from config.constants import WorkflowStage

        try:
            stage = WorkflowStage(stage_value)
        except ValueError:
            stage = WorkflowStage.PRODUCT_ANALYSIS

        fraction = stage_progress_fraction(stage)
        phase_label = {"started": "Running", "completed": "Done", "failed": "Failed"}.get(phase, phase)

        lines = [
            f"⚙️ *{escape_markdown(project_name)}*",
            "",
            f"{stage_emoji(stage)} {escape_markdown(stage_label(stage))} — {escape_markdown(phase_label)}",
            escape_markdown(progress_bar(fraction)),
        ]
        text = "\n".join(lines)
        self._render(chat_id, message_id, text, keyboards.workflow_progress_keyboard(project_id))

    # --- EventBus subscribers, registered once in FactDropTelegramBot.__init__ ---

    def on_stage_started(self: BotContext, event: Event) -> None:
        """EventBus handler for ``stage.started`` — updates the owning chat's panel."""
        self._handle_progress_event(event, phase="started")

    def on_stage_completed(self: BotContext, event: Event) -> None:
        """EventBus handler for ``stage.completed`` — updates the owning chat's panel."""
        self._handle_progress_event(event, phase="completed")

    def on_workflow_completed(self: BotContext, event: Event) -> None:
        """EventBus handler for ``workflow.completed`` — sends a final success message."""
        project_id = event.payload.get("project_id")
        chat_id = self.project_chat_map.get(project_id)
        if chat_id is None or project_id is None:
            return
        try:
            project = self.project_manager.get_project(project_id)
        except ProjectNotFoundError:
            return
        text = (
            f"✅ *{escape_markdown(project.name)}* finished successfully\\!\n\n"
            "Use 📦 Export or 🗂️ Assets to download the results\\."
        )
        self.bot.send_message(chat_id, text, parse_mode="MarkdownV2", reply_markup=keyboards.project_detail(project))

    def on_workflow_failed(self: BotContext, event: Event) -> None:
        """EventBus handler for ``workflow.failed`` — sends a failure notice with retry option."""
        project_id = event.payload.get("project_id")
        chat_id = self.project_chat_map.get(project_id)
        if chat_id is None or project_id is None:
            return
        error = event.payload.get("error", "Unknown error")
        try:
            project = self.project_manager.get_project(project_id)
        except ProjectNotFoundError:
            return
        from telegram_bot.formatters import truncate

        text = (
            f"❌ *{escape_markdown(project.name)}* failed\\.\n\n"
            f"_{escape_markdown(truncate(error, 300))}_\n\n"
            "Tap 🔄 Retry to resume from the last completed stage\\."
        )
        self.bot.send_message(chat_id, text, parse_mode="MarkdownV2", reply_markup=keyboards.project_detail(project))

    def on_workflow_paused(self: BotContext, event: Event) -> None:
        """EventBus handler for ``workflow.paused`` — confirms the pause took effect."""
        project_id = event.payload.get("project_id")
        chat_id = self.project_chat_map.get(project_id)
        if chat_id is None or project_id is None:
            return
        try:
            project = self.project_manager.get_project(project_id)
        except ProjectNotFoundError:
            return
        text = f"⏸️ *{escape_markdown(project.name)}* paused\\. Tap ▶️ Resume to continue anytime\\."
        self.bot.send_message(chat_id, text, parse_mode="MarkdownV2", reply_markup=keyboards.project_detail(project))

    def _handle_progress_event(self: BotContext, event: Event, phase: str) -> None:
        """Shared logic for per-stage progress events: locate the chat and re-render its panel."""
        project_id = event.payload.get("project_id")
        stage_value = event.payload.get("stage")
        if project_id is None or stage_value is None:
            return
        chat_id = self.project_chat_map.get(project_id)
        if chat_id is None:
            return

        state = self.chat_states.get(chat_id)
        try:
            project = self.project_manager.get_project(project_id)
        except ProjectNotFoundError:
            return
        self._render_progress(chat_id, state.panel_message_id, project_id, project.name, stage_value, phase)
