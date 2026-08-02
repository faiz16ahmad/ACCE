"""Shared fixtures: quiet logging, a job-context factory, and sample outputs."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from core.models import JobContext, StageResult, UserInput
from memory.store import ArtifactStore


@pytest.fixture(autouse=True)
def quiet_logging():
    logging.disable(logging.CRITICAL)
    yield
    logging.disable(logging.NOTSET)


@pytest.fixture
def make_ctx(tmp_path):
    """Build a JobContext with an ArtifactStore in tmp and optional stage outputs."""

    def _make(**stage_outputs) -> JobContext:
        store = ArtifactStore(tmp_path / "out" / "job-test")
        ctx = JobContext(
            job_id="job-test",
            input=UserInput(topic="Neural Networks", instructions=["short"], duration=60),
            store=store,
        )
        for stage, output in stage_outputs.items():
            ctx.results[stage] = StageResult(stage=stage, ok=True, output=output)
        return ctx

    return _make


@pytest.fixture
def research():
    from modules.research.schemas import ResearchFact, ResearchOutput, ResearchSource

    return ResearchOutput(
        topic="Neural Networks",
        facts=[ResearchFact(content="f1", sources=["https://example.com/s1"])],
        sources=[ResearchSource(url="https://example.com/x", title="X")],
        summary="A short research summary.",
    )


@pytest.fixture
def script():
    from modules.script.schemas import NarrationBlock, ScriptOutput

    paragraphs = ["Hook!", "Body 1", "Ending!"]
    return ScriptOutput(
        hook=paragraphs[0],
        body=paragraphs[1:-1],
        ending=paragraphs[-1],
        narration=[NarrationBlock(paragraph=p) for p in paragraphs],
    )


@pytest.fixture
def scenes():
    from modules.scenes.schemas import Scene, ScenePlan

    return ScenePlan(
        scenes=[
            Scene(
                scene=1,
                duration=20,
                narration="Neural networks learn by adjusting weights on every pass.",
                search_keywords=["neural", "networks"],
            ),
            Scene(
                scene=2,
                duration=20,
                narration="The network improves its predictions with more training data.",
                search_keywords=["neural"],
            ),
        ]
    )


@pytest.fixture
def media():
    from modules.media.schemas import MediaAssetPlan, MediaPlan
    from providers.models import MediaHit

    return MediaPlan(
        assets=[
            MediaAssetPlan(
                scene_number=1,
                asset_id="asset_0001",
                selected_provider="stub",
                asset_type="video",
                asset_url="https://u",
                license="stub",
                candidates=[MediaHit(provider="stub", media_type="video", url="https://u")],
            )
        ]
    )


@pytest.fixture
def audio(tmp_path):
    """A realistic AudioOutput with real narration/music/subtitle files.

    Duration matches the two 20s scenes fixture so quality duration checks pass.
    """
    from modules.audio.schemas import AudioMetadata, AudioOutput, AudioTrack

    audio_dir = Path(tmp_path) / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    narration = audio_dir / "narration.txt"
    narration.write_text("n1\n\nn2", encoding="utf-8")
    mixed = audio_dir / "master_audio.txt"
    mixed.write_text("mix", encoding="utf-8")
    subtitles = audio_dir / "subtitles.srt"
    subtitles.write_text(
        "1\n00:00:00,000 --> 00:00:20,000\nn1\n\n2\n00:00:20,000 --> 00:00:40,000\nn2\n",
        encoding="utf-8",
    )
    return AudioOutput(
        narration_path=narration,
        mixed_audio_path=mixed,
        subtitle_path=subtitles,
        master_path=mixed,
        duration=40.0,
        tracks=[
            AudioTrack(kind="narration", provider="stub", title="n1", local_path=narration, duration=20.0),
            AudioTrack(kind="music", provider="stub", title="bed", duration=40.0),
        ],
        metadata=AudioMetadata(duration=40.0, narration_duration=40.0, engine="stub"),
    )
