from urllib.parse import quote

from ..base import ImageProvider
from ..models import MediaHit


class StubImageProvider(ImageProvider):
    name = "stub"

    def search(self, query: str, *, count: int = 1) -> list[MediaHit]:
        return [
            MediaHit(
                provider=self.name,
                media_type="image",
                url=f"https://placeholder.example/image?q={quote(query)}&n={i}",
                license="stub",
            )
            for i in range(count)
        ]
