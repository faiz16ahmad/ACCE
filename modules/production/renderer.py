"""Renderer seam for the production stage.

Renderers consume ONLY a `RenderManifest` — never `ScenePlan` / `MediaPlan` /
`AudioOutput` — so backends are isolated and replaceable, and a render job is
replayable from its manifest. The stub renderer keeps the pipeline runnable
without FFmpeg; FFmpegRenderer builds and runs an ffmpeg command.

Instrumented: saves ffmpeg_command.txt, ffmpeg_stdout.log, ffmpeg_stderr.log
into the output directory for every render.
"""

from __future__ import annotations

import json
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path

from config.settings import ProductionConfig

from .ffmpeg import build_command
from .schemas import RenderManifest, RenderResult


class RendererError(RuntimeError):
    """A render backend failed."""


class Renderer(ABC):
    @abstractmethod
    def render(self, manifest: RenderManifest, out_path: Path) -> RenderResult:
        """Render `manifest` to `out_path`; return the result and a log."""


class StubRenderer(Renderer):
    name = "stub"

    def render(self, manifest: RenderManifest, out_path: Path) -> RenderResult:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            f"[stub-renderer] {len(manifest.timeline.clips)} clip(s) -> {out_path.name}",
            encoding="utf-8",
        )
        log_text = (
            f"stub render of {out_path.name} "
            f"({len(manifest.timeline.clips)} clips, {manifest.timeline.duration:.1f}s)"
        )
        return RenderResult(video_path=out_path, log=log_text)


class FFmpegRenderer(Renderer):
    name = "ffmpeg"

    def __init__(self, ffmpeg_path: str | None = None) -> None:
        self.ffmpeg_path = ffmpeg_path or "ffmpeg"

    def render(self, manifest: RenderManifest, out_path: Path) -> RenderResult:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        command = self._build_command(manifest, out_path)

        # --- INSTRUMENTATION: save the exact command ---
        diag_dir = out_path.parent
        cmd_file = diag_dir / "ffmpeg_command.txt"
        cmd_file.write_text(json.dumps(command, indent=2), encoding="utf-8")
        # Also save the manifest used to build this command
        (diag_dir / "render_manifest_during_render.json").write_text(
            manifest.model_dump_json(indent=2), encoding="utf-8"
        )

        log_text = self._run(command, diag_dir)
        return RenderResult(video_path=out_path, log=log_text)

    def _build_command(self, manifest: RenderManifest, out_path: Path) -> list[str]:
        return build_command(manifest, out_path, self.ffmpeg_path)

    def _run(self, command: list[str], diag_dir: Path) -> str:
        try:
            proc = subprocess.run(
                command, capture_output=True, text=True, timeout=600
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise RendererError(f"ffmpeg failed to start: {exc}") from exc

        # --- INSTRUMENTATION: save complete stdout and stderr ---
        (diag_dir / "ffmpeg_stdout.log").write_text(
            proc.stdout or "", encoding="utf-8"
        )
        (diag_dir / "ffmpeg_stderr.log").write_text(
            proc.stderr or "", encoding="utf-8"
        )

        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "")[-2000:]
            raise RendererError(f"ffmpeg exited {proc.returncode}: {tail}")
        return (proc.stderr or "")[-4000:]  # ffmpeg logs progress to stderr


def build_renderer(config: ProductionConfig) -> Renderer:
    if config.renderer == "stub":
        return StubRenderer()
    if config.renderer == "ffmpeg":
        return FFmpegRenderer(config.ffmpeg_path)
    raise ValueError(f"unknown renderer: {config.renderer!r}")
