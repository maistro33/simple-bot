"""
Asset Manager — the single point of contact for writing any generated
file (image, audio, video, subtitle, document) to disk and registering
it in the ``assets`` table so it can be discovered later by the Export
Manager or the (future) GUI.
"""
from __future__ import annotations

import hashlib
import mimetypes
import shutil
from pathlib import Path

from config import get_settings
from config.constants import AssetType
from core.exceptions import AssetError
from core.logger import get_logger
from database.models.asset import Asset
from database.repositories.domain_repositories import AssetRepository
from database.session import session_scope

logger = get_logger(__name__)


class AssetManager:
    """
    Persists binary/text assets under ``assets/<project_id>/`` (or the
    dedicated ``voices/`` directory for audio) and records metadata in
    the database via :class:`AssetRepository`.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._repo = AssetRepository()

    def _project_dir(self, project_id: str, asset_type: AssetType) -> Path:
        """Compute (and create) the destination directory for a given asset type."""
        base = self._settings.voices_dir if asset_type == AssetType.AUDIO else self._settings.assets_dir
        directory = base / project_id / asset_type.value
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @staticmethod
    def _checksum(path: Path) -> str:
        """Compute the SHA-256 checksum of a file on disk."""
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def save_bytes(
        self,
        project_id: str,
        asset_type: AssetType,
        file_name: str,
        content: bytes,
        source_stage: str | None = None,
        extra_metadata: dict | None = None,
    ) -> Asset:
        """
        Write raw bytes to disk under the appropriate project asset folder
        and register the resulting file as an :class:`Asset` row.

        Args:
            project_id: Owning project's ID.
            asset_type: The :class:`AssetType` classification of this file.
            file_name: The desired file name (sanitised automatically).
            content: The raw file bytes to write.
            source_stage: The pipeline stage that produced this asset.
            extra_metadata: Arbitrary JSON-serialisable metadata.

        Raises:
            AssetError: If the file cannot be written to disk.
        """
        safe_name = self._sanitise_filename(file_name)
        directory = self._project_dir(project_id, asset_type)
        destination = directory / safe_name

        try:
            destination.write_bytes(content)
        except OSError as exc:
            raise AssetError(f"Failed to write asset '{safe_name}': {exc}") from exc

        mime_type, _ = mimetypes.guess_type(str(destination))
        checksum = self._checksum(destination)

        with session_scope() as session:
            asset = self._repo.create(
                session,
                project_id=project_id,
                asset_type=asset_type,
                file_path=str(destination),
                file_name=safe_name,
                mime_type=mime_type,
                size_bytes=destination.stat().st_size,
                checksum_sha256=checksum,
                source_stage=source_stage,
                extra_metadata=extra_metadata,
            )
            session.flush()
            asset_id = asset.id

        logger.info("Saved asset '{}' ({} bytes) for project {}", safe_name, len(content), project_id)
        with session_scope() as session:
            return self._repo.get_by_id(session, asset_id)

    def save_text(
        self,
        project_id: str,
        asset_type: AssetType,
        file_name: str,
        content: str,
        source_stage: str | None = None,
        extra_metadata: dict | None = None,
        encoding: str = "utf-8",
    ) -> Asset:
        """Convenience wrapper around :meth:`save_bytes` for text content."""
        return self.save_bytes(
            project_id, asset_type, file_name, content.encode(encoding), source_stage, extra_metadata
        )

    def copy_external_file(
        self,
        project_id: str,
        asset_type: AssetType,
        source_path: Path,
        source_stage: str | None = None,
    ) -> Asset:
        """Copy an externally-produced file (e.g. an OpenAI image download) into asset storage."""
        if not source_path.exists():
            raise AssetError(f"Source file does not exist: {source_path}")
        content = source_path.read_bytes()
        return self.save_bytes(project_id, asset_type, source_path.name, content, source_stage)

    def list_assets(self, project_id: str) -> list[Asset]:
        """Return every asset registered for a project."""
        with session_scope() as session:
            return list(self._repo.list_by_project(session, project_id))

    def delete_project_assets(self, project_id: str) -> None:
        """Remove a project's entire asset directory tree from disk."""
        for base in (self._settings.assets_dir, self._settings.voices_dir):
            target = base / project_id
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
        logger.info("Deleted on-disk assets for project {}", project_id)

    @staticmethod
    def _sanitise_filename(file_name: str) -> str:
        """Strip path separators and unsafe characters from a candidate filename."""
        cleaned = Path(file_name).name
        cleaned = "".join(c for c in cleaned if c.isalnum() or c in "._- ")
        return cleaned or "unnamed_file"
