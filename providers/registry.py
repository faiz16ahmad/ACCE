"""Provider resolution.

`get_provider(kind, name)` returns a fresh instance from the registered
implementations. Names that are real integrations but not yet implemented
raise a clear error pointing at the milestone that owns them.
"""

from __future__ import annotations

from .base import LLMProvider, MusicProvider, Provider, TTSProvider
from .gemini import GeminiProvider
from .pexels import PexelsImageProvider, PexelsVideoProvider
from .pixabay import PixabayImageProvider, PixabayVideoProvider
from .stubs.image import StubImageProvider
from .stubs.llm import StubLLMProvider
from .stubs.music import StubMusicProvider
from .stubs.tts import StubTTSProvider
from .stubs.video import StubVideoProvider
from .wikimedia import WikimediaImageProvider, WikimediaVideoProvider

_LLMS: dict[str, type[LLMProvider]] = {"stub": StubLLMProvider, "gemini": GeminiProvider}
_IMAGES = {
    "stub": StubImageProvider,
    "pexels": PexelsImageProvider,
    "pixabay": PixabayImageProvider,
    "wikimedia": WikimediaImageProvider,
}
_VIDEOS = {
    "stub": StubVideoProvider,
    "pexels": PexelsVideoProvider,
    "pixabay": PixabayVideoProvider,
    "wikimedia": WikimediaVideoProvider,
}
_MUSIC: dict[str, type[MusicProvider]] = {"stub": StubMusicProvider}
_TTS: dict[str, type[TTSProvider]] = {"stub": StubTTSProvider}

_TABLES = {
    "llm": _LLMS,
    "image": _IMAGES,
    "video": _VIDEOS,
    "music": _MUSIC,
    "tts": _TTS,
}

# Real integrations planned for later milestones.
# LLM names: implementing the LLMProvider interface + registering here is all
# that's needed (OpenAI/Anthropic/GLM/DeepSeek/OpenRouter).
_UNIMPLEMENTED = {
    "openai": "implement providers/openai.py and register it",
    "anthropic": "implement providers/anthropic.py and register it",
    "glm": "implement providers/glm.py and register it",
    "deepseek": "implement providers/deepseek.py and register it",
    "openrouter": "implement providers/openrouter.py and register it",
}


class ProviderNotImplementedError(NotImplementedError):
    def __init__(self, kind: str, name: str, hint: str) -> None:
        super().__init__(f"{kind} provider {name!r} is not implemented in V1 ({hint}). "
                         "Set the matching ACCE_* setting to 'stub', or implement it.")
        self.kind = kind
        self.name = name


def get_provider(kind: str, name: str, **config: object) -> Provider:
    table = _TABLES.get(kind)
    if table is None:
        raise ValueError(f"unknown provider kind: {kind!r}")
    if name in table:
        return table[name](**config)
    raise ProviderNotImplementedError(kind, name, _UNIMPLEMENTED.get(name, "not yet implemented"))
