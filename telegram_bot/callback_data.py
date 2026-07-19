"""
Callback data schema for the Telegram control panel.

All ``callback_data`` strings follow a simple ``domain:action:arg`` shape
(colon-delimited, ASCII-only, well under Telegram's 64-byte limit) so
:mod:`telegram_bot.bot` can dispatch every callback with one ``split(":")``
instead of parsing free-form strings per handler.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CallbackData:
    """A parsed ``domain:action:arg`` callback payload."""

    domain: str
    action: str
    arg: str = ""

    def encode(self) -> str:
        """Serialise back to the wire format ``domain:action:arg``."""
        return f"{self.domain}:{self.action}:{self.arg}" if self.arg else f"{self.domain}:{self.action}"

    @classmethod
    def parse(cls, raw: str) -> "CallbackData":
        """Parse a raw callback_data string into its domain/action/arg parts."""
        parts = raw.split(":", 2)
        domain = parts[0] if len(parts) > 0 else ""
        action = parts[1] if len(parts) > 1 else ""
        arg = parts[2] if len(parts) > 2 else ""
        return cls(domain=domain, action=action, arg=arg)


def cb(domain: str, action: str, arg: str = "") -> str:
    """Shorthand to build an encoded callback_data string."""
    return CallbackData(domain, action, arg).encode()
