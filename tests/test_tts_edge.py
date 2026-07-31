"""Milestone 10: EdgeTTS provider + automatic stub fallback tests."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from providers.edge_tts import DEFAULT_VOICE, EdgeTTSProvider
from providers.registry import FallbackTTSProvider, get_provider


def _patch_edge_tts(monkeypatch, module) -> None:
    """Make `import edge_tts` resolve to `module` (or raise if None)."""
    monkeypatch.setitem(sys.modules, "edge_tts", module)


def test_registry_wraps_edge_with_stub_fallback():
    provider = get_provider("tts", "edge")
    assert isinstance(provider, FallbackTTSProvider)
    assert provider.name == "edge"


def test_missing_extra_degrades_to_stub(monkeypatch, tmp_path):
    _patch_edge_tts(monkeypatch, None)  # edge-tts "not installed"
    provider = get_provider("tts", "edge")
    out = provider.synthesize("hello world", voice=DEFAULT_VOICE, out_path=tmp_path / "n.mp3")
    assert out.exists()
    assert "[stub-tts]" in out.read_text(encoding="utf-8")


def test_edge_success_writes_audio(monkeypatch, tmp_path):
    class FakeCommunicate:
        def __init__(self, text: str, voice: str) -> None:
            self.text = text
            self.voice = voice

        async def save(self, path: str) -> None:
            Path(path).write_bytes(b"ID3fake-mp3")

    _patch_edge_tts(monkeypatch, SimpleNamespace(Communicate=FakeCommunicate))
    out = EdgeTTSProvider().synthesize("hi", out_path=tmp_path / "n.mp3")
    assert out.read_bytes() == b"ID3fake-mp3"


def test_unknown_voice_retries_with_default(monkeypatch, tmp_path):
    class FakeCommunicate:
        def __init__(self, text: str, voice: str) -> None:
            if voice != DEFAULT_VOICE:
                raise ValueError(f"unknown voice: {voice}")

        async def save(self, path: str) -> None:
            Path(path).write_bytes(b"ID3-default")

    _patch_edge_tts(monkeypatch, SimpleNamespace(Communicate=FakeCommunicate))
    out = EdgeTTSProvider().synthesize("hi", voice="en-US-Garbage", out_path=tmp_path / "n.mp3")
    assert out.read_bytes() == b"ID3-default"


def test_primary_failure_falls_back_to_stub(monkeypatch, tmp_path):
    class FailingCommunicate:
        def __init__(self, text: str, voice: str) -> None:
            raise RuntimeError("network down")

        async def save(self, path: str) -> None:  # pragma: no cover
            pass

    _patch_edge_tts(monkeypatch, SimpleNamespace(Communicate=FailingCommunicate))
    provider = get_provider("tts", "edge")
    out = provider.synthesize("hi", voice=DEFAULT_VOICE, out_path=tmp_path / "n.mp3")
    assert "[stub-tts]" in out.read_text(encoding="utf-8")
