"""Sarvam AI TTS — multilingual Indic narration (Bulbul).

Sarvam's REST endpoint returns base64-encoded audio (WAV by default) for a
language + speaker, authenticated with an `api-subscription-key` header. The
provider advertises its `TTSCapabilities` (11 Indic languages, `output_suffix`,
`requires_key`) so the frozen router treats it as data: it is a candidate for
any pack whose `tts_preference` lists `sarvam`, and it is skipped when the
key is missing or the language isn't covered.

Sarvam speakers (shubh / ishita / varun) are language-agnostic — the language
comes from the per-call `language` kwarg, not the voice. Failures are mapped to
the recoverable `ProviderError` subclasses so the router falls through to the
next candidate (edge → stub) instead of failing the job.
"""

from __future__ import annotations

import base64
import json
import logging
import urllib.error
import urllib.request
from pathlib import Path

from .base import (
    ProviderUnavailableError,
    QuotaExceededError,
    TTSCapabilities,
    TTSProvider,
    TTSSynthesizeOptions,
    UnauthenticatedError,
    VoiceSpec,
)

log = logging.getLogger(__name__)

BASE_URL = "https://api.sarvam.ai"
DEFAULT_MODEL = "bulbul:v3"
DEFAULT_SPEAKER = "shubh"
ENDPOINT = "/text-to-speech"

# Sarvam uses BCP-47-style language codes (hi-IN); our packs use language-only
# codes (hi). This mapping is the only place the two dialects meet.
_LANG_CODES = {
    "en": "en-IN",
    "hi": "hi-IN",
    "bn": "bn-IN",
    "ta": "ta-IN",
    "te": "te-IN",
    "kn": "kn-IN",
    "ml": "ml-IN",
    "mr": "mr-IN",
    "gu": "gu-IN",
    "pa": "pa-IN",
    "od": "od-IN",
}

# Known Sarvam speakers (Bulbul v3). A foreign voice (e.g. an Edge voice) is
# mapped to the default so the narrator pick never crashes the request.
_SPEAKERS = {"shubh", "ishita", "varun"}


class SarvamTTSProvider(TTSProvider):
    name = "sarvam"
    capabilities = TTSCapabilities(
        languages=set(_LANG_CODES),
        voices=[
            VoiceSpec(id="shubh", language="en", name="Shubh", gender="male"),
            VoiceSpec(id="ishita", language="en", name="Ishita", gender="female"),
            VoiceSpec(id="varun", language="en", name="Varun", gender="male"),
        ],
        deployment="cloud",
        requires_key=True,
        output_suffix="wav",
        max_input_chars=2500,
        cost_tier=2,
    )

    def __init__(
        self,
        voice: str | None = None,
        base_url: str = BASE_URL,
        model: str = DEFAULT_MODEL,
    ) -> None:
        self.voice = voice
        self.base_url = base_url.rstrip("/")
        self.model = model

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
        key = (api_key or "").strip()
        if not key:
            raise UnauthenticatedError("no Sarvam API key configured (ACCE_TTS__API_KEYS={\"sarvam\": ...})")

        lang_code = _LANG_CODES.get(language or "en")
        if lang_code is None:
            raise ProviderUnavailableError(f"sarvam does not support language {language!r}")

        speaker = voice or self.voice or DEFAULT_SPEAKER
        if speaker not in _SPEAKERS:
            log.info("sarvam: unknown speaker %r; using %r", speaker, DEFAULT_SPEAKER)
            speaker = DEFAULT_SPEAKER

        body = json.dumps(
            {"text": text, "language_code": lang_code, "speaker": speaker, "model": self.model}
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{ENDPOINT}",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "api-subscription-key": key,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as resp:
                content_type = resp.headers.get("Content-Type", "")
                payload = resp.read()
        except urllib.error.HTTPError as exc:
            raise self._http_error(exc) from exc
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise ProviderUnavailableError(f"sarvam connection failed: {exc}") from exc

        audio = _extract_audio(payload, content_type)
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(audio)
        return out_path

    @staticmethod
    def _http_error(exc: urllib.error.HTTPError) -> Exception:
        status = exc.code
        if status in (401, 403):
            return UnauthenticatedError(f"sarvam rejected the API key (HTTP {status})")
        if status == 429:
            return QuotaExceededError("sarvam rate limit / quota exceeded (HTTP 429)")
        if status >= 500:
            return ProviderUnavailableError(f"sarvam server error (HTTP {status})")
        return ProviderUnavailableError(f"sarvam request failed (HTTP {status}): {exc.reason}")


def _extract_audio(payload: bytes, content_type: str) -> bytes:
    """Sarvam returns base64 WAV in JSON `audios[]`; some surfaces return raw audio."""
    if "application/json" in content_type or payload.lstrip().startswith(b"{"):
        try:
            data = json.loads(payload.decode("utf-8"))
            audios = data.get("audios") or []
            if audios:
                return base64.b64decode(audios[0])
        except (ValueError, TypeError, KeyError) as exc:
            raise ProviderUnavailableError(f"sarvam returned an unparseable response: {exc}") from exc
    return payload  # raw audio body
