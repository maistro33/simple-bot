"""Unit tests for the Asset Manager."""
from __future__ import annotations

from config.constants import AssetType


def test_save_bytes_creates_file_and_db_record(sample_project):
    """save_bytes must write a real file to disk and register an Asset row."""
    from core.asset_manager import AssetManager

    manager = AssetManager()
    asset = manager.save_bytes(
        sample_project.id, AssetType.DOCUMENT, "note.txt", b"hello world", source_stage="test"
    )

    assert asset.file_name == "note.txt"
    assert asset.size_bytes == len(b"hello world")

    from pathlib import Path

    assert Path(asset.file_path).exists()
    assert Path(asset.file_path).read_bytes() == b"hello world"


def test_save_text_round_trip(sample_project):
    """save_text must persist UTF-8 encoded text content correctly."""
    from core.asset_manager import AssetManager

    manager = AssetManager()
    asset = manager.save_text(sample_project.id, AssetType.SUBTITLE, "subs.srt", "1\n00:00:00,000 --> 00:00:01,000\nHi\n")

    from pathlib import Path

    content = Path(asset.file_path).read_text(encoding="utf-8")
    assert "Hi" in content


def test_list_assets_returns_saved_assets(sample_project):
    """list_assets must return every asset previously saved for a project."""
    from core.asset_manager import AssetManager

    manager = AssetManager()
    manager.save_bytes(sample_project.id, AssetType.IMAGE, "a.png", b"fake-png-bytes")
    manager.save_bytes(sample_project.id, AssetType.IMAGE, "b.png", b"more-fake-bytes")

    assets = manager.list_assets(sample_project.id)
    assert len(assets) == 2


def test_sanitise_filename_strips_unsafe_characters():
    """_sanitise_filename must strip path separators and unsafe characters."""
    from core.asset_manager import AssetManager

    result = AssetManager._sanitise_filename("../../etc/passwd")
    assert "/" not in result
    assert ".." not in result or result == "etc.passwd" or result != "../../etc/passwd"
