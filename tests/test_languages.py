"""Language architecture tests (frozen): packs, Locale/Narrator resolution,
profile-driven tokenizer, and the TTS capability router."""

from __future__ import annotations

from config.languages import LanguageProfile, LanguageRegistry
from config.settings import Settings, TTSConfig
from core.models import JobStatus, Locale, Narrator, UserInput
from core.stages import Stage
from memory.store import ArtifactStore
from modules import build_orchestrator
from modules.script.metrics import MetricsProfile, compute_metrics, count_sentences, count_words
from providers.base import ProviderUnavailableError, TTSCapabilities
from providers.stubs.tts import StubTTSProvider
from providers.tts_router import RoutingTTSProvider, build_tts_router

_HINDI_TEXT = "नमस्ते दुनिया। यह एक परीक्षण है!"


# ── registry + packs --------------------------------------------------------


def test_registry_loads_en_and_hi():
    codes = {p.code for p in LanguageRegistry().languages()}
    assert {"en", "hi"} <= codes


def test_hi_profile_fields():
    hi = LanguageRegistry().profile("hi")
    assert hi.native_name == "हिन्दी"
    assert hi.script == "devanagari"
    assert "।" in hi.punctuation
    assert hi.readability == "none"
    assert hi.tts_preference[0] == "sarvam"  # Indic TTS is primary for Hindi
    assert hi.tts_preference[-1] == "stub"
    assert hi.default_voice == "shubh"  # Sarvam speaker
    assert hi.retrieval_language == "en"  # visuals stay English (§4)


def test_unknown_language_raises():
    import pytest

    with pytest.raises(ValueError):
        LanguageRegistry().profile("xx")


def test_resolve_hi_locale():
    locale = LanguageRegistry().resolve("hi")
    assert isinstance(locale, Locale)
    assert locale.language == "hi"
    assert locale.narration_language == "hi"
    assert locale.subtitle_language == "hi"
    assert locale.retrieval_language == "en"


def test_default_narrator_hi_voice():
    narrator = LanguageRegistry().default_narrator("hi")
    assert isinstance(narrator, Narrator)
    # hi is sarvam-primary now — the default voice is a Sarvam speaker.
    assert narrator.voice_id == "shubh"


def test_locale_defaults_to_english():
    assert Locale().language == "en"
    assert Narrator().voice_id is None


# ── profile-driven tokenizer (§3) --------------------------------------------


def test_devanagari_word_count_not_zero():
    # The old English regex would report 0 words for Devanagari text.
    assert count_words(_HINDI_TEXT, "devanagari") > 0


def test_hindi_sentence_split_on_danda():
    assert count_sentences("एक वाक्य। दूसरा वाक्य।", ("।",)) == 2
    # Without the danda in the terminator set, it is one sentence.
    assert count_sentences("एक वाक्य। दूसरा वाक्य।") == 1


def test_compute_metrics_hi_has_no_readability():
    hi = MetricsProfile(script="devanagari", punctuation=("।",), readability="none", words_per_minute=140)
    m = compute_metrics(_HINDI_TEXT, None, 140, hi)
    assert m.readability is None
    assert m.word_count > 0
    assert m.estimated_duration > 0


def test_compute_metrics_en_default_preserves_readability():
    m = compute_metrics("The cat sat on the mat.", 60, 150)
    assert m.readability is not None
    assert m.readability.words == 6


# ── TTS capability router (§7) ----------------------------------------------


def test_router_output_suffix_stub_default():
    en = LanguageRegistry().profile("en")
    router = build_tts_router(TTSConfig(provider="stub"), en, voice=en.default_voice)
    assert isinstance(router, RoutingTTSProvider)
    assert router.output_suffix == "txt"  # stub first → txt, identical to V1


def test_router_output_suffix_edge_configured():
    en = LanguageRegistry().profile("en")
    router = build_tts_router(TTSConfig(provider="edge"), en, voice=en.default_voice)
    assert router.output_suffix == "mp3"


def test_router_falls_back_to_stub_on_recoverable_error(tmp_path):
    class _Flaky:
        name = "flaky"
        capabilities = TTSCapabilities()  # empty languages = usable for any

        def synthesize(self, text, *, voice=None, options=None, out_path, language=None, api_key=None):
            raise ProviderUnavailableError("boom")

    router = RoutingTTSProvider(
        [_Flaky()],
        voice="x",
        language="en",
    )
    out = router.synthesize("hello", out_path=tmp_path / "n.txt")
    assert out.read_text(encoding="utf-8").startswith("[stub-tts]")
    assert router.last_used_name == "stub"


def test_router_skips_unsupported_language_capability(tmp_path):
    # edge advertises en/hi only; for an unsupported language it is skipped
    # and the stub (any-language) produces the marker.
    profile = LanguageProfile(code="zz", native_name="Zulu", english_name="Zulu", tts_preference=["edge", "stub"])
    router = build_tts_router(TTSConfig(provider="auto"), profile)
    out = router.synthesize("hello", out_path=tmp_path / "n.txt")
    assert out.read_text(encoding="utf-8").startswith("[stub-tts]")
    assert router.last_used_name == "stub"


# ── integration: full stub pipeline in Hindi ---------------------------------


def test_stub_pipeline_runs_in_hindi(tmp_path):
    settings = Settings(_env_file=None)
    settings.paths.cache_dir = tmp_path / "cache"
    settings.paths.output_dir = tmp_path / "out"
    orch = build_orchestrator(settings)

    ctx = orch.run(
        UserInput(topic="Hello World", language="hi", duration=60),
        job_id="e2e-hi",
        store=ArtifactStore(tmp_path / "out" / "e2e-hi"),
    )

    assert ctx.status == JobStatus.SUCCEEDED
    assert ctx.locale.language == "hi"
    assert ctx.locale.narration_language == "hi"
    script = ctx.results[Stage.SCRIPT].output
    assert script.language == "hi"
    audio = ctx.results[Stage.AUDIO].output
    # hi's default Narrator is the Sarvam speaker now.
    assert audio.metadata.voice == "shubh"
    # Default stub provider → stub narration markers (.txt), never edge.
    assert audio.narration_path.suffix == ".txt"
