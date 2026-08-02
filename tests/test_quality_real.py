"""Quality module tests (milestone 8).

Passing pipeline, missing artifacts, placeholder media, duration mismatch,
retry recommendation, severity classification, score calculation, fix
suggestions, and historical metadata. Fully deterministic — no AI, no network.
"""

from __future__ import annotations

import pytest

from config.settings import QualityConfig
from core.models import JobContext, StageResult, UserInput
from core.stages import Stage
from memory.store import ArtifactStore
from modules.audio.schemas import AudioMetadata, AudioOutput, AudioTrack
from modules.media.schemas import MediaAssetPlan, MediaPlan
from modules.production.schemas import ProductionOutput
from modules.quality.default import DefaultQualityModule
from modules.quality.schemas import QualityIssue, QualityReport
from modules.research.schemas import ResearchFact, ResearchOutput, ResearchSource
from modules.scenes.schemas import Scene, ScenePlan
from modules.script.schemas import NarrationBlock, ReadabilityStats, ScriptMetrics, ScriptOutput
from modules.shots.schemas import Shot, ShotPlan


@pytest.fixture
def clean_ctx(tmp_path):
    """A fully clean 6-stage job: every check passes, score 100."""
    store = ArtifactStore(tmp_path / "out" / "job-clean")
    ctx = JobContext(job_id="job-clean", input=UserInput(topic="T", duration=60), store=store)

    audio_dir = tmp_path / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    narration = audio_dir / "narration.txt"
    narration.write_text("n", encoding="utf-8")
    mixed = audio_dir / "mixed.txt"
    mixed.write_text("m", encoding="utf-8")
    subs = audio_dir / "subs.srt"
    subs.write_text("1\n00:00:00,000 --> 00:00:60,000\nn\n", encoding="utf-8")
    img = tmp_path / "a.jpg"
    img.write_bytes(b"x")

    research = ResearchOutput(
        topic="T",
        facts=[ResearchFact(content="f", sources=["https://e"], verified=True)],
        sources=[ResearchSource(url="https://e", title="E")],
        summary="s",
    )
    script = ScriptOutput(
        hook="H",
        body=["B"],
        ending="E",
        narration=[NarrationBlock(paragraph="H B E")],
        metrics=ScriptMetrics(
            word_count=10,
            estimated_duration=60.0,
            words_per_minute=150,
            readability=ReadabilityStats(words=10, sentences=2, syllables=12, reading_ease=60.0, grade_level=8.0),
        ),
    )
    scenes = ScenePlan(
        scenes=[Scene(scene=1, narration="s", duration=60.0, visual_description="v", search_keywords=["k"])]
    )
    media = MediaPlan(
        assets=[
            MediaAssetPlan(
                scene_number=1,
                shot_id="shot_0001",
                asset_id="asset_0001",
                selected_provider="p",
                asset_type="image",
                asset_url="https://u",
                local_path=img,
                license="royalty-free",
            )
        ]
    )
    shots = ShotPlan(
        shots=[
            Shot(
                shot_id="shot_0001",
                scene_id="scene_0001",
                position=1,
                purpose="main",
                visual_description="v",
                search_queries=["neural", "network"],
                content_kind="stock_image",
                media_preference="image",
                motion_intent="none",
                importance="medium",
                transition_out="cut",
            )
        ]
    )
    audio = AudioOutput(
        narration_path=narration,
        mixed_audio_path=mixed,
        subtitle_path=subs,
        master_path=mixed,
        duration=60.0,
        tracks=[
            AudioTrack(kind="narration", provider="stub", title="n", duration=60.0),
            AudioTrack(kind="music", provider="stub", title="m", duration=60.0),
        ],
        metadata=AudioMetadata(duration=60.0, engine="stub"),
    )
    production = ProductionOutput(
        video_path=img,
        timeline_path=img,
        render_manifest_path=img,
        render_log_path=img,
        title="T",
        description="d",
        duration=60.0,
    )

    for stage, output in [
        (Stage.RESEARCH, research),
        (Stage.SCRIPT, script),
        (Stage.SCENES, scenes),
        (Stage.SHOTS, shots),
        (Stage.MEDIA, media),
        (Stage.AUDIO, audio),
        (Stage.PRODUCTION, production),
    ]:
        ctx.results[stage] = StageResult(stage=stage, ok=True, output=output)

    for stage, name in [
        ("research", "research.json"),
        ("script", "script.json"),
        ("scenes", "scene_plan.json"),
        ("shots", "shot_plan.json"),
        ("media", "media_plan.json"),
        ("audio", "audio.json"),
    ]:
        store.save_json(stage, name, {"ok": True})
    # Phase-3 music artifacts: a real Phase-2 run writes these, and the music
    # quality checks validate them (intent, asset, bed coverage, duck/fades).
    store.save_json(
        "audio",
        "audio_plan.json",
        {
            "music": [
                {
                    "emotion": "calm",
                    "energy": 0.5,
                    "tempo_bpm": None,
                    "intensity": 0.5,
                    "intensity_curve": [],
                    "style": "documentary",
                    "fade_preferences": {"fade_in": 1.0, "fade_out": 1.0, "crossfade": False},
                }
            ]
        },
    )
    store.save_json(
        "audio",
        "mix_plan.json",
        {
            "segments": [
                {"kind": "narration", "start": 0.0, "end": 60.0, "fade_in": 0.2, "fade_out": 0.2},
                {
                    "kind": "music",
                    "start": 0.0,
                    "end": 60.0,
                    "volume": 0.2,
                    "fade_in": 1.0,
                    "fade_out": 1.0,
                    "duck": {"depth_db": 8.0, "attack": 0.05, "release": 0.5},
                },
            ],
            "master_gain": 1.0,
        },
    )
    return ctx


