"""Per-module standalone tests: validate_input -> run -> validate_output.

Each test builds the module with its stub dependencies and a synthetic
context, proving every stage is independently runnable and that it writes its
artifacts into `out/<job_id>/<stage>/`.
"""

from __future__ import annotations

from core.stages import Stage
from memory.cache import DiskCache
from modules.audio.default import DefaultAudioModule
from modules.audio.engine import StubAudioEngine
from modules.audio.schemas import AudioOutput
from modules.media.default import DefaultMediaModule
from modules.media.schemas import MediaPlan
from modules.production.default import DefaultProductionModule
from modules.production.schemas import ProductionOutput
from modules.quality.default import DefaultQualityModule
from modules.quality.schemas import QualityReport
from modules.research.default import DefaultResearchModule
from modules.research.schemas import ResearchOutput
from modules.scenes.default import DefaultScenesModule
from modules.scenes.schemas import ScenePlan
from modules.script.default import DefaultScriptModule
from modules.script.schemas import ScriptOutput
from providers.media_chain import build_media_chain
from providers.music_chain import build_music_chain
from providers.stubs.llm import StubLLMProvider
from providers.stubs.tts import StubTTSProvider


def _exercise(module, ctx, expected_cls):
    module.validate_input(ctx)
    result = module.run(ctx)
    module.validate_output(result, ctx)
    assert result.ok
    assert isinstance(result.output, expected_cls)
    assert result.artifacts_written
    return result


def test_research_module(make_ctx, tmp_path):
    ctx = make_ctx()
    module = DefaultResearchModule(StubLLMProvider(), DiskCache(tmp_path / "cache"))
    _exercise(module, ctx, ResearchOutput)
    assert ctx.store.exists(Stage.RESEARCH, "research.json")


def test_script_module(make_ctx, research):
    ctx = make_ctx(**{Stage.RESEARCH: research})
    _exercise(DefaultScriptModule(StubLLMProvider()), ctx, ScriptOutput)
    assert ctx.store.exists(Stage.SCRIPT, "script.json")


def test_scenes_module(make_ctx, script):
    ctx = make_ctx(**{Stage.SCRIPT: script})
    result = _exercise(DefaultScenesModule(StubLLMProvider()), ctx, ScenePlan)
    assert result.output.scenes
    assert all(s.duration > 0 for s in result.output.scenes)
    assert ctx.store.exists(Stage.SCENES, "scene_plan.json")


def test_media_module(make_ctx, scenes, tmp_path):
    ctx = make_ctx(**{Stage.SCENES: scenes})
    cache = DiskCache(tmp_path / "cache")
    module = DefaultMediaModule(build_media_chain(["stub"], cache), cache)
    result = _exercise(module, ctx, MediaPlan)
    assert result.output.assets
    assert all(a.scene_index >= 1 for a in result.output.assets)
    assert all(a.asset_id.startswith("asset_") for a in result.output.assets)
    assert ctx.store.exists(Stage.MEDIA, "media_plan.json")


def test_audio_module(make_ctx, scenes, tmp_path):
    ctx = make_ctx(**{Stage.SCENES: scenes})
    cache = DiskCache(tmp_path / "cache")
    module = DefaultAudioModule(StubTTSProvider(), build_music_chain(["stub"]), StubAudioEngine(), cache)
    result = _exercise(module, ctx, AudioOutput)
    assert result.output.master_path.exists()
    assert result.output.mixed_audio_path == result.output.master_path
    assert result.output.subtitle_path is not None and result.output.subtitle_path.exists()
    assert result.output.duration > 0
    assert any(t.kind == "narration" for t in result.output.tracks)
    assert any(t.kind == "music" for t in result.output.tracks)
    assert ctx.store.exists(Stage.AUDIO, "mix_plan.json")


def test_production_module(make_ctx, research, script, scenes, media, audio):
    ctx = make_ctx(
        **{
            Stage.RESEARCH: research,
            Stage.SCRIPT: script,
            Stage.SCENES: scenes,
            Stage.MEDIA: media,
            Stage.AUDIO: audio,
        }
    )
    result = _exercise(DefaultProductionModule(), ctx, ProductionOutput)
    assert result.output.video_path.exists()  # stub renderer marker
    assert result.output.subtitle_path.exists()  # fallback subtitles (audio fixture has none)
    assert result.output.title
    assert result.output.duration > 0
    assert ctx.store.exists(Stage.PRODUCTION, "final_video.mp4")
    assert ctx.store.exists(Stage.PRODUCTION, "timeline.json")
    assert ctx.store.exists(Stage.PRODUCTION, "render_manifest.json")
    assert ctx.store.exists(Stage.PRODUCTION, "render_log.json")


def test_quality_module(make_ctx, research, script, scenes, media, audio):
    ctx = make_ctx(
        **{
            Stage.RESEARCH: research,
            Stage.SCRIPT: script,
            Stage.SCENES: scenes,
            Stage.MEDIA: media,
            Stage.AUDIO: audio,
        }
    )
    production_result = DefaultProductionModule().run(ctx)
    ctx.results[Stage.PRODUCTION] = production_result

    result = _exercise(DefaultQualityModule(), ctx, QualityReport)
    assert result.output.passed is True
    assert ctx.store.exists(Stage.QUALITY, "quality.json")
