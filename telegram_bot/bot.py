"""
FactDropTelegramBot — the complete Telegram remote control panel for
FACT DROP AI STUDIO.

Composed via multiple inheritance from the handler mixins in
``telegram_bot.handlers`` so each feature area (projects, workflow,
queue, logs, stats, settings, assets, backups, cache, health, search)
lives in its own small, focused module while sharing one set of
dependencies (managers, controller, trackers) constructed once here.
"""
from __future__ import annotations

import telebot
from telebot.apihelper import ApiTelegramException
from telebot.types import CallbackQuery, InlineKeyboardMarkup, Message

from config import get_settings
from core.asset_manager import AssetManager
from core.backup_manager import BackupManager
from core.cache_manager import CacheManager
from core.event_bus import get_event_bus
from core.exceptions import ConfigurationError
from core.export_manager import ExportManager
from core.logger import get_logger
from core.project_manager import get_project_manager
from core.settings_manager import get_settings_manager
from core.usage_tracker import get_usage_tracker
from core.workflow_controller import get_workflow_controller
from telegram_bot.auth import is_authorized
from telegram_bot.callback_data import CallbackData
from telegram_bot.handlers import (
    AssetHandlers,
    BackupHandlers,
    CacheHandlers,
    DashboardHandlers,
    HealthHandlers,
    LogHandlers,
    ProjectHandlers,
    QueueHandlers,
    SearchHandlers,
    SettingsHandlers,
    StatsHandlers,
    WorkflowHandlers,
)
from telegram_bot.state import PendingInputKind, get_chat_state_store

logger = get_logger(__name__)


