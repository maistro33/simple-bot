"""
Telegram Bot package — the full remote control panel for FACT DROP AI
STUDIO. Built with pyTelegramBotAPI (telebot), driven entirely by
InlineKeyboard menus rather than typed commands, and wired directly
into the existing core/engines/services architecture (no duplicated
business logic — every handler simply calls the same managers the CLI
uses).
"""
from telegram_bot.bot import FactDropTelegramBot

__all__ = ["FactDropTelegramBot"]
