"""
Full end-to-end integration test: drives a project through the ENTIRE
16-stage pipeline via the real :class:`WorkflowEngine`, with only the
external network-dependent boundaries (AI text/JSON completion, image
generation, video rendering) replaced by deterministic fakes. Every
other layer — database persistence, engines, the export bundle, the
event bus — runs for real, proving the whole system is correctly wired
end-to-end without requiring live API credentials in CI.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


class _IntegrationFakeAIManager:
    """Routes every generate_json call to a canned response keyed by system-prompt keyword."""

    _RESPONSES: dict[str, dict[str, Any]] = {
        "senior e-commerce product analyst": {
            "product_title": "Self-Stirring Travel Mug",
            "product_description": "A mug that stirs your coffee automatically via USB.",
            "key_features": ["auto-stir", "USB rechargeable", "leak-proof lid"],
            "price_range": "$19.99-$24.99",
            "unique_selling_points": ["hands-free stirring", "no more soggy sugar"],
            "target_use_cases": ["commuting", "office desk"],
        },
        "product taxonomy and brand-detection specialist": {
            "category": "home_and_kitchen",
            "brand_name": None,
            "category_confidence": 0.92,
        },
        "consumer market research analyst": {
            "primary_demographic": "busy professionals",
            "age_range": "25-40",
            "pain_points": ["forgetting to stir", "spilling drinks"],
            "desires": ["convenience", "novelty gadgets"],
            "buying_triggers": ["curiosity", "gift potential"],
            "platforms": ["youtube_shorts", "tiktok"],
            "content_tone_recommendation": "energetic and fun",
        },
        "competitive content strategist": {
            "common_angles": ["unboxing", "before/after"],
            "overused_hooks": ["you won't believe this"],
            "content_gaps": ["office use-case content"],
            "differentiation_opportunities": ["focus on office workers"],
        },
        "marketing strategist": {
            "core_angle": "The mug that thinks for you",
            "emotional_driver": "relief from a tiny daily annoyance",
            "content_pillars": ["convenience", "novelty"],
            "recommended_hook_styles": ["curiosity"],
            "recommended_video_length_seconds": 40,
            "call_to_action_strategy": "link in bio for 20% off",
            "posting_strategy": "post 3x per week",
            "differentiation_statement": "the only self-stirring mug under $25",
        },
        "viral short-form video copywriter": {
            "hooks": [
                {"text": "This mug stirs itself. I'm not kidding.", "style": "curiosity", "rationale": "pattern interrupt"},
            ]
        },
        "YouTube Shorts scriptwriter": {
            "full_script": (
                "This mug stirs itself. No more soggy sugar at the bottom of your cup. "
                "Just press the button and watch it spin. Perfect for your morning commute. "
                "Grab yours using the link below before the sale ends."
            ),
            "call_to_action": "Tap the link in bio to grab yours!",
            "tone": "energetic",
            "beats": [
                {"beat_name": "hook", "text": "This mug stirs itself.", "approx_seconds": 3},
                {"beat_name": "body", "text": "No more soggy sugar.", "approx_seconds": 20},
                {"beat_name": "cta", "text": "Grab yours now.", "approx_seconds": 7},
            ],
        },
        "professional video director": {
            "scenes": [
                {
                    "scene_number": 1,
                    "scene_title": "The Reveal",
                    "narration_text": "This mug stirs itself.",
                    "visual_description": "Close-up of the mug spinning coffee on a desk.",
                    "camera_angle": "close-up",
                    "duration_seconds": 3,
                    "on_screen_text": "WAIT FOR IT",
                    "transition": "cut",
                    "sound_effect": "whoosh",
                },
                {
                    "scene_number": 2,
                    "scene_title": "The Benefit",
                    "narration_text": "No more soggy sugar.",
                    "visual_description": "Split screen comparing stirred vs unstirred coffee.",
                    "camera_angle": "medium shot",
                    "duration_seconds": 4,
                    "on_screen_text": None,
                    "transition": "fade",
                    "sound_effect": None,
                },
            ]
        },
        "cinematic AI image/video prompt engineer": {
            "positive_prompt": "photorealistic self-stirring mug on a wooden desk, warm morning light, 50mm lens",
            "negative_prompt": "blurry, distorted, low quality",
            "lighting": "warm morning sunlight",
            "camera_motion": "slow push-in",
            "style_reference": "commercial product photography",
        },
        "YouTube thumbnail strategist": {
            "concepts": [
                {
                    "concept_title": "Shocked Face Concept",
                    "headline_text": "THIS MUG STIRS ITSELF",
                    "visual_description": "Shocked person pointing at spinning mug",
                    "color_scheme": "red and yellow high contrast",
                    "emotion": "shock",
                    "image_prompt": "shocked person pointing at a self-stirring mug, bold colors",
                },
            ]
        },
        "SEO specialist": {
            "titles": [
                "This Mug Stirs Itself?!",
                "The Self-Stirring Mug You Need",
                "No More Stirring Your Coffee",
                "This Gadget Changed My Mornings",
                "Self-Stirring Mug Review",
            ],
            "description": "Discover the self-stirring travel mug that's taking over TikTok. Perfect for busy mornings.",
            "tags": ["self stirring mug", "coffee gadget", "kitchen gadget"],
            "hashtags": ["#selfstirringmug", "#coffeegadget", "#kitchengadgets"],
            "primary_keyword": "self stirring mug",
            "secondary_keywords": ["auto stir mug", "coffee mixer mug"],
            "pinned_comment": "Link to grab yours is in the bio!",
        },
        "content quality auditor": {
            "quality_score": 87,
            "strengths": ["Strong curiosity-driven hook", "Clear, specific benefit claims"],
            "risks": ["CTA could be more urgent"],
            "recommendations": ["Add a limited-time discount mention to the CTA"],
        },
        "producer writing an executive summary": {
            "summary": (
                "This project generated a complete Shorts package for a self-stirring travel mug, "
                "anchored on a curiosity-driven hook and a convenience-focused strategy targeting "
                "busy professionals across YouTube Shorts and TikTok."
            )
        },
    }

    def __init__(self) -> None:
        self.call_log: list[str] = []

    def generate_json(self, system_prompt: str, user_prompt: str, temperature: float = 0.7) -> dict:
        for keyword, response in self._RESPONSES.items():
            if keyword in system_prompt:
                self.call_log.append(keyword)
                return response
        raise AssertionError(f"No fake response registered for prompt: {system_prompt[:80]}")

    def generate_text(self, system_prompt: str, user_prompt: str, temperature: float = 0.8) -> str:
        return "fake generated text"


def test_full_pipeline_runs_end_to_end(monkeypatch, tmp_path):
    """
    Drive a project through every single pipeline stage — research through
    export — using the real WorkflowEngine, and assert that each stage's
    database rows, on-disk assets and the final export bundle all exist.
    """
    fake_ai = _IntegrationFakeAIManager()
    monkeypatch.setattr("engines.base_engine.get_ai_manager", lambda: fake_ai)

    from services.image_generation_service import ImageGenerationService
    from services.video_generation_service import VideoGenerationService

    monkeypatch.setattr(
        ImageGenerationService, "generate_thumbnail", lambda self, prompt, quality="hd": b"fake-thumbnail-bytes"
    )
    monkeypatch.setattr(
        VideoGenerationService,
        "generate_scene_visual",
        lambda self, prompt, aspect_ratio="9:16": b"fake-scene-image-bytes",
    )

    def _fake_assemble_video(self, scene_image_paths, scene_durations, voice_over_path, subtitle_cues, output_path, **kwargs):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake-mp4-bytes")
        return output_path

    monkeypatch.setattr(VideoGenerationService, "assemble_video", _fake_assemble_video)

    from core.project_manager import ProjectManager
    from core.workflow_engine import WorkflowEngine

    project = ProjectManager().create_project(
        raw_input="A self-stirring travel mug with USB charging and a leak-proof lid.",
        name="Integration Test Mug",
    )

    engine = WorkflowEngine()
    context = engine.run(project.id, resume=False)

    # --- Assert every stage actually produced its expected output -----------
    assert context["product_profile"]["product_title"] == "Self-Stirring Travel Mug"
    assert context["category"] == "home_and_kitchen"
    assert context["strategy"]["core_angle"] == "The mug that thinks for you"
    assert "stirs itself" in context["script"]["full_script"]
    assert len(context["storyboard"]) == 2
    assert len(context["prompts"]) == 2
    assert context["seo"]["primary_keyword"] == "self stirring mug"
    assert context["report"]["quality_score"] == 87.0
    assert context["final_video_path"] is not None
    assert Path(context["final_video_path"]).exists()
    assert context["export_path"] is not None
    assert Path(context["export_path"]).exists()

    # --- Assert the project reached a terminal, successful state ------------
    final_project = ProjectManager().get_project(project.id)
    assert final_project.status.value == "completed"
    assert final_project.current_stage.value == "finished"

    # --- Assert every database table actually received rows -----------------
    from database.repositories import (
        PromptRepository, ReportRepository, ScriptRepository, SeoRepository,
        StoryboardRepository, ThumbnailRepository,
    )
    from database.repositories.domain_repositories import AssetRepository
    from database.session import session_scope

    with session_scope() as session:
        assert len(ScriptRepository().list_by_project(session, project.id)) == 1
        assert len(StoryboardRepository().list_by_project(session, project.id)) == 2
        assert len(PromptRepository().list_by_project(session, project.id)) == 2
        assert len(SeoRepository().list_by_project(session, project.id)) == 1
        assert len(ReportRepository().list_by_project(session, project.id)) == 1
        assert len(ThumbnailRepository().list_by_project(session, project.id)) == 1
        assert len(AssetRepository().list_by_project(session, project.id)) >= 3


def test_pipeline_resume_skips_completed_stages(monkeypatch):
    """
    Resuming a project must not re-run stages already completed: after a
    full run, resetting the project back to SEO_GENERATION and resuming
    must only re-invoke SEO/Report/Export stages, reusing the already
    persisted research/strategy/script/storyboard/prompt data.
    """
    fake_ai = _IntegrationFakeAIManager()
    monkeypatch.setattr("engines.base_engine.get_ai_manager", lambda: fake_ai)

    from services.image_generation_service import ImageGenerationService
    from services.video_generation_service import VideoGenerationService

    monkeypatch.setattr(
        ImageGenerationService, "generate_thumbnail", lambda self, prompt, quality="hd": b"fake-thumbnail-bytes"
    )
    monkeypatch.setattr(
        VideoGenerationService,
        "generate_scene_visual",
        lambda self, prompt, aspect_ratio="9:16": b"fake-scene-image-bytes",
    )

    def _fake_assemble_video(self, scene_image_paths, scene_durations, voice_over_path, subtitle_cues, output_path, **kwargs):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake-mp4-bytes")
        return output_path

    monkeypatch.setattr(VideoGenerationService, "assemble_video", _fake_assemble_video)

    from config.constants import WorkflowStage, WorkflowStatus
    from core.project_manager import ProjectManager
    from core.workflow_engine import WorkflowEngine

    project = ProjectManager().create_project(raw_input="A resumable test gadget.", name="Resume Test")

    engine = WorkflowEngine()
    engine.run(project.id, resume=False)

    # Simulate a crash that left the project paused right before SEO generation.
    ProjectManager().update_stage(project.id, WorkflowStage.SEO_GENERATION, WorkflowStatus.PAUSED)
    fake_ai.call_log.clear()

    context = engine.run(project.id, resume=True)

    assert context["seo"]["primary_keyword"] == "self stirring mug"
    assert "senior e-commerce product analyst" not in fake_ai.call_log
    assert "viral short-form video copywriter" not in fake_ai.call_log
    assert "professional video director" not in fake_ai.call_log
    assert "SEO specialist" in fake_ai.call_log
    assert "producer writing an executive summary" in fake_ai.call_log

    final_project = ProjectManager().get_project(project.id)
    assert final_project.status.value == "completed"
