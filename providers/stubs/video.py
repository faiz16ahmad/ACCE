from urllib.parse import quote

from ..base import VideoProvider
from ..models import MediaHit


class StubVideoProvider(VideoProvider):
    name = "stub"

    def search(self, query: str, *, count: int = 1) -> list[MediaHit]:
        return [
            MediaHit(
                provider=self.name,
                media_type="video",
                url=f"https://placeholder.example/video?q={quote(query)}&n={i}",
                license="stub",
            )
            for i in range(count)
        ]
