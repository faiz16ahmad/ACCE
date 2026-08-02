"""Deterministic shot planning — the Phase 1 pass-through fallback.

Phase 1 produces exactly one shot per scene, mirroring the scene's existing
visual plan (description, search keywords, visual type, transition). Because
1 scene == 1 shot, the V2 edit layer is behaviourally identical to V1; nothing
downstream consumes the ShotPlan yet (Phase 2 wires Media/Timeline to it).

This template is also the key-free fallback the LLM Shot Planner (Phase 3) will
reuse. Only *plans* shots — never retrieves media, times clips, or renders.
"""

from __future__ import annotations

from ..scenes.schemas import ScenePlan
from .schemas import ContentKind, MediaPreference, Shot, ShotPlan

# V1 visual_type -> V2 content_kind. Real content providers (animation,
# infographic, AI media) land later; these mappings keep the pass-through
# faithful to today's scene plan.
_CONTENT_KIND_BY_VISUAL_TYPE: dict[str, ContentKind] = {
    "stock_video": "stock_video",
    "stock_image": "stock_image",
    "animation": "stock_video",  # no animation kind yet; motion video is closest
    "infographic": "chart",  # no infographic kind yet; chart is closest
    "map": "map",
    "text_overlay": "text",
}

_MEDIA_PREFERENCE_BY_VISUAL_TYPE: dict[str, MediaPreference] = {
    "stock_video": "video",
    "animation": "video",
    "stock_image": "image",
    "infographic": "image",
    "map": "image",
    "text_overlay": "either",  # text scenes carry no media
}


def scene_id_for(scene_number: int) -> str:
    """Stable edit-layer id for a scene (matches the V2 id scheme)."""
    return f"scene_{scene_number:04d}"


def shot_id_for(index: int) -> str:
    """Global, zero-padded shot id (`shot_0001`, …)."""
    return f"shot_{index:04d}"


def _purpose_for(index: int, count: int) -> str:
    if count <= 1:
        return "main"
    if index == 0:
        return "establish"
    if index == count - 1:
        return "closing"
    return "main"


def plan_shots(scenes: ScenePlan) -> ShotPlan:
    """One shot per scene, carrying the scene's existing visual plan."""
    shots: list[Shot] = []
    count = len(scenes.scenes)
    for scene in scenes.scenes:
        visual_type = scene.visual_type
        shots.append(
            Shot(
                shot_id=shot_id_for(len(shots) + 1),
                scene_id=scene_id_for(scene.scene_number),
                position=1,
                purpose=_purpose_for(scene.scene_number - 1, count),
                visual_description=scene.visual_description,
                search_queries=list(scene.search_keywords),
                content_kind=_CONTENT_KIND_BY_VISUAL_TYPE.get(visual_type, "stock_video"),
                media_preference=_MEDIA_PREFERENCE_BY_VISUAL_TYPE.get(visual_type, "either"),
                motion_intent="none",
                importance="medium",
                transition_out=scene.transition,
            )
        )
    return ShotPlan(shots=shots)
