"""Default production implementation.

Pipeline (milestone 7):
ScenePlan -> Timeline Builder -> Render Manifest -> Renderer -> ProductionOutput.

The module builds the timeline and the self-contained render manifest (the
renderer's complete input) and never modifies research/script/scenes, retrieves
media, generates audio, or validates quality. The renderer — stub by default
(no FFmpeg needed) or FFmpeg — is isolated behind the Renderer interface and
consumes only the manifest.
"""

from __future__ import annotations

import logging
from pathlib import Path

from config.settings import ProductionConfig
from core.errors import InputValidationError
from core.models import Artifact, JobContext, StageResult
from core.stages import Stage

from ..audio.schemas import AudioOutput
from ..media.schemas import MediaPlan
from ..scenes.schemas import ScenePlan
from .ass import build_ass
from .interface import ProductionModule
from .manifest import build_manifest
from .renderer import Renderer, RendererError, build_renderer
from .schemas import ProductionOutput, RenderLog, SubtitleCue
from .srt import build_srt
from .thumbnail import make_thumbnail
from .timeline import build_timeline

log = logging.getLogger(__name__)


class DefaultProductionModule(ProductionModule):
    def __init__(self, config: ProductionConfig | None = None, renderer: Renderer | None = None) -> None:
        self.config = config or ProductionConfig()
        self.renderer = renderer or build_renderer(self.config)

    def validate_input(self, ctx: JobContext) -> None:
        for stage in (Stage.SCENES, Stage.MEDIA, Stage.AUDIO):
            result = ctx.results.get(stage)
            if result is None or result.output is None:
                raise InputValidationError(f"production requires a {stage.value} output")

    def run(self, ctx: JobContext) -> StageResult:
        scenes: ScenePlan = ctx.results[Stage.SCENES].output
        media: MediaPlan = ctx.results[Stage.MEDIA].output
        audio: AudioOutput = ctx.results[Stage.AUDIO].output
        research = ctx.results[Stage.RESEARCH].output if ctx.results.get(Stage.RESEARCH) else None
        if ctx.store is None:
            raise RuntimeError("JobContext.store is not set — run through the orchestrator")

        written: list[Artifact] = []

        # 1. Timeline — use actual narration durations from the audio stage
        #    when available, falling back to the scene plan's LLM estimates.
        ctx.progress("Building timeline...")
        narr_durations: dict[int, float] = {}
        for i, track in enumerate(audio.tracks):
            if track.kind == "narration" and track.duration:
                narr_durations[i + 1] = track.duration
        shot_plan = ctx.results[Stage.SHOTS].output if ctx.results.get(Stage.SHOTS) else None
        timeline = build_timeline(scenes, media, narr_durations, shot_plan)
        ctx.progress(f"Timeline: {timeline.duration:.1f}s, {len(timeline.clips)} clip(s)")
        timeline_artifact = self._save(ctx, "timeline.json", timeline)
        written.append(timeline_artifact)

        # 2. Subtitles: the SRT stays the contract artifact; a styled ASS (same
        #    cues) drives the burn-in for a publishable look.
        cues = self._subtitle_cues(audio, scenes)
        subtitle_path = audio.subtitle_path
        if subtitle_path is None or not Path(subtitle_path).exists():
            subtitle_path = ctx.store.save_text(self.name, "subtitles.srt", build_srt(cues)).path
        ass_path = ctx.store.save_text(self.name, "subtitles.ass", build_ass(cues)).path

        # 3. Render manifest — the renderer's complete input.
        manifest = build_manifest(timeline, scenes, media, audio, self.config, ass_path)
        manifest_artifact = self._save(ctx, "render_manifest.json", manifest)
        written.append(manifest_artifact)

        # 4. Render (stub by default; FFmpeg when configured).
        ctx.progress("Rendering video...")
        video_path = ctx.store.resolve(self.name, "final_video.mp4")
        try:
            result = self.renderer.render(manifest, video_path)
        except RendererError as exc:
            log.error("render failed: %s", exc)
            return StageResult(stage=self.name, ok=False, error=f"render failed: {exc}")

        # 4b. Thumbnail poster: a video frame, or the first downloaded image.
        fallback_image = next(
            (
                asset.local_path
                for asset in media.assets
                if asset.asset_type == "image"
                and asset.local_path
                and Path(asset.local_path).exists()
            ),
            None,
        )
        thumbnail_path = make_thumbnail(
            ctx.store.resolve(self.name, "thumbnail.jpg"),
            video_path=result.video_path if self.renderer.name == "ffmpeg" else None,
            duration=timeline.duration,
            fallback_image=fallback_image,
            ffmpeg_path=self.config.ffmpeg_path,
        )
        if thumbnail_path is not None:
            written.append(Artifact(stage=self.name.value, name=thumbnail_path.name, path=thumbnail_path))

        # 5. Render log + production output.
        render_log = RenderLog(renderer=self.renderer.name, duration=timeline.duration, log=result.log)
        render_log_artifact = self._save(ctx, "render_log.json", render_log)
        written.append(render_log_artifact)

        title = f"{ctx.input.topic} — {ctx.input.style or 'Explainer'}"
        if research is not None:
            description = (
                f"{title}\n\n{research.summary}\n\n"
                f"Target duration: {ctx.input.duration or 180}s · style: {ctx.input.style or 'default'}"
            )
        else:
            description = title

        output = ProductionOutput(
            video_path=result.video_path,
            timeline_path=timeline_artifact.path,
            render_manifest_path=manifest_artifact.path,
            render_log_path=render_log_artifact.path,
            subtitle_path=subtitle_path,
            duration=timeline.duration,
            title=title,
            description=description,
            metadata={
                "renderer": self.renderer.name,
                "scenes": len(scenes.scenes),
                "clips": len(timeline.clips),
                "fps": self.config.fps,
                "thumbnail": thumbnail_path.name if thumbnail_path is not None else None,
            },
        )
        meta_artifact = self._save(ctx, "output.json", output)
        written.append(meta_artifact)
        return StageResult(stage=self.name, ok=True, output=output, artifacts_written=written)

    @staticmethod
    def _subtitle_cues(audio: AudioOutput, scenes: ScenePlan) -> list[SubtitleCue]:
        """Sentence cues from the audio stage, or scene-level cues as a fallback."""
        if audio.cues:
            return [
                SubtitleCue(index=cue.index, start=cue.start, end=cue.end, text=cue.text)
                for cue in audio.cues
            ]
        cues: list[SubtitleCue] = []
        cursor = 0.0
        for scene in scenes.scenes:
            cues.append(
                SubtitleCue(index=len(cues) + 1, start=cursor, end=cursor + scene.duration, text=scene.narration)
            )
            cursor += scene.duration
        return cues
