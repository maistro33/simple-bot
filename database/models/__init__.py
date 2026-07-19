"""
Aggregates every ORM model so that a single import — ``import database.models``
— registers all fourteen tables on :class:`database.base.Base` metadata.

This module MUST be imported before calling ``Base.metadata.create_all``,
which is exactly what :func:`database.session.init_database` does.
"""
from database.models.asset import Asset
from database.models.cache import Cache
from database.models.export import Export
from database.models.history import History
from database.models.log import Log
from database.models.project import Project
from database.models.prompt import Prompt
from database.models.report import Report
from database.models.script import Script
from database.models.seo import Seo
from database.models.setting import Setting
from database.models.storyboard import Storyboard
from database.models.subtitle import Subtitle
from database.models.thumbnail import Thumbnail
from database.models.voice import Voice

__all__ = [
    "Asset",
    "Cache",
    "Export",
    "History",
    "Log",
    "Project",
    "Prompt",
    "Report",
    "Script",
    "Seo",
    "Setting",
    "Storyboard",
    "Subtitle",
    "Thumbnail",
    "Voice",
]
