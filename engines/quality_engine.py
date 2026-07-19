"""
Quality Engine — cross-cutting content quality assessment, consumed by
the Report Engine. Not a standalone pipeline stage; instead it scores
the accumulated project context (script, hook, SEO, storyboard) for
strengths, risks and concrete improvement recommendations.
"""
from __future__ import annotations

from typing import Any

from core.exceptions import StageExecutionError
from engines.base_engine import BaseEngine

_QUALITY_SYSTEM_PROMPT = """You are a meticulous content quality auditor for affiliate marketing \
video pipelines. Given the full generated package (hook, script, storyboard, SEO), critically assess \
its quality. Be honest — flag weak hooks, generic claims, unclear CTAs, or SEO that doesn't match \
search intent. Respond only with JSON: {"quality_score": number, "strengths": [str], "risks": [str], \
"recommendations": [str]}. quality_score must be a number from 0 to 100."""


class QualityEngine(BaseEngine):
    """Produces an automated quality score plus strengths/risks/recommendations."""

    def execute(self, project_id: str, context: dict[str, Any]) -> dict[str, Any]:
        """Assess the accumulated project context and return a structured quality report."""
        assessment_input = {
            "hook": context.get("hook"),
            "script": context.get("script"),
            "storyboard_scene_count": len(context.get("storyboard", []) or []),
            "seo": context.get("seo"),
            "strategy": context.get("strategy"),
        }

        try:
            result = self.ai.generate_json(_QUALITY_SYSTEM_PROMPT, str(assessment_input), temperature=0.4)
        except Exception as exc:
            raise StageExecutionError("quality_assessment", str(exc)) from exc

        score = result.get("quality_score", 0)
        try:
            score = max(0.0, min(100.0, float(score)))
        except (TypeError, ValueError):
            score = 0.0
        result["quality_score"] = score

        self.logger.info("Quality assessment for project {}: score={}", project_id, score)
        return result
