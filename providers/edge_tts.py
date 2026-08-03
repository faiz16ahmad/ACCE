"""Edge TTS — real narration with no API key.

Wraps the `edge-tts` package (Microsoft Edge neural voices) behind the frozen
`TTSProvider` contract. Imported lazily so an uninstalled optional extra
degrades to the stub rather than breaking imports. If the requested voice is
unknown or a call fails, the provider retries with the bundled default voice
before giving up — the TTS router catches the raised `ProviderUnavailableError`
and falls back, so a missing network/extra never fails a job.

The provider advertises its `TTSCapabilities` (languages, voices, output
suffix) so selection is data-driven; the router never special-cases it.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from .base import ProviderUnavailableError, TTSCapabilities, TTSProvider, TTSSynthesizeOptions, VoiceSpec

log = logging.getLogger(__name__)

DEFAULT_VOICE = "en-US-AriaNeural"

# Representative locales Edge can speak. Honest coverage for the packs we ship;
# future language packs rely on the router's capability filter, never a branch.
_EDGE_LANGUAGES = {"en", "hi", "bn", "ta", "te", "fr", "ja", "es", "de"}

# Language-appropriate fallback voice when the requested voice is unknown or
# belongs to another provider (e.g. a Sarvam speaker). Keeps Hindi narration
# Hindi when the primary provider is down.
_VOICE_FOR_LANGUAGE = {"hi": "hi-IN-MadhurNeural"}


class EdgeTTSProvider(TTSProvider):
    name = "edge"
    capabilities = TTSCapabilities(
        languages=set(_EDGE_LANGUAGES),
        voices=[
            VoiceSpec(id="en-US-AriaNeural", language="en", name="Aria", gender="female"),
            VoiceSpec(id="hi-IN-MadhurNeural", language="hi", name="Madhur", gender="male"),
            VoiceSpec(id="hi-IN-SwaraNeural", language="hi", name="Swara", gender="female"),
        ],
        deployment="edge",
        output_suffix="mp3",
    )

    def __init__(self, voice: str | None = None) -> None:
        self.voice = voice or DEFAULT_VOICE

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
        try:
            import edge_tts
        except ImportError as exc:  # optional extra not installed
            raise ProviderUnavailableError("edge-tts is not installed (pip install acce[tts])") from exc

        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        requested = voice or self.voice
        try:
            asyncio.run(self._synthesize(edge_tts, text, requested, out_path))
        except Exception as exc:  # noqa: BLE001 - retry once with a fallback voice
            fallback = _VOICE_FOR_LANGUAGE.get(language) or DEFAULT_VOICE
            log.warning("edge-tts failed with voice %r (%s); retrying with %r", requested, exc, fallback)
            try:
                out_path.unlink(missing_ok=True)
                asyncio.run(self._synthesize(edge_tts, text, fallback, out_path))
            except Exception as fallback_exc:  # noqa: BLE001 - surface as ProviderUnavailableError
                raise ProviderUnavailableError(f"edge-tts failed: {fallback_exc}") from fallback_exc
        return out_path

    @staticmethod
    async def _synthesize(edge_tts, text: str, voice: str, out_path: Path) -> None:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(out_path))
