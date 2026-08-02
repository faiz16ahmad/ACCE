"""Background-music sub-pipeline (architecture-audio.md).

Phase 1: structures only — nothing here is wired into the audio module yet,
so the mix output is byte-identical to today. The Audio stage consumes these
contracts starting in Phase 2.
"""

from .schemas import (
    AudioPlan,
    AudioTimeline,
    CurvePoint,
    DuckSpec,
    FadePreferences,
    LoopSpec,
    MusicAsset,
    MusicIntent,
    MusicSelection,
    MusicSpan,
    RankedAsset,
    VolumePoint,
)

__all__ = [
    "AudioPlan",
    "AudioTimeline",
    "CurvePoint",
    "DuckSpec",
    "FadePreferences",
    "LoopSpec",
    "MusicAsset",
    "MusicIntent",
    "MusicSelection",
    "MusicSpan",
    "RankedAsset",
    "VolumePoint",
]
