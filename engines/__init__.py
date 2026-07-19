"""
Engines package — one class per pipeline capability. Every engine
inherits from :class:`BaseEngine` (defined in ``engines.base_engine``),
which injects the shared :class:`AIManager` and standardises the
``execute`` contract so the Workflow Engine can invoke any engine
polymorphically.
"""
from engines.base_engine import BaseEngine
from engines.prompt_engine import PromptEngine
from engines.quality_engine import QualityEngine
from engines.report_engine import ReportEngine
from engines.research_engine import ResearchEngine
from engines.script_engine import ScriptEngine
from engines.seo_engine import SeoEngine
from engines.storyboard_engine import StoryboardEngine
from engines.strategy_engine import StrategyEngine
from engines.subtitle_engine import SubtitleEngine
from engines.thumbnail_engine import ThumbnailEngine
from engines.video_engine import VideoEngine
from engines.voice_engine import VoiceEngine

__all__ = [
    "BaseEngine",
    "PromptEngine",
    "QualityEngine",
    "ReportEngine",
    "ResearchEngine",
    "ScriptEngine",
    "SeoEngine",
    "StoryboardEngine",
    "StrategyEngine",
    "SubtitleEngine",
    "ThumbnailEngine",
    "VideoEngine",
    "VoiceEngine",
]
