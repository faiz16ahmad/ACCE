"""Local music folder provider (keyless).

Scans a configured directory for audio files treated as the user's own
royalty-free assets. Relevance is naive (filename word overlap with the
query); no network involved.
"""

from __future__ import annotations

import re
from pathlib import Path

from .base import MusicProvider
from .models import MusicHit

_AUDIO_SUFFIXES = {".mp3", ".wav", ".ogg", ".m4a", ".flac"}


class LocalMusicProvider(MusicProvider):
    name = "local"

    def __init__(self, local_dir: str = "assets/music", **_: object) -> None:
        self.local_dir = Path(local_dir)

    def search(self, query: str, *, count: int = 1) -> list[MusicHit]:
        if not self.local_dir.is_dir():
            return []
        files = [p for p in self.local_dir.rglob("*") if p.suffix.lower() in _AUDIO_SUFFIXES]
        tokens = set(re.findall(r"[a-z0-9]+", query.lower()))

        def relevance(path: Path) -> int:
            name = path.stem.lower()
            return sum(word in name for word in tokens)

        files.sort(key=relevance, reverse=True)
        return [
            MusicHit(
                provider=self.name,
                title=path.stem,
                url="",
                local_path=path,
                license="royalty-free (local)",
            )
            for path in files[:count]
        ]
