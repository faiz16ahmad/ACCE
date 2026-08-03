"""Provider interfaces.

Modules depend on these abstractions, never on concrete implementations.
V1 provides stub implementations behind them; real providers are added per
milestone without touching any module.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .models import MediaHit, MusicHit


class Provider(ABC):  # noqa: B024 - marker base; families add their own abstract methods
    name: str = "abstract"


class ProviderError(RuntimeError):
    """Provider-level failure (network, auth, malformed response)."""


class ProviderUnavailableError(ProviderError):
    """Transient/structural unavailability: network drop, 5xx, missing local model.

    The TTS router treats this as recoverable and tries the next candidate.
    """


class UnauthenticatedError(ProviderError):
    """Bad or missing API key / local-model license.

    Recoverable at the router: an unauthenticated candidate is skipped.
    """


class QuotaExceededError(ProviderError):
    """Rate limit / quota exhausted (e.g. HTTP 429, daily free-model cap).

    Recoverable at the router: a quota-limited candidate is skipped.
    """


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


class VoiceSpec(BaseModel):
    """A voice a TTS provider can render."""

    id: str  # e.g. "hi-IN-MadhurNeural"
    language: str  # e.g. "hi"
    name: str | None = None  # "Madhur" (UI label, future narrator picker)
    gender: str | None = None
    styles: list[str] = Field(default_factory=list)
    local: bool = False  # bundled / offline-capable voice


class TTSCapabilities(BaseModel):
    """What a TTS provider advertises — the router selects from this data.

    An empty `languages` set means "supports any language" (the stub: it writes
    a text marker regardless of language). Adding a capability is a descriptor
    change, never a contract change.
    """

    languages: set[str] = Field(default_factory=set)
    voices: list[VoiceSpec] = Field(default_factory=list)
    streaming: bool = False
    emotion_control: bool = False
    style_presets: list[str] = Field(default_factory=list)
    deployment: Literal["cloud", "local", "edge"] = "cloud"
    offline: bool = False
    requires_key: bool = False
    max_input_chars: int | None = None  # None = no hard limit
    output_suffix: str = "mp3"
    cost_tier: int = 0  # router tie-break when several providers qualify


class TTSSynthesizeOptions(BaseModel):
    """Per-call modulation. Providers that support it consume the fields;
    others ignore them harmlessly."""

    rate: float | None = None  # speaking-rate multiplier
    emotion: str | None = None  # style preset id, if emotion_control
    style: str | None = None


class TTSProvider(Provider):
    capabilities: TTSCapabilities = TTSCapabilities()

    @property
    def output_suffix(self) -> str:
        """What this provider writes (the router overrides with its choice)."""
        return self.capabilities.output_suffix

    @abstractmethod
    def synthesize(
        self,
        text: str,
        *,
        voice: str | None = None,
        options: TTSSynthesizeOptions | None = None,
        out_path: Path,
        language: str | None = None,
        api_key: str | None = None,
    ) -> Path:
        """Render narration for `text` to `out_path` and return it.

        `language` is the narration language code (pack code, e.g. "hi") for
        providers that need it in the request; `api_key` is that provider's
        credential from `TTSConfig.api_keys`. Both are per-call so providers
        stay stateless and pluggable. Providers that don't need them (edge,
        stub) ignore them.
        """
