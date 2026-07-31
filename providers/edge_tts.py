"""Edge TTS — real narration with no API key.

Wraps the `edge-tts` package (Microsoft Edge neural voices) behind the frozen
`TTSProvider` contract. Imported lazily so an uninstalled optional extra
degrades to the stub rather than breaking imports. If the requested voice is
unknown or a call fails, the provider retries with the bundled default voice
before giving up — callers (the audio module) route a `ProviderError` back to
the stub fallback, so a missing network/extra never fails a job.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from .base import ProviderError, TTSProvider

log = logging.getLogger(__name__)

DEFAULT_VOICE = "en-US-AriaNeural"


class EdgeTTSProvider(TTSProvider):
    name = "edge"

    def __init__(self, voice: str | None = None) -> None:
        self.voice = voice or DEFAULT_VOICE

    def synthesize(self, text: str, *, voice: str | None = None, out_path: Path) -> Path:
        try:
            import edge_tts
        except ImportError as exc:  # optional extra not installed
            raise ProviderError("edge-tts is not installed (pip install acce[tts])") from exc

        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        requested = voice or self.voice
        try:
            asyncio.run(self._synthesize(edge_tts, text, requested, out_path))
        except Exception as exc:  # noqa: BLE001 - retry once with the default voice
            log.warning("edge-tts failed with voice %r (%s); retrying with %r", requested, exc, DEFAULT_VOICE)
            try:
                out_path.unlink(missing_ok=True)
                asyncio.run(self._synthesize(edge_tts, text, DEFAULT_VOICE, out_path))
            except Exception as fallback_exc:  # noqa: BLE001 - surface as ProviderError
                raise ProviderError(f"edge-tts failed: {fallback_exc}") from fallback_exc
        return out_path

    @staticmethod
    async def _synthesize(edge_tts, text: str, voice: str, out_path: Path) -> None:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(out_path))
