"""Director export — produce the final video from the frozen visuals + new audio.

The documentary's visuals are immutable, so export never re-encodes video:
`remux` copies the frozen `final_video.mp4`'s video stream byte-for-byte and
muxes the newly remixed master as the audio track (`-c:v copy -c:a aac`).
Preview and export are the same operation with different destinations (§6).

A full re-render fallback (`render_from_manifest`) exists for robustness /
future visual edits — it copies the original `RenderManifest`, swaps
`audio_path`, and runs the existing `FFmpegRenderer` unchanged.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from modules.production.renderer import FFmpegRenderer, RendererError
from modules.production.schemas import RenderManifest

from .library import probe_duration

log = logging.getLogger(__name__)


def remux(
    video_path: Path,
    master_path: Path,
    out_path: Path,
    *,
    ffmpeg_path: str = "ffmpeg",
) -> Path:
    """Mux the frozen video stream with a new audio master (video copied)."""
    video_path = Path(video_path)
    master_path = Path(master_path)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not video_path.is_file():
        raise RendererError(f"frozen video missing: {video_path}")
    if not master_path.is_file():
        raise RendererError(f"remixed master missing: {master_path}")
    cmd = [
        ffmpeg_path, "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(video_path),
        "-i", str(master_path),
        "-map", "0:v", "-map", "1:a",
        "-c:v", "copy", "-c:a", "aac",
        "-shortest",
        str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        raise RendererError(f"remux failed: {(proc.stderr or proc.stdout)[-400:]}")
    if not out_path.is_file():
        raise RendererError("remux produced no output")
    return out_path


def render_from_manifest(
    manifest: RenderManifest,
    audio_path: Path,
    out_path: Path,
    *,
    ffmpeg_path: str = "ffmpeg",
) -> Path:
    """Fallback: full re-render from a manifest copy with a swapped audio track.

    Used only when the video stream itself must change (future visual edits) —
    never for music-only exports.
    """
    clone = manifest.model_copy(deep=True)
    clone.audio_path = audio_path
    renderer = FFmpegRenderer(ffmpeg_path=ffmpeg_path)
    result = renderer.render(clone, out_path)
    return Path(result.video_path)


def export_duration(master_path: Path, ffmpeg_path: str = "ffmpeg") -> float:
    """Duration of the master (for the export record)."""
    return probe_duration(master_path, ffmpeg_path)
