"""Script Engine — pipeline stages 7-8: hook generation and full Shorts script."""
from __future__ import annotations

from typing import Any

from config.constants import DEFAULT_SHORT_VIDEO_SECONDS, WorkflowStage
from core.exceptions import StageExecutionError
from database.repositories import ScriptRepository
from database.session import session_scope
from engines.base_engine import BaseEngine

_HOOK_SYSTEM_PROMPT = """You are a viral short-form video copywriter. Given a product profile, \
marketing strategy and target audience, write 5 distinct 3-second attention hooks for the opening \
of a YouTube Shorts / TikTok affiliate video. Each hook must be pattern-interrupting, curiosity-driven \
or bold-claim-driven, spoken in a natural, punchy voice. Respond only with JSON: \
{"hooks": [{"text": str, "style": str, "rationale": str}]}"""

_SCRIPT_SYSTEM_PROMPT = """You are an expert YouTube Shorts scriptwriter for affiliate product videos. \
Given a chosen hook, product profile, marketing strategy and target audience, write a complete, \
timed video script of roughly {duration} seconds at natural spoken pace (~2.5 words/second). \
Structure it into clear beats: hook, problem/agitation, product reveal, key benefits (as vivid, \
specific, sensory claims), social proof or credibility angle, and a strong call-to-action. \
Respond only with JSON matching this schema: {{"full_script": str, "call_to_action": str, \
"tone": str, "beats": [{{"beat_name": str, "text": str, "approx_seconds": number}}]}}"""


class ScriptEngine(BaseEngine):
    """Generates attention hooks and the full narrated video script."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._script_repo = ScriptRepository()

    def execute(self, project_id: str, context: dict[str, Any]) -> dict[str, Any]:
        """Generate hooks, select the strongest one, then write the full script."""
        product_profile = context.get("product_profile")
        strategy = context.get("strategy")
        audience = context.get("audience")

        if not product_profile or not strategy:
            raise StageExecutionError(
                WorkflowStage.SCRIPT_GENERATION.value,
                "Missing product_profile or strategy from earlier stages.",
                recoverable=False,
            )

        hook = self._generate_hook(product_profile, strategy, audience)
        script = self._generate_script(hook, product_profile, strategy, audience)

        with session_scope() as session:
            existing = self._script_repo.get_latest(session, project_id)
            next_version = (existing.version + 1) if existing else 1
            self._script_repo.create(
                session,
                project_id=project_id,
                version=next_version,
                hook_text=hook["text"],
                hook_style=hook.get("style"),
                full_script=script["full_script"],
                call_to_action=script.get("call_to_action"),
                estimated_duration_seconds=self._sum_beat_durations(script.get("beats", [])),
                beats=script.get("beats"),
                tone=script.get("tone"),
                word_count=len(script["full_script"].split()),
            )

        self.logger.info("Script generated for project {} ({} words)", project_id, len(script["full_script"].split()))
        return {"hook": hook, "script": script}

    def _generate_hook(self, product_profile: dict, strategy: dict, audience: dict | None) -> dict:
        """Stage 7: generate multiple hook candidates and select the one matching strategy."""
        user_prompt = f"Product: {product_profile}\nStrategy: {strategy}\nAudience: {audience}"
        try:
            result = self.ai.generate_json(_HOOK_SYSTEM_PROMPT, user_prompt, temperature=0.9)
        except Exception as exc:
            raise StageExecutionError(WorkflowStage.HOOK_GENERATION.value, str(exc)) from exc

        hooks = result.get("hooks", [])
        if not hooks:
            raise StageExecutionError(WorkflowStage.HOOK_GENERATION.value, "AI returned zero hooks.")

        preferred_styles = strategy.get("recommended_hook_styles", [])
        for hook in hooks:
            if hook.get("style") in preferred_styles:
                return hook
        return hooks[0]

    def _generate_script(self, hook: dict, product_profile: dict, strategy: dict, audience: dict | None) -> dict:
        """Stage 8: write the full timed script using the selected hook."""
        duration = strategy.get("recommended_video_length_seconds", DEFAULT_SHORT_VIDEO_SECONDS)
        system_prompt = _SCRIPT_SYSTEM_PROMPT.format(duration=duration)
        user_prompt = (
            f"Selected hook: {hook}\nProduct: {product_profile}\nStrategy: {strategy}\nAudience: {audience}"
        )
        try:
            return self.ai.generate_json(system_prompt, user_prompt, temperature=0.75)
        except Exception as exc:
            raise StageExecutionError(WorkflowStage.SCRIPT_GENERATION.value, str(exc)) from exc

    @staticmethod
    def _sum_beat_durations(beats: list[dict]) -> int:
        """Sum estimated per-beat durations, falling back to the default length if absent."""
        total = sum(float(b.get("approx_seconds", 0)) for b in beats)
        return int(total) if total > 0 else DEFAULT_SHORT_VIDEO_SECONDS
