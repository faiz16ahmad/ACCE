"""DirectorService — the orchestration layer (docs/director-mode.md).

Reads the frozen pipeline outputs (never modifies them) and exposes the V1
Director workflow: load → edit music → preview → export. The service owns the
policy of resolving a `MusicEdit` into a path, caching the remix, and building
immutable exports. It never touches the orchestrator, factory, or any pipeline
module except via `remix.py` / `export.py`.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from modules.audio.music.retrieve import rank_assets
from modules.audio.music.schemas import MusicAsset, MusicSelection
from modules.audio.music.timeline import AudioPlan
from config.settings import Settings

from .export import export_duration, remux
from .library import MusicLibrary
from .remix import build_director_plan, remix_master
from .schemas import (
    DirectorSnapshot,
    DirectorState,
    ExportRecord,
    MusicEdit,
    MusicTrack,
    TrackRef,
)
from .store import DirectorStore, new_export_id

log = logging.getLogger(__name__)


def _music_state_hash(music: MusicEdit) -> str:
    """Stable cache key for a music state (§6)."""
    payload = music.model_dump(mode="json", exclude_defaults=False)
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]


class DirectorService:
    """Per-job post-production service for the Studio API layer."""

    def __init__(self, job_id: str, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self.job_id = job_id
        output_dir = self.settings.paths.output_dir
        self.store = DirectorStore(output_dir / job_id)
        self.library = MusicLibrary([], self.settings.production.ffmpeg_path or "ffmpeg")
        # lazy-init library list (probed once per request; jobs are few)
        self._library_cache: list[MusicTrack] | None = None

    # -- library --------------------------------------------------------------

    def list_library(self) -> list[MusicTrack]:
        if self._library_cache is not None:
            return self._library_cache
        from modules.director.library import BundledSource, UploadSource
        # Global uploads (shared across all jobs), not per-job.
        sources = [
            BundledSource(self.settings.music.local_dir),
            UploadSource(self.settings.music.upload_dir),
        ]
        self.library = MusicLibrary(sources, self.settings.production.ffmpeg_path or "ffmpeg")
        self._library_cache = self.library.list()
        return self._library_cache

    def stream_path(self, track_id: str) -> Path | None:
        return self.library.resolve(track_id)

    # -- recommendations -------------------------------------------------------

    def _recommendations(self, limit: int = 5) -> list[MusicTrack]:
        """Top-N alternatives from the same retrieval ranking the pipeline uses."""
        audio = self._read_json(self.store.job_dir / "audio" / "audio.json")
        audio_plan = self._read_json(self.store.job_dir / "audio" / "audio_plan.json")
        music_plan = audio_plan.get("music") or []
        if not music_plan:
            return []
        intent = AudioPlan(music=music_plan).music[0]
        total = audio.get("duration") or 0.0
        library = self.library.list()
        if not library:
            return []
        selection = MusicSelection(
            intent=intent, duration_hint=total, genre_hint=audio.get("metadata", {}).get("style_genre")
        )
        assets = [MusicAsset(
            asset_id=t.track_id, provider=t.provider, title=t.title,
            local_path=self.library.resolve(t.track_id), duration=t.duration, bpm=t.bpm, license=t.license or "unknown",
        ) for t in library]
        ranked = rank_assets(assets, selection, self.settings.music)
        score_by_id = {r.asset.asset_id: r.score for r in ranked}
        recommendations = []
        seen = set()
        for r in ranked[1:]:
            if r.asset.asset_id in seen:
                continue
            track = next((t for t in library if t.track_id == r.asset.asset_id), None)
            if track is None:
                continue
            recommendations.append(track.model_copy(update={"score": score_by_id[r.asset.asset_id]}))
            seen.add(r.asset.asset_id)
            if len(recommendations) >= limit:
                break
        return recommendations

    # -- snapshot --------------------------------------------------------------

    def snapshot(self) -> DirectorSnapshot:
        state = self.store.load()
        library = self.list_library()
        current_track = self._current_track(state, library)
        return DirectorSnapshot(
            state=state,
            current_track=current_track,
            recommendations=self._recommendations(),
            library=library,
        )

    def _current_track(self, state: DirectorState, library: list[MusicTrack]) -> MusicTrack | None:
        music = state.music
        if music.mode == "none":
            return None
        if music.track_ref is not None:
            match = next((t for t in library if t.track_id == music.track_ref.track_id), None)
            if match is not None:
                return match
        if music.mode == "ai" and state.base.ai_track:
            match = next((t for t in library if t.track_id == state.base.ai_track), None)
            if match is not None:
                return match
        return None

    # -- edit -----------------------------------------------------------------

    def set_music(self, edit: MusicEdit) -> DirectorSnapshot:
        """Apply a music edit and persist the new state."""
        if edit.mode not in ("ai", "library", "upload", "none"):
            raise ValueError(f"invalid mode: {edit.mode!r}")
        if edit.mode == "ai":
            edit.track_ref = TrackRef(track_id="ai", source="system")
        elif edit.mode == "none":
            edit.track_ref = None
        # For library/upload modes: track_ref is required and must be in the library.
        elif edit.mode in ("library", "upload"):
            if edit.track_ref is None:
                raise ValueError("track_ref required for library/upload mode")
            self.list_library()  # ensure library is built before resolving
            if self.library.resolve(edit.track_ref.track_id) is None:
                raise ValueError(f"track not found: {edit.track_ref.track_id!r}")
        state = self.store.load()
        state.music = edit
        state.updated_at = datetime.now(UTC).isoformat()
        self.store.save(state)
        return self.snapshot()

    # -- upload ----------------------------------------------------------------

    def upload(self, filename: str, content: bytes, name: str = "") -> DirectorSnapshot:
        """Add a track to the global music library (shared across all jobs)."""
        from modules.director.library import UploadSource
        source = UploadSource(self.settings.music.upload_dir)
        source.add_file(filename, content, name)
        self._library_cache = None  # library changed → rebuild on next snapshot
        return self.snapshot()

    def rename_upload(self, track_id: str, name: str) -> DirectorSnapshot:
        """Rename a user-uploaded track in the global library."""
        from modules.director.library import UploadSource
        source = UploadSource(self.settings.music.upload_dir)
        source.rename(track_id, name)
        self._library_cache = None
        return self.snapshot()

    # -- preview / export ------------------------------------------------------

    def _resolved_track_path(self, state: DirectorState) -> Path | None:
        """The bed file the current music edit points to, or None."""
        self.list_library()  # ensure library is built before resolving
        music = state.music
        if music.mode == "none":
            return None
        if music.mode == "ai":
            path = self.library.resolve(state.base.ai_track or "")
            if path is not None:
                return path
            # AI bed unresolvable → fall back to the frozen master (no remix)
            frozen = self.store.master_path()
            return frozen if frozen.is_file() else None
        if music.track_ref is not None:
            return self.library.resolve(music.track_ref.track_id)
        return None

    def preview(self) -> Path:
        """Build remix + video-copy remux, cached by music state hash (§6)."""
        state = self.store.load()
        h = _music_state_hash(state.music)
        preview = self.store.preview_dir / f"preview_{h}.mp4"
        if preview.is_file():
            return preview
        master = self.store.preview_dir / f"master_{h}.m4a"
        plan_path = self.store.mix_plan_path()
        if not plan_path.is_file():
            raise FileNotFoundError("no mix_plan.json — cannot remix")
        from modules.audio.schemas import AudioMixPlan
        original = AudioMixPlan.model_validate(json.loads(plan_path.read_text(encoding="utf-8")))
        track_path = self._resolved_track_path(state)
        plan = build_director_plan(original, state.music, track_path)
        ffmpeg = self.settings.production.ffmpeg_path or "ffmpeg"
        remix_master(plan, master, ffmpeg_path=ffmpeg, duck=state.music.duck)
        self.store.preview_dir.mkdir(parents=True, exist_ok=True)
        frozen_video = self.store.video_path()
        remux(frozen_video, master, preview, ffmpeg_path=ffmpeg)
        return preview

    def export(self) -> ExportRecord:
        """Create an immutable export (§7). The original documentary is untouched."""
        state = self.store.load()
        export_id = new_export_id()
        export_dir = self.store.new_export_dir(export_id)
        # Reuse the same remix pipeline as preview (same master key).
        h = _music_state_hash(state.music)
        master = self.store.preview_dir / f"master_{h}.m4a"
        if not master.is_file():
            # remix if preview cache missed (shouldn't happen after preview(), but be safe)
            plan_path = self.store.mix_plan_path()
            if not plan_path.is_file():
                raise FileNotFoundError("no mix_plan.json")
            from modules.audio.schemas import AudioMixPlan
            original = AudioMixPlan.model_validate(json.loads(plan_path.read_text(encoding="utf-8")))
            track_path = self._resolved_track_path(state)
            plan = build_director_plan(original, state.music, track_path)
            ffmpeg = self.settings.production.ffmpeg_path or "ffmpeg"
            remix_master(plan, master, ffmpeg_path=ffmpeg, duck=state.music.duck)
            self.store.preview_dir.mkdir(parents=True, exist_ok=True)
        out_video = export_dir / "final_video.mp4"
        ffmpeg = self.settings.production.ffmpeg_path or "ffmpeg"
        remux(self.store.video_path(), master, out_video, ffmpeg_path=ffmpeg)
        duration = export_duration(out_video, ffmpeg)
        record = ExportRecord(
            export_id=export_id,
            created_at=datetime.now(UTC).isoformat(),
            video_path=str(out_video.relative_to(self.store.job_dir)),
            size=out_video.stat().st_size,
            duration=duration,
            music=state.music,
            url=f"/artifacts/{self.job_id}/{out_video.relative_to(self.store.job_dir).as_posix()}",
        )
        self.store.save_export_record(record)
        # also persist export metadata as a file for artifact explorer
        (export_dir / "export.json").write_text(
            json.dumps(record.model_dump(mode="json"), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        log.info("export %s created (%.1fs, %.0fKB)", export_id, duration, out_video.stat().st_size / 1024)
        return record

    def exports(self) -> list[ExportRecord]:
        return self.store.load().exports

    # -- helpers ---------------------------------------------------------------

    @staticmethod
    def _read_json(path: Path) -> dict:
        if not path.is_file():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
