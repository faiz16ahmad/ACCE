"""Sarvam TTS provider tests (mocked HTTP — no network, no key needed).

Verifies the provider speaks the frozen TTS contract: correct request shape
(language_code from the pack, speaker, auth header), base64-WAV decode, and
error mapping to the recoverable ProviderError subclasses so the router falls
through to edge → stub instead of failing the job.
"""

from __future__ import annotations

import base64
import io
import json
import urllib.error
from pathlib import Path

import pytest

from config.languages import LanguageRegistry
from config.settings import TTSConfig
from providers.base import ProviderUnavailableError, QuotaExceededError, UnauthenticatedError
from providers.registry import get_provider
from providers.sarvam_tts import SarvamTTSProvider
from providers.stubs.tts import StubTTSProvider
from providers.tts_router import RoutingTTSProvider, build_tts_router

_HI = LanguageRegistry().profile("hi")


class _FakeResponse:
    def __init__(self, payload: bytes, content_type: str = "application/json") -> None:
        self.payload = payload
        self._headers = {"Content-Type": content_type}

    def read(self) -> bytes:
        return self.payload

    @property
    def headers(self):
        return self._headers

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _capture_urlopen(monkeypatch, captured: dict, payload: bytes, content_type: str = "application/json"):
    def fake(request, timeout):
        captured["request"] = request
        return _FakeResponse(payload, content_type)

    monkeypatch.setattr("providers.sarvam_tts.urllib.request.urlopen", fake)


def _json_payload(audio: bytes) -> bytes:
    return json.dumps({"request_id": "x", "audios": [base64.b64encode(audio).decode()]}).encode()


def _http_error(monkeypatch, status: int):
    def boom(request, timeout):
        raise urllib.error.HTTPError(request.full_url, status, "err", {}, io.BytesIO())

    monkeypatch.setattr("providers.sarvam_tts.urllib.request.urlopen", boom)


def test_registered_provider_constructs_and_suffix_is_wav():
    provider = get_provider("tts", "sarvam")
    assert isinstance(provider, SarvamTTSProvider)
    assert provider.output_suffix == "wav"
    assert provider.capabilities.requires_key is True


def test_router_selects_sarvam_with_key():
    router = build_tts_router(
        TTSConfig(provider="sarvam", api_keys={"sarvam": "k"}), _HI, voice="shubh"
    )
    assert router.output_suffix == "wav"
    assert [p.name for p in router.candidates] == ["sarvam", "edge", "stub"]


def test_builds_correct_request_and_decodes_wav(monkeypatch, tmp_path):
    wav = b"RIFF fake wav bytes"
    captured: dict = {}
    _capture_urlopen(monkeypatch, captured, _json_payload(wav))

    provider = SarvamTTSProvider()
    out = provider.synthesize("नमस्ते", voice="shubh", language="hi", api_key="k", out_path=tmp_path / "n.wav")

    req = captured["request"]
    assert req.full_url == "https://api.sarvam.ai/text-to-speech"
    assert req.get_method() == "POST"
    # urllib capitalizes header names on add; get_header is case-sensitive.
    assert req.headers.get("Api-subscription-key") == "k"
    body = json.loads(req.data.decode())
    assert body == {"text": "नमस्ते", "language_code": "hi-IN", "speaker": "shubh", "model": "bulbul:v3"}
    assert out.read_bytes() == wav


def test_speaker_override_from_voice(monkeypatch, tmp_path):
    captured: dict = {}
    _capture_urlopen(monkeypatch, captured, _json_payload(b"wav"))
    provider = SarvamTTSProvider()
    provider.synthesize("x", voice="ishita", language="hi", api_key="k", out_path=tmp_path / "n.wav")
    assert json.loads(captured["request"].data)["speaker"] == "ishita"


def test_foreign_voice_maps_to_default_speaker(monkeypatch, tmp_path):
    captured: dict = {}
    _capture_urlopen(monkeypatch, captured, _json_payload(b"wav"))
    provider = SarvamTTSProvider()
    # An Edge voice id passed through from the narrator → Sarvam uses its default.
    provider.synthesize("x", voice="hi-IN-MadhurNeural", language="hi", api_key="k", out_path=tmp_path / "n.wav")
    assert json.loads(captured["request"].data)["speaker"] == "shubh"


def test_missing_key_raises_unauthenticated(tmp_path):
    provider = SarvamTTSProvider()
    with pytest.raises(UnauthenticatedError):
        provider.synthesize("x", language="hi", api_key=None, out_path=tmp_path / "n.wav")


def test_unsupported_language_raises_unavailable(tmp_path):
    provider = SarvamTTSProvider()
    with pytest.raises(ProviderUnavailableError):
        provider.synthesize("x", language="xx", api_key="k", out_path=tmp_path / "n.wav")


@pytest.mark.parametrize("status,expected", [(401, UnauthenticatedError), (403, UnauthenticatedError), (429, QuotaExceededError), (500, ProviderUnavailableError)])
def test_http_errors_map_to_recoverable(monkeypatch, tmp_path, status, expected):
    _http_error(monkeypatch, status)
    provider = SarvamTTSProvider()
    with pytest.raises(expected):
        provider.synthesize("x", language="hi", api_key="k", out_path=tmp_path / "n.wav")


def test_network_error_raises_unavailable(monkeypatch, tmp_path):
    def boom(request, timeout):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("providers.sarvam_tts.urllib.request.urlopen", boom)
    with pytest.raises(ProviderUnavailableError):
        SarvamTTSProvider().synthesize("x", language="hi", api_key="k", out_path=tmp_path / "n.wav")


def test_router_falls_back_to_stub_when_sarvam_down(monkeypatch, tmp_path):
    def boom(request, timeout):
        raise urllib.error.URLError("down")

    monkeypatch.setattr("providers.sarvam_tts.urllib.request.urlopen", boom)
    router = RoutingTTSProvider(
        [SarvamTTSProvider(), StubTTSProvider()],
        voice="shubh",
        api_keys={"sarvam": "k"},
        language="hi",
    )
    out = router.synthesize("नमस्ते", out_path=tmp_path / "n.txt")
    assert out.read_text(encoding="utf-8").startswith("[stub-tts]")
    assert router.last_used_name == "stub"


def test_router_skips_sarvam_when_no_key():
    router = build_tts_router(TTSConfig(provider="sarvam"), _HI, voice="shubh")
    # No key → sarvam unusable → the suffix reflects the next usable candidate (edge).
    assert router.output_suffix == "mp3"
