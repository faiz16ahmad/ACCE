"""DiskCache behavior."""

from __future__ import annotations

from memory.cache import DiskCache


def test_missing_returns_none(tmp_path):
    cache = DiskCache(tmp_path)
    assert cache.get("media", "nope") is None
    assert not cache.has("media", "nope")


def test_set_get_roundtrip(tmp_path):
    cache = DiskCache(tmp_path)
    cache.set("media", "key", {"a": 1})
    assert cache.get("media", "key") == {"a": 1}


def test_overwrite(tmp_path):
    cache = DiskCache(tmp_path)
    cache.set("audio", "k", [1])
    cache.set("audio", "k", [2])
    assert cache.get("audio", "k") == [2]


def test_namespaces_are_isolated(tmp_path):
    cache = DiskCache(tmp_path)
    cache.set("media", "same", "image")
    cache.set("research", "same", "text")
    assert cache.get("media", "same") == "image"
    assert cache.get("research", "same") == "text"


def test_delete(tmp_path):
    cache = DiskCache(tmp_path)
    cache.set("media", "k", 1)
    cache.delete("media", "k")
    assert cache.get("media", "k") is None
