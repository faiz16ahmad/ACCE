"""Thumbnail (poster) generation for the production stage.

Extracts a frame near the 40% mark of the rendered video with ffmpeg when a
real render happened; otherwise (stub renderer) falls back to copying the
first downloaded image asset as a poster. Returns `None` when neither exists —
the UI already tolerates a missing poster.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

_VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm"}


def make_thumbnail(
    out_path: Path,
    *,
    video_path: Path | None = None,
    duration: float = 0.0,
    fallback_image: Path | None = None,
    ffmpeg_path: str | None = None,
) -> Path | None:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if video_path is not None and Path(video_path).suffix.lower() in _VIDEO_SUFFIXES:
        seek = max(0.0, duration * 0.4)
        cmd = [
            ffmpeg_path or "ffmpeg",
            "-y",
            "-ss",
            f"{seek:.2f}",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-vf",
            "scale=1280:-2",
            str(out_path),
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if proc.returncode == 0 and out_path.exists() and out_path.stat().st_size > 0:
                return out_path
            log.warning("thumbnail extraction failed (%s); using image fallback", proc.returncode)
        except (OSError, subprocess.SubprocessError) as exc:  # noqa: BLE001
            log.warning("thumbnail extraction error: %s; using image fallback", exc)

    if fallback_image is not None and Path(fallback_image).exists():
        shutil.copyfile(fallback_image, out_path)
        return out_path

    return None
