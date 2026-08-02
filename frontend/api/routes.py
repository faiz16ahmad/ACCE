"""HTTP endpoints for the ACCE dashboard."""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
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


@router.get("/jobs/{job_id}/music")
def get_music(job_id: str) -> dict:
    """The background-music track selected for this job (a library asset, not
    a job artifact), so the Studio preview can audition the actual bed."""
    info = _music_info(job_id)
    if info is None:
        return {"music": None}
    return {"music": info}


@router.get("/jobs/{job_id}/music/stream")
def stream_music(job_id: str) -> FileResponse:
    path = _music_file(job_id)
    if path is None:
        raise HTTPException(status_code=404, detail="no background music for this job")
    media_type = mimetypes.guess_type(path.name)[0] or "audio/wav"
    return FileResponse(path, media_type=media_type, filename=path.name)


def _music_file(job_id: str, output_dir: Path | None = None) -> Path | None:
    """Resolve the selected bed file, or None when there is none / it's gone."""
    root = output_dir or settings.paths.output_dir
    audio_json = root / job_id / "audio" / "audio.json"
    if not audio_json.is_file():
        return None
    try:
        data = json.loads(audio_json.read_text(encoding="utf-8"))
    except Exception:
        return None
    raw = data.get("music_path")
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = root.parent / path
    path = path.resolve()
    return path if path.is_file() else None


def _music_info(job_id: str, output_dir: Path | None = None) -> dict | None:
    """Metadata for the selected bed: title/provider/license/bpm/duration + stream URL."""
    root = output_dir or settings.paths.output_dir
    path = _music_file(job_id, root)
    if path is None:
        return None
    audio_json = root / job_id / "audio" / "audio.json"
    meta: dict = {}
    try:
        data = json.loads(audio_json.read_text(encoding="utf-8"))
        meta = data.get("metadata") or {}
    except Exception:
        pass
    # License/bpm/duration live on the ranked asset in music_assets.json.
    asset_info: dict = {}
    assets_json = root / job_id / "audio" / "music_assets.json"
    if assets_json.is_file():
        try:
            ranked = json.loads(assets_json.read_text(encoding="utf-8"))
            if ranked:
                asset_info = ranked[0].get("asset") or {}
        except Exception:
            pass
    return {
        "title": meta.get("music_title") or path.stem,
        "provider": meta.get("music_provider"),
        "license": asset_info.get("license"),
        "bpm": asset_info.get("bpm"),
        "duration": asset_info.get("duration") or meta.get("music_duration"),
        "url": f"/api/jobs/{job_id}/music/stream",
    }
