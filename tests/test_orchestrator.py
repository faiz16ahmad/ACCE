"""Orchestrator behavior: end-to-end stub run, per-stage retry, registry guards."""

from __future__ import annotations

import pytest

from config.settings import Settings
from core.errors import StageRetryableError
from core.models import JobStatus, StageResult, UserInput
from core.orchestrator import PipelineOrchestrator
from core.stages import Stage
from memory.store import ArtifactStore
from modules import build_orchestrator
from modules.base import StageModule
from providers.registry import ProviderNotImplementedError, get_provider


def test_end_to_end_stub_pipeline(tmp_path):
    settings = Settings(_env_file=None)
    settings.paths.cache_dir = tmp_path / "cache"
    orch = build_orchestrator(settings)

    store = ArtifactStore(tmp_path / "out" / "e2e")
    ctx = orch.run(
        UserInput(topic="Hello World", instructions=["be brief"], duration=60),
        job_id="e2e",
        store=store,
    )

    assert ctx.status == JobStatus.SUCCEEDED
    for stage in Stage:
        assert ctx.results[stage].ok, f"stage {stage.value} failed: {ctx.results[stage].error}"

    for stage, name in [
        (Stage.RESEARCH, "research.json"),
        (Stage.SCRIPT, "script.json"),
        (Stage.SCENES, "scene_plan.json"),
        (Stage.MEDIA, "media.json"),
        (Stage.AUDIO, "audio.json"),
        (Stage.PRODUCTION, "subtitles.srt"),
        (Stage.QUALITY, "report.json"),
    ]:
        assert store.exists(stage, name), f"{stage.value} missing {name}"
    assert store.exists("meta", "job.json")

    # Quality should pass on the stub run (only informational/warning issues).
    assert ctx.results[Stage.QUALITY].output.passed is True


class _FlakyModule(StageModule):
    name = Stage.RESEARCH

    def __init__(self) -> None:
        self.calls = 0

    def run(self, ctx):
        self.calls += 1
        if self.calls == 1:
            raise StageRetryableError("transient failure")
        return StageResult(
            stage=self.name,
            ok=True,
            artifacts_written=[ctx.store.save_json(self.name, "out.json", {"ok": True})],
        )


def test_retries_only_the_failed_stage(tmp_path):
    flaky = _FlakyModule()
    orch = PipelineOrchestrator({Stage.RESEARCH: flaky}, retries=2, output_root=tmp_path / "out")
    ctx = orch.run(UserInput(topic="x"))
    assert ctx.status == JobStatus.SUCCEEDED
    assert flaky.calls == 2
    assert ctx.results[Stage.RESEARCH].retries == 1


class _AlwaysFails(StageModule):
    name = Stage.RESEARCH

    def run(self, ctx):
        raise StageRetryableError("always fails")


def test_gives_up_after_retries(tmp_path):
    orch = PipelineOrchestrator({Stage.RESEARCH: _AlwaysFails()}, retries=2, output_root=tmp_path / "out")
    ctx = orch.run(UserInput(topic="x"))
    assert ctx.status == JobStatus.FAILED
    assert ctx.results[Stage.RESEARCH].ok is False
    assert ctx.results[Stage.RESEARCH].retries == 2


def test_progress_events_are_emitted(tmp_path):
    events = []
    orch = PipelineOrchestrator(
        {Stage.RESEARCH: _FlakyModule()},
        retries=1,
        output_root=tmp_path / "out",
        on_progress=events.append,
    )
    orch.run(UserInput(topic="x"))
    assert any(e.status.value == "started" for e in events)
    assert any(e.status.value == "retrying" for e in events)
    assert any(e.status.value == "succeeded" for e in events)


def test_registry_rejects_unimplemented_providers():
    with pytest.raises(ProviderNotImplementedError):
        get_provider("llm", "openai")
    with pytest.raises(ProviderNotImplementedError):
        get_provider("image", "pexels")


def test_unknown_provider_kind_raises():
    with pytest.raises(ValueError):
        get_provider("nonsense", "stub")
