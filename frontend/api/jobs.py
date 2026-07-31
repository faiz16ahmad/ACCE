"""In-memory job store + threaded pipeline runner.

V1 keeps job state in memory (logs deque + results snapshot) and lets the
pipeline write its real artifacts to `out/<job_id>/`. A durable store
(sqlite) is a later milestone if the dashboard needs history.
"""

from __future__ import annotations

import threading
import uuid
from collections import deque
from dataclasses import dataclass, field

from config.settings import Settings
from core.models import UserInput
from modules import build_orchestrator

MAX_LOG_LINES = 500


@dataclass
class JobRecord:
    job_id: str
    input: UserInput
    status: str = "pending"
    current_stage: str | None = None
    logs: deque[str] = field(default_factory=lambda: deque(maxlen=MAX_LOG_LINES))
    result: dict | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "current_stage": self.current_stage,
            "logs": list(self.logs),
            "result": self.result,
            "error": self.error,
        }


class JobStore:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._jobs: dict[str, JobRecord] = {}
        self._lock = threading.Lock()

    def create(self, ui: UserInput) -> str:
        job_id = f"job-{uuid.uuid4().hex[:12]}"
        record = JobRecord(job_id=job_id, input=ui)
        with self._lock:
            self._jobs[job_id] = record
        threading.Thread(target=self._run, args=(job_id,), name=f"acce-{job_id}", daemon=True).start()
        return job_id

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def _run(self, job_id: str) -> None:
        record = self._jobs[job_id]
        record.status = "running"
        orch = build_orchestrator(self._settings, on_progress=self._log_progress(record))
        try:
            ctx = orch.run(record.input, job_id=record.job_id)
            record.result = ctx.dump()
            record.status = ctx.status.value
        except Exception as exc:  # noqa: BLE001 - report to the dashboard
            record.status = "failed"
            record.error = f"{type(exc).__name__}: {exc}"
            record.logs.append(f"ERROR: {record.error}")

    @staticmethod
    def _log_progress(record: JobRecord):
        def on_progress(event) -> None:
            record.current_stage = event.stage
            record.logs.append(f"[{event.stage}] {event.status.value}: {event.message}")
        return on_progress
