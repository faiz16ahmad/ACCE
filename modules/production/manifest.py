"""Render manifest construction.

The manifest is the renderer's complete, self-contained input: the timeline,
per-scene asset references, audio + subtitle references, render settings, and
transition metadata. Renderers consume only this manifest and never inspect
`ScenePlan` / `MediaPlan` / `AudioOutput` directly.
"""

from __future__ import annotations

from config.settings import ProductionConfig
from modules.audio.schemas import AudioOutput
from modules.media.schemas import MediaPlan
from modules.scenes.schemas import ScenePlan

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
    assets_by_scene = {asset.scene_number: asset for asset in media.assets}

    manifest_assets: list[ManifestAsset] = []
    transitions: dict[int, str] = {}
    for timeline_scene in timeline.scenes:
        scene = scenes_by_number.get(timeline_scene.scene_number)
        asset = assets_by_scene.get(timeline_scene.scene_number)
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
                scene_number=timeline_scene.scene_number,
                asset_id=timeline_scene.asset_id,
                asset_type=asset_type,
                local_path=local_path,
                url=url,
                text=text,
            )
        )
        transitions[timeline_scene.scene_number] = timeline_scene.transition

    return RenderManifest(
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
        transitions=transitions,
    )
