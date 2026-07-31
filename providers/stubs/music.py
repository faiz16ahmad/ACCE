from urllib.parse import quote

from ..base import MusicProvider
from ..models import MusicHit


class StubMusicProvider(MusicProvider):
    name = "stub"

    def search(self, query: str, *, count: int = 1) -> list[MusicHit]:
        return [
            MusicHit(
                provider=self.name,
                title=f"stub track for {query!r}",
                url=f"https://placeholder.example/music?q={quote(query)}&n={i}",
                duration=30.0,
                bpm=120,
                license="royalty-free (stub)",
            )
            for i in range(count)
        ]
