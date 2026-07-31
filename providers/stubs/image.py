from urllib.parse import quote

from ..base import ImageProvider
from ..models import MediaHit


class StubImageProvider(ImageProvider):
    name = "stub"

    def __init__(self, **_: object) -> None:
        pass

    def search(self, query: str, *, count: int = 1) -> list[MediaHit]:
        return [
            MediaHit(
                provider=self.name,
                media_type="image",
                url=f"https://placeholder.example/image?q={quote(query)}&n={i}",
                license="royalty-free",
                attribution="Stub provider (demo)",
                title=f"stock image for {query}",
                width=1920,
                height=1080,
            )
            for i in range(count)
        ]
