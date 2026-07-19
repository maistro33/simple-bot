"""Unit tests for the database models and repositories."""
from __future__ import annotations

from config.constants import AssetType, WorkflowStatus
from database.repositories import AssetRepository, ScriptRepository
from database.repositories.project_repository import ProjectRepository
from database.session import session_scope


def test_create_and_fetch_project():
    """A created project must be retrievable by ID with the correct fields."""
    repo = ProjectRepository()
    with session_scope() as session:
        project = repo.create(session, name="Widget", raw_input="A cool widget")
        project_id = project.id

    with session_scope() as session:
        fetched = repo.get_by_id(session, project_id)
        assert fetched is not None
        assert fetched.name == "Widget"
        assert fetched.raw_input == "A cool widget"


def test_project_cascade_delete_removes_children():
    """Deleting a project must cascade-delete its dependent asset rows."""
    project_repo = ProjectRepository()
    asset_repo = AssetRepository()

    with session_scope() as session:
        project = project_repo.create(session, name="Cascade Test", raw_input="test")
        project_id = project.id
        asset_repo.create(
            session,
            project_id=project_id,
            asset_type=AssetType.IMAGE,
            file_path="/tmp/fake.png",
            file_name="fake.png",
        )

    with session_scope() as session:
        assets_before = asset_repo.list_by_project(session, project_id)
        assert len(assets_before) == 1

    with session_scope() as session:
        project_repo.delete(session, project_id)

    with session_scope() as session:
        assets_after = asset_repo.list_by_project(session, project_id)
        assert len(assets_after) == 0


def test_get_by_status_filters_correctly():
    """get_by_status should only return projects matching the requested status."""
    repo = ProjectRepository()
    with session_scope() as session:
        p1 = repo.create(session, name="P1", raw_input="x", status=WorkflowStatus.RUNNING)
        repo.create(session, name="P2", raw_input="y", status=WorkflowStatus.COMPLETED)

    with session_scope() as session:
        running = repo.get_by_status(session, WorkflowStatus.RUNNING)
        assert any(p.id == p1.id for p in running)
        assert all(p.status == WorkflowStatus.RUNNING for p in running)


def test_script_repository_get_latest_returns_highest_version():
    """ScriptRepository.get_latest must return the script with the highest version number."""
    project_repo = ProjectRepository()
    script_repo = ScriptRepository()

    with session_scope() as session:
        project = project_repo.create(session, name="Script Test", raw_input="x")
        project_id = project.id
        script_repo.create(
            session, project_id=project_id, version=1, hook_text="hook1",
            full_script="script v1", estimated_duration_seconds=30,
        )
        script_repo.create(
            session, project_id=project_id, version=2, hook_text="hook2",
            full_script="script v2", estimated_duration_seconds=45,
        )

    with session_scope() as session:
        latest = script_repo.get_latest(session, project_id)
        assert latest.version == 2
        assert latest.full_script == "script v2"


def test_base_repository_update_and_delete():
    """Generic update/delete on BaseRepository should mutate/remove the correct row."""
    repo = ProjectRepository()
    with session_scope() as session:
        project = repo.create(session, name="Original", raw_input="x")
        project_id = project.id

    with session_scope() as session:
        repo.update(session, project_id, name="Updated")

    with session_scope() as session:
        fetched = repo.get_by_id(session, project_id)
        assert fetched.name == "Updated"

    with session_scope() as session:
        deleted = repo.delete(session, project_id)
        assert deleted is True

    with session_scope() as session:
        assert repo.get_by_id(session, project_id) is None
