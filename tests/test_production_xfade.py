"""Milestone 10: true xfade crossfade graph + graceful fallback tests."""

from __future__ import annotations

from pathlib import Path

from modules.production.ffmpeg import build_command
from modules.production.schemas import (
    ManifestAsset,
    RenderManifest,
    RenderSettings,
    Timeline,
    TimelineScene,
)


def _manifest(
    durations: list[float],
    transitions: list[str],
    *,
    fade: float = 0.5,
    subtitle: Path | None = None,
) -> RenderManifest:
    start = 0.0
    scenes = []
    for index, (duration, transition) in enumerate(zip(durations, transitions, strict=True)):
        scenes.append(
            TimelineScene(
                scene_number=index + 1,
                asset_id=f"a{index + 1}",
                start_time=start,
                end_time=start + duration,
                transition=transition,
            )
        )
        start += duration
    assets = [
        ManifestAsset(scene_number=i + 1, asset_id=f"a{i + 1}", asset_type="placeholder", text=f"t{i + 1}")
        for i in range(len(durations))
    ]
    manifest = RenderManifest(
        timeline=Timeline(scenes=scenes, duration=sum(durations)),
        assets=assets,
        settings=RenderSettings(fade=fade),
        subtitle_path=subtitle,
    )
    return manifest


def test_two_scene_fade_uses_xfade(tmp_path):
    cmd = build_command(_manifest([5.0, 5.0], ["cut", "fade"]), tmp_path / "o.mp4")
    joined = " ".join(cmd)
    assert "xfade=transition=fade:duration=0.500:offset=5.500" in joined
    assert "concat=n=2:v=1:a=0" not in joined
    # Scene 1 (placeholder color source) is extended by the fade window so
    # the total output duration still equals the timeline (10.0s).
    assert "d=5.5" in joined
    assert "-t" in cmd and "10.0" in joined


def test_cut_transition_maps_to_xfade_cut(tmp_path):
    cmd = build_command(_manifest([5.0, 5.0], ["cut", "cut"]), tmp_path / "o.mp4")
    assert "xfade=transition=cut" in " ".join(cmd)


def test_fade_to_black_maps_to_fadeblack(tmp_path):
    cmd = build_command(_manifest([5.0, 5.0], ["cut", "fade_to_black"]), tmp_path / "o.mp4")
    assert "xfade=transition=fadeblack" in " ".join(cmd)


def test_three_scene_offsets_accumulate(tmp_path):
    cmd = build_command(_manifest([4.0, 4.0, 4.0], ["cut", "fade", "dissolve"]), tmp_path / "o.mp4")
    joined = " ".join(cmd)
    # Into scene 2: 4.0 + 0.5. Into scene 3: (4.5 + 4.0) + 0.5 = 9.0.
    assert "offset=4.500" in joined
    assert "offset=9.000" in joined
    assert "transition=dissolve" in joined


def test_single_scene_falls_back_to_concat(tmp_path):
    cmd = build_command(_manifest([5.0], ["cut"]), tmp_path / "o.mp4")
    joined = " ".join(cmd)
    assert "xfade=" not in joined
    assert "concat=n=1:v=1:a=0" in joined


def test_short_scene_falls_back_to_fade_approximation(tmp_path):
    # Scene 1 (0.6s) is shorter than the 2*fade window -> fade fallback.
    cmd = build_command(_manifest([0.6, 5.0], ["fade", "cut"]), tmp_path / "o.mp4")
    joined = " ".join(cmd)
    assert "xfade=" not in joined
    assert "concat=n=2:v=1:a=0" in joined
    assert "fade=t=in" in joined and "fade=t=out" in joined


def test_zero_fade_uses_concat(tmp_path):
    cmd = build_command(_manifest([5.0, 5.0], ["fade", "fade"], fade=0.0), tmp_path / "o.mp4")
    assert "xfade=" not in " ".join(cmd)


def test_subtitle_still_burned_after_xfade(tmp_path):
    sub = tmp_path / "subs.ass"
    sub.write_text("[Script Info]", encoding="utf-8")
    cmd = build_command(
        _manifest([5.0, 5.0], ["cut", "fade"], subtitle=sub), tmp_path / "o.mp4"
    )
    joined = " ".join(cmd)
    assert "xfade=" in joined
    assert "subtitles=" in joined
