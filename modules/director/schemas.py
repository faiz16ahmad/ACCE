"""Director Mode state contracts (docs/director-mode.md).

Director Mode is a post-production overlay on the Audio Pipeline. It never
modifies the pipeline's outputs — it loads frozen references, records the
user's music edits in `director.json`, and *derives* new audio/exports.

Track identity rule: tracks are referenced by a stable `track_id` (never a
filesystem path). Paths are resolved by the library per source. `track_id`
shapes: `bundled:<stem>` (assets/music/), `upload:<stem>` (job uploads),
`pixabay:<id>` (future online source).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# music.mode — the semantics of the current music state.
MusicMode = Literal["ai", "library", "upload", "none"]


class TrackRef(BaseModel):
    """A stable reference to a library track (never a path)."""

    track_id: str
    source: str = "bundled"  # bundled | upload | online


class MusicEdit(BaseModel):
    """The user's current music settings (the editable dimension)."""

    mode: MusicMode = "ai"
    track_ref: TrackRef | None = None  # required unless mode == "none"
    volume: float = Field(0.2, ge=0.0, le=1.0)  # mirrors ACCE_AUDIO__MUSIC_VOLUME
    fade_in: float = Field(1.0, ge=0.0)
    fade_out: float = Field(1.0, ge=0.0)
    duck: bool = True
    loop: bool = True


class DirectorBase(BaseModel):
    """Frozen references into the automatic pipeline (read-only)."""

    audio_plan_path: str = "audio/audio_plan.json"
    mix_plan_path: str = "audio/mix_plan.json"
    master_path: str = "audio/master_audio.m4a"
    video_path: str = "production/final_video.mp4"
    ai_track: str | None = None  # library track_id of the AI-selected bed


class ExportRecord(BaseModel):
    """One immutable export (created by Director Mode, never rewritten)."""

    export_id: str
    created_at: str
    video_path: str
    size: int = 0
    duration: float = 0.0
    music: MusicEdit  # the exact music snapshot that produced this export
    url: str = ""


class DirectorState(BaseModel):
    """The authoritative editor state, persisted as director/director.json."""

    version: int = 1
    base: DirectorBase = Field(default_factory=DirectorBase)
    music: MusicEdit = Field(default_factory=MusicEdit)
    uploads: list[str] = Field(default_factory=list)  # filenames in director/uploads/
    exports: list[ExportRecord] = Field(default_factory=list)  # newest first
    updated_at: str = ""


# -- DTOs for the API / Studio UI ---------------------------------------------


class MusicTrack(BaseModel):
    """One library track as the UI sees it — source-agnostic."""

    track_id: str
    title: str
    provider: str  # bundled | upload | online:…
    source: str  # human label chip, e.g. "bundled" | "uploaded"
    duration: float = 0.0
    bpm: int | None = None
    license: str | None = None
    stream_url: str = ""
    is_ai: bool = False  # true when this is the automatic pick for a job
    score: float | None = None  # retrieval score when surfaced as a recommendation


class DirectorSnapshot(BaseModel):
    """GET /api/jobs/{id}/director — the state plus the resolved current track."""

    state: DirectorState
    current_track: MusicTrack | None = None  # None when mode == "none" or unresolvable
    recommendations: list[MusicTrack] = Field(default_factory=list)
    library: list[MusicTrack] = Field(default_factory=list)
