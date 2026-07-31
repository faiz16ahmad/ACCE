"""Media retrieval tests (milestone 5).

Chain ranking + satisfactory stop, per-provider caching, provider fallback and
failure tolerance, placeholder generation, candidate persistence, asset ids,
and the separate download step. No real providers or network beyond a local
test HTTP server.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from config.settings import MediaConfig
from core.stages import Stage
from memory.cache import DiskCache
from modules.media.default import DefaultMediaModule, refine_query
from providers.base import ProviderError
from providers.download import download_asset
from providers.media_chain import MediaChain
from providers.models import MediaHit
from providers.ranking import is_satisfactory, rank_hit, rank_hits


def _hit(name: str, query: str, **over: object) -> MediaHit:
    """A hit that comfortably clears the satisfaction threshold."""
    defaults = {
        "provider": name,
        "media_type": "image",
        "url": f"https://cdn.example/{name}.jpg",
        "license": "royalty-free",
        "width": 1920,
        "height": 1080,
        "title": f"stock image for {query}",
    }
    defaults.update(over)
    return MediaHit(**defaults)


class RecordingProvider:
    """Duck-typed Image/VideoProvider: returns scripted hits or raises."""

    def __init__(self, name: str, hits: list[MediaHit] | None = None, error: Exception | None = None) -> None:
        self.name = name
        self.hits = hits or []
        self.error = error
        self.calls: list[str] = []

    def search(self, query: str, *, count: int = 1) -> list[MediaHit]:
        self.calls.append(query)
        if self.error is not None:
            raise self.error
        return self.hits[:count]


def make_chain(cache: DiskCache, providers: list, media_type: str = "image") -> MediaChain:
    images = providers if media_type == "image" else []
    videos = providers if media_type == "video" else []
    return MediaChain(images, videos, cache)


# -- chain: cache / fallback / failure / ranking ------------------------------


def test_chain_cache_hit_serves_second_search(tmp_path):
    cache = DiskCache(tmp_path / "cache")
    provider = RecordingProvider("p", hits=[_hit("p", "neural")])
    chain = make_chain(cache, [provider])

    first = chain.best("neural", media_type="image")
    second = chain.best("neural", media_type="image")

    assert first and second
    assert second[0].url == first[0].url
    assert len(provider.calls) == 1  # second search served from cache


def test_chain_cache_miss_calls_provider(tmp_path):
    cache = DiskCache(tmp_path / "cache")
    provider = RecordingProvider("p", hits=[_hit("p", "a")])
    chain = make_chain(cache, [provider])

    assert chain.best("a", media_type="image")
    assert len(provider.calls) == 1


def test_chain_provider_fallback_when_top_not_satisfactory(tmp_path):
    cache = DiskCache(tmp_path / "cache")
    poor = RecordingProvider("poor", hits=[MediaHit(provider="poor", media_type="image", url="u", license="unknown")])
    good = RecordingProvider("good", hits=[_hit("good", "q")])
    chain = make_chain(cache, [poor, good])

    best = chain.best("q", media_type="image")
    assert best and best[0].provider == "good"
    assert len(poor.calls) == 1 and len(good.calls) == 1


def test_chain_provider_failure_is_tolerated(tmp_path):
    cache = DiskCache(tmp_path / "cache")
    broken = RecordingProvider("broken", error=ProviderError("boom"))
    good = RecordingProvider("good", hits=[_hit("good", "q")])
    chain = make_chain(cache, [broken, good])

    best = chain.best("q", media_type="image")
    assert best and best[0].provider == "good"
    assert len(good.calls) == 1


def test_chain_all_providers_fail_returns_empty(tmp_path):
    cache = DiskCache(tmp_path / "cache")
    broken = RecordingProvider("broken", error=ProviderError("boom"))
    chain = make_chain(cache, [broken])
    assert chain.best("q", media_type="image") == []


def test_rank_hits_orders_and_threshold():
    query = "neural network"
    good = _hit("a", query)
    poor = MediaHit(provider="a", media_type="image", url="u", license="unknown", width=320, height=240)

    ranked = rank_hits([poor, good], query, "image")
    assert ranked[0].url == good.url
    assert is_satisfactory(rank_hit(good, query, "image"), 0.6)
    assert not is_satisfactory(rank_hit(poor, query, "image"), 0.6)


# -- module: placeholder, candidates, asset ids -------------------------------


def test_module_placeholder_when_no_suitable_asset(make_ctx, scenes, tmp_path):
    ctx = make_ctx(**{Stage.SCENES: scenes})
    cache = DiskCache(tmp_path / "cache")
    poor = RecordingProvider("poor", hits=[MediaHit(provider="poor", media_type="video", url="u", license="unknown")])
    module = DefaultMediaModule(make_chain(cache, [poor], "video"), cache, config=MediaConfig(download=False))

    result = module.run(ctx)
    assert result.ok
    assert all(a.selected_provider == "placeholder" for a in result.output.assets)
    assert all(a.license == "placeholder" for a in result.output.assets)
    assert all(a.asset_url == "" and a.candidates == [] for a in result.output.assets)
    assert ctx.store.exists(Stage.MEDIA, "media_plan.json")


def test_module_persists_ranked_candidates_and_asset_ids(make_ctx, scenes, tmp_path):
    ctx = make_ctx(**{Stage.SCENES: scenes})
    cache = DiskCache(tmp_path / "cache")
    hits = [_hit("p", "q", width=1920, height=1080), _hit("p", "q", width=1280, height=720)]
    module = DefaultMediaModule(
        make_chain(cache, [RecordingProvider("p", hits)]), cache, config=MediaConfig(download=False)
    )

    result = module.run(ctx)
    for index, plan in enumerate(result.output.assets, start=1):
        assert plan.candidates  # full ranked list persisted
        assert plan.selected_provider == plan.candidates[0].provider
        assert plan.asset_url == plan.candidates[0].url
        assert plan.asset_type == plan.candidates[0].media_type
        assert plan.asset_id == f"asset_{index:04d}"
        assert plan.local_path is None  # download disabled
        assert plan.search_query  # query came from the scene keywords


def test_module_downloads_selected_asset(make_ctx, scenes, tmp_path, file_server):
    ctx = make_ctx(**{Stage.SCENES: scenes})
    cache = DiskCache(tmp_path / "cache")
    hit = _hit("p", "q", url=file_server, media_type="video", width=1920, height=1080)
    module = DefaultMediaModule(
        make_chain(cache, [RecordingProvider("p", [hit])], "video"), cache, config=MediaConfig()
    )

    result = module.run(ctx)
    plan = result.output.assets[0]
    assert plan.local_path is not None and plan.local_path.exists()
    assert plan.local_path.read_bytes() == b"fake-media-bytes"


def test_refine_query_strips_quotes_and_truncates():
    assert refine_query(["'quoted'", "phrase"]) == "quoted phrase"
    long_query = refine_query(["word"] * 60)
    assert len(long_query) <= 200


# -- download step (separate from ranking) ------------------------------------


class _FileHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - stdlib name
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.end_headers()
        self.wfile.write(b"fake-media-bytes")

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass


@pytest.fixture
def file_server():
    server = HTTPServer(("127.0.0.1", 0), _FileHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/asset.jpg"
    server.shutdown()
    thread.join()


def test_download_asset_caches_binary(tmp_path, file_server):
    cache_root = tmp_path / ".cache"
    dest1 = tmp_path / "out" / "scene_01.jpg"
    dest2 = tmp_path / "out" / "scene_02.jpg"

    assert download_asset(file_server, dest1, cache_root) == dest1
    assert dest1.read_bytes() == b"fake-media-bytes"
    assert download_asset(file_server, dest2, cache_root) == dest2  # copied from cache
    assert dest2.read_bytes() == b"fake-media-bytes"
    assert len(list((cache_root / "media_files").iterdir())) == 1


def test_download_asset_skips_placeholder_url(tmp_path):
    dest = tmp_path / "a.jpg"
    assert download_asset("https://placeholder.example/x.jpg", dest, tmp_path / ".cache") is None
    assert not dest.exists()
