"""Provider-level result types.

These are the return types the provider interfaces expose. `bpm` is present
on music tracks now so V2 beat-synchronization needs no schema change.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel


class MediaHit(BaseModel):
    provider: str
    media_type: Literal["image", "video"]
    url: str
    local_path: Path | None = None
    license: str = "unknown"
    attribution: str | None = None
    width: int | None = None
    height: int | None = None


class MusicHit(BaseModel):
    provider: str
    title: str
    url: str
    local_path: Path | None = None
    duration: float | None = None
    bpm: int | None = None
    license: str = "royalty-free"
