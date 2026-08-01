"""Timeline construction for the production stage.

Scene timings come from actual narration durations when available (the
AudioOutput tracks measured after TTS), falling back to the ScenePlan's
LLM-estimated durations. Each timeline scene carries the scene number,
the selected asset id (from the MediaPlan, or "placeholder" when missing),
its start/end times, and its transition.
"""

from __future__ import annotations

from modules.media.schemas import MediaPlan
from modules.scenes.schemas import ScenePlan

from .schemas import Timeline, TimelineScene

PLACEHOLDER_ASSET_ID = "placeholder"


def build_timeline(
    scenes: ScenePlan,
    media: MediaPlan,
    narration_durations: dict[int, float] | None = None,
) -> Timeline:
    """Build a timeline from scene plan and media plan.

    *narration_durations* maps scene_number → actual measured narration length
    (seconds).  When provided, these override the LLM-estimated durations so
    the timeline matches the real audio.  Scenes not present in the dict
    fall back to ``scene.estimated_duration``.
    """
    assets_by_scene = {asset.scene_number: asset for asset in media.assets}
    narration_durations = narration_durations or {}
    timeline_scenes: list[TimelineScene] = []
    cursor = 0.0
    for scene in scenes.scenes:
        asset = assets_by_scene.get(scene.scene_number)
        duration = narration_durations.get(
            scene.scene_number, scene.estimated_duration
        )
        duration = max(0.0, duration)
        timeline_scenes.append(
            TimelineScene(
                scene_number=scene.scene_number,
                asset_id=asset.asset_id if asset else PLACEHOLDER_ASSET_ID,
                start_time=round(cursor, 3),
                end_time=round(cursor + duration, 3),
                transition=scene.transition,
            )
        )
        cursor += duration
    return Timeline(scenes=timeline_scenes, duration=round(cursor, 3))
