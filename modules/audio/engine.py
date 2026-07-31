"""Audio mixing engines.

An `AudioEngine` consumes an `AudioMixPlan` and produces one master audio
file. The plan/engine split is what lets V2 beat-synchronization be added as
a plan-building concern only — this contract never changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from .schemas import AudioMixPlan


class AudioEngine(ABC):
    @abstractmethod
    def mix(self, plan: AudioMixPlan, out_path: Path) -> Path:
        """Mix `plan` into a single master audio file at `out_path`."""


class StubAudioEngine(AudioEngine):
    """Writes a placeholder marker — real mixing needs ffmpeg + real assets."""

    def mix(self, plan: AudioMixPlan, out_path: Path) -> Path:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            f"[stub-audio-engine] {len(plan.segments)} segment(s) -> {out_path.name}",
            encoding="utf-8",
        )
        return out_path


class FfmpegAudioEngine(AudioEngine):
    """Real mixing via ffmpeg (audio milestone). Requires the binary."""

    def __init__(self, ffmpeg_path: str | None = None) -> None:
        self.ffmpeg_path = ffmpeg_path or "ffmpeg"

    def mix(self, plan: AudioMixPlan, out_path: Path) -> Path:
        raise NotImplementedError(
            "FfmpegAudioEngine requires ffmpeg and real audio assets (audio milestone). "
            "Set ACCE_AUDIO__ENGINE=stub for the V1 skeleton."
        )


def build_audio_engine(engine_name: str, ffmpeg_path: str | None = None) -> AudioEngine:
    if engine_name == "stub":
        return StubAudioEngine()
    if engine_name == "ffmpeg":
        return FfmpegAudioEngine(ffmpeg_path)
    raise ValueError(f"unknown audio engine: {engine_name!r}")
