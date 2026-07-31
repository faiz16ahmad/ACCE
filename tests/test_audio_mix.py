"""Milestone 10: real ffmpeg mix-graph builder tests (pure, no binary)."""

from __future__ import annotations

from pathlib import Path

from modules.audio.mix import _silence_command, build_mix_command
from modules.audio.schemas import AudioMixPlan, MixSegment


def _plan(base: Path, narration: bool = True, music: bool = True) -> AudioMixPlan:
    segments = []
    if narration:
        narr = base / "narr.mp3"
        narr.write_bytes(b"x")
        segments.append(
            MixSegment(
                kind="narration",
                source_path=narr,
                start=0.0,
                end=5.0,
                volume=1.0,
                fade_in=0.2,
                fade_out=0.2,
            )
        )
    if music:
        bed = base / "bed.mp3"
        bed.write_bytes(b"x")
        segments.append(
            MixSegment(
                kind="music",
                source_path=bed,
                start=0.0,
                end=5.0,
                volume=0.2,
                fade_in=1.0,
                fade_out=1.0,
            )
        )
    return AudioMixPlan(segments=segments, master_gain=1.0)


def test_build_mix_command_places_and_levels_segments(tmp_path):
    cmd = build_mix_command(_plan(tmp_path), tmp_path / "master.m4a")
    joined = " ".join(cmd)
    assert "adelay=0|0" in joined
    assert "volume=1.0000" in joined and "volume=0.2000" in joined
    assert "afade=t=in:st=0:d=0.200" in joined
    assert "afade=t=out:st=4.800:d=0.200" in joined
    assert "amix=inputs=2:duration=longest:normalize=0" in joined
    assert "loudnorm=I=-16:TP=-1.5:LRA=11" in joined
    assert "-c:a" in cmd and "aac" in cmd
    assert cmd[-1] == str(tmp_path / "master.m4a")


def test_build_mix_command_ducks_music_under_narration(tmp_path):
    cmd = build_mix_command(_plan(tmp_path), tmp_path / "master.m4a")
    assert "sidechaincompress=threshold=0.03:ratio=6:attack=20:release=300" in " ".join(cmd)


def test_no_duck_when_narration_only(tmp_path):
    cmd = build_mix_command(_plan(tmp_path, music=False), tmp_path / "master.m4a")
    assert "sidechaincompress" not in " ".join(cmd)


def test_skips_missing_segment_files(tmp_path):
    plan = _plan(tmp_path)
    plan.segments[0].source_path = tmp_path / "does_not_exist.mp3"
    cmd = build_mix_command(plan, tmp_path / "master.m4a")
    # Only the music segment is mixed, so it's a single-input amix.
    assert "amix=inputs=1:duration=longest:normalize=0" in " ".join(cmd)


def test_empty_plan_produces_silence(tmp_path):
    cmd = build_mix_command(AudioMixPlan(), tmp_path / "master.m4a")
    assert "-f" in cmd and "lavfi" in cmd and "anullsrc" in " ".join(cmd)


def test_silence_command_helpers(tmp_path):
    cmd = _silence_command(tmp_path / "s.m4a", "ffmpeg")
    assert "anullsrc" in " ".join(cmd) and "aac" in cmd
