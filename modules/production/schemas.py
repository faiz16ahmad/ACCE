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


class TimelineScene(BaseModel):
    scene_number: int
    asset_id: str
    start_time: float
    end_time: float
    transition: str


class Timeline(BaseModel):
    scenes: list[TimelineScene] = Field(default_factory=list)
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
    """One asset reference in the render manifest (per timeline scene)."""

    scene_number: int
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
    """

    version: int = 1
    timeline: Timeline
    assets: list[ManifestAsset] = Field(default_factory=list)
    audio_path: Path | None = None
    subtitle_path: Path | None = None
    settings: RenderSettings = Field(default_factory=RenderSettings)
    transitions: dict[int, str] = Field(default_factory=dict)


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
