"""Milestone 10: durable job summaries + thumbnail URL helpers."""

from __future__ import annotations

from frontend.api.jobs import scan_job_dirs, thumbnail_url


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
