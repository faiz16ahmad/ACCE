"""Milestone 10: thumbnail/poster generation tests."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

from modules.production.thumbnail import make_thumbnail


def test_image_fallback_copies_asset(tmp_path):
    img = tmp_path / "asset.jpg"
    img.write_bytes(b"JPEGDATA")
    out = make_thumbnail(tmp_path / "thumb.jpg", fallback_image=img)
    assert out is not None
    assert out.read_bytes() == b"JPEGDATA"


def test_video_extract_success(tmp_path, monkeypatch):
    video = tmp_path / "final_video.mp4"
    video.write_bytes(b"mp4")

    def fake_run(cmd, **kwargs):
        out = next(c for c in cmd if c.endswith(".jpg"))
        Path(out).write_bytes(b"THUMB")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    out = make_thumbnail(tmp_path / "thumb.jpg", video_path=video, duration=60.0)
    assert out is not None
    assert out.read_bytes() == b"THUMB"


def test_video_failure_falls_back_to_image(tmp_path, monkeypatch):
    video = tmp_path / "final_video.mp4"
    video.write_bytes(b"mp4")
    img = tmp_path / "asset.jpg"
    img.write_bytes(b"IMG")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=1))
    out = make_thumbnail(tmp_path / "thumb.jpg", video_path=video, fallback_image=img)
    assert out is not None
    assert out.read_bytes() == b"IMG"


def test_nothing_available_returns_none(tmp_path):
    assert make_thumbnail(tmp_path / "thumb.jpg") is None
