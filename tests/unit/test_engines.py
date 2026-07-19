"""
Unit tests for individual engines, using a fake :class:`AIManager` so
tests never make real network calls to OpenAI. Each engine receives the
fake manager via constructor injection (``BaseEngine.__init__`` accepts
an optional ``ai_manager``), demonstrating the Dependency Inversion
Principle in action.
"""
from __future__ import annotations

from typing import Any


class FakeAIManager:
    """Deterministic stand-in for AIManager, returning canned JSON per system prompt keyword."""

    def __init__(self, json_responses: dict[str, dict[str, Any]]) -> None:
        """
        Args:
            json_responses: Maps a substring that must appear in the system
                prompt to the JSON dict that should be "generated" for it.
        """
        self._json_responses = json_responses
        self.calls: list[tuple[str, str]] = []

    def generate_json(self, system_prompt: str, user_prompt: str, temperature: float = 0.7) -> dict:
        self.calls.append((system_prompt, user_prompt))
        for keyword, response in self._json_responses.items():
            if keyword in system_prompt:
                return response
        raise AssertionError(f"No fake response configured for prompt: {system_prompt[:60]}")

    def generate_text(self, system_prompt: str, user_prompt: str, temperature: float = 0.8) -> str:
        return "fake text response"


def test_strategy_engine_persists_strategy(sample_project):
    """StrategyEngine.execute must persist strategy_data onto the project row."""
    from engines.strategy_engine import StrategyEngine

    fake_ai = FakeAIManager({
        "marketing strategist": {
            "core_angle": "Convenience for busy professionals",
            "emotional_driver": "relief",
            "content_pillars": ["speed", "ease"],
            "recommended_hook_styles": ["curiosity"],
            "recommended_video_length_seconds": 45,
            "call_to_action_strategy": "link in bio",
            "posting_strategy": "3x/week",
            "differentiation_statement": "faster than competitors",
        }
    })

    engine = StrategyEngine(ai_manager=fake_ai)
    context = {
        "product_profile": {"product_title": "Self-Stirring Mug"},
        "competitors": {"synthesis": {}},
        "audience": {"primary_demographic": "busy professionals"},
    }

    result = engine.execute(sample_project.id, context)

    assert result["strategy"]["core_angle"] == "Convenience for busy professionals"

    from core.project_manager import ProjectManager

    fetched = ProjectManager().get_project(sample_project.id)
    assert fetched.strategy_data["core_angle"] == "Convenience for busy professionals"


def test_script_engine_generates_hook_and_script(sample_project):
    """ScriptEngine.execute must select a hook and persist a Script row."""
    from database.repositories import ScriptRepository
    from database.session import session_scope
    from engines.script_engine import ScriptEngine

    fake_ai = FakeAIManager({
        "viral short-form video copywriter": {
            "hooks": [
                {"text": "This mug stirs itself?!", "style": "curiosity", "rationale": "surprising"},
            ]
        },
        "YouTube Shorts scriptwriter": {
            "full_script": "This mug stirs itself. No more soggy sugar at the bottom.",
            "call_to_action": "Link in bio!",
            "tone": "energetic",
            "beats": [{"beat_name": "hook", "text": "This mug stirs itself.", "approx_seconds": 3}],
        },
    })

    engine = ScriptEngine(ai_manager=fake_ai)
    context = {
        "product_profile": {"product_title": "Self-Stirring Mug"},
        "strategy": {"recommended_hook_styles": ["curiosity"], "recommended_video_length_seconds": 45},
        "audience": {},
    }

    result = engine.execute(sample_project.id, context)

    assert result["hook"]["text"] == "This mug stirs itself?!"
    assert "stirs itself" in result["script"]["full_script"]

    with session_scope() as session:
        script_repo = ScriptRepository()
        latest = script_repo.get_latest(session, sample_project.id)
        assert latest is not None
        assert latest.version == 1


def test_seo_engine_persists_seo_package(sample_project):
    """SeoEngine.execute must generate and persist titles/tags/hashtags."""
    from database.repositories import SeoRepository
    from database.session import session_scope
    from engines.seo_engine import SeoEngine

    fake_ai = FakeAIManager({
        "SEO specialist": {
            "titles": ["This Mug Changes Everything", "Self-Stirring Mug Review"],
            "description": "A great mug.",
            "tags": ["mug", "gadget"],
            "hashtags": ["#mug", "#gadget"],
            "primary_keyword": "self stirring mug",
            "secondary_keywords": ["auto stir mug"],
            "pinned_comment": "Link below!",
        }
    })

    engine = SeoEngine(ai_manager=fake_ai)
    context = {
        "product_profile": {"product_title": "Self-Stirring Mug"},
        "script": {"full_script": "text"},
        "hook": {"text": "hook"},
        "audience": {},
    }

    result = engine.execute(sample_project.id, context)
    assert "#mug" in result["seo"]["hashtags"]

    with session_scope() as session:
        seo_repo = SeoRepository()
        rows = seo_repo.list_by_project(session, sample_project.id)
        assert len(rows) == 1


def test_quality_engine_clamps_score_to_valid_range():
    """QualityEngine must clamp an out-of-range score into [0, 100]."""
    from engines.quality_engine import QualityEngine

    fake_ai = FakeAIManager({
        "content quality auditor": {
            "quality_score": 150,
            "strengths": ["strong hook"],
            "risks": ["weak CTA"],
            "recommendations": ["tighten the CTA"],
        }
    })

    engine = QualityEngine(ai_manager=fake_ai)
    result = engine.execute("fake-project-id", {"hook": {}, "script": {}})

    assert result["quality_score"] == 100.0


def test_subtitle_engine_generates_valid_srt(sample_project):
    """SubtitleEngine must produce well-formed SRT cues covering the whole script."""
    from engines.subtitle_engine import SubtitleEngine

    engine = SubtitleEngine()
    context = {
        "script": {"full_script": "This is a short test script for subtitle generation testing purposes."},
        "voice_duration_seconds": 10.0,
    }

    result = engine.execute(sample_project.id, context)
    cues = result["subtitle_cues"]

    assert len(cues) > 0
    assert cues[0]["start"] == 0.0
    assert all(cue["end"] > cue["start"] for cue in cues)
