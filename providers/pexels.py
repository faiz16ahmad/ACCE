"""Pexels image/video providers (https://www.pexels.com/api/)."""

from __future__ import annotations

import os
from urllib.parse import quote

from ._http import get_json
from .base import ImageProvider, ProviderError, VideoProvider
from .models import MediaHit

_BASE = "https://api.pexels.com"


def _api_key(configured: str | None) -> str:
    key = configured or os.environ.get("PEXELS_API_KEY", "")
    if not key:
        raise ProviderError("Pexels requires an API key — set PEXELS_API_KEY or ACCE_MEDIA__PEXELS_API_KEY")
    return key


class _PexelsBase:
    def __init__(self, api_key: str | None = None, timeout: float = 15.0, **_: object) -> None:
        self.api_key = _api_key(api_key)
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {"Authorization": self.api_key}


def _pick_mp4(files: list[dict]) -> tuple[str, int | None, int | None]:
    best_url, best_w, best_h, best_area = "", None, None, -1
    for entry in files:
        if entry.get("file_type") != "video/mp4":
            continue
        w = entry.get("width") or 0
        h = entry.get("height") or 0
        if w * h > best_area:
            best_area, best_url, best_w, best_h = w * h, entry.get("link") or "", w or None, h or None
    return best_url, best_w, best_h


class PexelsImageProvider(_PexelsBase, ImageProvider):
    name = "pexels"

    def search(self, query: str, *, count: int = 1) -> list[MediaHit]:
        url = f"{_BASE}/v1/search?query={quote(query)}&per_page={count}&orientation=landscape"
        data = get_json(url, headers=self._headers(), timeout=self.timeout)
        hits = []
        for photo in data.get("photos", []):
            src = photo.get("src") or {}
            hits.append(
                MediaHit(
                    provider=self.name,
                    media_type="image",
                    url=src.get("large2x") or src.get("large") or src.get("original") or "",
                    license="pexels",
                    attribution=f"Photo by {photo.get('photographer')} on Pexels",
                    width=photo.get("width"),
                    height=photo.get("height"),
                    title=photo.get("alt"),
                )
            )
        return hits


class PexelsVideoProvider(_PexelsBase, VideoProvider):
    name = "pexels"

    def search(self, query: str, *, count: int = 1) -> list[MediaHit]:
        url = f"{_BASE}/videos/search?query={quote(query)}&per_page={count}&orientation=landscape"
        data = get_json(url, headers=self._headers(), timeout=self.timeout)
        hits = []
        for video in data.get("videos", []):
            url, width, height = _pick_mp4(video.get("video_files") or [])
            user = (video.get("user") or {}).get("name")
            hits.append(
                MediaHit(
                    provider=self.name,
                    media_type="video",
                    url=url,
                    license="pexels",
                    attribution=f"Video by {user} on Pexels",
                    width=width,
                    height=height,
                    duration=video.get("duration"),
                )
            )
        return hits
