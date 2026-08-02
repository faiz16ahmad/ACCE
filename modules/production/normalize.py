"""Manifest normalizer: v1 (scene-keyed) -> v2 (clip-keyed).

Old saved V1 render manifests (`version == 1`, `timeline.scenes`) are
translated into the v2 clip shape so a v2 renderer can replay them. The 1:1
scene<->shot assumption of Phase 1 makes this lossless: each scene becomes one
clip with a synthesized shot/scene id, and each asset gains its shot_id.
"""

from __future__ import annotations

from modules.shots.template import scene_id_for, shot_id_for

from .schemas import RenderManifest


def normalize_manifest(manifest: RenderManifest | dict) -> RenderManifest:
    """Return a v2 `RenderManifest` from a v2 model or a v1/v2 JSON dict."""
    if isinstance(manifest, RenderManifest):
        if manifest.version >= 2 and manifest.timeline.clips:
            return manifest
        data = manifest.model_dump(mode="json")
    else:
        data = dict(manifest)

    version = data.get("version", 1)
    timeline = data.get("timeline") or {}
    if version >= 2 and timeline.get("clips"):
        return RenderManifest.model_validate(data)

    # v1: `timeline.scenes` -> clips; assets get a synthesized shot_id.
    scenes = timeline.get("scenes") or []
    clips: list[dict] = []
    for scene in scenes:
        number = scene.get("scene_number", 0) or 0
        clips.append(
            {
                "shot_id": shot_id_for(number),
                "scene_id": scene_id_for(number),
                "asset_id": scene.get("asset_id", "placeholder"),
                "start": scene.get("start_time", 0.0),
                "end": scene.get("end_time", 0.0),
                "transition_out": scene.get("transition", "cut"),
                "motion": None,
            }
        )
    data["timeline"] = {"clips": clips, "duration": timeline.get("duration", 0.0)}
    for asset in data.get("assets", []):
        number = asset.get("scene_number", 0) or 0
        if not asset.get("shot_id") and number:
            asset["shot_id"] = shot_id_for(number)
    data["version"] = 2
    return RenderManifest.model_validate(data)
