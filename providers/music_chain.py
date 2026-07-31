"""Music provider chain.

Priority: Pixabay Music -> Local assets -> Stub. The chain returns the first
provider's non-empty hits and skips any provider that raises, so a real music
source can fail without breaking narration-only audio.
"""

from __future__ import annotations

import logging

from .base import MusicProvider
from .models import MusicHit
from .registry import get_provider

log = logging.getLogger(__name__)


class MusicChain:
    def __init__(self, providers: list[MusicProvider]) -> None:
        self._providers = list(providers)

    def search(self, query: str, *, count: int = 1) -> list[MusicHit]:
        for provider in self._providers:
            try:
                hits = provider.search(query, count=count)
            except Exception as exc:  # noqa: BLE001 - a failing provider must not break the chain
                log.warning("music provider %s failed for %r: %s", provider.name, query, exc)
                continue
            if hits:
                return hits
        return []


def build_music_chain(
    provider_names: list[str],
    *,
    api_keys: dict[str, str] | None = None,
    local_dir: str = "assets/music",
) -> MusicChain:
    keys = api_keys or {}
    providers = []
    for name in provider_names:
        if name == "pixabay":
            providers.append(get_provider("music", name, api_key=keys.get(name)))
        elif name == "local":
            providers.append(get_provider("music", name, local_dir=local_dir))
        else:
            providers.append(get_provider("music", name))
    return MusicChain(providers)
