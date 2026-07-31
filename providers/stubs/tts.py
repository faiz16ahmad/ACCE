from pathlib import Path

from ..base import TTSProvider


class StubTTSProvider(TTSProvider):
    """Writes a text marker instead of audio — real synthesis needs a TTS
    provider + ffmpeg, both outside V1 scope."""

    name = "stub"

    def synthesize(self, text: str, *, voice: str | None = None, out_path: Path) -> Path:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(f"[stub-tts] voice={voice or 'default'} :: {text}", encoding="utf-8")
        return out_path
