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


class UserInput(BaseModel):
    """The single accepted input shape for a generation job."""

    topic: str = Field(min_length=1)
    instructions: list[str] = Field(default_factory=list)
    duration: int | None = Field(default=None, ge=10)  # target seconds
    style: str | None = None


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
