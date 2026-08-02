"""DirectorStore — the authoritative editor state, persisted under the job dir.

Layout (never touches the pipeline's audio/ or production/ dirs):

    out/<job_id>/
      director/
        director.json     # DirectorState (versioned)
        uploads/          # user-uploaded tracks (copied in)
        preview/          # transient preview master + preview.mp4
      exports/
        <export_id>/
          final_video.mp4
          export.json
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from .schemas import DirectorState, ExportRecord

log = logging.getLogger(__name__)

_FILENAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")


def new_export_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return f"ex_{stamp}_{uuid.uuid4().hex[:4]}"


def _ai_track_from_audio(audio: dict) -> str | None:
    """Map the pipeline's music_path to a library track_id (bundled:<stem>)."""
    raw = audio.get("music_path")
    if not raw:
        return None
    stem = Path(raw).stem
    if not stem:
        return None
    return f"bundled:{stem}"


class DirectorStore:
    def __init__(self, job_dir: Path) -> None:
        self.job_dir = Path(job_dir)
        self.director_dir = self.job_dir / "director"
        self.uploads_dir = self.director_dir / "uploads"
        self.preview_dir = self.director_dir / "preview"
        self.exports_dir = self.job_dir / "exports"

    # -- state ----------------------------------------------------------------

    def load(self) -> DirectorState:
        path = self.director_dir / "director.json"
        if path.is_file():
            try:
                return DirectorState.model_validate(
                    json.loads(path.read_text(encoding="utf-8"))
                )
            except Exception as exc:
                log.warning("director.json unreadable (%s); re-initializing", exc)
        return self.initialize()

    def initialize(self) -> DirectorState:
        """Default state from the frozen pipeline (AI pick, unchanged settings)."""
        audio = self._read_audio_json()
        state = DirectorState(
            base=DirectorState().base,  # relative refs into the job dir
            music=DirectorState().music,  # mode="ai", default volume/fades
        )
        state.base.ai_track = _ai_track_from_audio(audio)
        state.updated_at = datetime.now(UTC).isoformat()
        self.save(state)
        return state

    def save(self, state: DirectorState) -> Path:
        self.director_dir.mkdir(parents=True, exist_ok=True)
        path = self.director_dir / "director.json"
        path.write_text(
            json.dumps(state.model_dump(mode="json"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    # -- frozen pipeline references ------------------------------------------

    def _read_audio_json(self) -> dict:
        path = self.job_dir / "audio" / "audio.json"
        if not path.is_file():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def master_path(self) -> Path:
        return self.job_dir / "audio" / "master_audio.m4a"

    def mix_plan_path(self) -> Path:
        return self.job_dir / "audio" / "mix_plan.json"

    def video_path(self) -> Path:
        return self.job_dir / "production" / "final_video.mp4"

    # -- uploads --------------------------------------------------------------

    def add_upload(self, filename: str, content: bytes) -> Path:
        safe = _FILENAME_RE.sub("-", Path(filename).name).strip("-") or "upload"
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        dest = self.uploads_dir / safe
        dest.write_bytes(content)
        state = self.load()
        if safe not in state.uploads:
            state.uploads.append(safe)
            state.updated_at = datetime.now(UTC).isoformat()
            self.save(state)
        return dest

    # -- exports --------------------------------------------------------------

    def new_export_dir(self, export_id: str) -> Path:
        path = self.exports_dir / export_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_export_record(self, record: ExportRecord) -> None:
        state = self.load()
        # newest first; dedupe on re-save
        state.exports = [e for e in state.exports if e.export_id != record.export_id]
        state.exports.insert(0, record)
        state.updated_at = datetime.now(UTC).isoformat()
        self.save(state)
