"""Production stage contracts."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel


class SubtitleCue(BaseModel):
    index: int
    start: float
    end: float
    text: str


class ProductionOutput(BaseModel):
    video_path: Path
    subtitle_path: Path | None = None
    thumbnail_path: Path | None = None
    title: str
    description: str
