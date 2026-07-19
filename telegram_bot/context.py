"""
Shared runtime context for the Telegram bot: every handler mixin reads
its dependencies (managers, controller, trackers) off ``self``, all
constructed once in :class:`telegram_bot.bot.FactDropTelegramBot.__init__`.
This module just documents/type-hints that shared surface area in one
place instead of scattering constructor wiring across every mixin.
"""
from __future__ import annotations

from typing import Protocol

from telebot import TeleBot

from core.asset_manager import AssetManager
from core.backup_manager import BackupManager
from core.cache_manager import CacheManager
from core.event_bus import EventBus
from core.export_manager import ExportManager
from core.project_manager import ProjectManager
from core.settings_manager import SettingsManager
from core.usage_tracker import UsageTracker
from core.workflow_controller import WorkflowController
from telegram_bot.state import ChatStateStore


class BotContext(Protocol):
    """
    Structural type describing every attribute handler mixins expect to
    find on ``self`` once mixed into :class:`FactDropTelegramBot`.
    """

    bot: TeleBot
    project_manager: ProjectManager
    workflow_controller: WorkflowController
    asset_manager: AssetManager
    backup_manager: BackupManager
    export_manager: ExportManager
    cache_manager: CacheManager
    settings_manager: SettingsManager
    usage_tracker: UsageTracker
    event_bus: EventBus
    chat_states: ChatStateStore
    project_chat_map: dict[str, int]
