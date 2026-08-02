"""Production module tests (milestone 7).

Timeline + render-manifest construction, image/video/text/placeholder scene
handling in the ffmpeg command, transition fades, subtitle overlay, renderer
failure, the stub renderer, and FFmpeg command generation. No ffmpeg or
network required.
"""

from __future__ import annotations

import json

import pytest

from config.settings import ProductionConfig, TimelineConfig
from core.stages import Stage
from modules.audio.schemas import AudioOutput
from modules.media.schemas import MediaAssetPlan, MediaPlan
from modules.production.default import DefaultProductionModule
from modules.production.ffmpeg import _fade_filters, build_command
from modules.production.manifest import build_manifest
from modules.production.renderer import FFmpegRenderer, RendererError, StubRenderer, build_renderer
from modules.production.schemas import RenderResult
from modules.production.timeline import build_timeline
from modules.scenes.schemas import Scene, ScenePlan
from modules.shots.schemas import Shot, ShotPlan
from modules.shots.template import plan_shots


def _scenes(*visual_types: str) -> ScenePlan:
    return ScenePlan(
        scenes=[
            Scene(scene=i, narration=f"scene {i} text.", duration=10.0, visual_type=visual)
            for i, visual in enumerate(visual_types, start=1)
        ]
    )


def _asset(scene: int, asset_type: str, local_path=None) -> MediaAssetPlan:
    return MediaAssetPlan(
        scene_number=scene,
        asset_id=f"asset_{scene:04d}",
        selected_provider="p",
        asset_type=asset_type,
        asset_url="https://u",
        local_path=local_path,
        license="p",
    )


def _asset_with_shot(scene: int, shot_id: str, asset_type: str, local_path=None) -> MediaAssetPlan:
    return MediaAssetPlan(
        scene_number=scene,
        shot_id=shot_id,
        asset_id=f"asset_{scene:04d}",
        selected_provider="p",
        asset_type=asset_type,
        asset_url="https://u",
        local_path=local_path,
        license="p",
    )


def _manifest(scenes: ScenePlan, media: MediaPlan, *, audio=None, subtitle=None, config=None) -> object:
    return build_manifest(build_timeline(scenes, media), scenes, media, audio, config, subtitle)


# -- timeline -----------------------------------------------------------------


def test_timeline_build_and_placeholder_asset():
    scenes = ScenePlan(
        scenes=[
            Scene(scene=1, narration="a", duration=10.0, visual_type="stock_video", transition="fade"),
            Scene(scene=2, narration="b", duration=5.0, visual_type="text_overlay"),
        ]
    )
    media = MediaPlan(assets=[_asset(1, "video")])
    timeline = build_timeline(scenes, media)

    assert [c.scene_id for c in timeline.clips] == ["scene_0001", "scene_0002"]
    assert [c.shot_id for c in timeline.clips] == ["shot_0001", "shot_0002"]
    assert timeline.clips[0].asset_id == "asset_0001"
    assert timeline.clips[1].asset_id == "placeholder"  # no media for scene 2
    assert timeline.clips[0].start == 0.0 and timeline.clips[0].end == 10.0
    assert timeline.clips[1].start == 10.0 and timeline.clips[1].end == 15.0
    assert timeline.clips[0].transition_out == "fade"
    assert timeline.duration == 15.0


def test_timeline_with_shot_plan_resolves_assets_by_shot_id():
    scenes = _scenes("stock_video")
    shot_plan = plan_shots(scenes)
    media = MediaPlan(assets=[_asset_with_shot(1, "shot_0001", "video")])
    timeline = build_timeline(scenes, media, shot_plan=shot_plan)

    assert len(timeline.clips) == 1
    assert timeline.clips[0].shot_id == "shot_0001"
    assert timeline.clips[0].scene_id == "scene_0001"
    assert timeline.clips[0].asset_id == "asset_0001"
    assert timeline.clips[0].motion is None


