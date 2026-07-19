"""
Per-chat UI state for the Telegram control panel.

Two responsibilities:
  1. Track the "active panel message" per chat so long-running menus
     (dashboard, project list, progress views) edit a single message in
     place instead of spamming the chat with new ones, per the
     requirement that all long operations update the same message.
  2. Track "pending input" per chat — e.g. after tapping "➕ New Project",
     the bot needs to know the next free-text message from that chat is
     the product URL/description, not a random message to ignore.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum


class PendingInputKind(str, Enum):
    """What kind of free-text input the bot is currently waiting for, per chat."""

    NONE = "none"
    NEW_PROJECT_INPUT = "new_project_input"
    SEARCH_QUERY = "search_query"
    SETTINGS_VALUE = "settings_value"


@dataclass(slots=True)
class ChatState:
    """UI state tracked for a single Telegram chat."""

    panel_message_id: int | None = None
    pending_input: PendingInputKind = PendingInputKind.NONE
    pending_context: dict = field(default_factory=dict)


class ChatStateStore:
    """Thread-safe in-memory registry of :class:`ChatState` keyed by chat ID."""

    def __init__(self) -> None:
        self._states: dict[int, ChatState] = {}
        self._lock = threading.Lock()

    def get(self, chat_id: int) -> ChatState:
        """Return the state for ``chat_id``, creating a fresh one if absent."""
        with self._lock:
            if chat_id not in self._states:
                self._states[chat_id] = ChatState()
            return self._states[chat_id]

    def set_panel_message(self, chat_id: int, message_id: int) -> None:
        """Record which message ID is the chat's current "live" panel message."""
        self.get(chat_id).panel_message_id = message_id

    def set_pending_input(
        self, chat_id: int, kind: PendingInputKind, context: dict | None = None
    ) -> None:
        """Mark that the next text message from this chat should be treated as ``kind`` input."""
        state = self.get(chat_id)
        state.pending_input = kind
        state.pending_context = context or {}

    def clear_pending_input(self, chat_id: int) -> None:
        """Reset the pending-input flag for a chat back to :attr:`PendingInputKind.NONE`."""
        state = self.get(chat_id)
        state.pending_input = PendingInputKind.NONE
        state.pending_context = {}


_chat_state_store: ChatStateStore | None = None


def get_chat_state_store() -> ChatStateStore:
    """Return the process-wide :class:`ChatStateStore` singleton."""
    global _chat_state_store
    if _chat_state_store is None:
        _chat_state_store = ChatStateStore()
    return _chat_state_store