def _replace(ctx: JobContext, stage: Stage, output) -> None:
    ctx.results[stage] = StageResult(stage=stage, ok=True, output=output)


def _run(ctx: JobContext) -> QualityReport:
    return DefaultQualityModule().run(ctx).output


# -- passing pipeline / score / metadata --------------------------------------


def test_passing_pipeline_score_100(clean_ctx):
    report = _run(clean_ctx)
    assert report.passed is True
    assert report.score == 100.0
    assert report.issues == []
    assert report.warnings == 0 and report.errors == 0
    assert report.recommended_retry_stage is None


def test_metadata_historical_summary(clean_ctx):
    report = _run(clean_ctx)
    for key in ("score", "warnings", "errors", "passed", "pipeline_complete", "generated_at"):
        assert key in report.metadata
    assert report.metadata["passed"] is True
    assert report.metadata["pipeline_complete"] is True
    assert report.metadata["stage_counts"]["production"] == 0

    clean_ctx.results.pop(Stage.PRODUCTION)
    assert _run(clean_ctx).metadata["pipeline_complete"] is False


def test_quality_json_artifact_written(clean_ctx):
    DefaultQualityModule().run(clean_ctx)
    assert clean_ctx.store.exists(Stage.QUALITY, "quality.json")


# -- missing artifacts / retry recommendation ----------------------------------


def test_missing_production_video(clean_ctx, tmp_path):
    prod = clean_ctx.results[Stage.PRODUCTION].output
    broken = prod.model_copy(update={"video_path": tmp_path / "nope.mp4"})
    _replace(clean_ctx, Stage.PRODUCTION, broken)

    report = _run(clean_ctx)
    assert report.passed is False
    assert report.recommended_retry_stage == "production"
    assert any(issue.code == "production.missing_video" for issue in report.issues)


def test_missing_audio_narration_errors_and_retry_audio(clean_ctx, tmp_path):
    audio = clean_ctx.results[Stage.AUDIO].output
    _replace(clean_ctx, Stage.AUDIO, audio.model_copy(update={"narration_path": tmp_path / "gone.txt"}))

    report = _run(clean_ctx)
    assert report.passed is False
    assert report.recommended_retry_stage == "audio"
    issue = next(i for i in report.issues if i.code == "audio.missing_narration")
    assert issue.level == "error"
    assert issue.suggested_fix == "Regenerate the Audio stage."


def test_retry_recommendation_earliest_stage(clean_ctx, tmp_path):
    # research stage fails AND production video missing -> research is earliest
    clean_ctx.results[Stage.RESEARCH] = StageResult(stage=Stage.RESEARCH, ok=False)
    prod = clean_ctx.results[Stage.PRODUCTION].output
    _replace(clean_ctx, Stage.PRODUCTION, prod.model_copy(update={"video_path": tmp_path / "nope.mp4"}))

    assert _run(clean_ctx).recommended_retry_stage == "research"


# -- placeholder media / severity ----------------------------------------------


def test_placeholder_media_warns_but_passes(clean_ctx):
    media = clean_ctx.results[Stage.MEDIA].output
    placeholder = media.assets[0].model_copy(
        update={"selected_provider": "placeholder", "asset_url": "", "local_path": None}
    )
    _replace(clean_ctx, Stage.MEDIA, media.model_copy(update={"assets": [placeholder]}))

    report = _run(clean_ctx)
    assert report.passed is True  # placeholders are warnings, not errors
    assert report.score < 100.0
    codes = {issue.code for issue in report.issues}
    assert "media.placeholder_asset" in codes and "media.missing_local" in codes