class FactDropTelegramBot(
    DashboardHandlers,
    ProjectHandlers,
    WorkflowHandlers,
    QueueHandlers,
    LogHandlers,
    StatsHandlers,
    SettingsHandlers,
    AssetHandlers,
    BackupHandlers,
    CacheHandlers,
    HealthHandlers,
    SearchHandlers,
):
    """
    The full Telegram control panel bot.

    Construct one instance, call :meth:`run` to start polling. Every
    feature is reachable purely through InlineKeyboard taps — the only
    free-text input the bot ever asks for is a product URL/description,
    a search query, or a numeric settings value.
    """

    def __init__(self, token: str | None = None) -> None:
        settings = get_settings()
        resolved_token = token or settings.telegram_bot_token
        if not resolved_token:
            raise ConfigurationError(
                "TELEGRAM_BOT_TOKEN is not configured. Set it in your .env (or Railway variables) first."
            )

        self.bot = telebot.TeleBot(resolved_token, parse_mode=None, threaded=True)

        # --- Shared managers, identical instances the CLI/Application use ---
        self.project_manager = get_project_manager()
        self.workflow_controller = get_workflow_controller()
        self.asset_manager = AssetManager()
        self.backup_manager = BackupManager()
        self.export_manager = ExportManager()
        self.cache_manager = CacheManager()
        self.settings_manager = get_settings_manager()
        self.usage_tracker = get_usage_tracker()
        self.event_bus = get_event_bus()
        self.chat_states = get_chat_state_store()

        # Maps an in-flight project_id to the chat that launched it, so
        # EventBus progress events know where to deliver updates.
        self.project_chat_map: dict[str, int] = {}

        self._register_handlers()
        self._register_event_subscriptions()
        logger.info("FactDropTelegramBot initialised.")

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def _register_handlers(self) -> None:
        """Wire up Telegram message and callback_query handlers."""
        self.bot.register_message_handler(self._handle_start, commands=["start", "menu"], pass_bot=False)
        self.bot.register_message_handler(self._handle_text, content_types=["text"], func=lambda m: True)
        self.bot.register_callback_query_handler(self._handle_callback, func=lambda c: True)

    def _register_event_subscriptions(self) -> None:
        """Subscribe to WorkflowEngine's EventBus events for live progress delivery."""
        self.event_bus.subscribe("stage.started", self.on_stage_started)
        self.event_bus.subscribe("stage.completed", self.on_stage_completed)
        self.event_bus.subscribe("workflow.completed", self.on_workflow_completed)
        self.event_bus.subscribe("workflow.failed", self.on_workflow_failed)
        self.event_bus.subscribe("workflow.paused", self.on_workflow_paused)

    # ------------------------------------------------------------------
    # Top-level entry points
    # ------------------------------------------------------------------

    def _handle_start(self, message: Message) -> None:
        """Handle ``/start`` and ``/menu`` — show the dashboard as a fresh message."""
        if not self._authorize(message.from_user.id, message.chat.id):
            return
        sent = self.bot.send_message(message.chat.id, "🏭 Welcome to Fact Drop AI Studio.")
        self.chat_states.set_panel_message(message.chat.id, sent.message_id)
        self.show_dashboard(message.chat.id, sent.message_id)

    def _handle_text(self, message: Message) -> None:
        """
        Route free-text messages based on the chat's pending-input state.

        Every other interaction happens through InlineKeyboard taps, so a
        free-text message only matters when the bot explicitly asked for
        one (new project input, search query, settings value).
        """
        if not self._authorize(message.from_user.id, message.chat.id):
            return
        if message.text and message.text.startswith("/"):
            return  # Unrecognised command — ignore rather than error.

        state = self.chat_states.get(message.chat.id)
        if state.pending_input == PendingInputKind.NEW_PROJECT_INPUT:
            self.handle_new_project_text(message)
        elif state.pending_input == PendingInputKind.SEARCH_QUERY:
            self.handle_search_query(message)
        elif state.pending_input == PendingInputKind.SETTINGS_VALUE:
            self.handle_settings_free_text(message)
        else:
            sent = self.bot.send_message(
                message.chat.id, "Use /menu to open the control panel, or tap a button below."
            )
            self.chat_states.set_panel_message(message.chat.id, sent.message_id)
            self.show_dashboard(message.chat.id, sent.message_id)

    def _handle_callback(self, call: CallbackQuery) -> None:
        """Central callback_query dispatcher — parses CallbackData and routes to a handler."""
        if not self._authorize(call.from_user.id, call.message.chat.id if call.message else 0):
            self.bot.answer_callback_query(call.id, "Not authorized.", show_alert=True)
            return

        chat_id = call.message.chat.id
        message_id = call.message.message_id
        data = CallbackData.parse(call.data or "")

        try:
            self._dispatch(chat_id, message_id, data, call)
        except Exception:  # noqa: BLE001 - never let a handler bug crash the bot process
            logger.exception("Error handling callback '{}' for chat {}", call.data, chat_id)
            self.bot.answer_callback_query(call.id, "⚠️ Something went wrong.", show_alert=True)
            return

        try:
            self.bot.answer_callback_query(call.id)
        except ApiTelegramException:
            pass

    # ------------------------------------------------------------------
    # Callback dispatch table
    # ------------------------------------------------------------------

    def _dispatch(self, chat_id: int, message_id: int, data: CallbackData, call: CallbackQuery) -> None:
        """Route a parsed callback to the appropriate handler mixin method."""
        if data.domain == "nav":
            self._dispatch_nav(chat_id, message_id, data.action)
        elif data.domain == "project":
            self._dispatch_project(chat_id, message_id, data.action, data.arg)
        elif data.domain == "workflow":
            self._dispatch_workflow(chat_id, message_id, data.action, data.arg)
        elif data.domain == "asset":
            self._dispatch_asset(chat_id, message_id, data.action, data.arg)
        elif data.domain == "settings":
            self._dispatch_settings(chat_id, message_id, data.action, data.arg)
        elif data.domain == "backup":
            self._dispatch_backup(chat_id, message_id, data.action, data.arg)
        elif data.domain == "cache":
            self._dispatch_cache(chat_id, message_id, data.action)
        else:
            logger.warning("Unknown callback domain: {}", data.domain)

    def _dispatch_nav(self, chat_id: int, message_id: int, action: str) -> None:
        """Route top-level navigation callbacks (dashboard, projects, settings, ...)."""
        routes = {
            "dashboard": lambda: self.show_dashboard(chat_id, message_id),
            "projects": lambda: self.show_project_list(chat_id, message_id, 0),
            "new_project": lambda: self.prompt_new_project(chat_id, message_id),
            "queue": lambda: self.show_queue(chat_id, message_id),
            "stats": lambda: self.show_stats(chat_id, message_id),
            "health": lambda: self.show_health(chat_id, message_id),
            "logs": lambda: self.show_logs(chat_id, message_id),
            "settings": lambda: self.show_settings(chat_id, message_id),
            "backups": lambda: self.bot.send_message(chat_id, "Open a project first, then tap 💾 Backups."),
            "search": lambda: self.prompt_search(chat_id, message_id),
            "cache": lambda: self.show_cache_menu(chat_id, message_id),
        }
        route = routes.get(action)
        if route:
            route()

    def _dispatch_project(self, chat_id: int, message_id: int, action: str, arg: str) -> None:
        """Route project-domain callbacks (view, list, create, delete, undo, export, history)."""
        if action == "view":
            self.show_project_detail(chat_id, message_id, arg)
        elif action == "list":
            self.show_project_list(chat_id, message_id, int(arg or 0))
        elif action == "confirm_create":
            self.confirm_create_project(chat_id, message_id, arg)
        elif action == "delete_confirm":
            self.delete_project_confirm(chat_id, message_id, arg)
        elif action == "delete":
            self.delete_project(chat_id, message_id, arg)
        elif action == "undo":
            self.undo_project(chat_id, message_id, arg)
        elif action == "export":
            self.export_project(chat_id, arg)
        elif action == "history":
            self.show_project_history(chat_id, message_id, arg)

    def _dispatch_workflow(self, chat_id: int, message_id: int, action: str, arg: str) -> None:
        """Route workflow-domain callbacks (start, pause, resume, retry)."""
        if action == "start":
            self.start_workflow(chat_id, message_id, arg)
        elif action == "pause":
            self.pause_workflow(chat_id, message_id, arg)
        elif action == "resume":
            self.resume_workflow(chat_id, message_id, arg)
        elif action == "retry":
            self.retry_workflow(chat_id, message_id, arg)

    def _dispatch_asset(self, chat_id: int, message_id: int, action: str, arg: str) -> None:
        """Route asset-domain callbacks (list, send)."""
        if action == "list":
            self.show_asset_list(chat_id, message_id, arg)
        elif action == "send":
            self.send_asset(chat_id, arg)

    def _dispatch_settings(self, chat_id: int, message_id: int, action: str, arg: str) -> None:
        """Route settings-domain callbacks (edit prompt, apply value)."""
        if action == "edit":
            self.prompt_edit_setting(chat_id, message_id, arg)
        elif action == "set":
            self.apply_setting(chat_id, message_id, arg)

    def _dispatch_backup(self, chat_id: int, message_id: int, action: str, arg: str) -> None:
        """Route backup-domain callbacks (create, restore)."""
        if action == "create":
            self.create_backup(chat_id, message_id, arg)
        elif action == "restore":
            self.bot.send_message(chat_id, f"Restoring from backup '{arg}' — contact the operator for manual restore.")

    def _dispatch_cache(self, chat_id: int, message_id: int, action: str) -> None:
        """Route cache-domain callbacks (clear_expired)."""
        if action == "clear_expired":
            self.clear_expired_cache(chat_id, message_id)

    # ------------------------------------------------------------------
    # Shared rendering helper
    # ------------------------------------------------------------------

    def _render(
        self, chat_id: int, message_id: int | None, text: str, keyboard: InlineKeyboardMarkup | None
    ) -> None:
        """
        Render ``text``/``keyboard`` by editing the chat's existing panel
        message when possible, falling back to sending a new message.

        This is the single choke point that satisfies the requirement
        that long-running/menu operations update one message instead of
        flooding the chat with new ones each time the user taps a button.
        """
        if message_id is not None:
            try:
                self.bot.edit_message_text(
                    text, chat_id=chat_id, message_id=message_id, parse_mode="MarkdownV2", reply_markup=keyboard
                )
                self.chat_states.set_panel_message(chat_id, message_id)
                return
            except ApiTelegramException as exc:
                if "message is not modified" in str(exc).lower():
                    return
                logger.debug("edit_message_text failed ({}), sending a new message instead.", exc)

        sent = self.bot.send_message(chat_id, text, parse_mode="MarkdownV2", reply_markup=keyboard)
        self.chat_states.set_panel_message(chat_id, sent.message_id)

    # ------------------------------------------------------------------
    # Auth helper
    # ------------------------------------------------------------------

    def _authorize(self, user_id: int, chat_id: int) -> bool:
        """Return True if ``user_id`` is whitelisted; otherwise log and ignore silently."""
        if is_authorized(user_id):
            return True
        logger.warning("Ignoring message from unauthorized user_id={}", user_id)
        return False

    # ------------------------------------------------------------------
    # Runtime
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Start long-polling. Blocks the calling thread — call this last, in ``bot_main.py``."""
        logger.info("Starting Telegram bot polling loop...")
        self.bot.infinity_polling(timeout=30, skip_pending=True)
