"""
Backup Manager — creates point-in-time archive snapshots of a project's
database row (as JSON) plus its on-disk asset tree, independent of the
final user-facing Export Manager bundles. Backups exist purely for
disaster recovery, not for delivery to the end user.
"""
from __future__ import annotations

import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from config import get_settings
from core.asset_manager import AssetManager
from core.exceptions import AssetError
from core.logger import get_logger
from database.repositories.project_repository import ProjectRepository
from database.session import session_scope

logger = get_logger(__name__)


class BackupManager:
    """Creates and restores lightweight disaster-recovery backups for projects."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._project_repo = ProjectRepository()
        self._asset_manager = AssetManager()
        self._backup_root = self._settings.exports_dir / "_backups"
        self._backup_root.mkdir(parents=True, exist_ok=True)

    def create_backup(self, project_id: str) -> Path:
        """
        Create a ``.zip`` backup containing the project's serialised state
        and every on-disk asset, and return the resulting archive path.
        """
        with session_scope() as session:
            project = self._project_repo.get_by_id(session, project_id)
            if project is None:
                raise AssetError(f"Cannot back up unknown project id={project_id}")
            project_snapshot = {
                "id": project.id,
                "name": project.name,
                "raw_input": project.raw_input,
                "current_stage": project.current_stage.value,
                "status": project.status.value,
                "research_data": project.research_data,
                "audience_data": project.audience_data,
                "strategy_data": project.strategy_data,
                "created_at": project.created_at.isoformat(),
                "updated_at": project.updated_at.isoformat(),
            }

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        archive_path = self._backup_root / f"{project_id}_{timestamp}.zip"

        with zipfile.ZipFile(archive_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("project.json", json.dumps(project_snapshot, indent=2, ensure_ascii=False))

            for base_dir in (self._settings.assets_dir / project_id, self._settings.voices_dir / project_id):
                if base_dir.exists():
                    for file_path in base_dir.rglob("*"):
                        if file_path.is_file():
                            arcname = f"assets/{file_path.relative_to(base_dir.parent.parent)}"
                            zf.write(file_path, arcname=arcname)

        logger.info("Created backup for project {} at {}", project_id, archive_path)
        return archive_path

    def list_backups(self, project_id: str) -> list[Path]:
        """Return every backup archive on disk for a given project, newest first."""
        backups = sorted(
            self._backup_root.glob(f"{project_id}_*.zip"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return backups

    def prune_old_backups(self, project_id: str, keep_latest: int = 5) -> int:
        """Delete all but the ``keep_latest`` most recent backups for a project."""
        backups = self.list_backups(project_id)
        to_delete = backups[keep_latest:]
        for path in to_delete:
            path.unlink(missing_ok=True)
        if to_delete:
            logger.info("Pruned {} old backup(s) for project {}", len(to_delete), project_id)
        return len(to_delete)

    def restore_snapshot(self, backup_path: Path, destination: Path) -> dict:
        """
        Extract a backup archive's ``project.json`` snapshot and restore its
        asset files to ``destination``. Returns the parsed project snapshot.
        """
        if not backup_path.exists():
            raise AssetError(f"Backup archive not found: {backup_path}")

        destination.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(backup_path, mode="r") as zf:
            zf.extractall(destination)
            snapshot = json.loads(zf.read("project.json").decode("utf-8"))

        logger.info("Restored backup {} into {}", backup_path, destination)
        return snapshot
