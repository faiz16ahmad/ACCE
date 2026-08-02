"""Timeline construction for the production stage (architecture v2).

The edit layer is shot-keyed: each `Clip` binds one `Shot`'s intent to a
chosen asset at concrete times. Scene timings come from actual narration
durations when available (the AudioOutput tracks measured after TTS), falling
back to the ScenePlan's LLM-estimated durations — never from media (invariant
I6). A `ShotPlan` is used when present; without one (direct/legacy callers) a
1:1 pass-through is synthesized, one clip per scene.
"""

from __future__ import annotations

from modules.media.schemas import MediaPlan
from modules.scenes.schemas import ScenePlan
from modules.shots.schemas import ShotPlan
from modules.shots.template import scene_id_for, shot_id_for

from .schemas import Clip, Timeline

PLACEHOLDER_ASSET_ID = "placeholder"


def build_timeline(
    scenes: ScenePlan,
    media: MediaPlan,
    narration_durations: dict[int, float] | None = None,
    shot_plan: ShotPlan | None = None,
) -> Timeline:
    """Build a shot-keyed timeline from scene plan, media plan, and shot plan.

    *narration_durations* maps scene_number → actual measured narration length
    (seconds). When provided, these override the LLM-estimated durations so
    the timeline matches the real audio. Scenes not present in the dict fall
    back to ``scene.estimated_duration``.

    *shot_plan* drives the clips when provided; otherwise one clip per scene
    is synthesized (the 1:1 pass-through) so the function stays usable without
    a shot plan.
    """
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
        for shot in shot_plan.shots:
            scene_number = scene_number_by_id.get(shot.scene_id)
            scene = scenes_by_number.get(scene_number) if scene_number is not None else None
            asset = assets_by_shot.get(shot.shot_id) or (
                assets_by_scene.get(scene_number) if scene_number is not None else None
            )
            duration = narration_durations.get(scene_number) if scene_number is not None else None
            if duration is None:
                duration = scene.estimated_duration if scene is not None else 0.0
            duration = max(0.0, duration)
            clips.append(
                Clip(
                    shot_id=shot.shot_id,
                    scene_id=shot.scene_id,
                    asset_id=asset.asset_id if asset else PLACEHOLDER_ASSET_ID,
                    start=round(cursor, 3),
                    end=round(cursor + duration, 3),
                    transition_out=shot.transition_out,
                    motion=None,
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
                    transition_out=scene.transition,
                    motion=None,
                )
            )
            cursor += duration

    return Timeline(clips=clips, duration=round(cursor, 3))
