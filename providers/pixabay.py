"""Pixabay image/video providers (https://pixabay.com/api/docs/)."""

from __future__ import annotations

import os
from urllib.parse import urlencode

from ._http import get_json
from .base import ImageProvider, ProviderError, VideoProvider
from .models import MediaHit

_BASE = "https://pixabay.com/api"


def _api_key(configured: str | None) -> str:
    key = configured or os.environ.get("PIXABAY_API_KEY", "")
    if not key:
        raise ProviderError("Pixabay requires an API key — set PIXABAY_API_KEY or ACCE_MEDIA__PIXABAY_API_KEY")
    return key


class _PixabayBase:
    def __init__(self, api_key: str | None = None, timeout: float = 15.0, **_: object) -> None:
        self.api_key = _api_key(api_key)
        self.timeout = timeout

    def _params(self, query: str, count: int) -> str:
        return urlencode({"key": self.api_key, "q": query, "per_page": count, "image_type": "photo"})


class PixabayImageProvider(_PixabayBase, ImageProvider):
    name = "pixabay"

    def search(self, query: str, *, count: int = 1) -> list[MediaHit]:
        data = get_json(f"{_BASE}/?{self._params(query, count)}", timeout=self.timeout)
        hits = []
        for item in data.get("hits", []):
            hits.append(
                MediaHit(
                    provider=self.name,
                    media_type="image",
                    url=item.get("largeImageURL") or item.get("webformatURL") or "",
                    license="pixabay",
                    attribution=f"Image by {item.get('user')} on Pixabay",
                    width=item.get("imageWidth"),
                    height=item.get("imageHeight"),
                    title=item.get("tags"),
                )
            )
        return hits


class PixabayVideoProvider(_PixabayBase, VideoProvider):
    name = "pixabay"

    def search(self, query: str, *, count: int = 1) -> list[MediaHit]:
        data = get_json(f"{_BASE}/videos/?{self._params(query, count)}", timeout=self.timeout)
        hits = []
        for item in data.get("hits", []):
            medium = (item.get("videos") or {}).get("medium") or {}
            hits.append(
                MediaHit(
                    provider=self.name,
                    media_type="video",
                    url=medium.get("url") or "",
                    license="pixabay",
                    attribution=f"Video by {item.get('user')} on Pixabay",
                    width=medium.get("width"),
                    height=medium.get("height"),
                    duration=item.get("duration"),
                    title=item.get("tags"),
                )
            )
        return hits
