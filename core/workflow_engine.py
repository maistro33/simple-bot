"""
Workflow Engine — the orchestrator that drives a project through every
pipeline stage in order, accumulating context, persisting progress
after each stage, publishing events, and delegating retry/failure
handling to the Recovery Manager.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable

from config.constants import WorkflowStage, WorkflowStatus
from core.event_bus import get_event_bus
from core.exceptions import StageExecutionError
from core.logger import get_logger
from core.project_manager import ProjectManager, get_project_manager
from core.recovery_manager import RecoveryManager
from database.repositories.project_repository import ProjectRepository
from database.session import session_scope
from engines.prompt_engine import PromptEngine
from engines.report_engine import ReportEngine
from engines.research_engine import ResearchEngine
from engines.script_engine import ScriptEngine
from engines.seo_engine import SeoEngine
from engines.storyboard_engine import StoryboardEngine
from engines.strategy_engine import StrategyEngine
from engines.subtitle_engine import SubtitleEngine
from engines.thumbnail_engine import ThumbnailEngine
from engines.video_engine import VideoEngine
from engines.voice_engine import VoiceEngine

logger = get_logger(__name__)

_STAGE_ENGINE_ORDER: list[WorkflowStage] = [
    WorkflowStage.PRODUCT_ANALYSIS,
    WorkflowStage.MARKETING_STRATEGY,
    WorkflowStage.SCRIPT_GENERATION,
    WorkflowStage.STORYBOARD_GENERATION,
    WorkflowStage.PROMPT_GENERATION,
    WorkflowStage.VOICE_GENERATION,
    WorkflowStage.SUBTITLE_GENERATION,
    WorkflowStage.THUMBNAIL_GENERATION,
    WorkflowStage.SEO_GENERATION,
    WorkflowStage.REPORT_GENERATION,
    WorkflowStage.EXPORT,
]


class WorkflowEngine:
    """
    Drives a single project through the entire content-generation
    pipeline, stage by stage, persisting progress and accumulated
    context after every step so execution can be paused, resumed, or
    retried from the last successful stage.
    """

    def __init__(self) -> None:
        self._project_manager: ProjectManager = get_project_manager()
        self._project_repo = ProjectRepository()
        self._recovery = RecoveryManager()
        self._event_bus = get_event_bus()

        self._research_engine = ResearchEngine()
        self._strategy_engine = StrategyEngine()
        self._script_engine = ScriptEngine()
        self._storyboard_engine = StoryboardEngine()
        self._prompt_engine = PromptEngine()
        self._voice_engine = VoiceEngine()
        self._subtitle_engine = SubtitleEngine()
        self._thumbnail_engine = ThumbnailEngine()
        self._seo_engine = SeoEngine()
        self._video_engine = VideoEngine()
        self._report_engine = ReportEngine()

        self._stage_handlers: dict[WorkflowStage, Callable[[str, dict], dict]] = {
            WorkflowStage.PRODUCT_ANALYSIS: self._research_engine.execute,
            WorkflowStage.MARKETING_STRATEGY: self._strategy_engine.execute,
            WorkflowStage.SCRIPT_GENERATION: self._script_engine.execute,
            WorkflowStage.STORYBOARD_GENERATION: self._storyboard_engine.execute,
            WorkflowStage.PROMPT_GENERATION: self._prompt_engine.execute,
            WorkflowStage.VOICE_GENERATION: self._voice_engine.execute,
            WorkflowStage.SUBTITLE_GENERATION: self._subtitle_engine.execute,
            WorkflowStage.THUMBNAIL_GENERATION: self._thumbnail_engine.execute,
            WorkflowStage.SEO_GENERATION: self._seo_engine.execute,
            WorkflowStage.REPORT_GENERATION: self._report_engine.execute,
            WorkflowStage.EXPORT: self._run_export_stage,
        }

    def run(
        self, project_id: str, resume: bool = False, cancel_event: "threading.Event | None" = None
    ) -> dict[str, Any]:
        """
        Execute the full pipeline for a project from its current stage
        through to completion.
        """
        project = self._project_manager.get_project(project_id)
        context: dict[str, Any] = {"raw_input": project.raw_input, "stage_durations": {}}

        start_index = 0
        if resume:
            try:
                start_index = _STAGE_ENGINE_ORDER.index(project.current_stage)
            except ValueError:
                start_index = 0
            context.update(self._hydrate_context_from_db(project_id))

        self._project_manager.update_stage(project_id, _STAGE_ENGINE_ORDER[start_index], WorkflowStatus.RUNNING)
        self._event_bus.publish("workflow.started", {"project_id": project_id})

        try:
            for stage in _STAGE_ENGINE_ORDER[start_index:]:
                if cancel_event is not None and cancel_event.is_set():
                    self._project_manager.update_stage(project_id, stage, WorkflowStatus.PAUSED)
                    self._event_bus.publish("workflow.paused", {"project_id": project_id, "stage": stage.value})
                    logger.info("Workflow for project {} paused before stage '{}'.", project_id, stage.value)
                    return context

                context = self._execute_stage(project_id, stage, context)

            self._project_manager.update_stage(project_id, WorkflowStage.FINISHED, WorkflowStatus.COMPLETED)
            self._event_bus.publish("workflow.completed", {"project_id": project_id})
            logger.info("Workflow completed successfully for project {}", project_id)
            return context

        except StageExecutionError as exc:
            self._recovery.mark_project_failed(project_id, str(exc))
            self._event_bus.publish("workflow.failed", {"project_id": project_id, "error": str(exc)})
            raise

    def _execute_stage(self, project_id: str, stage: WorkflowStage, context: dict[str, Any]) -> dict[str, Any]:
        """Execute a single stage with retry support and merge its output into the running context."""
        handler = self._stage_handlers[stage]
        self._project_manager.update_stage(project_id, stage, WorkflowStatus.RUNNING)
        self._event_bus.publish("stage.started", {"project_id": project_id, "stage": stage.value})

        start_time = time.monotonic()
        result = self._recovery.execute_with_retry(stage.value, lambda: handler(project_id, context))
        elapsed = round(time.monotonic() - start_time, 2)

        context = {**context, **result}
        context["stage_durations"][stage.value] = elapsed

        self._event_bus.publish(
            "stage.completed", {"project_id": project_id, "stage": stage.value, "duration_seconds": elapsed}
        )
        logger.info("Stage '{}' completed for project {} in {}s", stage.value, project_id, elapsed)
        return context

    def _hydrate_context_from_db(self, project_id: str) -> dict[str, Any]:
        """
        Reconstruct the in-memory pipeline context from previously persisted
        database rows, so resuming a project part-way through the pipeline
        gives downstream stages the same data they would have had if the
        run had never been interrupted.
        """
        from database.repositories import (
            PromptRepository,
            ScriptRepository,
            SeoRepository,
            StoryboardRepository,
            SubtitleRepository,
            ThumbnailRepository,
            VoiceRepository,
        )

        context: dict[str, Any] = {}

        with session_scope() as session:
            project = self._project_repo.get_by_id(session, project_id)
            if project is None:
                return context

            if project.research_data:
                context["product_profile"] = project.research_data.get("product_profile")
                context["competitors"] = project.research_data.get("competitors")
            if project.audience_data:
                context["audience"] = project.audience_data
            if project.category:
                context["category"] = project.category.value
            if project.brand_name:
                context["brand_name"] = project.brand_name
            if project.strategy_data:
                context["strategy"] = project.strategy_data

            latest_script = ScriptRepository().get_latest(session, project_id)
            if latest_script is not None:
                context["script"] = {
                    "full_script": latest_script.full_script,
                    "call_to_action": latest_script.call_to_action,
                    "tone": latest_script.tone,
                    "beats": latest_script.beats,
                }
                context["hook"] = {"text": latest_script.hook_text, "style": latest_script.hook_style}

            storyboard_rows = StoryboardRepository().list_ordered(session, project_id)
            if storyboard_rows:
                context["storyboard"] = [
                    {
                        "scene_number": s.scene_number,
                        "scene_title": s.scene_title,
                        "narration_text": s.narration_text,
                        "visual_description": s.visual_description,
                        "camera_angle": s.camera_angle,
                        "duration_seconds": s.duration_seconds,
                        "on_screen_text": s.on_screen_text,
                        "transition": s.transition,
                        "sound_effect": s.sound_effect,
                    }
                    for s in storyboard_rows
                ]

            prompt_rows = PromptRepository().list_by_project(session, project_id)
            if prompt_rows:
                context["prompts"] = [
                    {
                        "scene_number": p.scene_number,
                        "positive_prompt": p.positive_prompt,
                        "negative_prompt": p.negative_prompt,
                        "lighting": p.lighting,
                        "camera_motion": p.camera_motion,
                        "style_reference": p.style_reference,
                    }
                    for p in prompt_rows
                ]

            voice_rows = VoiceRepository().list_by_project(session, project_id)
            if voice_rows:
                latest_voice = voice_rows[-1]
                context["voice_over_path"] = latest_voice.file_path
                context["voice_duration_seconds"] = latest_voice.duration_seconds

            subtitle_rows = SubtitleRepository().list_by_project(session, project_id)
            if subtitle_rows:
                context["subtitle_cues"] = subtitle_rows[-1].cues

            thumbnail_rows = ThumbnailRepository().list_by_project(session, project_id)
            if thumbnail_rows:
                context["thumbnails"] = [
                    {
                        "concept_title": t.concept_title,
                        "headline_text": t.headline_text,
                        "file_path": t.file_path,
                        "is_selected": t.is_selected,
                    }
                    for t in thumbnail_rows
                ]

            seo_rows = SeoRepository().list_by_project(session, project_id)
            if seo_rows:
                latest_seo = seo_rows[-1]
                context["seo"] = {
                    "titles": latest_seo.titles,
                    "description": latest_seo.description,
                    "tags": latest_seo.tags,
                    "hashtags": latest_seo.hashtags,
                    "primary_keyword": latest_seo.primary_keyword,
                    "secondary_keywords": latest_seo.secondary_keywords,
                    "pinned_comment": latest_seo.pinned_comment,
                }

        return context

    def _run_export_stage(self, project_id: str, context: dict[str, Any]) -> dict[str, Any]:
        """
        Final stage: assemble the video (Video Engine) and bundle everything
        (Export Manager) into the delivery archive.
        """
        video_result = self._video_engine.execute(project_id, context)
        context = {**context, **video_result}

        from core.export_manager import ExportManager

        export_manager = ExportManager()
        export_path = export_manager.export_project(project_id)
        return {**video_result, "export_path": str(export_path)}
