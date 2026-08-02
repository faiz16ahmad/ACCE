"""Background-music sub-pipeline tests (architecture-audio.md, Phase 1).

Phase 1 is structures only: schemas, the normalizer (A7 enforcement), and the
deterministic retrieval ranking (§3.5). Nothing is wired into the audio module
yet, so these tests are unit-level and byte-compatible with the current mix.
"""

from __future__ import annotations

from pathlib import Path

from config.settings import MusicConfig
from modules.audio.music.normalize import normalize_audio_plan, normalize_music_intent
from modules.audio.music.retrieve import rank_assets, rank_one, stable_cache_key
from modules.audio.music.schemas import (
    AudioPlan,
    CurvePoint,
    MusicAsset,
    MusicIntent,
    MusicSelection,
)


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
