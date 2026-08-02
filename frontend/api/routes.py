"""HTTP endpoints for the ACCE dashboard."""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from config.settings import Settings
from core.models import UserInput

from modules.director.schemas import MusicEdit
from modules.director.service import DirectorService

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


# ---------------------------------------------------------------------------
#  Music library (Director Mode §4)
# ---------------------------------------------------------------------------

@router.get("/music/library")
def list_music_library(q: str = "", provider: str = "") -> dict:
    """Unified library index: bundled + global uploaded tracks."""
    from modules.director.library import BundledSource, UploadSource
    from modules.director.schemas import MusicTrack as MusicTrackDTO
    # Uploads are a GLOBAL library (shared across all jobs), not per-job.
    sources = [
        BundledSource(settings.music.local_dir),
        UploadSource(settings.music.upload_dir),
    ]
    tracks: list[MusicTrackDTO] = []
    ffmpeg = settings.production.ffmpeg_path or "ffmpeg"
    for source in sources:
        for t in source.list(ffmpeg):
            tracks.append(t)
    # filter
    if q:
        q_lower = q.lower()
        tracks = [t for t in tracks if q_lower in t.title.lower()]
    if provider:
        tracks = [t for t in tracks if t.provider == provider]
    return {"tracks": [t.model_dump(mode="json") for t in tracks]}


@router.get("/music/library/{track_id:path}/stream")
def stream_library_track(track_id: str) -> FileResponse:
    from modules.director.library import BundledSource, UploadSource
    bundled = BundledSource(settings.music.local_dir)
    uploads = UploadSource(settings.music.upload_dir)
    path = bundled.resolve(track_id) or uploads.resolve(track_id)
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail=f"track not found: {track_id}")
    media_type = mimetypes.guess_type(path.name)[0] or "audio/wav"
    return FileResponse(path, media_type=media_type, filename=path.name)


# ---------------------------------------------------------------------------
#  Director Mode endpoints (§9)
# ---------------------------------------------------------------------------

class MusicEditRequest(BaseModel):
    mode: str = "ai"
    track_id: str | None = None
    volume: float = Field(0.2, ge=0.0, le=1.0)
    fade_in: float = Field(1.0, ge=0.0)
    fade_out: float = Field(1.0, ge=0.0)
    duck: bool = True
    loop: bool = True


class RenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


@router.get("/jobs/{job_id}/director")
def get_director(job_id: str) -> dict:
    svc = _director_svc(job_id)
    snap = svc.snapshot()
    return {
        "state": snap.state.model_dump(mode="json"),
        "current_track": snap.current_track.model_dump(mode="json") if snap.current_track else None,
        "recommendations": [t.model_dump(mode="json") for t in snap.recommendations],
        "library": [t.model_dump(mode="json") for t in snap.library],
    }


@router.put("/jobs/{job_id}/director/music")
def set_music(job_id: str, req: MusicEditRequest) -> dict:
    svc = _director_svc(job_id)
    track_ref = MusicEdit(mode=req.mode, volume=req.volume, fade_in=req.fade_in,
                          fade_out=req.fade_out, duck=req.duck, loop=req.loop)
    if req.track_id:
        from modules.director.schemas import TrackRef
        track_ref.track_ref = TrackRef(track_id=req.track_id)
    snap = svc.set_music(track_ref)
    return {
        "state": snap.state.model_dump(mode="json"),
        "current_track": snap.current_track.model_dump(mode="json") if snap.current_track else None,
    }


@router.post("/jobs/{job_id}/director/upload")
def upload_track(job_id: str, file: UploadFile = File(...), name: str = Form("")) -> dict:
    """Upload a track to the GLOBAL music library, with a user-assigned name.

    `name` is optional — when omitted the file stem is used. The track becomes
    available to every job's Director Mode library.
    """
    svc = _director_svc(job_id)
    content = file.file.read()
    snap = svc.upload(file.filename or "upload.wav", content, name=name)
    return {
        "state": snap.state.model_dump(mode="json"),
        "library": [t.model_dump(mode="json") for t in snap.library],
    }


@router.put("/music/library/upload/{track_id}/name")
def rename_upload(track_id: str, req: RenameRequest) -> dict:
    """Rename a user-uploaded track (genre / BGM name) in the global library."""
    from modules.director.library import UploadSource
    source = UploadSource(settings.music.upload_dir)
    if not track_id.startswith("upload:"):
        track_id = f"upload:{track_id}"  # accept the bare stem too
    source.rename(track_id, req.name)
    track = next(
        (t for t in source.list(settings.production.ffmpeg_path or "ffmpeg") if t.track_id == track_id),
        None,
    )
    return {"track": track.model_dump(mode="json") if track else None}


@router.post("/jobs/{job_id}/director/preview")
def create_preview(job_id: str) -> dict:
    svc = _director_svc(job_id)
    preview_path = svc.preview()
    url = f"/artifacts/{job_id}/director/preview/{preview_path.name}"
    return {"preview_url": url}


@router.post("/jobs/{job_id}/director/export")
def create_export(job_id: str) -> dict:
    svc = _director_svc(job_id)
    record = svc.export()
    return {"export": record.model_dump(mode="json")}


@router.get("/jobs/{job_id}/exports")
def list_exports(job_id: str) -> dict:
    svc = _director_svc(job_id)
    return {"exports": [e.model_dump(mode="json") for e in svc.exports()]}


@router.delete("/jobs/{job_id}/exports/{export_id}")
def delete_export(job_id: str, export_id: str) -> dict:
    svc = _director_svc(job_id)
    export_dir = svc.store.exports_dir / export_id
    if export_dir.is_dir():
        import shutil
        shutil.rmtree(export_dir)
    state = svc.store.load()
    state.exports = [e for e in state.exports if e.export_id != export_id]
    svc.store.save(state)
    return {"deleted": export_id}


def _director_svc(job_id: str) -> DirectorService:
    return DirectorService(job_id, settings)
