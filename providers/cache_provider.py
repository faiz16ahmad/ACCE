"""Cache-first wrapper implementing media priority #1 (Cache).

Wraps any image/video provider: identical queries are served from the disk
cache before hitting the provider at all.
"""

from __future__ import annotations

import logging

from memory.cache import DiskCache

from .models import MediaHit

log = logging.getLogger(__name__)

CACHE_NAMESPACE = "media"


class CachingProvider:
    def __init__(self, inner: object, cache: DiskCache, media_type: str) -> None:
        self.inner = inner
        self.cache = cache
        self.media_type = media_type
        self.name = f"cache:{getattr(inner, 'name', '?')}"

    def search(self, query: str, *, count: int = 1) -> list[MediaHit]:
        key = f"{self.media_type}:{self.inner.name}:{query}:{count}"
        cached = self.cache.get(CACHE_NAMESPACE, key)
        if cached is not None:
            log.debug("media cache hit for %r", query)
            return [MediaHit.model_validate(item) for item in cached]
        hits = self.inner.search(query, count=count)
        self.cache.set(CACHE_NAMESPACE, key, [h.model_dump(mode="json") for h in hits])
        return hits
