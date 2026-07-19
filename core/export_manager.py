"""
Export Manager — bundles a completed project's script, storyboard,
prompts, voice-over, subtitles, thumbnails, SEO package and report into
a single delivery archive (or plain folder) for the end user.
"""
from __future__ import annotations

import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from config import get_settings
from config.constants import ExportFormat
from core.exceptions import ExportError
from core.logger import get_logger
from database.repositories import (
    ExportRepository,
    PromptRepository,
    ReportRepository,
    ScriptRepository,
    SeoRepository,
    StoryboardRepository,
    SubtitleRepository,
    ThumbnailRepository,
    VoiceRepository,
)
from database.repositories.domain_repositories import AssetRepository
from database.repositories.project_repository import ProjectRepository
from database.session import session_scope

logger = get_logger(__name__)


class ExportManager:
    """
    Collects every artefact produced for a project and writes a
    self-contained, human-browsable export bundle to
    ``exports/<project_id>_<timestamp>/``.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._project_repo = ProjectRepository()
        self._script_repo = ScriptRepository()
        self._storyboard_repo = StoryboardRepository()
        self._prompt_repo = PromptRepository()
        self._voice_repo = VoiceRepository()
        self._subtitle_repo = SubtitleRepository()
        self._thumbnail_repo = ThumbnailRepository()
        self._seo_repo = SeoRepository()
        self._report_repo = ReportRepository()
        self._asset_repo = AssetRepository()
        self._export_repo = ExportRepository()

    def export_project(
        self, project_id: str, export_format: ExportFormat = ExportFormat.ZIP
    ) -> Path:
        """
        Build and persist a complete export bundle for ``project_id``.

        Args:
            project_id: The project to export.
            export_format: Whether to leave the bundle as a plain folder
                or additionally compress it into a ``.zip`` archive.

        Returns:
            Path to the resulting bundle (folder or zip file).

        Raises:
            ExportError: If the referenced project does not exist.
        """
        with session_scope() as session:
            project = self._project_repo.get_by_id(session, project_id)
            if project is None:
                raise ExportError(f"Cannot export unknown project id={project_id}")

            bundle = {
                "project": {
                    "id": project.id,
                    "name": project.name,
                    "product_title": project.product_title,
                    "product_url": project.product_url,
                    "brand_name": project.brand_name,
                    "category": project.category.value,
                    "status": project.status.value,
                    "created_at": project.created_at.isoformat(),
                },
                "strategy": project.strategy_data,
                "research": project.research_data,
                "audience": project.audience_data,
            }

            scripts = self._script_repo.list_by_project(session, project_id)
            bundle["scripts"] = [
                {
                    "version": s.version,
                    "hook_text": s.hook_text,
                    "hook_style": s.hook_style,
                    "full_script": s.full_script,
                    "call_to_action": s.call_to_action,
                    "estimated_duration_seconds": s.estimated_duration_seconds,
                    "beats": s.beats,
                }
                for s in scripts
            ]

            storyboards = self._storyboard_repo.list_ordered(session, project_id)
            bundle["storyboard"] = [
                {
                    "scene_number": sb.scene_number,
                    "scene_title": sb.scene_title,
                    "narration_text": sb.narration_text,
                    "visual_description": sb.visual_description,
                    "camera_angle": sb.camera_angle,
                    "duration_seconds": sb.duration_seconds,
                    "on_screen_text": sb.on_screen_text,
                    "transition": sb.transition,
                    "sound_effect": sb.sound_effect,
                }
                for sb in storyboards
            ]

            prompts = self._prompt_repo.list_by_project(session, project_id)
            bundle["prompts"] = [
                {
                    "scene_number": p.scene_number,
                    "prompt_type": p.prompt_type,
                    "positive_prompt": p.positive_prompt,
                    "negative_prompt": p.negative_prompt,
                    "aspect_ratio": p.aspect_ratio,
                    "camera_motion": p.camera_motion,
                    "lighting": p.lighting,
                }
                for p in prompts
            ]

            seo_entries = self._seo_repo.list_by_project(session, project_id)
            bundle["seo"] = [
                {
                    "titles": s.titles,
                    "description": s.description,
                    "tags": s.tags,
                    "hashtags": s.hashtags,
                    "primary_keyword": s.primary_keyword,
                    "secondary_keywords": s.secondary_keywords,
                    "pinned_comment": s.pinned_comment,
                }
                for s in seo_entries
            ]

            reports = self._report_repo.list_by_project(session, project_id)
            bundle["reports"] = [
                {
                    "summary": r.summary,
                    "strengths": r.strengths,
                    "risks": r.risks,
                    "recommendations": r.recommendations,
                    "quality_score": r.quality_score,
                }
                for r in reports
            ]

            thumbnails = self._thumbnail_repo.list_by_project(session, project_id)
            subtitles = self._subtitle_repo.list_by_project(session, project_id)
            voices = self._voice_repo.list_by_project(session, project_id)
            assets = self._asset_repo.list_by_project(session, project_id)

            thumbnail_paths = [t.file_path for t in thumbnails if t.file_path]
            subtitle_records = [(s.format, s.raw_content) for s in subtitles]
            voice_paths = [v.file_path for v in voices if v.file_path]
            asset_paths = [(a.file_path, a.asset_type.value) for a in assets]

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        bundle_dir = self._settings.exports_dir / f"{project_id}_{timestamp}"
        bundle_dir.mkdir(parents=True, exist_ok=True)

        (bundle_dir / "project_bundle.json").write_text(
            json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        if bundle["scripts"]:
            (bundle_dir / "script.txt").write_text(
                bundle["scripts"][-1]["full_script"], encoding="utf-8"
            )

        for fmt, content in subtitle_records:
            (bundle_dir / f"subtitles.{fmt}").write_text(content, encoding="utf-8")

        media_dir = bundle_dir / "media"
        media_dir.mkdir(exist_ok=True)
        for path_str in [*thumbnail_paths, *voice_paths, *[p for p, _ in asset_paths]]:
            if not path_str:
                continue
            source = Path(path_str)
            if source.exists():
                shutil.copy2(source, media_dir / source.name)

        included_count = len(thumbnail_paths) + len(voice_paths) + len(asset_paths)
        final_path: Path = bundle_dir

        if export_format == ExportFormat.ZIP:
            zip_path = bundle_dir.with_suffix(".zip")
            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for file_path in bundle_dir.rglob("*"):
                    if file_path.is_file():
                        zf.write(file_path, arcname=file_path.relative_to(bundle_dir))
            shutil.rmtree(bundle_dir)
            final_path = zip_path

        with session_scope() as session:
            self._export_repo.create(
                session,
                project_id=project_id,
                export_format=export_format,
                file_path=str(final_path),
                size_bytes=self._calculate_size(final_path),
                included_assets_count=included_count,
            )

        logger.info("Exported project {} to {}", project_id, final_path)
        return final_path

    @staticmethod
    def _calculate_size(path: Path) -> int:
        """Return the total size in bytes of a file, or recursively of a folder."""
        if path.is_file():
            return path.stat().st_size
        return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
