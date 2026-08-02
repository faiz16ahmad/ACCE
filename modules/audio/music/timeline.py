"""Audio Timeline — owns ALL music timing (architecture-audio.md §3, A4).

Consumes a normalized `AudioPlan` + a retrieved `MusicAsset` (never selects
files itself) + the measured narration total (the clock, A5) and produces the
`AudioTimeline`. Flattening to the renderer's stable `AudioMixPlan` is also
timeline-owned: narration segments come from the measured TTS tracks, music
segments from the placed spans. The renderer is never asked to plan or loop.

Phase 2: V1 places exactly one bed spanning the whole narration clock.
"""

from __future__ import annotations

from config.settings import AudioConfig, MusicConfig

from ..schemas import AudioMixPlan, DuckSpec, MixSegment
from ..schemas import AudioTrack  # noqa: F401 - narration tracks for flatten
from .schemas import AudioPlan, AudioTimeline, LoopSpec, MusicAsset, MusicIntent, MusicSpan, VolumePoint


def build_audio_timeline(
    plan: AudioPlan,
    asset: MusicAsset | None,
    narration_total: float,
    audio_config: AudioConfig,
    music_config: MusicConfig,
) -> AudioTimeline:
    """Place the music bed. No music asset -> an empty music layer (A10)."""
    intent = plan.music[0] if plan.music else MusicIntent()
    total = max(0.0, narration_total)
    music_spans: list[MusicSpan] = []
    if asset is not None and total > 0:
        fade_in = _bound_fade(intent.fade_preferences.fade_in, audio_config.music_fade, music_config.max_fade_seconds)
        fade_out = _bound_fade(intent.fade_preferences.fade_out, audio_config.music_fade, music_config.max_fade_seconds)
        asset_duration = asset.duration or 0.0
        loop = LoopSpec(enabled=bool(asset_duration and asset_duration < total), crossfade_seconds=0.5)
        automation = [VolumePoint(at=round(point.at * total, 3), value=point.value) for point in intent.intensity_curve]
        music_spans.append(
            MusicSpan(
                asset_id=asset.asset_id,
                start=0.0,
                end=round(total, 3),
                volume=audio_config.music_volume,
                fade_in=fade_in,
                fade_out=fade_out,
                duck=DuckSpec(),
                loop=loop,
                automation=automation,
            )
        )
    return AudioTimeline(
        narration_spans=[(0.0, round(total, 3))] if total > 0 else [],
        music_spans=music_spans,
        master_gain=audio_config.master_gain,
    )


def flatten_timeline(
    timeline: AudioTimeline,
    narration_tracks: list[AudioTrack],
    music_assets: dict[str, MusicAsset],
    audio_config: AudioConfig,
) -> AudioMixPlan:
    """Flatten to the stable `AudioMixPlan` (the renderer's input).

    Narration segments are placed sequentially from measured track durations
    (the clock); music segments map spans -> sources by `asset_id`.
    """
    segments: list[MixSegment] = []
    cursor = 0.0
    for track in narration_tracks:
        end = cursor + (track.duration or 5.0)
        segments.append(
            MixSegment(
                kind="narration",
                source_path=track.local_path,
                start=cursor,
                end=end,
                volume=audio_config.narration_volume,
                fade_in=audio_config.narration_fade,
                fade_out=audio_config.narration_fade,
            )
        )
        cursor = end
    for span in timeline.music_spans:
        asset = music_assets.get(span.asset_id)
        if asset is None:
            continue
        # The plan records the music even when the source isn't local yet; the
        # renderer skips segments whose source is missing (A10).
        segments.append(
            MixSegment(
                kind="music",
                source_path=asset.local_path,
                start=span.start,
                end=span.end,
                volume=span.volume,
                fade_in=span.fade_in,
                fade_out=span.fade_out,
                duck=span.duck,
            )
        )
    return AudioMixPlan(segments=segments, master_gain=timeline.master_gain)


def _bound_fade(preference: float | None, fallback: float, max_fade: float) -> float:
    if preference is None:
        return round(max(0.0, min(max_fade, fallback)), 3)
    return round(max(0.0, min(max_fade, preference)), 3)
