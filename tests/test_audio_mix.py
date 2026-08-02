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
    assert "afade=t=in:st=0.000:d=0.200" in joined
    assert "afade=t=out:st=4.800:d=0.200" in joined
    assert "amix=inputs=2:duration=longest:normalize=0" in joined
    assert "loudnorm=I=-16:TP=-1.5:LRA=11" in joined
    assert "-c:a" in cmd and "aac" in cmd
    assert cmd[-1] == str(tmp_path / "master.m4a")


def test_build_mix_command_ducks_music_under_narration(tmp_path):
    cmd = build_mix_command(_plan(tmp_path), tmp_path / "master.m4a")
    joined = " ".join(cmd)
    assert "sidechaincompress=threshold=0.03:ratio=6:attack=20:release=300" in joined
    # Regression: the music bed must be looped so it covers the whole narration
    # span, and the narration amix must be split so the sidechain gets its own
    # copy (sharing the stream truncated the amix to its first segment).
    assert "-stream_loop -1 -i" in joined
    assert "asplit=2[narrA][narrB]" in joined
    assert "][narrA]sidechaincompress" in joined
    assert "][narrB]amix=inputs=2:duration=longest:normalize=0" in joined


def test_music_looped_and_capped_when_duck_disabled(tmp_path):
    cmd = build_mix_command(_plan(tmp_path), tmp_path / "master.m4a", duck=False)
    joined = " ".join(cmd)
    # Looped bed is unbounded; it must be trimmed to the music span so the
    # narration (longest) ends the mix, and no sidechain is used.
    assert "-stream_loop -1 -i" in joined
    assert "atrim=end=5.000" in joined
    assert "sidechaincompress" not in joined


def test_no_duck_when_narration_only(tmp_path):
    cmd = build_mix_command(_plan(tmp_path, music=False), tmp_path / "master.m4a")
    assert "sidechaincompress" not in " ".join(cmd)


def test_skips_missing_segment_files(tmp_path):
    plan = _plan(tmp_path)
    plan.segments[0].source_path = tmp_path / "does_not_exist.mp3"
    cmd = build_mix_command(plan, tmp_path / "master.m4a")
    # Only the music segment is mixed, so it's a single-input amix.
    assert "amix=inputs=1:duration=longest:normalize=0" in " ".join(cmd)


def test_missing_music_source_does_not_shift_narration_inputs(tmp_path):
    """Regression: a skipped segment must not shift ffmpeg input indices.

    When the music bed's source file is missing (e.g. an empty local music
    dir), the narration segments used to be labeled [1:a]..[N:a] with no
    [0:a], which ffmpeg rejects with 'Invalid file index'.
    """
    missing_bed = tmp_path / "bed.mp3"  # deliberately not created
    narr1 = tmp_path / "narr1.mp3"
    narr1.write_bytes(b"x")
    narr2 = tmp_path / "narr2.mp3"
    narr2.write_bytes(b"x")
    plan = AudioMixPlan(
        segments=[
            MixSegment(kind="music", source_path=missing_bed, start=0.0, end=5.0, volume=0.2),
            MixSegment(kind="narration", source_path=narr1, start=0.0, end=3.0, volume=1.0),
            MixSegment(kind="narration", source_path=narr2, start=3.0, end=6.0, volume=1.0),
        ],
        master_gain=1.0,
    )
    cmd = build_mix_command(plan, tmp_path / "master.m4a")
    joined = " ".join(cmd)
    # Exactly two real inputs were added; the filtergraph must reference them
    # as [0:a] and [1:a] — never [1:a]/[2:a] (which would point past the end).
    assert cmd.count("-i") == 2
    assert "[0:a]aformat" in joined and "[1:a]aformat" in joined
    assert "[2:a]aformat" not in joined
    # Both narration labels still feed the final amix.
    assert "amix=inputs=2:duration=longest:normalize=0" in joined


def test_empty_plan_produces_silence(tmp_path):
    cmd = build_mix_command(AudioMixPlan(), tmp_path / "master.m4a")
    assert "-f" in cmd and "lavfi" in cmd and "anullsrc" in " ".join(cmd)


def test_silence_command_helpers(tmp_path):
    cmd = _silence_command(tmp_path / "s.m4a", "ffmpeg")
    assert "anullsrc" in " ".join(cmd) and "aac" in cmd
