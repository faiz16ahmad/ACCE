"""Background-music sub-pipeline tests (architecture-audio.md, Phases 1-2).

Phase 1: schemas, the normalizer (A7 enforcement), and the deterministic
retrieval ranking (§3.5). Phase 2 adds the planner (LLM + fallback) and the
Audio Timeline (A4) plus module-level wiring (audio_plan.json / music_assets.json).
"""

from __future__ import annotations

import json
from pathlib import Path

from config.settings import AudioConfig, MusicConfig
from modules.audio.music.normalize import normalize_audio_plan, normalize_music_intent
from modules.audio.music.planner import fallback_intent, plan_music
from modules.audio.music.retrieve import rank_assets, rank_one, stable_cache_key
from modules.audio.music.schemas import (
    AudioPlan,
    CurvePoint,
    MusicAsset,
    MusicIntent,
    MusicSelection,
)
from modules.audio.music.timeline import build_audio_timeline, flatten_timeline
from modules.audio.schemas import AudioTrack, DuckSpec
from modules.scenes.schemas import ScenePlan
from providers.base import LLMProvider
from providers.models import MusicHit


def _intent(**overrides) -> MusicIntent:
    base = dict(emotion="tense", energy=0.8, tempo_bpm=120, intensity=0.7)
    base.update(overrides)
    return MusicIntent(**base)


def _asset(asset_id: str, *, title: str = "calm ambient", duration: float = 90.0, bpm: int | None = None) -> MusicAsset:
    return MusicAsset(
        asset_id=asset_id,
        provider="local",
        title=title,
        local_path=Path(f"assets/music/{title}.mp3"),
        duration=duration,
        bpm=bpm,
    )


# -- schemas ------------------------------------------------------------------


def test_intent_has_no_files_and_no_absolute_time():
    intent = _intent(intensity_curve=[CurvePoint(at=0.5, value=0.9)])
    dumped = intent.model_dump(mode="json")
    assert "local_path" not in dumped and "start" not in dumped and "end" not in dumped
    # curve positions are relative (0..1), never seconds
    assert 0.0 <= dumped["intensity_curve"][0]["at"] <= 1.0


def test_audio_plan_is_music_subset():
    plan = AudioPlan(music=[_intent()])
    assert len(plan.music) == 1
    assert plan.music[0].emotion == "tense"
    assert "music" in plan.model_dump(mode="json")


def test_music_asset_has_no_narrative_or_emotion():
    asset = _asset("music_0001", bpm=110)
    dumped = asset.model_dump(mode="json")
    assert "emotion" not in dumped and "intent" not in dumped and "narration" not in dumped
    assert "start" not in dumped and "end" not in dumped
    assert dumped["local_path"] is not None and dumped["duration"] == 90.0


# -- normalizer (A7) -----------------------------------------------------------


def test_normalizer_coerces_unknown_emotion():
    out = normalize_music_intent(_intent(emotion="hologram"))
    assert out.emotion == "calm"  # first of the controlled vocabulary


def test_normalizer_clamps_energy_intensity_and_curve():
    out = normalize_music_intent(_intent(energy=1.7, intensity=-0.4, intensity_curve=[CurvePoint(at=2.0, value=5.0)]))
    assert out.energy == 1.0
    assert out.intensity == 0.0
    assert out.intensity_curve[0].at == 1.0 and out.intensity_curve[0].value == 1.0


def test_normalizer_bounds_tempo_and_fades():
    cfg = MusicConfig(tempo_min=60, tempo_max=140, max_fade_seconds=6.0)
    out = normalize_music_intent(
        _intent(tempo_bpm=500, fade_preferences={"fade_in": 30.0, "fade_out": -2.0}),
        cfg,
    )
    assert out.tempo_bpm == 140
    assert out.fade_preferences.fade_in == 6.0
    assert out.fade_preferences.fade_out == 0.0


def test_normalizer_curve_sorted_deduped_and_capped():
    points = [CurvePoint(at=0.9, value=0.5), CurvePoint(at=0.1, value=0.2), CurvePoint(at=0.1, value=0.9)]
    out = normalize_music_intent(_intent(intensity_curve=points))
    ats = [p.at for p in out.intensity_curve]
    assert ats == sorted(ats) and ats == [0.1, 0.9]  # duplicate dropped, sorted


def test_normalizer_never_invents_intent():
    out = normalize_music_intent(_intent(emotion="hopeful", energy=0.5))
    assert out.emotion == "hopeful" and out.energy == 0.5


def test_normalize_audio_plan_maps_every_segment():
    plan = AudioPlan(music=[_intent(emotion="hologram"), _intent(emotion="uplifting")])
    out = normalize_audio_plan(plan)
    assert [m.emotion for m in out.music] == ["calm", "uplifting"]


# -- deterministic retrieval ranking (§3.5) -----------------------------------


