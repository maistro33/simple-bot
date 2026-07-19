#!/usr/bin/env python3
"""
FACT DROP AI STUDIO — Telegram Bot Entry Point.

This is the process Railway (or any host) should run to serve the
Telegram control panel 24/7. It performs the same application bootstrap
as the CLI (database schema, filesystem directories, background
scheduler) before starting the bot's long-polling loop.

Usage:
    python bot_main.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.application import get_application  # noqa: E402
from core.exceptions import ConfigurationError  # noqa: E402
from core.logger import get_logger  # noqa: E402
from telegram_bot.bot import FactDropTelegramBot  # noqa: E402

logger = get_logger(__name__)


def main() -> None:
    """Bootstrap the application and start the Telegram bot's polling loop."""
    application = get_application()

    try:
        bot = FactDropTelegramBot()
    except ConfigurationError as exc:
        logger.error("Cannot start Telegram bot: {}", exc)
        sys.exit(1)

    try:
        bot.run()
    except KeyboardInterrupt:
        logger.info("Telegram bot stopped by user.")
    finally:
        application.shutdown()


if __name__ == "__main__":
    main()
