"""Media fallback chain.

Priority: Cache (via the per-provider wrapper) -> Pexels -> Pixabay ->
Wikimedia. V1 ships the chain logic with stub providers; real providers are
registered per milestone and require no changes here.
"""

from __future__ import annotations

from memory.cache import DiskCache

from .base import ImageProvider, VideoProvider
from .cache_provider import CachingProvider
from .models import MediaHit
from .registry import get_provider


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


def build_media_chain(provider_names: list[str], cache: DiskCache) -> MediaChain:
    return MediaChain(
        image_providers=[get_provider("image", name) for name in provider_names],
        video_providers=[get_provider("video", name) for name in provider_names],
        cache=cache,
    )
