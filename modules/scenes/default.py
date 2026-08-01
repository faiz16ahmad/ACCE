"""Default scene planner.

Milestone 4: converts `ScriptOutput` narration into a timed `ScenePlan` (one
scene per narration block) with a visual plan per scene. A real LLM provider
writes the visual descriptions / search keywords / visual types / transitions;
the stub falls back to the deterministic template, which also fills any
per-field output that can't be applied. The module only *plans* — no research,
no media retrieval, no rendering.
"""

from __future__ import annotations

import json
import logging
import re

from pydantic import ValidationError

from core.errors import InputValidationError, StageRetryableError
from core.models import JobContext, StageResult
from core.stages import Stage
from providers.base import LLMProvider

from ..script.schemas import ScriptOutput
from .interface import ScenesModule
from .schemas import ScenePlan
from .template import VISUAL_TYPES, plan_scenes

log = logging.getLogger(__name__)


def extract_json(text: str) -> dict:
    """Pull the outermost JSON object out of an LLM response."""
    text = re.sub(r"```(?:json)?", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found in LLM response")
    return json.loads(text[start : end + 1])


def build_visuals_prompt(topic: str, style: str, scenes: ScenePlan) -> str:
    scene_lines = "\n".join(f"{index + 1}. {scene.narration_segment}" for index, scene in enumerate(scenes.scenes))
    return (
        f"Plan the visuals for a {style} video about {topic}.\n"
        f"Scenes (narration segments):\n{scene_lines}\n\n"
        'Return ONLY JSON: {"visuals": [{"visual_description": str, "search_keywords": [str, ...], '
        '"visual_type": "stock_video|stock_image|animation|infographic|map|text_overlay", '
        '"transition": str}]} with exactly one entry per scene, in order.\n'
        "Write concise but highly descriptive visual prompts that are factual and consistent with the "
        "narration. Search keywords should be optimized for stock media search: prefer concrete nouns, "
        "locations, events, people, and objects — avoid generic keywords such as 'technology' or 'history'."
    )


class DefaultScenesModule(ScenesModule):
    def __init__(self, llm: LLMProvider) -> None:
        self.llm = llm

    def validate_input(self, ctx: JobContext) -> None:
        result = ctx.results.get(Stage.SCRIPT)
        if result is None or result.output is None:
            raise InputValidationError("scenes requires a script output")

    def run(self, ctx: JobContext) -> StageResult:
        script: ScriptOutput = ctx.results[Stage.SCRIPT].output
        total = ctx.input.duration or 180
        style = getattr(script, "style", "") or ctx.input.style or "explainer"
        ctx.progress("Planning scenes...")
        plan = plan_scenes(script, total, ctx.input.topic, style=style)
        ctx.progress(f"Generated {len(plan.scenes)} scenes")
        if self.llm.name != "stub":
            ctx.progress("Generating visual descriptions...")
            self._apply_llm_visuals(plan, ctx.input.topic, style)
        total_dur = sum(s.estimated_duration for s in plan.scenes)
        ctx.progress(f"Timeline: {total_dur:.1f}s total")
        return StageResult(
            stage=self.name,
            ok=True,
            output=plan,
            artifacts_written=[self._save(ctx, "scene_plan.json", plan)],
        )

    def _apply_llm_visuals(self, plan: ScenePlan, topic: str, style: str) -> None:
        system = "You are a video scene planner. Return ONLY valid JSON matching the requested schema."
        raw = self.llm.complete(build_visuals_prompt(topic, style, plan), system=system)
        try:
            visuals = extract_json(raw)["visuals"]
        except (KeyError, ValueError, TypeError, ValidationError) as exc:
            log.warning("scene visuals parse failed; attempting one repair: %s", exc)
            repair = (
                f"Your previous response was not valid JSON ({exc}). Respond with ONLY JSON matching the "
                f"requested schema. Previous response:\n{raw[:2000]}"
            )
            try:
                visuals = extract_json(self.llm.complete(repair, system=system))["visuals"]
            except Exception as exc2:  # noqa: BLE001 - surfaced as a retryable stage failure
                raise StageRetryableError(f"scene visuals not valid JSON after repair: {exc2}") from exc

        for scene, entry in zip(plan.scenes, visuals or [], strict=False):
            if not isinstance(entry, dict):
                continue
            if isinstance(entry.get("visual_description"), str) and entry["visual_description"].strip():
                scene.visual_description = entry["visual_description"].strip()
            if isinstance(entry.get("search_keywords"), list):
                keywords = [str(k).strip() for k in entry["search_keywords"] if str(k).strip()]
                if keywords:
                    scene.search_keywords = keywords[:8]
            if entry.get("visual_type") in VISUAL_TYPES:
                scene.visual_type = entry["visual_type"]
            if isinstance(entry.get("transition"), str) and entry["transition"].strip():
                scene.transition = entry["transition"].strip()
