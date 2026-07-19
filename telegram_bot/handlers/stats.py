"""Statistics handler mixin — project counts, asset totals, and API usage/cost."""
from __future__ import annotations

from config.constants import AssetType
from database.repositories.domain_repositories import AssetRepository
from database.session import session_scope
from sqlalchemy import func, select
from telegram_bot import keyboards
from telegram_bot.formatters import escape_markdown, format_bytes, format_usd


class StatsHandlers:
    """Renders aggregate statistics: projects, generated media, storage and cost."""

    def show_stats(self, chat_id: int, message_id: int | None) -> None:
        """Render project counts, asset counts/storage, and cumulative API usage cost."""
        projects = self.project_manager.list_projects(limit=1000)

        asset_repo = AssetRepository()
        with session_scope() as session:
            total_size = session.execute(select(func.coalesce(func.sum(asset_repo.model.size_bytes), 0))).scalar_one()
            counts_by_type: dict[str, int] = {}
            for asset_type in AssetType:
                count = session.execute(
                    select(func.count()).select_from(asset_repo.model).where(asset_repo.model.asset_type == asset_type)
                ).scalar_one()
                if count:
                    counts_by_type[asset_type.value] = count

        usage = self.usage_tracker.get_summary()

        lines = [
            "📊 *Statistics*",
            "",
            f"📁 Projects: *{len(projects)}*",
            "",
            "*Generated Assets*",
        ]
        for asset_type, count in counts_by_type.items():
            lines.append(f"  • {escape_markdown(asset_type)}: *{count}*")
        lines.append(f"  • total storage: *{escape_markdown(format_bytes(total_size))}*")

        lines += [
            "",
            "*API Usage \\(lifetime\\)*",
            f"  • Text tokens: *{usage.total_prompt_tokens + usage.total_completion_tokens:,}*".replace(",", "\\,"),
            f"  • Images generated: *{usage.total_images}*",
            f"  • Voice characters: *{usage.total_characters:,}*".replace(",", "\\,"),
            f"  • Estimated cost: *{escape_markdown(format_usd(usage.total_estimated_cost_usd))}*",
        ]
        text = "\n".join(lines)
        self._render(chat_id, message_id, text, keyboards.back_to_dashboard())
