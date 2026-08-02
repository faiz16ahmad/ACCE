"""Unified music library for Director Mode (docs/director-mode.md §4).

The UI never cares where a track came from — it sees a flat, source-agnostic
`MusicTrack` index. V1 sources: **bundled** (assets/music/) and **upload**
(per-job director/uploads/). Online sources (Pixabay, future collections) plug
in behind the same `MusicSource` seam; nothing here knows what a source is.

Tracks are referenced by a stable `track_id` (`bundled:<stem>` / `upload:<stem>`),
never a path. Durations are probed with ffprobe — never guessed.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from pathlib import Path

from config.settings import MusicConfig, ProductionConfig

from .schemas import MusicTrack

log = logging.getLogger(__name__)

_AUDIO_SUFFIXES = {".mp3", ".wav", ".ogg", ".m4a", ".flac"}


def probe_duration(path: Path, ffmpeg_path: str = "ffmpeg") -> float:
    """Actual audio duration via ffprobe (ffmpeg -i parse as fallback)."""
    ffprobe = Path(ffmpeg_path)
    if ffprobe.is_file():
        probe = ffprobe.parent / "ffprobe.exe" if ffprobe.suffix.lower() == ".exe" else ffprobe.parent / "ffprobe"
    else:
        probe = Path("ffprobe")
    try:
        proc = subprocess.run(
            [str(probe), "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=10,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return round(float(proc.stdout.strip()), 2)
    except Exception:
        pass
    try:
        proc = subprocess.run(
            [ffmpeg_path, "-hide_banner", "-i", str(path), "-f", "null", "-"],
            capture_output=True, text=True, timeout=10,
        )
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", proc.stderr)
        if m:
            return round(int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)), 2)
    except Exception:
        pass
    return 0.0


class MusicSource(ABC):
    """A named source of library tracks (bundled, upload, online…)."""

    name: str
    chip: str  # human label shown in the UI

    @abstractmethod
    def list(self, ffmpeg_path: str = "ffmpeg") -> list[MusicTrack]:
        """Every track this source provides, probed for duration."""

    def resolve(self, track_id: str) -> Path | None:
        """The file for a track_id this source owns, or None."""
        prefix = f"{self.name}:"
        if not track_id.startswith(prefix):
            return None
        return self._path_for_stem(track_id[len(prefix):])

    @abstractmethod
    def _path_for_stem(self, stem: str) -> Path | None:
        ...

    @staticmethod
    def _scan(root: Path) -> list[Path]:
        if not root.is_dir():
            return []
        return [p for p in sorted(root.rglob("*")) if p.suffix.lower() in _AUDIO_SUFFIXES]


class BundledSource(MusicSource):
    """The bundled local library (assets/music/) — reuses the LocalMusicProvider dir."""

    name = "bundled"
    chip = "bundled"

    def __init__(self, local_dir: str = "assets/music", license: str = "royalty-free (local)") -> None:
        self.local_dir = Path(local_dir)
        self._license = license

    def list(self, ffmpeg_path: str = "ffmpeg") -> list[MusicTrack]:
        tracks: list[MusicTrack] = []
        for path in self._scan(self.local_dir):
            stem = path.stem
            tracks.append(
                MusicTrack(
                    track_id=f"bundled:{stem}",
                    title=stem,
                    provider=self.name,
                    source=self.chip,
                    duration=probe_duration(path, ffmpeg_path),
                    license=self._license,
                )
            )
        return tracks

    def _path_for_stem(self, stem: str) -> Path | None:
        path = self.local_dir / f"{stem}.wav"
        if path.is_file():
            return path
        for p in self._scan(self.local_dir):
            if p.stem == stem:
                return p
        return None


class UploadSource(MusicSource):
    """Global user-uploaded tracks, shared across all jobs (Director Mode).

    Files live in a global upload dir (gitignored). A sidecar `manifest.json`
    records the user-assigned name for each file, so an upload is titled by the
    user (genre / BGM name) rather than the raw filename. The manifest is the
    source of truth for titles; `track_id` stays stable (`upload:<stem>`).
    """

    name = "upload"
    chip = "uploaded"
    MANIFEST = "manifest.json"

    def __init__(self, upload_dir: str = "assets/uploads", license: str | None = "user upload") -> None:
        self.upload_dir = Path(upload_dir)
        self._license = license

    # -- manifest --------------------------------------------------------------

    def _manifest(self) -> dict:
        path = self.upload_dir / self.MANIFEST
        if not path.is_file():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_manifest(self, data: dict) -> None:
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        (self.upload_dir / self.MANIFEST).write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _title_for(self, filename: str) -> str:
        entry = self._manifest().get(filename) or {}
        return entry.get("title") or Path(filename).stem

    # -- listing / resolution --------------------------------------------------

    def list(self, ffmpeg_path: str = "ffmpeg") -> list[MusicTrack]:
        tracks: list[MusicTrack] = []
        for path in self._scan(self.upload_dir):
            stem = path.stem
            tracks.append(
                MusicTrack(
                    track_id=f"upload:{stem}",
                    title=self._title_for(path.name),
                    provider=self.name,
                    source=self.chip,
                    duration=probe_duration(path, ffmpeg_path),
                    license=self._license,
                )
            )
        return tracks

    def _path_for_stem(self, stem: str) -> Path | None:
        for p in self._scan(self.upload_dir):
            if p.stem == stem:
                return p
        return None

    # -- add / rename -----------------------------------------------------------

    def add_file(self, filename: str, content: bytes, name: str = "") -> str:
        """Copy an upload into the global dir and record its user-assigned name."""
        safe = Path(filename).name.replace(" ", "-")
        if not safe:
            raise ValueError("empty filename")
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        dest = self.upload_dir / safe
        dest.write_bytes(content)
        manifest = self._manifest()
        manifest[safe] = {
            "title": name.strip() or Path(safe).stem,
            "original_name": filename,
            "uploaded_at": datetime.now(UTC).isoformat(),
        }
        self._save_manifest(manifest)
        return f"upload:{Path(safe).stem}"

    def rename(self, track_id: str, name: str) -> None:
        """Rename an uploaded track by updating its manifest entry."""
        if not track_id.startswith(f"{self.name}:"):
            raise ValueError(f"not an upload: {track_id}")
        stem = track_id[len(f"{self.name}:"):]
        path = self._path_for_stem(stem)
        if path is None:
            raise ValueError(f"track not found: {track_id}")
        manifest = self._manifest()
        manifest[path.name] = {**(manifest.get(path.name) or {}), "title": name.strip() or stem}
        self._save_manifest(manifest)


class MusicLibrary:
    """Aggregates all sources into one source-agnostic index."""

    def __init__(
        self,
        sources: list[MusicSource],
        ffmpeg_path: str = "ffmpeg",
    ) -> None:
        self._sources = sources
        self.ffmpeg_path = ffmpeg_path

    def list(self) -> list[MusicTrack]:
        tracks: list[MusicTrack] = []
        for source in self._sources:
            tracks.extend(source.list(self.ffmpeg_path))
        return tracks

    def resolve(self, track_id: str) -> Path | None:
        for source in self._sources:
            path = source.resolve(track_id)
            if path is not None and path.is_file():
                return path
        return None

    def find(self, track_id: str) -> MusicTrack | None:
        return next((t for t in self.list() if t.track_id == track_id), None)


def build_library(
    music_config: MusicConfig,
    production_config: ProductionConfig,
    uploads_dir: Path,
) -> MusicLibrary:
    """Wire the V1 sources: bundled + global user uploads.

    `uploads_dir` is the *global* upload dir (shared across jobs) — not a
    per-job directory.
    """
    sources: list[MusicSource] = [
        BundledSource(local_dir=music_config.local_dir),
        UploadSource(upload_dir=str(uploads_dir)),
    ]
    return MusicLibrary(sources, ffmpeg_path=production_config.ffmpeg_path or "ffmpeg")
