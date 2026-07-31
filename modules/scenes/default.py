"""Default (stub) scene planner.

Milestone 1: deterministically splits the script narration into timed scenes
using the requested duration. Milestone 4 makes pacing/visual choices smarter.
"""

from __future__ import annotations

import logging
import re

from core.errors import InputValidationError
from core.models import JobContext, StageResult
from core.stages import Stage
from providers.base import LLMProvider

from ..script.schemas import ScriptOutput
from .interface import ScenesModule
from .schemas import Scene, ScenePlan

log = logging.getLogger(__name__)


def keywords_for(topic: str) -> list[str]:
    words = [w.strip(".,!?;:") for w in re.split(r"\s+", topic)]
    return list(dict.fromkeys(w.lower() for w in words if w))[:5]


def plan_scenes(script: ScriptOutput, total_seconds: int, topic: str) -> ScenePlan:
    count = max(3, min(len(script.narration), 8))
    per_scene = total_seconds // count
    scenes = []
    for index, block in enumerate(script.narration[:count]):
        scenes.append(
            Scene(
                scene=index + 1,
                duration=per_scene,
                narration=block.paragraph,
                visual_description=f"(placeholder) visual for {script.hook[:60]!r}",
                search_keywords=keywords_for(topic),
            )
        )
    return ScenePlan(scenes=scenes)


class DefaultScenesModule(ScenesModule):
    def __init__(self, llm: LLMProvider) -> None:
        self.llm = llm

    def validate_input(self, ctx: JobContext) -> None:
        result = ctx.results.get(Stage.SCRIPT)
        if result is None or result.output is None:
            raise InputValidationError("scenes requires a script output")

    def run(self, ctx: JobContext) -> StageResult:
        script: ScriptOutput = ctx.results[Stage.SCRIPT].output
        raw = self.llm.complete(
            f"Suggest search keywords and visuals for a video about: {script.hook[:200]}",
            system="You are a video scene planner.",
        )
        log.debug("scenes llm response: %.200s", raw)

        total = ctx.input.duration or 180
        plan = plan_scenes(script, total, ctx.input.topic)
        return StageResult(
            stage=self.name, ok=True, output=plan, artifacts_written=[self._save(ctx, "scenes.json", plan)]
        )
