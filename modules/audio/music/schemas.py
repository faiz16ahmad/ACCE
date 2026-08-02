"""Background-music contracts (architecture-audio.md §3).

Phase 1 adds *structures only* — nothing here is wired into the audio module,
so the mix output is byte-identical to today. The boundary follows the frozen
architecture: the planner emits intent (no files, no absolute time), the
retriever returns files with deterministic scores, the timeline owns all music
timing, and the renderer consumes the existing `AudioMixPlan`/`MixSegment`.

`AudioPlan` is the future-proof planning object; `MusicIntent` is its
music-specific V1 subset (future kinds — ambient, sfx — are added as sibling
fields, never by reshaping `AudioPlan`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class CurvePoint(BaseModel):
    """One point on the intensity arc.

    `at` is a *relative* position within the documentary (0.0..1.0), never an
    absolute second — the planner must not assign timestamps (A1); the Audio
    Timeline maps `at` to seconds using the measured narration total (A4).
    """

    at: float = 0.0
    value: float = 0.5


class FadePreferences(BaseModel):
    """Fade durations the planner *prefers*; the timeline owns the final
    values and clamps them within configured bounds (A4)."""

    fade_in: float | None = None  # seconds
    fade_out: float | None = None  # seconds
    crossfade: bool = False  # prefer crossfade between music segments (future)


class MusicIntent(BaseModel):
    """Planner output: structured intent only — no files, no timestamps."""

    emotion: str = "calm"  # controlled vocabulary (normalizer enforces, A7)
    energy: float = 0.5  # 0.0..1.0
    tempo_bpm: int | None = None  # target BPM, or None for "any"
    intensity: float = 0.5  # 0.0..1.0 overall arc intensity
    intensity_curve: list[CurvePoint] = Field(default_factory=list)  # optional
    style: str = "documentary"  # documentary style echo
    fade_preferences: FadePreferences = Field(default_factory=FadePreferences)


class AudioPlan(BaseModel):
    """Normalized plan — the enforcement boundary (A7).

    V1 carries *music* intents only (exactly one, the whole documentary).
    Future kinds (ambient, sfx) are added as sibling fields, never by
    reshaping this model.
    """

    music: list[MusicIntent] = Field(default_factory=list)


class MusicSelection(BaseModel):
    """Retrieval request, derived by the audio stage from the clock.

    `duration_hint` is the seconds the bed must cover, computed from the
    *measured narration*, never from the planner (A5).
    """

    intent: MusicIntent
    duration_hint: float = 0.0
    genre_hint: str | None = None  # legacy style→genre mapping, a hint only


class MusicAsset(BaseModel):
    """A file + factual metadata. Contains no narrative information (A3)."""

    asset_id: str
    provider: str
    title: str = ""
    local_path: Path | None = None
    duration: float = 0.0  # measured file duration
    bpm: int | None = None
    license: str = "unknown"
    tags: list[str] = Field(default_factory=list)  # retriever-side metadata


class RankedAsset(BaseModel):
    """Retrieval result: an asset plus its deterministic score and the
    per-criterion reasons (explainability, §3.5)."""

    asset: MusicAsset
    score: float = 0.0  # 0.0..1.0, deterministic
    reasons: dict[str, float] = Field(default_factory=dict)


# -- Audio Timeline: owns ALL music timing (A4) --------------------------------


class DuckSpec(BaseModel):
    """Narration ducking parameters for a music span (owned by the timeline)."""

    depth_db: float = 8.0
    attack: float = 0.05
    release: float = 0.5


class LoopSpec(BaseModel):
    """Loop policy for a span shorter than the music bed it must cover."""

    enabled: bool = False
    crossfade_seconds: float = 0.5


class VolumePoint(BaseModel):
    """Absolute-time volume automation point (timeline-mapped)."""

    at: float = 0.0  # seconds within the music segment
    value: float = 0.5  # 0.0..1.0


class MusicSpan(BaseModel):
    """One placed music segment: timing is decided only here (A4)."""

    asset_id: str
    start: float = 0.0  # seconds on the master clock
    end: float = 0.0
    volume: float = 1.0
    fade_in: float = 0.0
    fade_out: float = 0.0
    duck: DuckSpec = Field(default_factory=DuckSpec)
    loop: LoopSpec | None = None
    automation: list[VolumePoint] = Field(default_factory=list)


class AudioTimeline(BaseModel):
    """The timeline's audio layer: narration spans (the clock) + music spans.

    Flattens to the existing `AudioMixPlan`/`MixSegment` before the renderer.
    """

    narration_spans: list[tuple[float, float]] = Field(default_factory=list)
    music_spans: list[MusicSpan] = Field(default_factory=list)
    master_gain: float = 1.0


# Re-exported Literal so downstream plans can widen kinds additively.
MusicKind = Literal["music"]
