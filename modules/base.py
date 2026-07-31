"""Base contract shared by every stage module.

Each module is independently runnable and testable through three methods:
`validate_input` (refuse to run on bad input), `run` (execute and persist
artifacts), and `validate_output` (verify the produced artifacts).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from core.errors import OutputValidationError
from core.models import Artifact, JobContext, StageResult
from core.stages import Stage

log = logging.getLogger(__name__)


class StageModule(ABC):
    """Contract implemented by every stage module."""

    name: Stage

    def validate_input(self, ctx: JobContext) -> None:  # noqa: B027 - optional hook
        """Raise InputValidationError when the stage cannot process `ctx`.

        Most stages override this; the default validates nothing.
        """

    @abstractmethod
    def run(self, ctx: JobContext) -> StageResult:
        """Execute the stage, persist its output to ctx.store, return a result."""

    def validate_output(self, result: StageResult, ctx: JobContext) -> None:
        """Verify the produced result recorded at least one written artifact."""
        if not result.artifacts_written:
            raise OutputValidationError(f"{self.name.value}: stage wrote no artifacts")

    def _save(self, ctx: JobContext, name: str, data: object) -> Artifact:
        """Persist JSON to this stage's directory and return the Artifact record."""
        if ctx.store is None:
            raise RuntimeError(
                "JobContext.store is not set — run through the orchestrator "
                "or attach an ArtifactStore."
            )
        return ctx.store.save_json(self.name, name, data)
