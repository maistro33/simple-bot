"""Handler mixins package — one module per feature area, combined in FactDropTelegramBot."""
from telegram_bot.handlers.assets import AssetHandlers
from telegram_bot.handlers.backups import BackupHandlers
from telegram_bot.handlers.cache import CacheHandlers
from telegram_bot.handlers.dashboard import DashboardHandlers
from telegram_bot.handlers.health import HealthHandlers
from telegram_bot.handlers.logs import LogHandlers
from telegram_bot.handlers.projects import ProjectHandlers
from telegram_bot.handlers.queue import QueueHandlers
from telegram_bot.handlers.search import SearchHandlers
from telegram_bot.handlers.settings import SettingsHandlers
from telegram_bot.handlers.stats import StatsHandlers
from telegram_bot.handlers.workflow import WorkflowHandlers

__all__ = [
    "AssetHandlers",
    "BackupHandlers",
    "CacheHandlers",
    "DashboardHandlers",
    "HealthHandlers",
    "LogHandlers",
    "ProjectHandlers",
    "QueueHandlers",
    "SearchHandlers",
    "SettingsHandlers",
    "StatsHandlers",
    "WorkflowHandlers",
]
