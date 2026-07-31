"""Real research pipeline + fetch layer tests (milestone 2).

Uses a fake LLM returning injectable JSON and a local HTTP server so no
external network or API keys are needed. The source of truth for
"verified" is the live fetch, so a 200 page marks a fact verified and a 404
does not.
"""

from __future__ import annotations

import http.server
import json
import threading

import pytest

from config.settings import ResearchConfig
from core.errors import StageRetryableError
from core.stages import Stage
from memory.cache import DiskCache
from modules.research.default import DefaultResearchModule, extract_json
from modules.research.fetch import SourceFetcher
from providers.base import LLMProvider


class FakeLLM(LLMProvider):
    name = "fake"

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls = 0
        self.model = "fake-model"

    def complete(self, prompt: str, *, system: str | None = None, **kwargs: object) -> str:
        self.calls += 1
        return self.responses.pop(0) if self.responses else "{}"


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - stdlib signature
        if self.path == "/ok":
            body = (
                b"<html><head><title>Test Source</title></head>"
                b"<body><p>Hello neural networks world.</p></body></html>"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args: object) -> None:  # silence request logging
        pass


@pytest.fixture
def source_server():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def _draft(base: str) -> dict:
    return {
        "topic": "Neural Networks",
        "summary": "A summary.",
        "facts": [
            {"content": "fact with a reachable source", "sources": [f"{base}/ok"], "confidence": 0.9},
            {"content": "fact with a broken source", "sources": [f"{base}/missing"], "confidence": 0.5},
        ],
        "sources": [
            {"url": f"{base}/ok", "title": "OK source"},
            {"url": f"{base}/missing", "title": "Missing source"},
        ],
        "angles": [{"title": "angle one", "description": "an angle"}],
        "entities": [{"name": "Neural Network", "kind": "concept"}],
        "chronology": [{"date": "2020", "title": "milestone event", "description": "desc", "sources": [f"{base}/ok"]}],
    }


# -- fetch layer --------------------------------------------------------------


def test_fetcher_extracts_title_and_excerpt(source_server):
    res = SourceFetcher(timeout=5).fetch(f"{source_server}/ok")
    assert res.ok is True
    assert res.http_status == 200
    assert res.title == "Test Source"
    assert "Hello neural networks world." in (res.excerpt or "")


def test_fetcher_reports_http_errors(source_server):
    res = SourceFetcher(timeout=5).fetch(f"{source_server}/nope")
    assert res.ok is False
    assert res.http_status == 404


def test_fetcher_retries_then_gives_up_on_unreachable():
    # Port 1 is almost always closed -> connection refused, fast.
    res = SourceFetcher(timeout=1, retries=1).fetch("http://127.0.0.1:1/")
    assert res.ok is False
    assert res.error


def test_fetcher_rejects_non_http_schemes():
    res = SourceFetcher().fetch("file:///etc/passwd")
    assert res.ok is False
    assert "unsupported scheme" in (res.error or "")


# -- JSON extraction ----------------------------------------------------------


def test_extract_json_handles_code_fences():
    assert extract_json("```json\n{\"a\": 1}\n```") == {"a": 1}


def test_extract_json_handles_surrounding_text():
    assert extract_json('Here you go: {"b": 2}. Hope that helps') == {"b": 2}


def test_extract_json_rejects_no_object():
    with pytest.raises(ValueError):
        extract_json("no json here")


def test_extract_json_rejects_malformed():
    with pytest.raises(ValueError):
        extract_json('{"a": }')


# -- research pipeline --------------------------------------------------------


def _module(tmp_path, llm, **overrides) -> DefaultResearchModule:
    defaults = {"fetch_timeout": 5, "refine": False}
    defaults.update(overrides)
    return DefaultResearchModule(llm, DiskCache(tmp_path / "cache"), config=ResearchConfig(**defaults))


def test_verified_and_unverified_facts(make_ctx, tmp_path, source_server):
    llm = FakeLLM([json.dumps(_draft(source_server))])
    ctx = make_ctx()
    result = _module(tmp_path, llm).run(ctx)

    assert result.ok
    out = result.output
    assert out.facts[0].verified is True
    assert out.facts[1].verified is False
    assert out.facts[1].verification_note

    by_url = {s.url: s for s in out.sources}
    ok = by_url[f"{source_server}/ok"]
    missing = by_url[f"{source_server}/missing"]
    # Curated draft title is preserved; the fetched excerpt is stamped in.
    assert ok.fetched is True and ok.http_status == 200
    assert ok.title == "OK source"
    assert ok.excerpt and "Hello neural networks world." in ok.excerpt
    assert missing.fetched is False and missing.http_status == 404

    assert out.angles[0].title == "angle one"
    assert out.entities[0].name == "Neural Network"
    assert out.chronology[0].title == "milestone event"
    assert out.metadata.fact_count == 2
    assert out.metadata.source_count == 2
    assert "1/2 facts verified" in out.metadata.verification_summary
    assert out.metadata.model == "fake-model"
    assert ctx.store.exists(Stage.RESEARCH, "research.json")


def test_drops_untraceable_fact(make_ctx, tmp_path, source_server):
    draft = _draft(source_server)
    draft["facts"] = [
        {"content": "no references at all", "sources": []},
        {"content": "traceable", "sources": [f"{source_server}/ok"]},
    ]
    out = _module(tmp_path, FakeLLM([json.dumps(draft)])).run(make_ctx()).output
    assert [f.content for f in out.facts] == ["traceable"]


def test_refine_applies_when_valid(make_ctx, tmp_path, source_server):
    draft = _draft(source_server)
    llm = FakeLLM(
        [
            json.dumps(draft),
            json.dumps({"facts": [{"content": "polished one", "verification_note": "clearer"},
                                  {"content": "polished two"}]}),
        ]
    )
    out = _module(tmp_path, llm, refine=True).run(make_ctx()).output
    assert out.facts[0].content == "polished one"
    assert out.facts[0].verification_note == "clearer"
    assert out.facts[1].content == "polished two"
    assert llm.calls == 2
    # Refine never changes the fetch-based verified flag.
    assert out.facts[0].verified is True


def test_refine_is_optional_and_failure_keeps_draft(make_ctx, tmp_path, source_server):
    draft = _draft(source_server)
    llm = FakeLLM([json.dumps(draft), "not valid json"])
    out = _module(tmp_path, llm, refine=True).run(make_ctx()).output
    assert out.facts[0].content.startswith("fact with")


def test_unparseable_draft_raises_retryable(make_ctx, tmp_path):
    llm = FakeLLM(["not json", "still not json"])
    with pytest.raises(StageRetryableError):
        _module(tmp_path, llm).run(make_ctx())


def test_cache_hit_returns_saved_output(make_ctx, tmp_path, source_server):
    cache = DiskCache(tmp_path / "cache")
    module = DefaultResearchModule(
        FakeLLM([json.dumps(_draft(source_server))]), cache, config=ResearchConfig(fetch_timeout=5)
    )
    ctx = make_ctx()
    first = module.run(ctx)
    llm2 = FakeLLM([])  # any call would blow up (empty responses)
    second = DefaultResearchModule(llm2, cache, config=ResearchConfig(fetch_timeout=5)).run(ctx)
    assert second.output == first.output
    assert llm2.calls == 0