def test_ranking_prefers_asset_that_covers_the_clock():
    selection = MusicSelection(intent=_intent(tempo_bpm=120), duration_hint=80.0)
    short = _asset("music_0001", duration=30.0, bpm=120)
    covering = _asset("music_0002", duration=90.0, bpm=120)
    ranked = rank_assets([short, covering], selection)
    assert ranked[0].asset.asset_id == "music_0002"
    assert ranked[0].reasons["duration"] == 1.0
    assert ranked[0].reasons["tempo"] == 1.0


def test_ranking_is_deterministic_and_tie_break_stable():
    selection = MusicSelection(intent=_intent(tempo_bpm=None), duration_hint=0.0)
    assets = [_asset(f"music_{i:04d}", title="same words", duration=90.0) for i in (3, 1, 2)]
    first = rank_assets(assets, selection)
    second = rank_assets(list(reversed(assets)), selection)
    assert [r.asset.asset_id for r in first] == [r.asset.asset_id for r in second]
    # equal scores -> ascending asset_id (stable tie-break)
    ids = [r.asset.asset_id for r in first]
    assert ids == sorted(ids)


def test_ranking_rejects_below_threshold():
    selection = MusicSelection(intent=_intent(), duration_hint=100.0)
    assets = [_asset("music_0001", title="unrelated words here", duration=5.0, bpm=30)]  # poor on every axis
    assert rank_assets(assets, selection) == []


def test_ranking_loopable_bed_not_rejected_for_short_duration():
    """Regression: the timeline loops beds (§5), so a bed shorter than the
    narration must not be disqualified by the duration reason alone — a
    60s bed under a ~125s narration used to score below the threshold and the
    mix came out narration-only."""
    selection = MusicSelection(intent=_intent(emotion="calm"), duration_hint=125.0)
    short_but_on_mood = _asset("music_0001", title="calm ambient", duration=60.0)
    ranked = rank_one(short_but_on_mood, selection, MusicConfig())
    # Loop-aware duration reason: 0.5 + 0.5*(60/125)
    assert ranked.reasons["duration"] == 0.5 + 0.5 * (60.0 / 125.0)
    assert ranked.score >= MusicConfig().music_satisfactory_score


def test_ranking_keyword_reason_is_normalized():
    selection = MusicSelection(intent=_intent(emotion="tense"), genre_hint="cinematic", duration_hint=0.0)
    ranked = rank_one(_asset("music_0001", title="cinematic tense drums", bpm=None), selection, MusicConfig())
    assert 0.0 < ranked.reasons["keyword"] <= 1.0
    assert 0.0 <= ranked.score <= 1.0


def test_ranking_duration_hint_zero_is_neutral():
    selection = MusicSelection(intent=_intent(), duration_hint=0.0)
    ranked = rank_one(_asset("music_0001", duration=5.0), selection, MusicConfig())
    assert ranked.reasons["duration"] == 1.0  # no clock requirement -> no penalty


def test_cache_key_stable_regardless_of_input_order():
    selection = MusicSelection(intent=_intent(), duration_hint=80.0)
    assets = [_asset("music_0002"), _asset("music_0001")]
    assert stable_cache_key(selection, assets) == stable_cache_key(selection, list(reversed(assets)))


# -- Phase 2: planner + timeline ------------------------------------------------


class FakeLLM(LLMProvider):
    name = "fake"

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)

    def complete(self, prompt: str, *, system: str | None = None, **kwargs: object) -> str:
        return self.responses.pop(0) if self.responses else "{}"


def test_fallback_intent_is_deterministic():
    a = fallback_intent("storytelling", AudioConfig())
    b = fallback_intent("storytelling", AudioConfig())
    assert a == b and a.emotion == "serious"  # cinematic -> serious
    assert a.fade_preferences.fade_in == 1.0  # music_fade default


def test_plan_music_fallback_produces_normalized_plan():
    plan = plan_music(ScenePlan(scenes=[]), style="storytelling", audio_config=AudioConfig())
    assert len(plan.music) == 1
    assert plan.music[0].emotion in MusicConfig().emotions


def test_plan_music_llm_path_normalizes_and_repairs():
    llm = FakeLLM([json.dumps({"emotion": "tense", "energy": 2.0, "intensity_curve": [{"at": 2.0, "value": 5.0}]})])
    plan = plan_music(ScenePlan(scenes=[]), llm=llm, audio_config=AudioConfig(), music_config=MusicConfig())
    intent = plan.music[0]
    assert intent.emotion == "tense"  # meaning preserved
    assert intent.energy == 1.0  # clamped
    assert intent.intensity_curve[0].at == 1.0 and intent.intensity_curve[0].value == 1.0  # clamped


def test_build_audio_timeline_places_bed():
    plan = AudioPlan(music=[_intent(emotion="hopeful", fade_preferences={"fade_in": 2.0})])
    asset = _asset("music_0001", duration=30.0)
    cfg = AudioConfig(music_volume=0.25, music_fade=1.5)
    timeline = build_audio_timeline(plan, asset, narration_total=40.0, audio_config=cfg, music_config=MusicConfig())
    assert len(timeline.music_spans) == 1
    span = timeline.music_spans[0]
    assert span.start == 0.0 and span.end == 40.0
    assert span.volume == 0.25
    assert span.fade_in == 2.0  # from the intent preference
    assert span.fade_out == 1.5  # falls back to config when pref is None
    assert span.duck == DuckSpec()
    assert span.loop is not None and span.loop.enabled  # 30s asset < 40s bed


