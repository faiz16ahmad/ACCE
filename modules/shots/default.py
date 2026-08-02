"""Default shot planner.

Phase 1 (architecture v2): converts the `ScenePlan` into a `ShotPlan` via the
deterministic pass-through template — one shot per scene, mirroring the
scene's visual plan. The module only *plans* shots; it never retrieves media,
times clips, or renders. The ShotPlan is written as an artifact but is not yet
consumed downstream (Phase 2 wires Media / Timeline to it).
"""

from __future__ import annotations

import logging

from core.errors import InputValidationError
from core.models import JobContext, StageResult
from core.stages import Stage

from ..scenes.schemas import ScenePlan
from .interface import ShotsModule
from .schemas import ShotPlan
from .template import plan_shots

log = logging.getLogger(__name__)


class DefaultShotsModule(ShotsModule):
    def validate_input(self, ctx: JobContext) -> None:
        result = ctx.results.get(Stage.SCENES)
        if result is None or result.output is None:
            raise InputValidationError("shots requires a scene plan")

    def run(self, ctx: JobContext) -> StageResult:
        scenes: ScenePlan = ctx.results[Stage.SCENES].output
        ctx.progress("Planning shots...")
        plan = plan_shots(scenes)
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
