"""Default shot planner (architecture v2, Phase 3).

A real LLM provider *proposes* a multi-shot plan from the scene narration
(2-5 shots per scene); the deterministic template is the key-free fallback.
Either way, the normalizer owns enforcement of limits and schema validity
(count bounds, valid enums, non-empty queries, contiguous positions, stable
ids). The module only *plans* shots — never retrieves media, times clips, or
renders.
"""

from __future__ import annotations

import json
import logging
import re

from config.settings import TimelineConfig
from core.errors import InputValidationError, StageRetryableError
from core.models import JobContext, StageResult
from core.stages import Stage
from providers.base import LLMProvider

from ..scenes.schemas import ScenePlan
from .interface import ShotsModule
from .normalize import normalize_shot_plan
from .schemas import ShotPlan
from .template import plan_shots

log = logging.getLogger(__name__)


def extract_json(text: str) -> dict:
    """Pull the outermost JSON object out of an LLM response."""
    text = re.sub(r"```(?:json)?", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found in LLM response")
    return json.loads(text[start : end + 1])


def build_shot_prompt(scenes: ScenePlan) -> str:
    scene_lines = "\n".join(
        f"Scene {scene.scene_number} (rhythm {scene.rhythm}): {scene.narration_segment}"
        for scene in scenes.scenes
    )
    return (
        "Plan the shots for a video from its scene narration.\n"
        f"{scene_lines}\n\n"
        "Return ONLY JSON: {\"shots\": [{\"scene\": <scene_number>, \"purpose\": str, "
        "\"visual_description\": str, \"search_queries\": [str, ...], "
        "\"content_kind\": \"stock_video|stock_image|text|chart|map\", "
        "\"media_preference\": \"video|image|either\", "
        "\"motion_intent\": \"none|zoom_in|zoom_out|pan\", "
        "\"importance\": \"low|medium|high|critical\", "
        "\"transition_out\": str}]}\n"
        "Propose 2-5 shots per scene, in order."
    )


class DefaultShotsModule(ShotsModule):
    def __init__(self, llm: LLMProvider | None = None, config: TimelineConfig | None = None) -> None:
        self.llm = llm
        self.config = config or TimelineConfig()

    def validate_input(self, ctx: JobContext) -> None:
        result = ctx.results.get(Stage.SCENES)
        if result is None or result.output is None:
            raise InputValidationError("shots requires a scene plan")

    def run(self, ctx: JobContext) -> StageResult:
        scenes: ScenePlan = ctx.results[Stage.SCENES].output
        style = ctx.input.style or "explainer"
        ctx.progress("Planning shots...")
        if self.llm is not None and self.llm.name != "stub":
            proposed = self._llm_plan(scenes)
        else:
            proposed = plan_shots(scenes, topic=ctx.input.topic, style=style)
        plan = normalize_shot_plan(proposed, scenes, self.config, topic=ctx.input.topic)
        for shot in plan.shots:
            ctx.progress(
                f"Shot {shot.shot_id} for {shot.scene_id}: "
                f"{shot.content_kind}, importance={shot.importance}"
            )
        ctx.progress(f"Generated {len(plan.shots)} shot(s) across {len(scenes.scenes)} scene(s)")
        log.info("shot plan: %d shot(s) across %d scene(s)", len(plan.shots), len(scenes.scenes))
        return StageResult(
            stage=self.name,
            ok=True,
            output=plan,
            artifacts_written=[self._save(ctx, "shot_plan.json", plan)],
        )

    def _llm_plan(self, scenes: ScenePlan) -> list[dict]:
        system = "You are a video shot planner. Return ONLY valid JSON matching the requested schema."
        raw = self.llm.complete(build_shot_prompt(scenes), system=system)
        try:
            entries = extract_json(raw)["shots"]
        except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
            log.warning("shot plan parse failed; attempting one repair: %s", exc)
            repair = (
                f"Your previous response was not valid JSON ({exc}). Respond with ONLY JSON matching "
                f"the requested schema. Previous response:\n{raw[:2000]}"
            )
            try:
                entries = extract_json(self.llm.complete(repair, system=system))["shots"]
            except Exception as exc2:  # noqa: BLE001 - surfaced as a retryable stage failure
                raise StageRetryableError(f"shot plan not valid JSON after repair: {exc2}") from exc
        return [entry for entry in (entries or []) if isinstance(entry, dict)]