def test_severity_classification(clean_ctx, tmp_path):
    audio = clean_ctx.results[Stage.AUDIO].output
    # missing music -> warning only
    narration_only = audio.model_copy(
        update={"tracks": [AudioTrack(kind="narration", provider="stub", title="n", duration=60.0)]}
    )
    _replace(clean_ctx, Stage.AUDIO, narration_only)
    report = _run(clean_ctx)
    music = next(i for i in report.issues if i.code == "audio.missing_music")
    assert music.level == "warning"

    # missing subtitles -> error
    _replace(clean_ctx, Stage.AUDIO, audio.model_copy(update={"subtitle_path": tmp_path / "no.srt"}))
    report = _run(clean_ctx)
    subtitles = next(i for i in report.issues if i.code == "audio.missing_subtitles")
    assert subtitles.level == "error"

    # missing license -> info
    media = clean_ctx.results[Stage.MEDIA].output
    no_license = media.assets[0].model_copy(update={"license": "unknown"})
    _replace(clean_ctx, Stage.MEDIA, media.model_copy(update={"assets": [no_license]}))
    report = _run(clean_ctx)
    license_issue = next(i for i in report.issues if i.code == "media.missing_license")
    assert license_issue.level == "info"

    # empty research -> error
    clean_ctx.results[Stage.RESEARCH] = StageResult(
        stage=Stage.RESEARCH, ok=True, output=ResearchOutput(topic="T", facts=[], summary="")
    )
    report = _run(clean_ctx)
    assert any(i.code == "research.empty_output" and i.level == "error" for i in report.issues)


def _write_mix(ctx, *, music_end: float, duck: bool, fades: bool) -> None:
    seg = {"kind": "music", "start": 0.0, "end": music_end, "volume": 0.2}
    if duck:
        seg["duck"] = {"depth_db": 8.0, "attack": 0.05, "release": 0.5}
    if fades:
        seg["fade_in"] = 1.0
        seg["fade_out"] = 1.0
    ctx.store.save_json(
        "audio",
        "mix_plan.json",
        {
            "segments": [
                {"kind": "narration", "start": 0.0, "end": 60.0, "fade_in": 0.2, "fade_out": 0.2},
                seg,
            ],
            "master_gain": 1.0,
        },
    )


def test_music_missing_asset_warns(clean_ctx):
    audio = clean_ctx.results[Stage.AUDIO].output
    narration_only = audio.model_copy(
        update={"tracks": [AudioTrack(kind="narration", provider="stub", title="n", duration=60.0)]}
    )
    _replace(clean_ctx, Stage.AUDIO, narration_only)
    report = _run(clean_ctx)
    issue = next(i for i in report.issues if i.code == "audio.missing_music_asset")
    assert issue.level == "warning"


def test_music_bed_coverage_warns(clean_ctx):
    _write_mix(clean_ctx, music_end=30.0, duck=True, fades=True)  # bed covers half
    report = _run(clean_ctx)
    issue = next(i for i in report.issues if i.code == "audio.music_bed_coverage")
    assert issue.level == "warning"


def test_music_duck_and_fades_missing_are_info(clean_ctx):
    _write_mix(clean_ctx, music_end=60.0, duck=False, fades=False)
    report = _run(clean_ctx)
    codes = {i.code for i in report.issues}
    assert "audio.music_no_duck" in codes and "audio.music_no_fades" in codes
    assert all(i.level == "info" for i in report.issues if i.code in ("audio.music_no_duck", "audio.music_no_fades"))


def test_duration_mismatch_warns(clean_ctx):
    script = clean_ctx.results[Stage.SCRIPT].output
    metrics = script.metrics.model_copy(update={"estimated_duration": 100.0})  # requested is 60
    _replace(clean_ctx, Stage.SCRIPT, script.model_copy(update={"metrics": metrics}))

    report = _run(clean_ctx)
    mismatch = next(i for i in report.issues if i.code == "script.duration_mismatch")
    assert mismatch.level == "warning"
    assert "Regenerate the Script" in (mismatch.suggested_fix or "")


def test_unverified_facts_warn(clean_ctx):
    research = clean_ctx.results[Stage.RESEARCH].output
    _replace(clean_ctx, Stage.RESEARCH, research.model_copy(update={"facts": [ResearchFact(content="f")]}))
    report = _run(clean_ctx)
    assert any(i.code == "research.unverified_facts" and i.level == "warning" for i in report.issues)


# -- score ---------------------------------------------------------------------


def test_score_calculation():
    module = DefaultQualityModule()
    assert module._score([QualityIssue(level="error", stage="a", message="e")]) == 75.0
    assert module._score([QualityIssue(level="warning", stage="a", message="w")]) == 95.0
    assert module._score([QualityIssue(level="info", stage="a", message="i")]) == 99.0
    assert module._score([QualityIssue(level="error", stage="a", message="e")] * 4) == 0.0  # floor
    assert module._score([]) == 100.0


def test_score_respects_custom_config():
    custom = DefaultQualityModule(QualityConfig(penalty_error=10.0, penalty_warning=2.0))
    issues = [
        QualityIssue(level="error", stage="a", message="e"),
        QualityIssue(level="warning", stage="a", message="w"),
    ]
    assert custom._score(issues) == 88.0
