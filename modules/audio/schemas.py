"""Audio stage contracts.

`AudioMixPlan`/`MixSegment` are the architecture-stable boundary: V2
beat-sync only changes *how segment timings are computed*, never how the
engine or downstream stages consume a plan.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class AudioTrack(BaseModel):
    kind: Literal["narration", "music"]
    provider: str
    title: str = ""
    url: str = ""
    local_path: Path | None = None
    duration: float | None = None
    bpm: int | None = None  # present now so beat-sync needs no schema change
    license: str = "unknown"


class DuckSpec(BaseModel):
    """Narration-ducking parameters for a music segment (timeline-owned, A4).

    Lives on the stable seam so the renderer can consume it directly. The
    engine already ducks the whole bed; this spec is the per-segment,
    plan-level statement of how the timeline wants it done.
    """

    depth_db: float = 8.0
    attack: float = 0.05
    release: float = 0.5


class MixSegment(BaseModel):
    kind: Literal["narration", "music"]
    source_path: Path | None = None
    start: float = 0.0
    end: float = 0.0
    volume: float = 1.0
    fade_in: float = 0.0
    fade_out: float = 0.0
    duck: DuckSpec | None = None  # additive: music segments may duck under narration


class AudioMixPlan(BaseModel):
    segments: list[MixSegment] = Field(default_factory=list)
    master_gain: float = 1.0


class AudioMetadata(BaseModel):
    duration: float = 0.0
    narration_duration: float = 0.0
    music_provider: str | None = None
    music_title: str | None = None
    style_genre: str | None = None
    engine: str = "stub"
    voice: str | None = None
    cue_count: int = 0


class AudioCue(BaseModel):
    """One subtitle cue with a stable internal id (SRT output unaffected)."""

    cue_id: str
    index: int
    start: float
    end: float
    text: str


class AudioOutput(BaseModel):
    # Milestone-6 fields.
    narration_path: Path | None = None
    music_path: Path | None = None
    mixed_audio_path: Path | None = None
    subtitle_path: Path | None = None
    duration: float = 0.0
    metadata: AudioMetadata = Field(default_factory=AudioMetadata)
    cues: list[AudioCue] = Field(default_factory=list)
    # Back-compat fields (production reads `master_path`; tests use tracks).
    master_path: Path | None = None
    tracks: list[AudioTrack] = Field(default_factory=list)
    mix_plan_path: Path | None = None