def test_timeline_shot_plan_uses_measured_narration_durations():
    scenes = _scenes("stock_video", "stock_video")
    shot_plan = plan_shots(scenes)
    media = MediaPlan(
        assets=[
            _asset_with_shot(1, "shot_0001", "video"),
            _asset_with_shot(2, "shot_0002", "video"),
        ]
    )
    timeline = build_timeline(
        scenes, media, narration_durations={1: 8.0, 2: 12.0}, shot_plan=shot_plan
    )
    assert timeline.duration == 20.0
    assert timeline.clips[0].end == 8.0
    assert timeline.clips[1].start == 8.0 and timeline.clips[1].end == 20.0


def test_timeline_allocation_honors_min_shot_duration():
    # Scene rhythm "high" -> "build" shaping collapses the first shot's weight
    # (~1.15s raw). The old global renormalize scaled it below min_shot_duration;
    # the pin-and-redistribute fix keeps it at the floor while preserving I7.
    scenes = ScenePlan(
        scenes=[Scene(scene=1, narration="One two three four five six seven eight nine ten.", rhythm="high")]
    )
    shot_plan = ShotPlan(
        shots=[
            Shot(shot_id="shot_0001", scene_id="scene_0001", position=1, importance="high"),
            Shot(shot_id="shot_0002", scene_id="scene_0001", position=2, importance="medium"),
            Shot(shot_id="shot_0003", scene_id="scene_0001", position=3, importance="high"),
        ]
    )
    config = TimelineConfig(min_shot_duration=1.5)
    timeline = build_timeline(
        scenes, MediaPlan(assets=[]), narration_durations={1: 6.456}, shot_plan=shot_plan, config=config
    )

    assert len(timeline.clips) == 3
    assert all(clip.end - clip.start >= config.min_shot_duration for clip in timeline.clips)
    # I7: the per-scene clip sum still equals the measured narration budget.
    assert abs(sum(clip.end - clip.start for clip in timeline.clips) - 6.456) < 0.01


# -- render manifest ----------------------------------------------------------


def test_render_manifest_build_and_roundtrip(tmp_path):
    img = tmp_path / "scene_01.jpg"
    img.write_bytes(b"x")
    scenes = _scenes("stock_image", "text_overlay")
    media = MediaPlan(assets=[_asset(1, "image", img)])
    manifest = _manifest(scenes, media, config=ProductionConfig(width=1280, height=720))

    assert manifest.version == 2
    assert manifest.assets[0].asset_type == "image" and manifest.assets[0].local_path == img
    assert manifest.assets[1].asset_type == "text" and manifest.assets[1].text == "scene 2 text."
    assert manifest.settings.width == 1280 and manifest.settings.fps == 30
    assert manifest.assets[0].shot_id == "shot_0001"
    assert manifest.assets[1].shot_id == "shot_0002"

    data = json.loads(manifest.model_dump_json())
    assert data["version"] == 2
    assert data["assets"][1]["asset_type"] == "text"
    assert data["timeline"]["clips"][1]["shot_id"] == "shot_0002"


def test_render_manifest_placeholder_when_missing_file(tmp_path):
    scenes = _scenes("stock_video")
    missing = tmp_path / "nope.mp4"
    media = MediaPlan(assets=[_asset(1, "video", missing)])  # local_path set but gone
    manifest = _manifest(scenes, media)
    assert manifest.assets[0].asset_type == "placeholder"


# -- ffmpeg command generation ------------------------------------------------


def test_command_image_scene(tmp_path):
    img = tmp_path / "a.jpg"
    img.write_bytes(b"x")
    scenes = _scenes("stock_image")
    media = MediaPlan(assets=[_asset(1, "image", img)])
    cmd = build_command(_manifest(scenes, media, config=ProductionConfig(width=640, height=360)), tmp_path / "out.mp4")

    assert "-loop" in cmd and "1" in cmd
    assert str(img) in cmd
    joined = " ".join(cmd)
    assert "trim=0:10.0" in joined and "scale=640:360" in joined
    assert "concat=n=1:v=1:a=0" in joined
    assert "-t" in cmd and "10.0" in joined


