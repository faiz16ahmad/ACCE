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
            Scene(scene=1, duration=20, narration="n1", search_keywords=["neural", "networks"]),
            Scene(scene=2, duration=20, narration="n2", search_keywords=["neural"]),
        ]
    )


@pytest.fixture
def media():
    from modules.media.schemas import MediaOutput, MediaResult
    from providers.models import MediaHit

    return MediaOutput(
        assets=[
            MediaResult(scene_index=1, asset=MediaHit(provider="stub", media_type="video", url="https://u"))
        ]
    )


@pytest.fixture
def audio(tmp_path):
    from modules.audio.schemas import AudioOutput

    return AudioOutput(master_path=Path(tmp_path) / "audio" / "master_audio.txt", tracks=[], mix_plan_path=None)
