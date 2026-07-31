"""Provider interfaces.

Modules depend on these abstractions, never on concrete implementations.
V1 provides stub implementations behind them; real providers are added per
milestone without touching any module.
"""

from abc import ABC, abstractmethod
from pathlib import Path

from .models import MediaHit, MusicHit


class Provider(ABC):  # noqa: B024 - marker base; families add their own abstract methods
    name: str = "abstract"


class LLMProvider(Provider):
    @abstractmethod
    def complete(self, prompt: str, *, system: str | None = None, **kwargs: object) -> str:
        """Return a completion for `prompt`."""


class ImageProvider(Provider):
    @abstractmethod
    def search(self, query: str, *, count: int = 1) -> list[MediaHit]:
        """Return image hits for `query`, most relevant first."""


class VideoProvider(Provider):
    @abstractmethod
    def search(self, query: str, *, count: int = 1) -> list[MediaHit]:
        """Return video hits for `query`, most relevant first."""


class MusicProvider(Provider):
    @abstractmethod
    def search(self, query: str, *, count: int = 1) -> list[MusicHit]:
        """Return royalty-free background music hits for `query`."""


class TTSProvider(Provider):
    @abstractmethod
    def synthesize(self, text: str, *, voice: str | None = None, out_path: Path) -> Path:
        """Render narration for `text` to `out_path` and return it."""
