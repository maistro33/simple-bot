"""Unit tests for the configuration/settings layer."""
from __future__ import annotations

import pytest


def test_settings_load_defaults():
    """Settings should load successfully with sensible defaults even without a .env file."""
    from config import get_settings

    settings = get_settings()
    assert settings.app_name == "Fact Drop AI Studio"
    assert settings.max_concurrent_workflows >= 1
    assert settings.log_level in {"TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"}


def test_settings_singleton_is_cached():
    """get_settings() must return the exact same instance across calls (singleton)."""
    from config import get_settings

    first = get_settings()
    second = get_settings()
    assert first is second


def test_invalid_video_provider_rejected(monkeypatch):
    """An unsupported VIDEO_PROVIDER value must raise a validation error."""
    from config.settings import Settings

    monkeypatch.setenv("VIDEO_PROVIDER", "not_a_real_provider")
    with pytest.raises(ValueError):
        Settings()


def test_has_openai_credentials_reflects_env(monkeypatch):
    """has_openai_credentials should be False when no key is set, True when one is."""
    from config import get_settings

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()
    assert get_settings().has_openai_credentials is False

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-123")
    get_settings.cache_clear()
    assert get_settings().has_openai_credentials is True


def test_workflow_stage_ordering():
    """WorkflowStage.ordered() must start at product_analysis and end at finished."""
    from config.constants import WorkflowStage

    stages = WorkflowStage.ordered()
    assert stages[0] == WorkflowStage.PRODUCT_ANALYSIS
    assert stages[-1] == WorkflowStage.FINISHED
    assert len(stages) == len(set(stages))


def test_workflow_stage_next_stage():
    """next_stage() should return the correct successor, and None after FINISHED."""
    from config.constants import WorkflowStage

    assert WorkflowStage.PRODUCT_ANALYSIS.next_stage() == WorkflowStage.CATEGORY_DETECTION
    assert WorkflowStage.FINISHED.next_stage() is None
