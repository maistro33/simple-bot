"""
Shared pytest fixtures for the FACT DROP AI STUDIO test suite.

Every test runs against an isolated, temporary SQLite database (never
the real ``database/fact_drop.db``) and a clean settings cache, so
tests never interfere with each other or with real project data.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def isolated_environment(tmp_path, monkeypatch):
    """Point the database, assets and exports at a temporary directory for every test."""
    db_path = tmp_path / "test_fact_drop.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))

    import config.settings as settings_module

    settings_module.get_settings.cache_clear()

    import database.session as session_module

    session_module._engine = None
    session_module._session_factory = None

    from database.session import init_database

    init_database()

    yield

    settings_module.get_settings.cache_clear()
    session_module._engine = None
    session_module._session_factory = None


@pytest.fixture
def sample_project():
    """Create and return a sample project via the real ProjectManager."""
    from core.project_manager import ProjectManager

    manager = ProjectManager()
    return manager.create_project(
        raw_input="A stainless steel self-stirring mug with USB charging",
        name="Test Self-Stirring Mug",
    )
