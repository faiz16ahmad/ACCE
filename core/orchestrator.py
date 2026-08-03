"""Sequential pipeline orchestration.

Runs the registered stage modules in `Stage` definition order. If a stage
fails, *only that stage* is retried (up to `retries`); a subsequent failure
fails the whole job. Progress is reported through an optional callback.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from memory.store import ArtifactStore

from .models import JobContext, JobStatus, Locale, Narrator, ProgressEvent, ProgressStatus, StageResult, UserInput
from .stages import Stage

if TYPE_CHECKING:
    from modules.base import StageModule

log = logging.getLogger(__name__)

ProgressCallback = Callable[[ProgressEvent], None]


class PipelineOrchestrator:
    def __init__(
        self,
        modules: Mapping[Stage, StageModule],
        *,
        retries: int = 2,
        on_progress: ProgressCallback | None = None,
        output_root: Path = Path("out"),
        locale_resolver: Callable[[str], Locale] | None = None,
        narrator_resolver: Callable[[str], Narrator] | None = None,
    ) -> None:
        self.modules = dict(modules)
        self.retries = retries
        self.on_progress = on_progress
        self.output_root = Path(output_root)
        self.locale_resolver = locale_resolver
        self.narrator_resolver = narrator_resolver

    def run(self, job_input: UserInput, *, job_id: str | None = None, store: ArtifactStore | None = None) -> JobContext:
        job_id = job_id or f"job-{uuid.uuid4().hex[:12]}"
        store = store or ArtifactStore.create(job_id, self.output_root)
        ctx = JobContext(
            job_id=job_id,
            input=job_input,
            # Language resolves once here (a simple radio pick → the rich
            # Locale + default Narrator); stages read ctx.locale, never parse.
            locale=(
                self.locale_resolver(job_input.language)
                if self.locale_resolver
                else Locale(language=job_input.language)
            ),
            narrator=(
                self.narrator_resolver(job_input.language)
                if self.narrator_resolver
                else Narrator()
            ),
            status=JobStatus.RUNNING,
            store=store,
            started_at=time.time(),
        )
        self._emit(ctx, "pipeline", ProgressStatus.STARTED, f"job {job_id} started", 0.0)

        total = len(list(Stage))
        for index, stage in enumerate(Stage):
            module = self.modules.get(stage)
            if module is None:
                log.warning("no module registered for stage %s; skipping", stage.value)
                continue
            ctx.current_stage = stage
            result = self._run_stage(module, ctx, index, total)
            ctx.results[stage] = result
            if not result.ok:
                ctx.status = JobStatus.FAILED
                ctx.errors.append(f"{stage.value}: {result.error}")
                self._emit(
                    ctx, stage.value, ProgressStatus.FAILED, result.error or "failed", self._percent(index, total)
                )
                break
        else:
            ctx.status = JobStatus.SUCCEEDED
            self._emit(ctx, "pipeline", ProgressStatus.SUCCEEDED, "pipeline finished", 100.0)

        ctx.finished_at = time.time()
        store.save_json("meta", "job.json", ctx.dump())
        log.info("job %s finished: %s (%.1fs)", ctx.job_id, ctx.status.value, ctx.elapsed_ms() / 1000.0)
        return ctx

    def _run_stage(self, module: StageModule, ctx: JobContext, index: int, total: int) -> StageResult:
        # Inject progress callback so stages can emit intra-stage events.
        ctx._progress_cb = self.on_progress

        for attempt in range(self.retries + 1):
            started = time.time()
            try:
                module.validate_input(ctx)
                result = module.run(ctx)
                module.validate_output(result, ctx)
                result.duration_ms = int((time.time() - started) * 1000)
                result.ok = True
                result.retries = attempt
                elapsed = time.time() - started
                self._emit(
                    ctx, module.name.value, ProgressStatus.SUCCEEDED,
                    f"ok ({elapsed:.1f}s)", self._percent(index, total),
                )
                return result
            except Exception as exc:  # noqa: BLE001 - orchestrator decides retry/fail
                log.exception("stage %s failed (attempt %d/%d)", module.name.value, attempt + 1, self.retries + 1)
                if attempt < self.retries:
                    self._emit(
                        ctx,
                        module.name.value,
                        ProgressStatus.RETRYING,
                        f"failed: {type(exc).__name__}: {exc}\nRetrying ({attempt + 1}/{self.retries})...",
                        self._percent(index, total),
                    )
                    continue
                return StageResult(
                    stage=module.name,
                    ok=False,
                    retries=attempt,
                    error=f"{type(exc).__name__}: {exc}",
                )

    def _emit(self, ctx: JobContext, stage: str, status: ProgressStatus, message: str, percent: float) -> None:
        event = ProgressEvent(stage=str(stage), status=status, message=message, percent=percent)
        log.info("[%s] %s: %s", event.stage, event.status.value, event.message)
        if self.on_progress is not None:
            self.on_progress(event)

    def _emit_stage(self, ctx: JobContext, status: ProgressStatus, message: str, percent: float) -> None:
        """Emit an event for the current stage."""
        if ctx.current_stage is not None:
            self._emit(ctx, ctx.current_stage.value, status, message, percent)

    @staticmethod
    def _percent(index: int, total: int) -> float:
        return round(((index + 1) / total) * 100, 1)
