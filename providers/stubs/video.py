from urllib.parse import quote

from ..base import VideoProvider
from ..models import MediaHit


class StubVideoProvider(VideoProvider):
    name = "stub"

    def __init__(self, **_: object) -> None:
        pass

    def search(self, query: str, *, count: int = 1) -> list[MediaHit]:
        return [
            MediaHit(
                provider=self.name,
                media_type="video",
                url=f"https://placeholder.example/video?q={quote(query)}&n={i}",
                license="royalty-free",
                attribution="Stub provider (demo)",
                title=f"stock video for {query}",
                width=1920,
                height=1080,
                duration=10.0,
            )
            for i in range(count)
        ]
