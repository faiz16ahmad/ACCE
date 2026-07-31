"""HTTP endpoints for the ACCE dashboard."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from config.settings import Settings
from core.models import UserInput

from .jobs import JobStore, list_artifacts, read_job_meta, scan_job_dirs

router = APIRouter(prefix="/api")

settings = Settings()
job_store = JobStore(settings)


class JobRequest(BaseModel):
    topic: str = Field(min_length=1)
    instructions: list[str] = Field(default_factory=list)
    duration: int | None = Field(default=None, ge=10)
    style: str | None = None


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "app": settings.app_name, "version": settings.app_version}


@router.post("/jobs", status_code=201)
def create_job(req: JobRequest) -> dict:
    job_id = job_store.create(UserInput(**req.model_dump()))
    return {"job_id": job_id}


@router.get("/jobs")
def list_jobs() -> dict:
    """Recent projects: in-memory records plus durable dirs from disk."""
    known = {entry["job_id"]: entry for entry in job_store.list_summaries()}
    for entry in scan_job_dirs(settings.paths.output_dir):
        known.setdefault(entry["job_id"], entry)
    jobs = sorted(known.values(), key=lambda entry: entry.get("created_at") or 0.0, reverse=True)
    return {"jobs": jobs}


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    record = job_store.get(job_id)
    if record is not None:
        return record.to_dict()
    # Durable fallback: a finished job from before the API restarted.
    meta = read_job_meta(settings.paths.output_dir, job_id)
    if meta is not None:
        return {
            "job_id": job_id,
            "status": meta.get("status", "succeeded"),
            "current_stage": None,
            "logs": [],
            "result": meta,
            "error": (meta.get("errors") or [None])[0] if meta.get("errors") else None,
        }
    raise HTTPException(status_code=404, detail=f"no such job: {job_id}")


@router.get("/jobs/{job_id}/logs")
def get_logs(job_id: str, limit: int = 200) -> dict:
    record = job_store.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"no such job: {job_id}")
    return {"logs": list(record.logs)[-limit:]}


@router.get("/jobs/{job_id}/artifacts")
def get_artifacts(job_id: str) -> dict:
    job_dir = settings.paths.output_dir / job_id
    if not job_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"no such job: {job_id}")
    return {"artifacts": list_artifacts(settings.paths.output_dir, job_id)}
