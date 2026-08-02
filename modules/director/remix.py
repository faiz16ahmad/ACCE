"""Director remix — re-derive a MixPlan from the frozen narration + a music edit.

`build_director_plan` keeps the original narration segments untouched and swaps
the single music segment (or drops it for mode="none"). The result is a normal
`AudioMixPlan` that the existing `FfmpegAudioEngine` mixes unchanged — Director
never touches the mixer, it only supplies a different plan.

V1 model: one music track, one span (0 → narration_total). Future multi-track /
scene-specific music = more segments; the mixer already accepts N.
"""

from __future__ import annotations

import logging
from pathlib import Path

from modules.audio.engine import FfmpegAudioEngine
from modules.audio.schemas import AudioMixPlan, DuckSpec, MixSegment

from .schemas import MusicEdit

log = logging.getLogger(__name__)


def narration_total(plan: AudioMixPlan) -> float:
    """The end of the last narration segment — the music span's duration."""
    ends = [seg.end for seg in plan.segments if seg.kind == "narration"]
    return round(max(ends) if ends else 0.0, 3)


def build_director_plan(
    original: AudioMixPlan,
    edit: MusicEdit,
    track_path: Path | None,
) -> AudioMixPlan:
    """Return a new plan with the music segment replaced by `edit`'s choice.

    mode="none" (or an unresolvable track) yields a narration-only plan. All
    narration segments and the master gain come from the frozen plan unchanged.
    """
    narration = [seg for seg in original.segments if seg.kind == "narration"]
    total = max((seg.end for seg in narration), default=0.0)

    music_segment: MixSegment | None = None
    if edit.mode != "none" and track_path is not None and track_path.is_file():
        music_segment = MixSegment(
            kind="music",
            source_path=track_path,
            start=0.0,
            end=total,
            volume=edit.volume,
            fade_in=edit.fade_in,
            fade_out=edit.fade_out,
            duck=DuckSpec() if edit.duck else None,
        )

    segments: list[MixSegment] = []
    if music_segment is not None:
        segments.append(music_segment)
    segments.extend(narration)

    return AudioMixPlan(segments=segments, master_gain=original.master_gain)


def remix_master(
    plan: AudioMixPlan,
    out_path: Path,
    *,
    ffmpeg_path: str = "ffmpeg",
    duck: bool = True,
) -> Path:
    """Mix `plan` to `out_path` with the existing engine (unchanged)."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    engine = FfmpegAudioEngine(ffmpeg_path=ffmpeg_path, duck=duck)
    return engine.mix(plan, out_path)
