from pathlib import Path

from ..base import TTSCapabilities, TTSProvider, TTSSynthesizeOptions


class StubTTSProvider(TTSProvider):
    """Writes a text marker instead of audio — real synthesis needs a TTS
    provider + ffmpeg, both outside V1 scope.

    The stub "speaks" every language (it writes the text verbatim), so the
    key-free demo runs in any Locale — the router's last-resort fallback.
    """

    name = "stub"
    capabilities = TTSCapabilities(
        languages=set(),  # empty = supports any language
        deployment="local",
        offline=True,
        output_suffix="txt",
    )

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
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(f"[stub-tts] voice={voice or 'default'} :: {text}", encoding="utf-8")
        return out_path
