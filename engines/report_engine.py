"""Report Engine — pipeline stage 15: final project summary report, incorporating quality scoring."""
from __future__ import annotations

from typing import Any

from config.constants import AssetType, WorkflowStage
from core.asset_manager import AssetManager
from core.exceptions import StageExecutionError
from database.repositories import ReportRepository
from database.session import session_scope
from engines.base_engine import BaseEngine
from engines.quality_engine import QualityEngine

_SUMMARY_SYSTEM_PROMPT = """You are a producer writing an executive summary for a completed \
affiliate marketing video project. Given the full generated package, write a concise 3-4 sentence \
summary of what was created and why the chosen angle should perform well. Respond only with JSON: \
{"summary": str}"""


class ReportEngine(BaseEngine):
    """Generates the final human-readable report summarising the whole project."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._report_repo = ReportRepository()
        self._asset_manager = AssetManager()
        self._quality_engine = QualityEngine(ai_manager=self.ai)

    def execute(self, project_id: str, context: dict[str, Any]) -> dict[str, Any]:
        """Run the quality audit, write an executive summary, render a Markdown report, and persist it."""
        quality = self._quality_engine.execute(project_id, context)

        try:
            summary_result = self.ai.generate_json(_SUMMARY_SYSTEM_PROMPT, str(context), temperature=0.5)
        except Exception as exc:
            raise StageExecutionError(WorkflowStage.REPORT_GENERATION.value, str(exc)) from exc

        summary_text = summary_result.get("summary", "")
        markdown_report = self._render_markdown(context, quality, summary_text)

        asset = self._asset_manager.save_text(
            project_id,
            AssetType.DOCUMENT,
            "project_report.md",
            markdown_report,
            source_stage=WorkflowStage.REPORT_GENERATION.value,
        )

        with session_scope() as session:
            self._report_repo.create(
                session,
                project_id=project_id,
                summary=summary_text,
                strengths=quality.get("strengths"),
                risks=quality.get("risks"),
                recommendations=quality.get("recommendations"),
                quality_score=quality.get("quality_score"),
                stage_durations=context.get("stage_durations"),
                file_path=asset.file_path,
            )

        self.logger.info("Report generated for project {} (quality_score={})", project_id, quality.get("quality_score"))
        return {"report": {"summary": summary_text, **quality}, "report_file_path": asset.file_path}

    @staticmethod
    def _render_markdown(context: dict[str, Any], quality: dict[str, Any], summary: str) -> str:
        """Render a human-readable Markdown report from the accumulated pipeline context."""
        product = context.get("product_profile", {}) or {}
        strategy = context.get("strategy", {}) or {}
        hook = context.get("hook", {}) or {}
        seo = context.get("seo", {}) or {}

        lines = [
            f"# Fact Drop AI Studio — Project Report",
            "",
            f"## Product: {product.get('product_title', 'N/A')}",
            "",
            "## Executive Summary",
            summary,
            "",
            f"## Quality Score: {quality.get('quality_score', 'N/A')} / 100",
            "",
            "### Strengths",
            *[f"- {s}" for s in quality.get("strengths", [])],
            "",
            "### Risks",
            *[f"- {r}" for r in quality.get("risks", [])],
            "",
            "### Recommendations",
            *[f"- {r}" for r in quality.get("recommendations", [])],
            "",
            "## Strategy",
            f"- Core angle: {strategy.get('core_angle', 'N/A')}",
            f"- Emotional driver: {strategy.get('emotional_driver', 'N/A')}",
            "",
            "## Selected Hook",
            f"> {hook.get('text', 'N/A')}",
            "",
            "## SEO Titles",
            *[f"- {t}" for t in seo.get("titles", [])],
        ]
        return "\n".join(lines)
