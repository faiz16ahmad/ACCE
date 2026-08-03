"""Shared domain models and job lifecycle types.

`JobContext` is the single object threaded through every stage. Modules read
prior stage outputs from `ctx.results[...].output` and write artifacts via
`ctx.store`. The artifact store and transient outputs are excluded from
serialization.
"""

from __future__ import annotations

import time
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from .stages import Stage


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ProgressStatus(StrEnum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRYING = "retrying"


class Locale(BaseModel):
    """Single per-job language configuration.

    Language ONLY — no voice, no narrator identity (who speaks is `Narrator`).
    The five dimensions collapse to `language` in V1; the cross-language future
    (EN narration + HI subtitles, bilingual subtitles, …) is just these fields
    disagreeing.
    """

    language: str = "en"  # user-facing primary code (the radio value)
    script_language: str = "en"  # what narration text is written in
    narration_language: str = "en"  # what TTS speaks
    subtitle_language: str = "en"  # SRT/ASS burn-in text
    metadata_language: str = "en"  # title / description / summary
    retrieval_language: str = "en"  # visual search-query language (default English)


class Narrator(BaseModel):
    """Who speaks the narration — voice identity, separate from `Locale`.

    The growth point for narrator selection, custom voices, and voice cloning;
    adding a voice field to `Locale` would be an architectural change.
    """

    voice_id: str | None = None  # None → the language pack's default voice
    provider: str | None = None  # None → the router's choice for the language
    emotion: str | None = None  # style preset, if the provider supports it
    rate: float | None = None  # speaking-rate multiplier
    clone_source: str | None = None  # future voice cloning reference


class UserInput(BaseModel):
    """The single accepted input shape for a generation job."""

    topic: str = Field(min_length=1)
    instructions: list[str] = Field(default_factory=list)
    duration: int | None = Field(default=None, ge=10)  # target seconds
    style: str | None = None
    language: str = "en"  # resolved into a `Locale` by the factory/orchestrator


class Artifact(BaseModel):
    """A file a stage wrote into the job directory."""

    stage: str
    name: str
    path: Path


class StageResult(BaseModel):
    """Outcome of one stage, including its structured output for downstream stages."""

    stage: Stage
    ok: bool = True
    retries: int = 0
    artifacts_written: list[Artifact] = Field(default_factory=list)
    error: str | None = None
    duration_ms: int = 0
    output: BaseModel | None = None

    @field_serializer("output")
    def _serialize_output(self, value: BaseModel | None) -> dict | None:
        # Serialize via the concrete model, not the abstract BaseModel annotation
        # (which pydantic would otherwise render as an empty dict).
        return value.model_dump(mode="json") if value is not None else None


class ProgressEvent(BaseModel):
    """Lightweight progress signal emitted by the orchestrator."""

    stage: str
    status: ProgressStatus
    message: str
    percent: float


class JobContext(BaseModel):
    """Mutable job state passed through the pipeline."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    job_id: str
    input: UserInput
    locale: Locale = Field(default_factory=Locale)
    narrator: Narrator = Field(default_factory=Narrator)
    status: JobStatus = JobStatus.PENDING
    current_stage: Stage | None = None
    results: dict[Stage, StageResult] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    started_at: float | None = None
    finished_at: float | None = None

    # Injected at runtime by the orchestrator; not part of the persisted
    # record. Typed Any to avoid a core<->memory import cycle.
    store: Any = None
    _progress_cb: Any = None

    def progress(self, message: str) -> None:
        """Emit a progress event from within a stage."""
        if self._progress_cb is not None and self.current_stage is not None:
            self._progress_cb(
                ProgressEvent(
                    stage=self.current_stage.value,
                    status=ProgressStatus.STARTED,
                    message=message,
                    percent=0.0,
                )
            )

    def dump(self) -> dict[str, Any]:
        """JSON-serializable snapshot (used for job status files and the API)."""
        return self.model_dump(mode="json", exclude={"store", "_progress_cb"})

    def elapsed_ms(self) -> int:
        end = self.finished_at or time.time()
        return int((end - (self.started_at or end)) * 1000)
