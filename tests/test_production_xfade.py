"""Milestone 10: true xfade crossfade graph + graceful fallback tests."""

from __future__ import annotations

from pathlib import Path

from modules.production.ffmpeg import build_command
from modules.production.normalize import normalize_manifest
from modules.production.schemas import Clip, ManifestAsset, RenderManifest, RenderSettings, Timeline


def _manifest(
    durations: list[float],
    transitions: list[str],
    *,
    fade: float = 0.5,
    subtitle: Path | None = None,
) -> RenderManifest:
    start = 0.0
    clips = []
    for index, (duration, transition) in enumerate(zip(durations, transitions, strict=True)):
        clips.append(
            Clip(
                shot_id=f"shot_{index + 1:04d}",
                scene_id=f"scene_{index + 1:04d}",
                asset_id=f"a{index + 1}",
                start=start,
                end=start + duration,
                transition_out=transition,
            )
        )
        start += duration
    assets = [
        ManifestAsset(
            shot_id=f"shot_{i + 1:04d}",
            scene_number=i + 1,
            asset_id=f"a{i + 1}",
            asset_type="placeholder",
            text=f"t{i + 1}",
        )
        for i in range(len(durations))
    ]
    manifest = RenderManifest(
        timeline=Timeline(clips=clips, duration=sum(durations)),
        assets=assets,
        settings=RenderSettings(fade=fade),
        subtitle_path=subtitle,
    )
    return manifest


def _v1_manifest_dict(durations: list[float], transitions: list[str]) -> dict:
    """A v1 (scene-keyed) manifest as it would exist on disk before migration."""
    start = 0.0
    scenes = []
    for index, (duration, transition) in enumerate(zip(durations, transitions, strict=True)):
        scenes.append(
            {
                "scene_number": index + 1,
                "asset_id": f"a{index + 1}",
                "start_time": start,
                "end_time": start + duration,
                "transition": transition,
            }
        )
        start += duration
    return {
        "version": 1,
        "timeline": {"scenes": scenes, "duration": sum(durations)},
        "assets": [
            {
                "scene_number": i + 1,
                "asset_id": f"a{i + 1}",
                "asset_type": "placeholder",
                "text": f"t{i + 1}",
            }
            for i in range(len(durations))
        ],
    }


def test_two_scene_fade_uses_xfade(tmp_path):
    cmd = build_command(_manifest([5.0, 5.0], ["cut", "fade"]), tmp_path / "o.mp4")
    joined = " ".join(cmd)
    # Offset equals the scene's start_time in the timeline (the cumulative
    # *visible* duration), not the extended clip length.  The first clip is
    # trimmed to d + fade (5.5) so it has enough tail content for xfade.
    assert "xfade=transition=fade:duration=0.500:offset=5.000" in joined
    assert "concat=n=2:v=1:a=0" not in joined
    assert "d=5.5" in joined
    assert "-t" in cmd and "10.0" in joined


def test_cut_transition_maps_to_xfade_cut(tmp_path):
    cmd = build_command(_manifest([5.0, 5.0], ["cut", "cut"]), tmp_path / "o.mp4")
    assert "xfade=transition=fade" in " ".join(cmd)


def test_fade_to_black_maps_to_fadeblack(tmp_path):
    cmd = build_command(_manifest([5.0, 5.0], ["cut", "fade_to_black"]), tmp_path / "o.mp4")
    assert "xfade=transition=fadeblack" in " ".join(cmd)


def test_three_scene_offsets_accumulate(tmp_path):
    cmd = build_command(_manifest([4.0, 4.0, 4.0], ["cut", "fade", "dissolve"]), tmp_path / "o.mp4")
    joined = " ".join(cmd)
    # Offsets follow timeline start_times: scene 2 at 4.0, scene 3 at 8.0.
    assert "offset=4.000" in joined
    assert "offset=8.000" in joined
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


# -- V1 manifest normalizer (old saved jobs still render) ----------------------


def test_normalize_manifest_converts_v1_dict_to_v2_clips():
    v2 = normalize_manifest(_v1_manifest_dict([5.0, 4.0], ["cut", "fade"]))
    assert v2.version == 2
    assert [c.shot_id for c in v2.timeline.clips] == ["shot_0001", "shot_0002"]
    assert [c.scene_id for c in v2.timeline.clips] == ["scene_0001", "scene_0002"]
    assert v2.timeline.clips[0].start == 0.0 and v2.timeline.clips[0].end == 5.0
    assert v2.timeline.clips[1].start == 5.0 and v2.timeline.clips[1].end == 9.0
    assert v2.timeline.clips[1].transition_out == "fade"
    assert v2.assets[1].shot_id == "shot_0002"
    assert v2.timeline.duration == 9.0


def test_normalize_manifest_is_idempotent():
    v2 = normalize_manifest(_v1_manifest_dict([5.0], ["cut"]))
    again = normalize_manifest(v2)
    assert again == v2


def test_build_command_accepts_v1_manifest_dict(tmp_path):
    # A V1 dict goes straight into the renderer entry point and renders.
    cmd = build_command(_v1_manifest_dict([5.0, 5.0], ["cut", "fade"]), tmp_path / "o.mp4")
    joined = " ".join(cmd)
    assert "xfade=transition=fade:duration=0.500:offset=5.000" in joined
    assert "concat=n=2:v=1:a=0" not in joined
