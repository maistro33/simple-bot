"""Asset handler mixin — browse and download a project's generated files via Telegram."""
from __future__ import annotations

from pathlib import Path

from config.constants import AssetType
from database.repositories.domain_repositories import AssetRepository
from database.session import session_scope
from telegram_bot import keyboards
from telegram_bot.context import BotContext
from telegram_bot.formatters import escape_markdown


class AssetHandlers:
    """Lists a project's generated assets and streams the chosen file back via Telegram."""

    def show_asset_list(self: BotContext, chat_id: int, message_id: int | None, project_id: str) -> None:
        """Render every asset registered for a project as a tappable list."""
        assets = self.asset_manager.list_assets(project_id)
        if not assets:
            text = "🗂️ *Assets*\n\nNo assets generated yet for this project\\."
        else:
            text = f"🗂️ *Assets* \\({len(assets)} files\\)\n\nTap a file to receive it in this chat\\."
        self._render(chat_id, message_id, text, keyboards.asset_list(assets, project_id))

    def send_asset(self: BotContext, chat_id: int, asset_id: str) -> None:
        """Send the requested asset's file directly into the chat, choosing the right media type."""
        asset_repo = AssetRepository()
        with session_scope() as session:
            asset = asset_repo.get_by_id(session, asset_id)
            if asset is None:
                self.bot.send_message(chat_id, "⚠️ Asset not found — it may have been deleted.")
                return
            file_path = Path(asset.file_path)
            asset_type = asset.asset_type
            file_name = asset.file_name

        if not file_path.exists():
            self.bot.send_message(chat_id, f"⚠️ File missing on disk: {file_name}")
            return

        caption = f"📎 {file_name}"
        with file_path.open("rb") as fh:
            if asset_type == AssetType.IMAGE or asset_type == AssetType.THUMBNAIL:
                self.bot.send_photo(chat_id, fh, caption=caption)
            elif asset_type == AssetType.AUDIO:
                self.bot.send_audio(chat_id, fh, caption=caption)
            elif asset_type == AssetType.VIDEO:
                self.bot.send_video(chat_id, fh, caption=caption)
            else:
                self.bot.send_document(chat_id, fh, caption=caption)
