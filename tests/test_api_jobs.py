"""Milestone 10: durable job summaries + thumbnail URL helpers."""

from __future__ import annotations

import json

from frontend.api.jobs import scan_job_dirs, thumbnail_url
from frontend.api.routes import _music_file, _music_info


def _write_meta(output_dir, job_id: str, status: str = "succeeded") -> None:
    directory = output_dir / job_id / "meta"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "job.json").write_text(
        f'{{"status": "{status}", "input": {{"topic": "T"}}}}', encoding="utf-8"
    )


def _make_thumbnail(output_dir, job_id: str) -> None:
    production = output_dir / job_id / "production"
    production.mkdir(parents=True, exist_ok=True)
    (production / "thumbnail.jpg").write_bytes(b"x")


def test_thumbnail_url_none_without_file(tmp_path):
    assert thumbnail_url(tmp_path, "job-x") is None


def test_thumbnail_url_when_production_made_one(tmp_path):
    _make_thumbnail(tmp_path, "job-x")
    assert thumbnail_url(tmp_path, "job-x") == "/artifacts/job-x/production/thumbnail.jpg"


def test_scan_job_dirs_includes_thumbnail(tmp_path):
    _write_meta(tmp_path, "job-a")
    _make_thumbnail(tmp_path, "job-a")
    entries = scan_job_dirs(tmp_path)
    assert entries[0]["job_id"] == "job-a"
    assert entries[0]["topic"] == "T"
    assert entries[0]["thumbnail"] == "/artifacts/job-a/production/thumbnail.jpg"


def test_scan_job_dirs_no_thumbnail_field_when_absent(tmp_path):
    _write_meta(tmp_path, "job-b")
    entries = scan_job_dirs(tmp_path)
    assert entries[0]["job_id"] == "job-b"
    assert "thumbnail" not in entries[0]


def _write_audio_meta(output_dir, job_id: str, *, music_path: str | None) -> None:
    audio = output_dir / job_id / "audio"
    audio.mkdir(parents=True, exist_ok=True)
    audio_json = {
        "music_path": music_path,
        "metadata": {"music_title": "calm_ambient_bed", "music_provider": "local"},
    }
    (audio / "audio.json").write_text(json.dumps(audio_json), encoding="utf-8")


def test_music_file_resolves_library_bed(tmp_path):
    bed = tmp_path.parent / "assets" / "music"
    bed.mkdir(parents=True, exist_ok=True)
    (bed / "calm_ambient_bed.wav").write_bytes(b"bed")
    _write_audio_meta(tmp_path, "job-m", music_path="assets/music/calm_ambient_bed.wav")
    assert _music_file("job-m", tmp_path) == (bed / "calm_ambient_bed.wav").resolve()


def test_music_file_none_without_audio_json(tmp_path):
    assert _music_file("job-x", tmp_path) is None


def test_music_file_none_when_no_music_selected(tmp_path):
    _write_audio_meta(tmp_path, "job-n", music_path=None)
    assert _music_file("job-n", tmp_path) is None


def test_music_info_metadata_and_stream_url(tmp_path):
    bed = tmp_path.parent / "assets" / "music"
    bed.mkdir(parents=True, exist_ok=True)
    (bed / "calm_ambient_bed.wav").write_bytes(b"bed")
    _write_audio_meta(tmp_path, "job-m", music_path="assets/music/calm_ambient_bed.wav")
    ranked = [{"asset": {"license": "royalty-free (local)", "bpm": None, "duration": 60.0}}]
    (tmp_path / "job-m" / "audio" / "music_assets.json").write_text(
        json.dumps(ranked), encoding="utf-8"
    )
    info = _music_info("job-m", tmp_path)
    assert info is not None
    assert info["title"] == "calm_ambient_bed"
    assert info["provider"] == "local"
    assert info["duration"] == 60.0
    assert info["url"] == "/api/jobs/job-m/music/stream"


def test_music_info_none_when_no_music(tmp_path):
    _write_audio_meta(tmp_path, "job-n", music_path=None)
    assert _music_info("job-n", tmp_path) is None
