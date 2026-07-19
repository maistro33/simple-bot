"""Repository package — one class per aggregate/table, generic CRUD + domain queries."""
from database.repositories.base_repository import BaseRepository
from database.repositories.project_repository import ProjectRepository
from database.repositories.domain_repositories import (
    AssetRepository,
    ExportRepository,
    HistoryRepository,
    LogRepository,
    PromptRepository,
    ReportRepository,
    ScriptRepository,
    SeoRepository,
    StoryboardRepository,
    SubtitleRepository,
    ThumbnailRepository,
    VoiceRepository,
)

__all__ = [
    "BaseRepository",
    "ProjectRepository",
    "AssetRepository",
    "ExportRepository",
    "HistoryRepository",
    "LogRepository",
    "PromptRepository",
    "ReportRepository",
    "ScriptRepository",
    "SeoRepository",
    "StoryboardRepository",
    "SubtitleRepository",
    "ThumbnailRepository",
    "VoiceRepository",
]
