"""Backup handler mixin — create, list and restore project disaster-recovery backups."""
from __future__ import annotations

from telegram_bot import keyboards
from telegram_bot.context import BotContext


class BackupHandlers:
    """Manages point-in-time backups for a project via the Telegram panel."""

    def show_backups(self: BotContext, chat_id: int, message_id: int | None, project_id: str) -> None:
        """List existing backups for a project with create/restore actions."""
        backups = self.backup_manager.list_backups(project_id)
        if not backups:
            text = "💾 *Backups*\n\nNo backups yet for this project\\."
        else:
            text = f"💾 *Backups* \\({len(backups)} found\\)"
        self._render(chat_id, message_id, text, keyboards.backups_menu(backups, project_id))

    def create_backup(self: BotContext, chat_id: int, message_id: int | None, project_id: str) -> None:
        """Create a fresh backup archive for a project and prune old ones."""
        path = self.backup_manager.create_backup(project_id)
        self.backup_manager.prune_old_backups(project_id)
        self.bot.send_message(chat_id, f"✅ Backup created: {path.name}")
        self.show_backups(chat_id, message_id, project_id)
