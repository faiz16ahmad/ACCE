"""Audio mixing engines.

An `AudioEngine` consumes an `AudioMixPlan` and produces one master audio
file. The plan/engine split is what lets V2 beat-synchronization be added as
a plan-building concern only — this contract never changes.

Milestone 10: `FfmpegAudioEngine` now implements the real mix (adelay + volume
+ fades + ducked music + loudness normalization) via `modules/audio/mix.py`.
The stub engine remains the key-free default and writes a marker file.
"""

from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod
from pathlib import Path

from .mix import build_mix_command
from .schemas import AudioMixPlan


class AudioEngineError(RuntimeError):
    """An audio mix backend failed."""


class AudioEngine(ABC):
    @abstractmethod
    def mix(self, plan: AudioMixPlan, out_path: Path) -> Path:
        """Mix `plan` into a single master audio file at `out_path`."""


class StubAudioEngine(AudioEngine):
    name = "stub"

    def mix(self, plan: AudioMixPlan, out_path: Path) -> Path:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            f"[stub-audio-engine] {len(plan.segments)} segment(s) -> {out_path.name}",
            encoding="utf-8",
        )
        return out_path


class FfmpegAudioEngine(AudioEngine):
    """Real mixing via ffmpeg: position, level, fades, ducking, loudnorm."""

    name = "ffmpeg"

    def __init__(
        self,
        ffmpeg_path: str | None = None,
        duck: bool = True,
        loudness: bool = True,
    ) -> None:
        self.ffmpeg_path = ffmpeg_path or "ffmpeg"
        self.duck = duck
        self.loudness = loudness

    def mix(self, plan: AudioMixPlan, out_path: Path) -> Path:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        command = build_mix_command(
            plan,
            out_path,
            ffmpeg_path=self.ffmpeg_path,
            duck=self.duck,
            loudness=self.loudness,
        )
        try:
            proc = subprocess.run(command, capture_output=True, text=True, timeout=600)
        except (OSError, subprocess.SubprocessError) as exc:
            raise AudioEngineError(f"ffmpeg failed to start: {exc}") from exc
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "")[-2000:]
            raise AudioEngineError(f"ffmpeg mix exited {proc.returncode}: {tail}")
        return out_path


def build_audio_engine(
    engine_name: str,
    ffmpeg_path: str | None = None,
    *,
    duck: bool = True,
) -> AudioEngine:
    if engine_name == "stub":
        return StubAudioEngine()
    if engine_name == "ffmpeg":
        return FfmpegAudioEngine(ffmpeg_path, duck=duck)
    raise ValueError(f"unknown audio engine: {engine_name!r}")