def test_command_video_scene(tmp_path):
    vid = tmp_path / "b.mp4"
    vid.write_bytes(b"x")
    scenes = _scenes("stock_video")
    media = MediaPlan(assets=[_asset(1, "video", vid)])
    cmd = build_command(_manifest(scenes, media), tmp_path / "out.mp4")

    joined = " ".join(cmd)
    assert "-stream_loop" in cmd and "trim=0:10.0" in joined
    assert "-loop" not in cmd


def test_command_text_and_placeholder_scenes(tmp_path):
    text = _scenes("text_overlay")
    text_manifest = _manifest(text, MediaPlan(assets=[]))
    out_text = tmp_path / "out_text.mp4"
    text_cmd = build_command(text_manifest, out_text)
    joined = " ".join(text_cmd)
    assert "color=c=" in joined
    assert "drawtext=textfile=" in joined
    # narration was written to a per-scene text file referenced by drawtext
    text_files = list(tmp_path.glob("out_text_text_*.txt"))
    assert text_files and "scene 1 text." in text_files[0].read_text(encoding="utf-8")

    placeholder = _scenes("stock_video")
    placeholder_manifest = _manifest(placeholder, MediaPlan(assets=[]))
    placeholder_cmd = build_command(placeholder_manifest, tmp_path / "out_placeholder.mp4")
    assert "color=c=" in " ".join(placeholder_cmd)


def test_transition_fades():
    assert _fade_filters("cut", 5.0, 0.5) == []
    fade = _fade_filters("fade", 5.0, 0.5)
    assert "fade=t=in" in fade[0] and "fade=t=out" in fade[1]
    dissolve = _fade_filters("dissolve", 5.0, 0.5)
    assert "fade=t=in" in dissolve[0] and "fade=t=out" in dissolve[1]
    fade_black = _fade_filters("fade_to_black", 5.0, 0.5)
    assert "fade=t=out" in fade_black[0] and len(fade_black) == 1


def test_command_subtitle_overlay(tmp_path):
    sub = tmp_path / "subs.srt"
    sub.write_text("1\n00:00:00,000 --> 00:00:10,000\nhi\n", encoding="utf-8")
    cmd = build_command(_manifest(_scenes("stock_video"), MediaPlan(assets=[]), subtitle=sub), tmp_path / "out.mp4")
    assert any("subtitles=" in part for part in cmd)
    assert sub.name in " ".join(cmd)  # path is filter-escaped, filename preserved


def test_command_audio_sync(tmp_path):
    audio = tmp_path / "master.mp3"
    audio.write_bytes(b"x")
    manifest = _manifest(_scenes("stock_video"), MediaPlan(assets=[]), audio=AudioOutput(mixed_audio_path=audio))
    cmd = build_command(manifest, tmp_path / "out.mp4")

    joined = " ".join(cmd)
    assert str(audio) in cmd
    assert "1:a" in joined  # audio is input index 1 (one scene input)
    assert "-c:a" in cmd and "aac" in cmd


def test_command_all_inputs_precede_maps(tmp_path):
    """Regression: ffmpeg rejects `-map` placed before an `-i` input.

    All `-i` options must come first, or ffmpeg treats the earlier `-map` as
    an input option for the next input file ("cannot be applied to input url").
    """
    audio = tmp_path / "master.mp3"
    audio.write_bytes(b"x")
    manifest = _manifest(_scenes("stock_video"), MediaPlan(assets=[]), audio=AudioOutput(mixed_audio_path=audio))
    cmd = build_command(manifest, tmp_path / "out.mp4")

    first_map = cmd.index("-map")
    last_input = max(i for i, part in enumerate(cmd) if part == "-i")
    assert last_input < first_map
    # The first -map references the filter output, the second the audio stream.
    assert cmd[first_map + 1].startswith("[")
    assert "1:a" in cmd


