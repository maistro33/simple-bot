"""
InlineKeyboardMarkup builders for every menu in the Telegram control panel.

Kept entirely separate from handler logic so the visual layout of the
panel can be redesigned without touching business logic, and vice versa.
"""
from __future__ import annotations

from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

from config.constants import WorkflowStatus
from database.models.asset import Asset
from database.models.project import Project
from telegram_bot.callback_data import cb
from telegram_bot.formatters import status_emoji, truncate


def main_menu() -> InlineKeyboardMarkup:
    """The root dashboard menu — the entry point to every other feature."""
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("📁 Projects", callback_data=cb("nav", "projects")),
        InlineKeyboardButton("➕ New Project", callback_data=cb("nav", "new_project")),
    )
    kb.add(
        InlineKeyboardButton("📋 Queue", callback_data=cb("nav", "queue")),
        InlineKeyboardButton("📊 Statistics", callback_data=cb("nav", "stats")),
    )
    kb.add(
        InlineKeyboardButton("🩺 System Health", callback_data=cb("nav", "health")),
        InlineKeyboardButton("📜 Logs", callback_data=cb("nav", "logs")),
    )
    kb.add(
        InlineKeyboardButton("⚙️ Settings", callback_data=cb("nav", "settings")),
        InlineKeyboardButton("💾 Backups", callback_data=cb("nav", "backups")),
    )
    kb.add(
        InlineKeyboardButton("🔎 Search", callback_data=cb("nav", "search")),
        InlineKeyboardButton("🧹 Cache", callback_data=cb("nav", "cache")),
    )
    kb.add(InlineKeyboardButton("🔄 Refresh", callback_data=cb("nav", "dashboard")))
    return kb


def back_to_dashboard() -> InlineKeyboardMarkup:
    """A minimal single "back" button, used on simple confirmation/result screens."""
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("⬅️ Dashboard", callback_data=cb("nav", "dashboard")))
    return kb


def project_list(projects: list[Project], page: int, total_pages: int) -> InlineKeyboardMarkup:
    """Paginated list of projects, one button per project plus pagination controls."""
    kb = InlineKeyboardMarkup(row_width=1)
    for project in projects:
        label = f"{status_emoji(project.status)} {truncate(project.name, 40)}"
        kb.add(InlineKeyboardButton(label, callback_data=cb("project", "view", project.id)))

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀️ Prev", callback_data=cb("project", "list", str(page - 1))))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Next ▶️", callback_data=cb("project", "list", str(page + 1))))
    if nav_row:
        kb.row(*nav_row)

    kb.add(InlineKeyboardButton("➕ New Project", callback_data=cb("nav", "new_project")))
    kb.add(InlineKeyboardButton("⬅️ Dashboard", callback_data=cb("nav", "dashboard")))
    return kb


def project_detail(project: Project) -> InlineKeyboardMarkup:
    """Action menu for a single project, context-sensitive to its current status."""
    kb = InlineKeyboardMarkup(row_width=2)
    pid = project.id

    if project.status in (WorkflowStatus.PENDING,):
        kb.add(InlineKeyboardButton("▶️ Start", callback_data=cb("workflow", "start", pid)))
    elif project.status == WorkflowStatus.RUNNING:
        kb.add(InlineKeyboardButton("⏸️ Pause", callback_data=cb("workflow", "pause", pid)))
    elif project.status == WorkflowStatus.PAUSED:
        kb.add(
            InlineKeyboardButton("▶️ Resume", callback_data=cb("workflow", "resume", pid)),
            InlineKeyboardButton("🔁 Restart", callback_data=cb("workflow", "start", pid)),
        )
    elif project.status == WorkflowStatus.FAILED:
        kb.add(
            InlineKeyboardButton("🔄 Retry", callback_data=cb("workflow", "retry", pid)),
            InlineKeyboardButton("🔁 Restart", callback_data=cb("workflow", "start", pid)),
        )
    elif project.status == WorkflowStatus.COMPLETED:
        kb.add(
            InlineKeyboardButton("📦 Export", callback_data=cb("project", "export", pid)),
            InlineKeyboardButton("🗂️ Assets", callback_data=cb("asset", "list", pid)),
        )

    kb.add(
        InlineKeyboardButton("🗂️ Assets", callback_data=cb("asset", "list", pid)),
        InlineKeyboardButton("🕐 History", callback_data=cb("project", "history", pid)),
    )
    kb.add(
        InlineKeyboardButton("↩️ Undo", callback_data=cb("project", "undo", pid)),
        InlineKeyboardButton("🗑️ Delete", callback_data=cb("project", "delete_confirm", pid)),
    )
    kb.add(InlineKeyboardButton("⬅️ Projects", callback_data=cb("nav", "projects")))
    return kb


