"""TTS routing (frozen architecture §7).

`RoutingTTSProvider` is a `TTSProvider` facade: the pipeline sees one narrator
and never learns which engine produced the audio. Selection is data-driven —
the configured provider first (back-compat with `ACCE_TTS__PROVIDER`), then the
language pack's `tts_preference` — filtered by advertised capabilities and
availability, with graceful fallback to the stub (which "speaks" every
language, so a job never fails because every real TTS is down).

Plugins: any `TTSProvider` registered in `providers.registry` becomes a
candidate for any language whose pack lists it. No module, no branch.
"""

from __future__ import annotations

import logging
from pathlib import Path

from config.languages import LanguageProfile
from config.settings import TTSConfig

from .base import (
    ProviderError,
    ProviderUnavailableError,
    QuotaExceededError,
    TTSCapabilities,
    TTSProvider,
    TTSSynthesizeOptions,
    UnauthenticatedError,
)
from .registry import ProviderNotImplementedError, get_provider
from .stubs.tts import StubTTSProvider

log = logging.getLogger(__name__)

# The ONLY failure codes the router treats as recoverable. Anything else
# propagates to the pipeline's normal retry path unchanged.
_RECOVERABLE = (ProviderUnavailableError, UnauthenticatedError, QuotaExceededError)


class RoutingTTSProvider(TTSProvider):
    name = "router"

    def __init__(
        self,
        candidates: list[TTSProvider],
        *,
        voice: str | None = None,
        api_keys: dict[str, str] | None = None,
        language: str = "en",
    ) -> None:
        self.candidates = list(candidates)
        self.voice = voice
        self.api_keys = api_keys or {}
        self.language = language
        self.last_used_name: str | None = None  # observability; never a branch
        self.capabilities = self._union_capabilities()

    @property
    def output_suffix(self) -> str:
        for provider in self.candidates:
            if self._usable(provider):
                return provider.capabilities.output_suffix
        return StubTTSProvider.capabilities.output_suffix

    def synthesize(
        self,
        text: str,
        *,
        voice: str | None = None,
        options: TTSSynthesizeOptions | None = None,
        out_path: Path,
    ) -> Path:
        out_path = Path(out_path)
        resolved = voice or self.voice
        for provider in self.candidates:
            if not self._usable(provider):
                continue
            try:
                result = provider.synthesize(
                    text,
                    voice=resolved,
                    options=options,
                    out_path=out_path,
                    language=self.language,
                    api_key=self.api_keys.get(provider.name),
                )
                self.last_used_name = provider.name
                return result
            except _RECOVERABLE as exc:
                log.warning("tts fallback: %s unavailable for %r (%s)", provider.name, self.language, exc)
                out_path.unlink(missing_ok=True)
                continue
        # Nothing worked (or nothing was usable) — the stub always completes.
        stub = StubTTSProvider()
        stub.synthesize(text, voice=resolved, options=options, out_path=out_path)
        self.last_used_name = stub.name
        return out_path

    def _usable(self, provider: TTSProvider) -> bool:
        caps = provider.capabilities
        if caps.languages and self.language not in caps.languages:
            return False  # capability filter — empty set means "any language"
        if caps.requires_key and not self.api_keys.get(provider.name):
            log.debug("tts skip %s: no api key configured", provider.name)
            return False
        return True

    def _union_capabilities(self) -> TTSCapabilities:
        languages: set[str] = set()
        for provider in self.candidates:
            if not provider.capabilities.languages:
                return TTSCapabilities(languages=set(), output_suffix=self.output_suffix)
            languages |= provider.capabilities.languages
        return TTSCapabilities(languages=languages, output_suffix=self.output_suffix)


def build_tts_router(
    tts_config: TTSConfig,
    profile: LanguageProfile,
    *,
    voice: str | None = None,
) -> RoutingTTSProvider:
    """Ordered candidates: configured provider first, then the pack preference.

    `provider="auto"` (or the default `"stub"`) lets the pack drive selection;
    an explicit provider name keeps today's back-compat behavior while the voice
    still comes from the language/Narrator.
    """
    names: list[str] = []
    if tts_config.provider and tts_config.provider != "auto":
        names.append(tts_config.provider)
    for name in profile.tts_preference:
        if name not in names:
            names.append(name)

    candidates: list[TTSProvider] = []
    for name in names:
        try:
            candidates.append(get_provider("tts", name))
        except (ProviderNotImplementedError, ValueError) as exc:
            log.debug("tts candidate %r unavailable: %s", name, exc)

    return RoutingTTSProvider(
        candidates,
        voice=voice,
        api_keys=tts_config.api_keys,
        language=profile.code,
    )