def test_timeline_automation_maps_relative_to_absolute():
    plan = AudioPlan(music=[_intent(intensity_curve=[CurvePoint(at=0.5, value=0.9)])])
    asset = _asset("music_0001", duration=60.0)
    timeline = build_audio_timeline(plan, asset, narration_total=40.0, audio_config=AudioConfig(), music_config=MusicConfig())
    automation = timeline.music_spans[0].automation
    assert automation and automation[0].at == 20.0  # 0.5 * 40 (relative -> seconds, A4)
    assert automation[0].value == 0.9


def test_timeline_no_asset_gives_empty_music_layer():
    plan = AudioPlan(music=[_intent()])
    timeline = build_audio_timeline(plan, None, narration_total=40.0, audio_config=AudioConfig(), music_config=MusicConfig())
    assert timeline.music_spans == []  # A10: narration-only, never an error


def test_flatten_timeline_keeps_narration_and_music_with_duck():
    plan = AudioPlan(music=[_intent()])
    asset = _asset("music_0001", duration=30.0)
    timeline = build_audio_timeline(plan, asset, narration_total=20.0, audio_config=AudioConfig(), music_config=MusicConfig())
    narration = [
        AudioTrack(kind="narration", provider="stub", title="n1", local_path=Path("n1.txt"), duration=8.0),
        AudioTrack(kind="narration", provider="stub", title="n2", local_path=Path("n2.txt"), duration=12.0),
    ]
    mixed = flatten_timeline(timeline, narration, {"music_0001": asset}, AudioConfig())
    music = next(s for s in mixed.segments if s.kind == "music")
    assert music.duck is not None and music.source_path is not None and music.start == 0.0 and music.end == 20.0
    narr = [s for s in mixed.segments if s.kind == "narration"]
    assert len(narr) == 2 and narr[0].end == 8.0 and narr[1].start == 8.0


def _music_hit(provider: str = "fake", title: str = "track", duration: float = 60.0) -> MusicHit:
    return MusicHit(provider=provider, title=title, url="https://music.example/track.mp3", duration=duration)


def test_audio_module_writes_music_artifacts(make_ctx, scenes, tmp_path):
    from core.stages import Stage
    from memory.cache import DiskCache
    from modules.audio.default import DefaultAudioModule
    from modules.audio.engine import StubAudioEngine
    from providers.base import MusicProvider
    from providers.music_chain import MusicChain
    from providers.stubs.tts import StubTTSProvider

    class FakeMusicProvider(MusicProvider):
        name = "fake"

        def search(self, query: str, *, count: int = 1) -> list[MusicHit]:
            return [_music_hit() for _ in range(count)]

    ctx = make_ctx(**{Stage.SCENES: scenes})
    module = DefaultAudioModule(
        StubTTSProvider(),
        MusicChain([FakeMusicProvider()]),
        StubAudioEngine(),
        DiskCache(tmp_path / "cache"),
    )
    result = module.run(ctx)

    assert ctx.store.exists(Stage.AUDIO, "audio_plan.json")
    assert ctx.store.exists(Stage.AUDIO, "music_assets.json")
    plan = json.loads(ctx.store.resolve(Stage.AUDIO, "audio_plan.json").read_text(encoding="utf-8"))
    assert len(plan["music"]) == 1
    assert result.output.metadata.music_provider == "fake"
    assert result.output.metadata.music_title == "track"


def test_to_asset_measures_local_duration(tmp_path):
    """A local file without a provider-supplied duration must be measured so the
    §3.5 `duration` reason is meaningful (regression: every local track scored 0
    on duration and fell below the satisfactory threshold)."""
    import math
    import struct
    import wave

    from config.settings import Settings
    from modules.audio.default import DefaultAudioModule
    from modules.audio.engine import StubAudioEngine
    from providers.music_chain import MusicChain
    from providers.stubs.tts import StubTTSProvider

    wav = tmp_path / "bed.wav"
    rate = 8000
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(
            b"".join(
                struct.pack("<h", int(16000 * math.sin(2 * math.pi * 220 * i / rate)))
                for i in range(rate)
            )
        )

    module = DefaultAudioModule(
        StubTTSProvider(),
        MusicChain([]),
        StubAudioEngine(),
        ffmpeg_path=Settings().production.ffmpeg_path,
    )
    hit = MusicHit(provider="local", title="bed", url="", local_path=wav)  # duration omitted
    asset = module._to_asset(hit, "music_0000")
    assert asset.duration > 0.5

    ranked = rank_assets(
        [asset],
        MusicSelection(intent=MusicIntent(emotion="calm", style="calm"), duration_hint=1.0, genre_hint="calm"),
        MusicConfig(),
    )
    assert ranked and ranked[0].asset.asset_id == "music_0000"
    assert ranked[0].reasons["duration"] > 0.5
