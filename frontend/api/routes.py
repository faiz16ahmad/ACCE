"""HTTP endpoints for the ACCE dashboard."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from config.settings import Settings
from core.models import UserInput

from .jobs import JobStore

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


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    record = job_store.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"no such job: {job_id}")
    return record.to_dict()


@router.get("/jobs/{job_id}/logs")
def get_logs(job_id: str, limit: int = 200) -> dict:
    record = job_store.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"no such job: {job_id}")
    return {"logs": list(record.logs)[-limit:]}
