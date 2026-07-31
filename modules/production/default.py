"""Default (stub) production implementation.

Milestone 1: derives title/description, writes a real SRT from the scene
plan, and records placeholder marker files for the thumbnail and the final
video (real rendering needs ffmpeg + downloaded assets — the production
milestone).
"""

from __future__ import annotations

import logging

from config.settings import ProductionConfig
from core.errors import InputValidationError
from core.models import JobContext, StageResult
from core.stages import Stage

from ..audio.schemas import AudioOutput
from ..research.schemas import ResearchOutput
from ..scenes.schemas import ScenePlan
from .interface import ProductionModule
from .schemas import ProductionOutput, SubtitleCue
from .srt import build_srt

log = logging.getLogger(__name__)


class DefaultProductionModule(ProductionModule):
    def __init__(self, config: ProductionConfig | None = None) -> None:
        self.config = config or ProductionConfig()

    def validate_input(self, ctx: JobContext) -> None:
        for stage in (Stage.RESEARCH, Stage.SCENES, Stage.AUDIO):
            result = ctx.results.get(stage)
            if result is None or result.output is None:
                raise InputValidationError(f"production requires a {stage.value} output")

    def _cues(self, scenes: ScenePlan) -> list[SubtitleCue]:
        cues: list[SubtitleCue] = []
        cursor = 0.0
        for scene in scenes.scenes:
            cues.append(
                SubtitleCue(index=len(cues) + 1, start=cursor, end=cursor + scene.duration, text=scene.narration)
            )
            cursor += scene.duration
        return cues

    def run(self, ctx: JobContext) -> StageResult:
        research: ResearchOutput = ctx.results[Stage.RESEARCH].output
        scenes: ScenePlan = ctx.results[Stage.SCENES].output
        audio: AudioOutput = ctx.results[Stage.AUDIO].output

        title = f"{ctx.input.topic} — {ctx.input.style or 'Explainer'}"
        description = (
            f"{title}\n\n{research.summary}\n\n"
            f"Target duration: {ctx.input.duration or 180}s · style: {ctx.input.style or 'default'}"
        )

        srt_artifact = ctx.store.save_text(self.name, "subtitles.srt", build_srt(self._cues(scenes)))
        thumb_artifact = ctx.store.save_text(
            self.name, "thumbnail.txt", f"[stub] thumbnail for {title!r} (production milestone)"
        )
        video_artifact = ctx.store.save_text(self.name, "final.mp4.placeholder", self._render_note(audio))

        output = ProductionOutput(
            video_path=video_artifact.path,
            subtitle_path=srt_artifact.path,
            thumbnail_path=thumb_artifact.path,
            title=title,
            description=description,
        )
        meta_artifact = self._save(ctx, "output.json", output)
        return StageResult(
            stage=self.name,
            ok=True,
            output=output,
            artifacts_written=[srt_artifact, thumb_artifact, video_artifact, meta_artifact],
        )

    @staticmethod
    def _render_note(audio: AudioOutput) -> str:
        return (
            "[stub] ffmpeg not invoked (production milestone). Intended render:\n"
            f"  - inputs: per-scene media + master audio {audio.master_path.name}\n"
            "  - assemble timeline, burn subtitles, encode H.264 -> final.mp4"
        )
