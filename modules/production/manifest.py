"""Render manifest construction (architecture v2).

The manifest is the renderer's complete, self-contained input: the shot-keyed
timeline, per-clip asset references, audio + subtitle references, and render
settings. Renderers consume only this manifest and never inspect `ScenePlan` /
`MediaPlan` / `AudioOutput` directly. Assets are resolved **by `asset_id`** —
the renderer never pairs clips to assets by position.
"""

from __future__ import annotations

from config.settings import ProductionConfig
from modules.audio.schemas import AudioOutput
from modules.media.schemas import MediaPlan
from modules.scenes.schemas import ScenePlan
from modules.shots.template import scene_id_for

from .schemas import ManifestAsset, RenderManifest, RenderSettings, Timeline


def build_manifest(
    timeline: Timeline,
    scenes: ScenePlan,
    media: MediaPlan,
    audio: AudioOutput | None,
    config: ProductionConfig | None = None,
    subtitle_path=None,
) -> RenderManifest:
    config = config or ProductionConfig()
    scenes_by_number = {scene.scene_number: scene for scene in scenes.scenes}
    scene_number_by_id = {scene_id_for(scene.scene_number): scene.scene_number for scene in scenes.scenes}
    assets_by_shot = {asset.shot_id: asset for asset in media.assets if asset.shot_id}
    assets_by_scene = {asset.scene_number: asset for asset in media.assets}

    manifest_assets: list[ManifestAsset] = []
    for clip in timeline.clips:
        scene_number = scene_number_by_id.get(clip.scene_id, 0)
        scene = scenes_by_number.get(scene_number)
        asset = assets_by_shot.get(clip.shot_id) or assets_by_scene.get(scene_number)
        text = scene.narration_segment if scene else ""

        if asset is not None and asset.local_path is not None and asset.local_path.exists():
            asset_type: str = asset.asset_type
            local_path = asset.local_path
            url = asset.asset_url
        elif scene is not None and scene.visual_type == "text_overlay":
            asset_type = "text"
            local_path = None
            url = ""
        else:
            asset_type = "placeholder"
            local_path = None
            url = asset.asset_url if asset else ""

        manifest_assets.append(
            ManifestAsset(
                shot_id=clip.shot_id,
                scene_number=scene_number,
                asset_id=clip.asset_id,
                asset_type=asset_type,
                local_path=local_path,
                url=url,
                text=text,
            )
        )

    return RenderManifest(
        version=2,
        timeline=timeline,
        assets=manifest_assets,
        audio_path=audio.mixed_audio_path if audio else None,
        subtitle_path=subtitle_path,
        settings=RenderSettings(
            width=config.width,
            height=config.height,
            fps=config.fps,
            fade=config.fade,
            crf=config.crf,
            preset=config.preset,
            faststart=config.faststart,
        ),
    )
