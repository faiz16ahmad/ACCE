"""Audio module tests (milestone 6).

Full pipeline (narration -> music -> mix plan -> mix -> subtitles ->
AudioOutput), style-driven music selection, chain priority/fallback, the
no-music narration-only path, and engine-independent sentence subtitles with
stable cue ids. No real providers or network.
"""

from __future__ import annotations

import json

import pytest

from config.settings import AudioConfig
from core.stages import Stage
from memory.cache import DiskCache
from modules.audio.default import DefaultAudioModule
from modules.audio.engine import StubAudioEngine
from modules.audio.subtitles import build_cues, cues_to_srt, split_sentences
from modules.production.srt import parse_srt
from providers.base import MusicProvider
from providers.local_music import LocalMusicProvider
from providers.models import MusicHit
from providers.music_chain import MusicChain, build_music_chain
from providers.stubs.tts import StubTTSProvider


class FakeMusicProvider(MusicProvider):
    name = "fake"

    def __init__(self, hits: list[MusicHit] | None = None, error: Exception | None = None) -> None:
        self.hits = hits or []
        self.error = error
        self.queries: list[str] = []

    def search(self, query: str, *, count: int = 1) -> list[MusicHit]:
        self.queries.append(query)
        if self.error is not None:
            raise self.error
        return self.hits[:count]


def _hit(provider: str = "fake", title: str = "track") -> MusicHit:
    return MusicHit(provider=provider, title=title, url="https://music.example/track.mp3", duration=30.0)


def _script(style: str):
    from modules.script.schemas import ScriptOutput

    return ScriptOutput(hook="H", body=["B"], ending="E", style=style)


def _module(music: MusicChain | None = None, *, config: AudioConfig | None = None, cache=None):
    return DefaultAudioModule(StubTTSProvider(), music or MusicChain([]), StubAudioEngine(), cache, config=config)


# -- full pipeline ------------------------------------------------------------


def test_full_audio_output(make_ctx, scenes, script, tmp_path):
    ctx = make_ctx(**{Stage.SCRIPT: script, Stage.SCENES: scenes})
    result = _module(cache=DiskCache(tmp_path / "cache")).run(ctx)

    out = result.output
    assert out.narration_path is not None and out.narration_path.exists()
    assert out.mixed_audio_path is not None and out.mixed_audio_path.exists()
    assert out.subtitle_path is not None and out.subtitle_path.exists()
    assert out.duration > 0
    assert out.metadata.duration == out.duration
    assert out.metadata.cue_count == len(out.cues)
    assert out.master_path == out.mixed_audio_path
    assert any(t.kind == "narration" for t in out.tracks)
    assert ctx.store.exists(Stage.AUDIO, "audio.json")


def test_style_drives_music_query(make_ctx, scenes, tmp_path):
    ctx = make_ctx(**{Stage.SCRIPT: _script("storytelling"), Stage.SCENES: scenes})
    fake = FakeMusicProvider(hits=[_hit()])
    result = _module(MusicChain([fake])).run(ctx)

    assert fake.queries and "cinematic" in fake.queries[0]
    assert result.output.metadata.style_genre == "cinematic"
    assert result.output.metadata.music_provider == "fake"
    assert result.output.metadata.music_title == "track"
    assert result.output.music_path is None  # hit has no local file


def test_no_music_narration_only(make_ctx, scenes, tmp_path):
    ctx = make_ctx(**{Stage.SCENES: scenes})
    out = _module().run(ctx).output
    assert out.metadata.music_provider is None
    assert not any(t.kind == "music" for t in out.tracks)
    assert out.duration > 0


def test_mix_plan_music_volume_and_fades(make_ctx, scenes, tmp_path):
    ctx = make_ctx(**{Stage.SCENES: scenes})
    fake = FakeMusicProvider(hits=[_hit()])
    config = AudioConfig(music_volume=0.25, music_fade=1.5, narration_fade=0.1)
    _module(MusicChain([fake]), config=config).run(ctx)

    plan = json.loads(ctx.store.resolve(Stage.AUDIO, "mix_plan.json").read_text(encoding="utf-8"))
    music = next(segment for segment in plan["segments"] if segment["kind"] == "music")
    narration = next(segment for segment in plan["segments"] if segment["kind"] == "narration")
    assert music["volume"] == 0.25
    assert music["fade_in"] == 1.5 and music["fade_out"] == 1.5
    assert narration["fade_in"] == 0.1


# -- music chain --------------------------------------------------------------


def test_music_chain_priority_and_fallback():
    empty = FakeMusicProvider(hits=[])
    good = FakeMusicProvider(hits=[_hit("good")])
    chain = MusicChain([empty, good])

    hits = chain.search("calm ambient", count=1)
    assert hits and hits[0].provider == "good"
    assert len(empty.queries) == 1 and len(good.queries) == 1


def test_music_chain_skips_failing_provider():
    broken = FakeMusicProvider(error=RuntimeError("boom"))
    good = FakeMusicProvider(hits=[_hit("good")])
    chain = MusicChain([broken, good])

    assert chain.search("x")[0].provider == "good"


def test_build_music_chain_stub_default():
    chain = build_music_chain(["stub"])
    hits = chain.search("calm ambient", count=1)
    assert hits and hits[0].provider == "stub"


def test_local_music_provider(tmp_path):
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    (music_dir / "calm_ambient.mp3").write_bytes(b"x")
    (music_dir / "other.wav").write_bytes(b"y")

    provider = LocalMusicProvider(local_dir=str(music_dir))
    hits = provider.search("calm ambient", count=1)
    assert hits and hits[0].title == "calm_ambient" and hits[0].local_path is not None
    assert len(provider.search("no overlap", count=5)) == 2  # all files when nothing matches
    assert LocalMusicProvider(local_dir=str(tmp_path / "missing")).search("anything") == []


# -- subtitles (engine-independent) -------------------------------------------


def test_subtitles_sentence_based_with_stable_cue_ids(make_ctx, scenes, tmp_path):
    ctx = make_ctx(**{Stage.SCENES: scenes})
    out = _module().run(ctx).output

    cues = out.cues
    assert cues
    assert [c.cue_id for c in cues] == [f"cue_{i:04d}" for i in range(1, len(cues) + 1)]
    for previous, current in zip(cues, cues[1:], strict=False):
        assert previous.end <= current.start  # sequential, non-overlapping

    parsed = parse_srt(out.subtitle_path)
    assert len(parsed) == len(cues)
    assert parsed[0].text == cues[0].text


def test_split_sentences():
    assert split_sentences("One. Two! Three?") == ["One.", "Two!", "Three?"]
    assert split_sentences("No punctuation here") == ["No punctuation here"]
    assert split_sentences("") == []


def test_build_cues_from_scene_timing(scenes):
    cues = build_cues(scenes)
    assert len(cues) == 2  # one sentence per scene in the fixture
    assert cues[1].end == pytest.approx(40.0)  # 2 scenes x 20s back-to-back
    assert cues_to_srt(cues).count("\n\n") == len(cues) - 1
