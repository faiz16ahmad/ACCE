"""Media fallback chain.

Priority: Cache (via the per-provider wrapper) -> Pexels -> Pixabay ->
Wikimedia. `best()` ranks each provider's candidates and stops at the first
provider whose top-ranked asset is satisfactory, returning the *full ranked
candidate list* (the selected asset is simply `candidates[0]`). `search()`
keeps the older first-nonempty behavior for compatibility.
"""

from __future__ import annotations

import logging

from memory.cache import DiskCache

from .base import ImageProvider, VideoProvider
from .cache_provider import CachingProvider
from .models import MediaHit
from .ranking import is_satisfactory, rank_hit, rank_hits
from .registry import get_provider

log = logging.getLogger(__name__)


class MediaChain:
    def __init__(
        self,
        image_providers: list[ImageProvider],
        video_providers: list[VideoProvider],
        cache: DiskCache,
    ) -> None:
        self._images = [CachingProvider(p, cache, "image") for p in image_providers]
        self._videos = [CachingProvider(p, cache, "video") for p in video_providers]

    def search(self, query: str, *, media_type: str = "image", count: int = 1) -> list[MediaHit]:
        chain = self._images if media_type == "image" else self._videos
        for provider in chain:
            hits = provider.search(query, count=count)
            if hits:
                return hits
        return []

    def best(
        self,
        query: str,
        *,
        media_type: str = "image",
        count: int = 10,
        threshold: float = 0.6,
        target_duration: float | None = None,
    ) -> list[MediaHit]:
        """Full ranked candidate list from the first provider with a satisfactory top hit."""
        chain = self._images if media_type == "image" else self._videos
        for provider in chain:
            try:
                hits = provider.search(query, count=count)
            except Exception as exc:  # noqa: BLE001 - a failing provider must not break the chain
                log.warning("media provider %s failed for %r: %s", getattr(provider, "name", "?"), query, exc)
                continue
            if not hits:
                continue
            ranked = rank_hits(hits, query, media_type, target_duration)
            if is_satisfactory(rank_hit(ranked[0], query, media_type, target_duration), threshold):
                return ranked
        return []


def build_media_chain(
    provider_names: list[str],
    cache: DiskCache,
    api_keys: dict[str, str] | None = None,
) -> MediaChain:
    keys = api_keys or {}
    image_providers = [get_provider("image", name, api_key=keys.get(name)) for name in provider_names]
    video_providers = [get_provider("video", name, api_key=keys.get(name)) for name in provider_names]
    return MediaChain(image_providers, video_providers, cache)
