"""Production stage contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class SubtitleCue(BaseModel):
    index: int
    start: float
    end: float
    text: str


class MotionDescriptor(BaseModel):
    """Concrete motion resolved by the Timeline, applied by the renderer."""

    kind: Literal[
        "none", "kenburns_zoom_in", "kenburns_zoom_out", "pan_left", "pan_right", "pan_up", "pan_down"
    ] = "none"
    duration: float = 0.0


class Clip(BaseModel):
    """One timed visual unit in the edit layer (architecture v2).

    Binds a Shot's intent to a chosen asset at concrete times. `motion` is the
    resolved motion descriptor (None until motion resolution lands; the
    renderer treats None as "no motion").
    """

    shot_id: str
    scene_id: str
    asset_id: str
    start: float
    end: float
    transition_out: str = "cut"
    motion: MotionDescriptor | None = None


class Timeline(BaseModel):
    clips: list[Clip] = Field(default_factory=list)
    duration: float = 0.0


class RenderSettings(BaseModel):
    width: int = 1920
    height: int = 1080
    fps: int = 30
    codec: str = "libx264"
    audio_codec: str = "aac"
    fade: float = 0.5  # V1 transition fade duration (seconds)
    # x264 encoding tuning (milestone 10). Additive — old manifests parse fine.
    crf: int = 18
    preset: str = "veryfast"
    faststart: bool = True


class ManifestAsset(BaseModel):
    """One asset reference in the render manifest (per timeline clip)."""

    shot_id: str = ""
    scene_number: int = 0
    asset_id: str
    asset_type: Literal["image", "video", "text", "placeholder"]
    local_path: Path | None = None
    url: str = ""
    text: str = ""  # narration text for text-overlay / placeholder scenes


class RenderManifest(BaseModel):
    """The renderer's complete, self-contained input.

    Renderers consume ONLY this manifest and never inspect ScenePlan /
    MediaPlan / AudioOutput directly, keeping backends isolated, replaceable,
    and the render job replayable.

    Version 2: the timeline is a list of `Clip`s and the renderer resolves
    assets **by `asset_id`** (never by position). V1 manifests (scene-keyed,
    `version == 1`) are converted by `normalize_manifest`.
    """

    version: int = 2
    timeline: Timeline
    assets: list[ManifestAsset] = Field(default_factory=list)
    audio_path: Path | None = None
    subtitle_path: Path | None = None
    settings: RenderSettings = Field(default_factory=RenderSettings)


class RenderResult(BaseModel):
    video_path: Path
    log: str = ""


class RenderLog(BaseModel):
    renderer: str
    duration: float = 0.0
    log: str = ""


class ProductionOutput(BaseModel):
    video_path: Path
    timeline_path: Path | None = None
    render_manifest_path: Path | None = None
    render_log_path: Path | None = None
    subtitle_path: Path | None = None
    thumbnail_path: Path | None = None
    duration: float = 0.0
    title: str
    description: str
    metadata: dict = Field(default_factory=dict)