def test_command_full_argv(tmp_path):
    img = tmp_path / "a.jpg"
    img.write_bytes(b"x")
    vid = tmp_path / "b.mp4"
    vid.write_bytes(b"x")
    scenes = ScenePlan(
        scenes=[
            Scene(scene=1, narration="one.", duration=5.0, visual_type="stock_image", transition="fade"),
            Scene(scene=2, narration="two.", duration=5.0, visual_type="stock_video", transition="cut"),
        ]
    )
    media = MediaPlan(assets=[_asset(1, "image", img), _asset(2, "video", vid)])
    audio = tmp_path / "master.mp3"
    audio.write_bytes(b"x")
    sub = tmp_path / "subs.srt"
    sub.write_text("1\n00:00:00,000 --> 00:00:05,000\nhi\n", encoding="utf-8")

    manifest = build_manifest(
        build_timeline(scenes, media), scenes, media,
        AudioOutput(mixed_audio_path=audio),
        ProductionConfig(width=640, height=360),
        sub,
    )
    cmd = build_command(manifest, tmp_path / "final_video.mp4", "ffmpeg")

    assert cmd[0] == "ffmpeg" and cmd[1] == "-y"
    assert str(img) in cmd and str(vid) in cmd and str(audio) in cmd
    joined = " ".join(cmd)
    # Two scenes + a fade window -> a true xfade chain, not a hard concat.
    assert "xfade=" in joined
    assert "concat=n=2:v=1:a=0" not in joined
    assert "subtitles=" in joined
    assert "2:a" in joined  # audio = input index 2
    assert "-t" in cmd and "10.0" in joined
    assert "-c:v" in cmd and "libx264" in cmd
    assert "-preset" in cmd and "veryfast" in cmd and "-crf" in cmd
    assert "-movflags" in cmd and "+faststart" in cmd
    assert "-c:a" in cmd and "aac" in cmd
    assert "final_video.mp4" in joined


# -- renderers ----------------------------------------------------------------


def test_build_renderer_selection():
    assert isinstance(build_renderer(ProductionConfig(renderer="stub")), StubRenderer)
    assert isinstance(build_renderer(ProductionConfig(renderer="ffmpeg")), FFmpegRenderer)
    with pytest.raises(ValueError):
        build_renderer(ProductionConfig(renderer="nope"))


def test_stub_renderer_writes_marker(tmp_path):
    scenes = _scenes("stock_video")
    manifest = _manifest(scenes, MediaPlan(assets=[]))
    result: RenderResult = StubRenderer().render(manifest, tmp_path / "final_video.mp4")
    assert result.video_path.exists()
    assert "stub-renderer" in result.video_path.read_text(encoding="utf-8")


def test_ffmpeg_renderer_binary_missing(tmp_path):
    renderer = FFmpegRenderer(str(tmp_path / "no_such_ffmpeg"))
    with pytest.raises(RendererError):
        renderer._run(["definitely-not-a-real-binary"], tmp_path)


class ExplodingRenderer:
    name = "boom"

    def render(self, manifest, out_path):
        raise RendererError("boom")


def test_renderer_failure_marks_stage_failed(make_ctx, scenes, media, audio, tmp_path):
    ctx = make_ctx(**{Stage.SCENES: scenes, Stage.MEDIA: media, Stage.AUDIO: audio})
    module = DefaultProductionModule(renderer=ExplodingRenderer())
    result = module.run(ctx)
    assert result.ok is False
    assert result.error and "render failed" in result.error


def test_production_module_stub_end_to_end(make_ctx, scenes, media, audio, tmp_path):
    ctx = make_ctx(**{Stage.SCENES: scenes, Stage.MEDIA: media, Stage.AUDIO: audio})
    result = DefaultProductionModule().run(ctx)

    assert result.ok
    assert result.output.video_path.exists()
    assert result.output.duration > 0
    assert result.output.metadata["renderer"] == "stub"
    for name in ("timeline.json", "render_manifest.json", "render_log.json", "output.json"):
        assert ctx.store.exists(Stage.PRODUCTION, name)
