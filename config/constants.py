"""
Application-wide constants and enumerations.

Centralising these values prevents "magic strings" from being scattered
across engines, services and database models, and gives us a single
source of truth that both SQLAlchemy models and Pydantic schemas can
share.
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path

# --------------------------------------------------------------------------
# Filesystem roots
# --------------------------------------------------------------------------
APP_ROOT: Path = Path(__file__).resolve().parent.parent
CONFIG_DIR: Path = APP_ROOT / "config"
DATABASE_DIR: Path = APP_ROOT / "database"
ASSETS_DIR: Path = APP_ROOT / "assets"
VOICES_DIR: Path = APP_ROOT / "voices"
PROJECTS_DIR: Path = APP_ROOT / "projects"
EXPORTS_DIR: Path = APP_ROOT / "exports"
LOGS_DIR: Path = APP_ROOT / "logs"
TEMPLATES_DIR: Path = APP_ROOT / "templates"

# --------------------------------------------------------------------------
# Domain enumerations
# --------------------------------------------------------------------------


class ProductCategory(str, Enum):
    """Supported high-level product categories used for strategy tuning."""

    ELECTRONICS = "electronics"
    HOME_AND_KITCHEN = "home_and_kitchen"
    BEAUTY_AND_PERSONAL_CARE = "beauty_and_personal_care"
    FASHION_AND_APPAREL = "fashion_and_apparel"
    HEALTH_AND_WELLNESS = "health_and_wellness"
    TOYS_AND_GAMES = "toys_and_games"
    SPORTS_AND_OUTDOORS = "sports_and_outdoors"
    PET_SUPPLIES = "pet_supplies"
    AUTOMOTIVE = "automotive"
    TOOLS_AND_HOME_IMPROVEMENT = "tools_and_home_improvement"
    OFFICE_AND_PRODUCTIVITY = "office_and_productivity"
    BABY_AND_KIDS = "baby_and_kids"
    GADGETS_AND_NOVELTY = "gadgets_and_novelty"
    UNKNOWN = "unknown"


class WorkflowStage(str, Enum):
    """Every discrete stage of the automated content pipeline, in order."""

    PRODUCT_ANALYSIS = "product_analysis"
    CATEGORY_DETECTION = "category_detection"
    BRAND_DETECTION = "brand_detection"
    COMPETITOR_RESEARCH = "competitor_research"
    AUDIENCE_ANALYSIS = "audience_analysis"
    MARKETING_STRATEGY = "marketing_strategy"
    HOOK_GENERATION = "hook_generation"
    SCRIPT_GENERATION = "script_generation"
    STORYBOARD_GENERATION = "storyboard_generation"
    PROMPT_GENERATION = "prompt_generation"
    VOICE_GENERATION = "voice_generation"
    SUBTITLE_GENERATION = "subtitle_generation"
    THUMBNAIL_GENERATION = "thumbnail_generation"
    SEO_GENERATION = "seo_generation"
    REPORT_GENERATION = "report_generation"
    EXPORT = "export"
    FINISHED = "finished"

    @classmethod
    def ordered(cls) -> list["WorkflowStage"]:
        """Return every stage in canonical pipeline execution order."""
        return [
            cls.PRODUCT_ANALYSIS,
            cls.CATEGORY_DETECTION,
            cls.BRAND_DETECTION,
            cls.COMPETITOR_RESEARCH,
            cls.AUDIENCE_ANALYSIS,
            cls.MARKETING_STRATEGY,
            cls.HOOK_GENERATION,
            cls.SCRIPT_GENERATION,
            cls.STORYBOARD_GENERATION,
            cls.PROMPT_GENERATION,
            cls.VOICE_GENERATION,
            cls.SUBTITLE_GENERATION,
            cls.THUMBNAIL_GENERATION,
            cls.SEO_GENERATION,
            cls.REPORT_GENERATION,
            cls.EXPORT,
            cls.FINISHED,
        ]

    def next_stage(self) -> "WorkflowStage | None":
        """Return the stage that logically follows this one, or None if final."""
        stages = WorkflowStage.ordered()
        idx = stages.index(self)
        if idx + 1 < len(stages):
            return stages[idx + 1]
        return None


class WorkflowStatus(str, Enum):
    """Lifecycle status of a project or of an individual stage execution."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


class AssetType(str, Enum):
    """Types of binary/text assets tracked by the Asset Manager."""

    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    SUBTITLE = "subtitle"
    DOCUMENT = "document"
    THUMBNAIL = "thumbnail"
    ARCHIVE = "archive"


class PlatformName(str, Enum):
    """Supported e-commerce / social platforms for plugins."""

    AMAZON = "amazon"
    ALIEXPRESS = "aliexpress"
    TEMU = "temu"
    EBAY = "ebay"
    SHOPIFY = "shopify"
    YOUTUBE = "youtube"
    TIKTOK = "tiktok"
    GENERIC = "generic"


class ExportFormat(str, Enum):
    """Supported bundle formats for the Export Manager."""

    ZIP = "zip"
    FOLDER = "folder"
    JSON = "json"
    PDF_REPORT = "pdf_report"


# --------------------------------------------------------------------------
# Misc numeric constants
# --------------------------------------------------------------------------
DEFAULT_SHORT_VIDEO_SECONDS: int = 60
DEFAULT_HOOK_DURATION_SECONDS: int = 3
DEFAULT_STORYBOARD_SCENES: int = 8
MAX_RETRY_ATTEMPTS: int = 3
RETRY_BACKOFF_SECONDS: float = 2.0
