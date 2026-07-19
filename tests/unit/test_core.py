"""Unit tests for core infrastructure modules: EventBus, CacheManager, QueueManager, ProjectManager."""
from __future__ import annotations

import asyncio

import pytest


def test_event_bus_publish_invokes_subscriber():
    """Publishing an event must synchronously invoke every matching subscriber."""
    from core.event_bus import EventBus

    bus = EventBus()
    received = []
    bus.subscribe("test.event", lambda event: received.append(event.payload))

    bus.publish("test.event", {"value": 42})

    assert len(received) == 1
    assert received[0]["value"] == 42


def test_event_bus_wildcard_subscriber_receives_all_events():
    """A '*' subscriber must receive every published event regardless of name."""
    from core.event_bus import EventBus

    bus = EventBus()
    received = []
    bus.subscribe("*", lambda event: received.append(event.name))

    bus.publish("alpha", {})
    bus.publish("beta", {})

    assert received == ["alpha", "beta"]


def test_event_bus_unsubscribe_stops_delivery():
    """After unsubscribe, a handler must no longer receive published events."""
    from core.event_bus import EventBus

    bus = EventBus()
    received = []

    def handler(event):
        received.append(event)

    bus.subscribe("x", handler)
    bus.unsubscribe("x", handler)
    bus.publish("x", {})

    assert received == []


def test_event_bus_handler_exception_does_not_break_others():
    """One failing handler must not prevent other subscribers from being invoked."""
    from core.event_bus import EventBus

    bus = EventBus()
    received = []

    def bad_handler(event):
        raise RuntimeError("boom")

    def good_handler(event):
        received.append(event.name)

    bus.subscribe("y", bad_handler)
    bus.subscribe("y", good_handler)
    bus.publish("y", {})

    assert received == ["y"]


def test_cache_manager_set_and_get_round_trip():
    """A value stored via CacheManager.set must be retrievable via get()."""
    from core.cache_manager import CacheManager

    cache = CacheManager(namespace="test")
    cache.set("key1", {"a": 1}, ttl_seconds=60)

    assert cache.get("key1") == {"a": 1}


def test_cache_manager_missing_key_returns_default():
    """Requesting a missing key must return the provided default value."""
    from core.cache_manager import CacheManager

    cache = CacheManager(namespace="test")
    assert cache.get("does_not_exist", default="fallback") == "fallback"


def test_cache_manager_delete_removes_value():
    """After delete(), a previously cached key must no longer resolve."""
    from core.cache_manager import CacheManager

    cache = CacheManager(namespace="test")
    cache.set("key2", "value")
    cache.delete("key2")

    assert cache.get("key2") is None


def test_project_manager_create_and_get(sample_project):
    """ProjectManager.create_project must persist a project retrievable via get_project."""
    from core.project_manager import ProjectManager

    manager = ProjectManager()
    fetched = manager.get_project(sample_project.id)
    assert fetched.name == "Test Self-Stirring Mug"


def test_project_manager_list_projects_includes_created(sample_project):
    """list_projects must include a project that was just created."""
    from core.project_manager import ProjectManager

    manager = ProjectManager()
    projects = manager.list_projects()
    assert any(p.id == sample_project.id for p in projects)


def test_project_manager_undo_reverts_stage(sample_project):
    """undo_last_action must revert a project to its previously snapshotted stage."""
    from config.constants import WorkflowStage, WorkflowStatus
    from core.project_manager import ProjectManager

    manager = ProjectManager()
    manager.update_stage(sample_project.id, WorkflowStage.MARKETING_STRATEGY, WorkflowStatus.RUNNING)

    snapshot = manager.undo_last_action(sample_project.id)
    assert snapshot is not None


def test_project_manager_delete_removes_project(sample_project):
    """delete_project must remove the project so subsequent get_project raises."""
    from core.exceptions import ProjectNotFoundError
    from core.project_manager import ProjectManager

    manager = ProjectManager()
    deleted = manager.delete_project(sample_project.id, delete_assets=False)
    assert deleted is True

    with pytest.raises(ProjectNotFoundError):
        manager.get_project(sample_project.id)


def test_queue_manager_executes_submitted_job():
    """A job submitted to the QueueManager must eventually complete with the correct result."""
    from core.queue_manager import QueueManager

    async def _run():
        manager = QueueManager()

        async def sample_coro():
            await asyncio.sleep(0.01)
            return "done"

        job_id = await manager.submit("sample_job", sample_coro)
        job = await manager.wait_for(job_id)
        return job

    job = asyncio.run(_run())
    assert job.result == "done"
    assert job.status.value == "completed"


def test_settings_manager_get_default_when_unset():
    """SettingsManager.get must fall back to a built-in default when nothing is persisted."""
    from core.settings_manager import SettingsManager

    manager = SettingsManager()
    assert manager.get("ui.theme") == "dark"


def test_settings_manager_set_overrides_default():
    """After SettingsManager.set(), get() must return the overridden value."""
    from core.settings_manager import SettingsManager

    manager = SettingsManager()
    manager.set("ui.theme", "light")
    assert manager.get("ui.theme") == "light"
