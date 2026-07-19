"""
Configuration package for FACT DROP AI STUDIO.

Exposes the singleton application settings object and shared constants
so the rest of the codebase can simply do:

    from config import get_settings
    settings = get_settings()
"""
from config.settings import Settings, get_settings
from config.constants import (
    ProductCategory,
    WorkflowStage,
    WorkflowStatus,
    AssetType,
    PlatformName,
    APP_ROOT,
)

__all__ = [
    "Settings",
    "get_settings",
    "ProductCategory",
    "WorkflowStage",
    "WorkflowStatus",
    "AssetType",
    "PlatformName",
    "APP_ROOT",
]
