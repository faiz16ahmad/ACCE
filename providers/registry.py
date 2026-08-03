"""Provider resolution.

`get_provider(kind, name)` returns a fresh instance from the registered
implementations. Names that are real integrations but not yet implemented
raise a clear error pointing at the milestone that owns them.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .base import LLMProvider, MusicProvider, Provider, ProviderError, TTSProvider, TTSSynthesizeOptions
from .edge_tts import EdgeTTSProvider
from .gemini import GeminiProvider
from .openrouter import OpenRouterProvider
from .local_music import LocalMusicProvider
from .pexels import PexelsImageProvider, PexelsVideoProvider
from .pixabay import PixabayImageProvider, PixabayMusicProvider, PixabayVideoProvider
from .sarvam_tts import SarvamTTSProvider
from .stubs.image import StubImageProvider
from .stubs.llm import StubLLMProvider
from .stubs.music import StubMusicProvider
from .stubs.tts import StubTTSProvider
from .stubs.video import StubVideoProvider
from .wikimedia import WikimediaImageProvider, WikimediaVideoProvider

log = logging.getLogger(__name__)

_LLMS: dict[str, type[LLMProvider]] = {"stub": StubLLMProvider, "gemini": GeminiProvider, "openrouter": OpenRouterProvider}
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
_MUSIC: dict[str, type[MusicProvider]] = {
    "stub": StubMusicProvider,
    "pixabay": PixabayMusicProvider,
    "local": LocalMusicProvider,
}
_TTS: dict[str, type[TTSProvider]] = {
    "stub": StubTTSProvider,
    "edge": EdgeTTSProvider,
    "sarvam": SarvamTTSProvider,
}


class FallbackTTSProvider(TTSProvider):
    """Edge TTS with automatic stub narration fallback.

    Represents the `edge` experience (`name="edge"`): real audio when Edge
    works, StubTTS markers when the extra is missing or a call fails. Callers
    never branch on provider, so a degraded run still completes like the
    key-free stub demo.
    """

    name = "edge"
    capabilities = EdgeTTSProvider.capabilities

    def __init__(self, primary: TTSProvider, fallback: TTSProvider) -> None:
        self.primary = primary
        self.fallback = fallback

    def synthesize(
        self,
        text: str,
        *,
        voice: str | None = None,
        options: TTSSynthesizeOptions | None = None,
        out_path: Path,
    ) -> Path:
        try:
            return self.primary.synthesize(text, voice=voice, options=options, out_path=out_path)
        except ProviderError as exc:
            log.warning("edge-tts unavailable (%s); falling back to stub narration", exc)
            return self.fallback.synthesize(text, voice=voice, options=options, out_path=out_path)

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
    if name not in table:
        raise ProviderNotImplementedError(kind, name, _UNIMPLEMENTED.get(name, "not yet implemented"))
    # Edge TTS: optional extra — any failure degrades to StubTTS automatically.
    if kind == "tts" and name == "edge":
        voice = config.pop("voice", None)
        return FallbackTTSProvider(EdgeTTSProvider(voice=voice), StubTTSProvider())
    return table[name](**config)
