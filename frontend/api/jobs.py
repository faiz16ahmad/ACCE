"""In-memory job store + threaded pipeline runner.

V1 keeps job state in memory (logs deque + results snapshot) and lets the
pipeline write its real artifacts to `out/<job_id>/`. The orchestrator also
persists a durable `out/<job_id>/meta/job.json`, so the API falls back to that
snapshot for jobs that finished (or were created) before an API restart.
"""

from __future__ import annotations

import json
import mimetypes
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from config.settings import Settings
from core.models import UserInput
from modules import build_orchestrator

MAX_LOG_LINES = 500


def _quality_score(snapshot: dict | None) -> float | None:
    """Quality score (0-100) from a job snapshot, when the Quality stage ran."""
    if not snapshot:
        return None
    quality = (snapshot.get("results") or {}).get("quality") or {}
    output = (quality.get("output") or {}) if isinstance(quality.get("output"), dict) else {}
    return output.get("score")


@dataclass
class JobRecord:
    job_id: str
    input: UserInput
    status: str = "pending"
    current_stage: str | None = None
    logs: deque[str] = field(default_factory=lambda: deque(maxlen=MAX_LOG_LINES))
    result: dict | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "current_stage": self.current_stage,
            "logs": list(self.logs),
            "result": self.result,
            "error": self.error,
        }

    def summary(self) -> dict:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "created_at": self.created_at,
            "topic": self.input.topic,
            "score": _quality_score(self.result),
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

    def list_summaries(self) -> list[dict]:
        with self._lock:
            entries = [record.summary() for record in self._jobs.values()]
        output_root = self._settings.paths.output_dir
        for entry in entries:
            thumb = thumbnail_url(output_root, entry["job_id"])
            if thumb is not None:
                entry["thumbnail"] = thumb
        return entries

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


# -- on-disk helpers (durable fallbacks for the dashboard) --------------------


def read_job_meta(output_dir: Path, job_id: str) -> dict | None:
    """The durable `ctx.dump()` snapshot written by the orchestrator, if present."""
    path = Path(output_dir) / job_id / "meta" / "job.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def thumbnail_url(output_dir: Path, job_id: str) -> str | None:
    """Artifact URL of a job's poster frame, when the Production stage made one."""
    if (Path(output_dir) / job_id / "production" / "thumbnail.jpg").is_file():
        return f"/artifacts/{job_id}/production/thumbnail.jpg"
    return None


def scan_job_dirs(output_dir: Path) -> list[dict]:
    """Job summaries from disk so the dashboard shows history across restarts."""
    root = Path(output_dir)
    if not root.is_dir():
        return []
    entries: list[dict] = []
    for path in root.iterdir():
        if not (path.is_dir() and path.name.startswith("job-")):
            continue
        meta = read_job_meta(root, path.name)
        entry = {
            "job_id": path.name,
            "status": (meta or {}).get("status", "succeeded"),
            "created_at": path.stat().st_mtime,
            "topic": ((meta or {}).get("input") or {}).get("topic", path.name),
            "score": _quality_score(meta),
        }
        thumb = thumbnail_url(root, path.name)
        if thumb is not None:
            entry["thumbnail"] = thumb
        entries.append(entry)
    return entries


def list_artifacts(output_dir: Path, job_id: str) -> list[dict]:
    """Every file in the job directory, with stage, size, mime, and a fetchable URL."""
    root = Path(output_dir) / job_id
    artifacts: list[dict] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        stage = rel.parts[0] if len(rel.parts) > 1 else "."
        artifacts.append(
            {
                "stage": stage,
                "name": path.name,
                "path": rel.as_posix(),
                "url": f"/artifacts/{job_id}/{rel.as_posix()}",
                "size": path.stat().st_size,
                "mime": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            }
        )
    return artifacts
