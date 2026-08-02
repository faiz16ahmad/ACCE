"""Timeline Sync for the production stage (architecture v2, Phase 3).

The edit layer is shot-keyed: each `Clip` binds one `Shot`'s intent to a
chosen asset at concrete times. Scene timings come from actual narration
durations when available (the AudioOutput tracks measured after TTS), falling
back to the ScenePlan's LLM-estimated durations — never from media (I6).

Timeline Sync allocates each scene's *measured* narration budget across its
shots: importance weights and rhythm shaping decide relative lengths, then the
result is clamped to `TimelineConfig` bounds and renormalized so the sum per
scene still equals the budget exactly (I7). The Shot Planner proposes; these
pacing rules (config, never the prompt) own the actual times. Motion intent is
resolved inline into a `MotionDescriptor` (the Shot Resolver seam stays
documented but unbuilt).
"""

from __future__ import annotations

from config.settings import TimelineConfig
from modules.media.schemas import MediaPlan
from modules.scenes.schemas import ScenePlan
from modules.shots.schemas import ShotPlan
from modules.shots.template import scene_id_for, shot_id_for

from .schemas import Clip, MotionDescriptor, Timeline

PLACEHOLDER_ASSET_ID = "placeholder"

_MOTION_KIND: dict[str, str] = {
    "zoom_in": "kenburns_zoom_in",
    "zoom_out": "kenburns_zoom_out",
    "pan": "pan_right",  # simple default; per-shot direction lands with the Resolver
}


def _shot_weights(shots, scene_rhythm: str, config: TimelineConfig) -> list[float]:
    """Relative duration weights: importance x rhythm shaping."""
    count = len(shots)
    shape = config.rhythm_multipliers.get(scene_rhythm, "flat")
    weights: list[float] = []
    for index, shot in enumerate(shots):
        weight = config.importance_weights.get(shot.importance, 1.0)
        if shape == "calm":  # first shot longest, then decays
            weight *= (count - index) / max(count, 1)
        elif shape == "build":  # gets busier toward the last shot
            weight *= (index + 1) / max(count, 1)
        elif shape == "rapid":  # near-even cuts: compress importance differences
            weight = 0.75 + 0.25 * weight
        # "flat": importance weights only
        weights.append(weight)
    return weights


def _allocate(budget: float, weights: list[float], config: TimelineConfig) -> list[float]:
    """Distribute a scene budget across shots; sum always equals `budget` (I7).

    Weighted allocation with hard per-shot [min, max] bounds. Shots that the
    raw proportional split pushes out of band are pinned at the bound and the
    difference is re-shared over the remaining (free) shots, so no clip ever
    ends up below `min_shot_duration`. (The previous global renormalize could
    scale a clamped clip back under the floor.) `lo <= budget/n` makes the
    floor always feasible, so the pin/redistribute loop converges.
    """
    count = len(weights)
    lo = min(config.min_shot_duration, budget / max(count, 1))
    hi = config.max_shot_duration
    if count * hi < budget:  # degenerate: even all-max is short of the budget
        hi = budget / max(count, 1)
    total = sum(weights) or 1.0
    durations = [budget * weight / total for weight in weights]

    free = set(range(count))
    for _ in range(count + 1):
        pinned = False
        for index in list(free):
            if durations[index] < lo or durations[index] > hi:
                durations[index] = min(hi, max(lo, durations[index]))
                free.discard(index)
                pinned = True
        if not free or not pinned:
            break
        diff = budget - sum(durations)
        free_total = sum(weights[index] for index in free) or 1.0
        for index in free:
            durations[index] += diff * weights[index] / free_total

    # Exact budget: round each clip, then let one clip absorb the rounding so
    # the floor is never re-broken (unlike a global scale, which would).
    durations = [round(d, 3) for d in durations]
    remainder = round(budget - sum(durations), 3)
    if remainder:
        absorb = max(range(count), key=lambda i: durations[i] - lo)
        durations[absorb] = round(durations[absorb] + remainder, 3)
    return durations


def _resolve_motion(shot, duration: float) -> MotionDescriptor | None:
    kind = _MOTION_KIND.get(shot.motion_intent)
    if kind is None:
        return None
    return MotionDescriptor(kind=kind, duration=duration)


def build_timeline(
    scenes: ScenePlan,
    media: MediaPlan,
    narration_durations: dict[int, float] | None = None,
    shot_plan: ShotPlan | None = None,
    config: TimelineConfig | None = None,
) -> Timeline:
    """Build a shot-keyed timeline from scene/media/shot plans and measured audio.

    *narration_durations* maps scene_number → actual measured narration length
    (seconds), overriding the LLM estimates so the timeline matches the real
    audio. Without a shot plan, one clip per scene is synthesized (the 1:1
    pass-through) so the function stays usable directly.
    """
    config = config or TimelineConfig()
    assets_by_shot = {asset.shot_id: asset for asset in media.assets if asset.shot_id}
    assets_by_scene = {asset.scene_number: asset for asset in media.assets}
    scenes_by_number = {scene.scene_number: scene for scene in scenes.scenes}
    narration_durations = narration_durations or {}

    clips: list[Clip] = []
    cursor = 0.0

    if shot_plan is not None and shot_plan.shots:
        scene_number_by_id = {
            scene_id_for(scene.scene_number): scene.scene_number for scene in scenes.scenes
        }
        shots_by_scene: dict[int, list] = {}
        for shot in shot_plan.shots:
            shots_by_scene.setdefault(scene_number_by_id.get(shot.scene_id), []).append(shot)

        for scene in scenes.scenes:
            scene_shots = shots_by_scene.get(scene.scene_number, [])
            if not scene_shots:
                continue
            budget = narration_durations.get(scene.scene_number, scene.estimated_duration)
            durations = _allocate(max(0.0, budget), _shot_weights(scene_shots, scene.rhythm, config), config)
            for shot, duration in zip(scene_shots, durations, strict=True):
                asset = assets_by_shot.get(shot.shot_id) or assets_by_scene.get(scene.scene_number)
                clips.append(
                    Clip(
                        shot_id=shot.shot_id,
                        scene_id=shot.scene_id,
                        asset_id=asset.asset_id if asset else PLACEHOLDER_ASSET_ID,
                        start=round(cursor, 3),
                        end=round(cursor + duration, 3),
                        transition_out=shot.transition_out or "cut",
                        motion=_resolve_motion(shot, duration),
                    )
                )
                cursor += duration
    else:
        for scene in scenes.scenes:
            asset = assets_by_scene.get(scene.scene_number)
            duration = narration_durations.get(scene.scene_number, scene.estimated_duration)
            duration = max(0.0, duration)
            clips.append(
                Clip(
                    shot_id=shot_id_for(scene.scene_number),
                    scene_id=scene_id_for(scene.scene_number),
                    asset_id=asset.asset_id if asset else PLACEHOLDER_ASSET_ID,
                    start=round(cursor, 3),
                    end=round(cursor + duration, 3),
                    transition_out=scene.transition or "cut",
                    motion=None,
                )
            )
            cursor += duration

    return Timeline(clips=clips, duration=round(cursor, 3))
