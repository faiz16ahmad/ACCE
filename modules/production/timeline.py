"""Timeline construction for the production stage.

Scene timings come entirely from the ScenePlan (never inferred from media
length). Each timeline scene carries the scene number, the selected asset id
(from the MediaPlan, or "placeholder" when missing), its start/end times, and
its transition.
"""

from __future__ import annotations

from modules.media.schemas import MediaPlan
from modules.scenes.schemas import ScenePlan

from .schemas import Timeline, TimelineScene

PLACEHOLDER_ASSET_ID = "placeholder"


def build_timeline(scenes: ScenePlan, media: MediaPlan) -> Timeline:
    assets_by_scene = {asset.scene_number: asset for asset in media.assets}
    timeline_scenes: list[TimelineScene] = []
    cursor = 0.0
    for scene in scenes.scenes:
        asset = assets_by_scene.get(scene.scene_number)
        duration = max(0.0, scene.estimated_duration)
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