def confirm_delete(project_id: str) -> InlineKeyboardMarkup:
    """Confirmation dialog before permanently deleting a project."""
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ Yes, delete", callback_data=cb("project", "delete", project_id)),
        InlineKeyboardButton("❌ Cancel", callback_data=cb("project", "view", project_id)),
    )
    return kb


def asset_list(assets: list[Asset], project_id: str) -> InlineKeyboardMarkup:
    """List of downloadable assets for a project, grouped as one button each."""
    kb = InlineKeyboardMarkup(row_width=1)
    for asset in assets:
        label = f"{_asset_type_emoji(asset.asset_type.value)} {truncate(asset.file_name, 45)}"
        kb.add(InlineKeyboardButton(label, callback_data=cb("asset", "send", asset.id)))
    kb.add(InlineKeyboardButton("⬅️ Back to Project", callback_data=cb("project", "view", project_id)))
    return kb


def _asset_type_emoji(asset_type: str) -> str:
    """Map an asset type string to a representative emoji."""
    return {
        "image": "🖼️",
        "audio": "🎙️",
        "video": "🎬",
        "subtitle": "💬",
        "document": "📄",
        "thumbnail": "🖌️",
        "archive": "📦",
    }.get(asset_type, "📎")


def settings_menu(current: dict) -> InlineKeyboardMarkup:
    """Settings menu — each row shows the current value and opens an edit prompt."""
    kb = InlineKeyboardMarkup(row_width=1)
    rows = [
        ("openai.text_model", "🧠 Text Model"),
        ("openai.image_model", "🖼️ Image Model"),
        ("openai.temperature", "🌡️ Temperature"),
        ("voice.default_provider", "🎙️ Voice Provider"),
        ("video.default_provider", "🎬 Video Provider"),
        ("video.aspect_ratio", "📐 Aspect Ratio"),
        ("video.duration_seconds", "⏱️ Video Duration"),
        ("workflow.max_retries", "🔁 Max Retries"),
        ("workflow.max_concurrency", "🧵 Max Concurrency"),
        ("language", "🌐 Language"),
    ]
    for key, label in rows:
        value = current.get(key, "—")
        kb.add(InlineKeyboardButton(f"{label}: {value}", callback_data=cb("settings", "edit", key)))
    kb.add(InlineKeyboardButton("⬅️ Dashboard", callback_data=cb("nav", "dashboard")))
    return kb


def settings_value_options(setting_key: str, options: list[str]) -> InlineKeyboardMarkup:
    """A picker of preset values for a given settings key (used for enum-like settings)."""
    kb = InlineKeyboardMarkup(row_width=2)
    buttons = [
        InlineKeyboardButton(opt, callback_data=cb("settings", "set", f"{setting_key}={opt}")) for opt in options
    ]
    kb.add(*buttons)
    kb.add(InlineKeyboardButton("⬅️ Settings", callback_data=cb("nav", "settings")))
    return kb


def backups_menu(backups: list, project_id: str) -> InlineKeyboardMarkup:
    """List of backups for a project, with create/restore actions."""
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("💾 Create Backup Now", callback_data=cb("backup", "create", project_id)))
    for path in backups:
        name = path.name if hasattr(path, "name") else str(path)
        kb.add(InlineKeyboardButton(f"♻️ Restore: {truncate(name, 40)}", callback_data=cb("backup", "restore", name)))
    kb.add(InlineKeyboardButton("⬅️ Back to Project", callback_data=cb("project", "view", project_id)))
    return kb


def queue_menu() -> InlineKeyboardMarkup:
    """Queue view controls — just refresh and back, the content is the message text."""
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🔄 Refresh", callback_data=cb("nav", "queue")),
        InlineKeyboardButton("⬅️ Dashboard", callback_data=cb("nav", "dashboard")),
    )
    return kb


def cache_menu() -> InlineKeyboardMarkup:
    """Cache management actions."""
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("🧹 Clear Expired Entries", callback_data=cb("cache", "clear_expired")))
    kb.add(InlineKeyboardButton("⬅️ Dashboard", callback_data=cb("nav", "dashboard")))
    return kb


def workflow_progress_keyboard(project_id: str) -> InlineKeyboardMarkup:
    """Minimal action keyboard shown under a live progress panel while a workflow is running."""
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("⏸️ Pause", callback_data=cb("workflow", "pause", project_id)),
        InlineKeyboardButton("🔄 Refresh", callback_data=cb("project", "view", project_id)),
    )
    kb.add(InlineKeyboardButton("⬅️ Projects", callback_data=cb("nav", "projects")))
    return kb


def project_creation_confirm() -> InlineKeyboardMarkup:
    """Confirm/cancel keyboard shown after the user submits new-project input."""
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("▶️ Create & Start", callback_data=cb("project", "confirm_create", "start")),
        InlineKeyboardButton("💾 Create Only", callback_data=cb("project", "confirm_create", "draft")),
    )
    kb.add(InlineKeyboardButton("❌ Cancel", callback_data=cb("nav", "dashboard")))
    return kb
