"""
Formatting helpers for the Telegram control panel: MarkdownV2 escaping,
progress bars, emoji/status mappings, and human-readable byte/duration
formatting. Centralised here so every handler renders text consistently.
"""
from __future__ import annotations

import re

from config.constants import WorkflowStage, WorkflowStatus

_MARKDOWN_V2_SPECIAL_CHARS = r"_*[]()~`>#+-=|{}.!"


def escape_markdown(text: str) -> str:
    """Escape every MarkdownV2 special character in ``text`` for safe rendering."""
    if not text:
        return ""
    pattern = f"([{re.escape(_MARKDOWN_V2_SPECIAL_CHARS)}])"
    return re.sub(pattern, r"\\\1", text)


def progress_bar(fraction: float, length: int = 12, filled_char: str = "▓", empty_char: str = "░") -> str:
    """Render a simple text progress bar, e.g. ``▓▓▓▓▓▓░░░░░░ 50%``."""
    fraction = max(0.0, min(1.0, fraction))
    filled = round(length * fraction)
    bar = filled_char * filled + empty_char * (length - filled)
    return f"{bar} {round(fraction * 100)}%"


def stage_progress_fraction(stage: WorkflowStage) -> float:
    """Return how far through the pipeline a given stage represents, as 0.0-1.0."""
    ordered = WorkflowStage.ordered()
    try:
        index = ordered.index(stage)
    except ValueError:
        return 0.0
    return index / max(len(ordered) - 1, 1)


_STAGE_EMOJI: dict[str, str] = {
    "product_analysis": "🔎",
    "category_detection": "🏷️",
    "brand_detection": "🏢",
    "competitor_research": "📊",
    "audience_analysis": "🎯",
    "marketing_strategy": "🧠",
    "hook_generation": "🪝",
    "script_generation": "📝",
    "storyboard_generation": "🎬",
    "prompt_generation": "🖼️",
    "voice_generation": "🎙️",
    "subtitle_generation": "💬",
    "thumbnail_generation": "🖌️",
    "seo_generation": "🔍",
    "report_generation": "📄",
    "export": "📦",
    "finished": "✅",
}

_STATUS_EMOJI: dict[str, str] = {
    "pending": "⏳",
    "running": "⚙️",
    "paused": "⏸️",
    "completed": "✅",
    "failed": "❌",
    "cancelled": "🚫",
    "retrying": "🔄",
}


def stage_emoji(stage: WorkflowStage | str) -> str:
    """Return an emoji representing the given workflow stage."""
    value = stage.value if isinstance(stage, WorkflowStage) else stage
    return _STAGE_EMOJI.get(value, "▫️")


def status_emoji(status: WorkflowStatus | str) -> str:
    """Return an emoji representing the given workflow status."""
    value = status.value if isinstance(status, WorkflowStatus) else status
    return _STATUS_EMOJI.get(value, "❔")


def stage_label(stage: WorkflowStage | str) -> str:
    """Return a human-friendly title-cased label for a workflow stage."""
    value = stage.value if isinstance(stage, WorkflowStage) else stage
    return value.replace("_", " ").title()


def format_bytes(size_bytes: int | float) -> str:
    """Format a byte count as a human-readable string (KB/MB/GB)."""
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def format_duration(seconds: float) -> str:
    """Format a duration in seconds as ``Hh Mm Ss`` (omitting zero leading units)."""
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def format_usd(amount: float) -> str:
    """Format a USD amount with 4 decimal places for small cost values."""
    if amount < 0.01:
        return f"${amount:.4f}"
    return f"${amount:.2f}"


def truncate(text: str, max_length: int = 60) -> str:
    """Truncate text to ``max_length`` characters, appending an ellipsis if cut."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 1].rstrip() + "…"
