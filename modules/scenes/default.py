"""Default scene planner (architecture v2, Phase 3).

Converts `ScriptOutput` narration into a timed `ScenePlan` — narrative only
(one scene per narration block, each with an estimated duration and a rhythm
hint). Visual planning is the Shot Planner's job (see `modules.shots`); the
Scene no longer carries visual fields. The module only *plans* — no research,
no media retrieval, no rendering.
"""

from __future__ import annotations

from core.errors import InputValidationError
from core.models import JobContext, StageResult
from core.stages import Stage

from ..script.schemas import ScriptOutput
from .interface import ScenesModule
from .schemas import ScenePlan
from .template import plan_scenes


class DefaultScenesModule(ScenesModule):
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
        total_dur = sum(scene.estimated_duration for scene in plan.scenes)
        ctx.progress(f"Timeline: {total_dur:.1f}s total")
        return StageResult(
            stage=self.name,
            ok=True,
            output=plan,
            artifacts_written=[self._save(ctx, "scene_plan.json", plan)],
        )
