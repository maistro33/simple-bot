"""
Subtitle Engine — pipeline stage 12: generates timed SRT/VTT subtitle
files from the script and voice-over duration.

Timing is computed deterministically (proportional word-count
distribution across the narration's duration) rather than via an LLM,
since caption timing must be precise and reproducible, not "creative".
"""
from __future__ import annotations

import re
from typing import Any

from config.constants import AssetType, WorkflowStage
from core.asset_manager import AssetManager
from core.exceptions import StageExecutionError
from database.repositories import SubtitleRepository
from database.session import session_scope
from engines.base_engine import BaseEngine

_MAX_CHARS_PER_CUE = 42
_MAX_WORDS_PER_CUE = 8


class SubtitleEngine(BaseEngine):
    """Splits the narration script into caption cues and renders SRT + VTT files."""

    def __init__(self, *args, asset_manager: AssetManager | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._subtitle_repo = SubtitleRepository()
        self._asset_manager = asset_manager or AssetManager()

    def execute(self, project_id: str, context: dict[str, Any]) -> dict[str, Any]:
        """Build subtitle cues, render SRT/VTT files and persist both to the database."""
        script = context.get("script")
        duration_seconds = context.get("voice_duration_seconds") or (
            script.get("beats", [{}])[-1].get("approx_seconds", 60) if script else 60
        )

        if not script or not script.get("full_script"):
            raise StageExecutionError(
                WorkflowStage.SUBTITLE_GENERATION.value, "Missing full_script from prior stage.", recoverable=False
            )

        cues = self._build_cues(script["full_script"], float(duration_seconds))
        srt_content = self._render_srt(cues)
        vtt_content = self._render_vtt(cues)

        srt_asset = self._asset_manager.save_text(
            project_id, AssetType.SUBTITLE, "subtitles.srt", srt_content, source_stage=WorkflowStage.SUBTITLE_GENERATION.value
        )
        self._asset_manager.save_text(
            project_id, AssetType.SUBTITLE, "subtitles.vtt", vtt_content, source_stage=WorkflowStage.SUBTITLE_GENERATION.value
        )

        with session_scope() as session:
            self._subtitle_repo.create(
                session,
                project_id=project_id,
                format="srt",
                file_path=srt_asset.file_path,
                raw_content=srt_content,
                cues=cues,
                language="en",
            )

        self.logger.info("Generated {} subtitle cues for project {}", len(cues), project_id)
        return {"subtitle_cues": cues, "subtitle_srt_path": srt_asset.file_path}

    def _build_cues(self, script_text: str, total_duration_seconds: float) -> list[dict[str, Any]]:
        """Split narration text into short caption-sized cues, evenly timed by word count."""
        words = re.sub(r"\s+", " ", script_text.strip()).split(" ")
        chunks: list[str] = []
        current: list[str] = []

        for word in words:
            candidate = " ".join(current + [word])
            if len(current) >= _MAX_WORDS_PER_CUE or len(candidate) > _MAX_CHARS_PER_CUE:
                if current:
                    chunks.append(" ".join(current))
                current = [word]
            else:
                current.append(word)
        if current:
            chunks.append(" ".join(current))

        total_words = max(len(words), 1)
        cues: list[dict[str, Any]] = []
        elapsed = 0.0
        for chunk in chunks:
            chunk_word_count = len(chunk.split())
            chunk_duration = total_duration_seconds * (chunk_word_count / total_words)
            start = round(elapsed, 2)
            end = round(elapsed + max(chunk_duration, 0.6), 2)
            cues.append({"start": start, "end": end, "text": chunk})
            elapsed = end

        return cues

    @staticmethod
    def _format_timestamp_srt(seconds: float) -> str:
        """Format seconds as an SRT timestamp: HH:MM:SS,mmm."""
        millis = int(round(seconds * 1000))
        hours, remainder = divmod(millis, 3_600_000)
        minutes, remainder = divmod(remainder, 60_000)
        secs, ms = divmod(remainder, 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"

    @staticmethod
    def _format_timestamp_vtt(seconds: float) -> str:
        """Format seconds as a WebVTT timestamp: HH:MM:SS.mmm."""
        millis = int(round(seconds * 1000))
        hours, remainder = divmod(millis, 3_600_000)
        minutes, remainder = divmod(remainder, 60_000)
        secs, ms = divmod(remainder, 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{ms:03d}"

    def _render_srt(self, cues: list[dict[str, Any]]) -> str:
        """Render subtitle cues as a standard ``.srt`` file body."""
        lines = []
        for index, cue in enumerate(cues, start=1):
            lines.append(str(index))
            lines.append(
                f"{self._format_timestamp_srt(cue['start'])} --> {self._format_timestamp_srt(cue['end'])}"
            )
            lines.append(cue["text"])
            lines.append("")
        return "\n".join(lines)

    def _render_vtt(self, cues: list[dict[str, Any]]) -> str:
        """Render subtitle cues as a standard ``.vtt`` file body."""
        lines = ["WEBVTT", ""]
        for cue in cues:
            lines.append(
                f"{self._format_timestamp_vtt(cue['start'])} --> {self._format_timestamp_vtt(cue['end'])}"
            )
            lines.append(cue["text"])
            lines.append("")
        return "\n".join(lines)
