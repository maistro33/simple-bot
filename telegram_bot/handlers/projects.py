"""Project handler mixin — list, detail, create, delete, undo and history views."""
from __future__ import annotations

from telebot.types import Message

from core.exceptions import ProjectNotFoundError
from database.repositories.domain_repositories import HistoryRepository
from database.session import session_scope
from telegram_bot import keyboards
from telegram_bot.context import BotContext
from telegram_bot.formatters import (
    escape_markdown,
    format_duration,
    stage_emoji,
    stage_label,
    status_emoji,
    truncate,
)
from telegram_bot.state import PendingInputKind

_PAGE_SIZE = 8


class ProjectHandlers:
    """Handles every project-scoped view and action in the control panel."""

    def show_project_list(self: BotContext, chat_id: int, message_id: int | None, page: int = 0) -> None:
        """Render a paginated list of all projects."""
        all_projects = self.project_manager.list_projects(limit=500)
        total_pages = max(1, (len(all_projects) + _PAGE_SIZE - 1) // _PAGE_SIZE)
        page = max(0, min(page, total_pages - 1))
        page_items = all_projects[page * _PAGE_SIZE : (page + 1) * _PAGE_SIZE]

        if not all_projects:
            text = "📁 *Projects*\n\nNo projects yet\\. Tap ➕ to create your first one\\."
        else:
            text = f"📁 *Projects* \\(page {page + 1}/{total_pages}\\)\n\nTap a project to view details\\."

        self._render(chat_id, message_id, text, keyboards.project_list(page_items, page, total_pages))

    def show_project_detail(self: BotContext, chat_id: int, message_id: int | None, project_id: str) -> None:
        """Render full detail for a single project, including live workflow status."""
        try:
            project = self.project_manager.get_project(project_id)
        except ProjectNotFoundError:
            self._render(chat_id, message_id, "⚠️ Project not found\\. It may have been deleted\\.", keyboards.back_to_dashboard())
            return

        run = self.workflow_controller.get_run(project_id)
        progress_line = ""
        if run is not None and run.status.value == "running":
            from telegram_bot.formatters import progress_bar, stage_progress_fraction

            fraction = stage_progress_fraction(project.current_stage)
            progress_line = f"\n{progress_bar(fraction)}\n"

        lines = [
            f"{status_emoji(project.status)} *{escape_markdown(project.name)}*",
            "",
            f"🆔 `{project.id}`",
            f"{stage_emoji(project.current_stage)} Stage: *{escape_markdown(stage_label(project.current_stage))}*",
            f"Status: *{escape_markdown(project.status.value)}*",
            progress_line,
            f"🏷️ Category: {escape_markdown(project.category.value)}",
            f"🏢 Brand: {escape_markdown(project.brand_name or 'N/A')}",
            f"📅 Created: {escape_markdown(project.created_at.strftime('%Y-%m-%d %H:%M'))}",
        ]
        if project.error_message:
            lines.append(f"\n❌ Last error: {escape_markdown(truncate(project.error_message, 200))}")

        text = "\n".join(lines)
        self._render(chat_id, message_id, text, keyboards.project_detail(project))

    def prompt_new_project(self: BotContext, chat_id: int, message_id: int | None) -> None:
        """Ask the user to send a product URL, title, or description as their next message."""
        self.chat_states.set_pending_input(chat_id, PendingInputKind.NEW_PROJECT_INPUT)
        text = (
            "➕ *New Project*\n\n"
            "Send me a product URL \\(Amazon, AliExpress, eBay, Shopify, etc\\.\\), "
            "or just type a product title/description\\.\n\n"
            "I'll research it, write the script, generate the video and SEO package automatically\\."
        )
        self._render(chat_id, message_id, text, keyboards.back_to_dashboard())

    def handle_new_project_text(self: BotContext, message: Message) -> None:
        """Consume the free-text message sent after ``prompt_new_project`` was shown."""
        chat_id = message.chat.id
        raw_input = message.text.strip()
        self.chat_states.clear_pending_input(chat_id)
        self.chat_states.get(chat_id).pending_context = {"raw_input": raw_input}

        text = (
            "📝 Ready to create a project from:\n\n"
            f"_{escape_markdown(truncate(raw_input, 300))}_\n\n"
            "What would you like to do?"
        )
        sent = self.bot.send_message(chat_id, text, parse_mode="MarkdownV2", reply_markup=keyboards.project_creation_confirm())
        self.chat_states.set_panel_message(chat_id, sent.message_id)

    def confirm_create_project(self: BotContext, chat_id: int, message_id: int | None, mode: str) -> None:
        """Actually create the project row, optionally launching the pipeline immediately."""
        raw_input = self.chat_states.get(chat_id).pending_context.get("raw_input")
        if not raw_input:
            self._render(chat_id, message_id, "⚠️ No pending project input found\\. Please try again\\.", keyboards.back_to_dashboard())
            return

        project = self.project_manager.create_project(raw_input)
        self.project_chat_map[project.id] = chat_id

        if mode == "start":
            self.workflow_controller.start(project.id, project.name)
            text = f"🚀 Project *{escape_markdown(project.name)}* created and started\\!"
        else:
            text = f"💾 Project *{escape_markdown(project.name)}* created as a draft\\."

        self.show_project_detail(chat_id, message_id, project.id)
        self.bot.send_message(chat_id, text, parse_mode="MarkdownV2")

    def delete_project_confirm(self: BotContext, chat_id: int, message_id: int | None, project_id: str) -> None:
        """Show a Yes/No confirmation before permanently deleting a project."""
        text = "🗑️ *Delete this project permanently\\?*\n\nThis also removes all generated assets\\. This cannot be undone\\."
        self._render(chat_id, message_id, text, keyboards.confirm_delete(project_id))

    def delete_project(self: BotContext, chat_id: int, message_id: int | None, project_id: str) -> None:
        """Permanently delete a project and its assets, then return to the project list."""
        self.project_manager.delete_project(project_id)
        self.project_chat_map.pop(project_id, None)
        self.show_project_list(chat_id, message_id, page=0)

    def undo_project(self: BotContext, chat_id: int, message_id: int | None, project_id: str) -> None:
        """Revert a project to its previous history snapshot and re-render the detail view."""
        snapshot = self.project_manager.undo_last_action(project_id)
        if snapshot is None:
            self.bot.send_message(chat_id, "⚠️ Nothing to undo for this project.")
        self.show_project_detail(chat_id, message_id, project_id)

    def export_project(self: BotContext, chat_id: int, project_id: str) -> None:
        """Build the project's full export bundle and send the resulting ZIP into the chat."""
        self.bot.send_message(chat_id, "📦 Building export bundle\\.\\.\\.", parse_mode="MarkdownV2")
        try:
            export_path = self.export_manager.export_project(project_id)
        except Exception as exc:  # noqa: BLE001
            self.bot.send_message(chat_id, f"❌ Export failed: {exc}")
            return

        with open(export_path, "rb") as fh:
            self.bot.send_document(chat_id, fh, caption=f"📦 {export_path.name}")

    def show_project_history(self: BotContext, chat_id: int, message_id: int | None, project_id: str) -> None:
        """Render the version history (undo log) for a project."""
        history_repo = HistoryRepository()
        with session_scope() as session:
            entries = history_repo.list_by_project(session, project_id)
            rows = [
                (e.sequence_number, e.action, e.stage, e.is_reverted, e.created_at)
                for e in sorted(entries, key=lambda e: e.sequence_number, reverse=True)[:15]
            ]

        if not rows:
            text = "🕐 *History*\n\nNo history recorded yet for this project\\."
        else:
            lines = ["🕐 *Project History* \\(last 15\\)", ""]
            for seq, action, stage, reverted, created_at in rows:
                mark = "↩️" if reverted else "•"
                lines.append(
                    f"{mark} \\#{seq} {escape_markdown(action)} → {escape_markdown(stage)} "
                    f"_{escape_markdown(created_at.strftime('%m\\-%d %H:%M'))}_"
                )
            text = "\n".join(lines)

        project = self.project_manager.get_project(project_id)
        self._render(chat_id, message_id, text, keyboards.project_detail(project))
