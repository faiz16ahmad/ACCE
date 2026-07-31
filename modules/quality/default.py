"""Default quality check.

Checks each earlier stage's output for completeness and consistency:
script structure, scene timing, media availability, subtitle timing, and the
render artifact. Reports a pass/fail `QualityReport` (info/warning/error).
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from core.models import JobContext, StageResult
from core.stages import Stage

from ..production.srt import parse_srt
from .interface import QualityModule
from .schemas import QualityIssue, QualityReport


class DefaultQualityModule(QualityModule):
    def run(self, ctx: JobContext) -> StageResult:
        issues: list[QualityIssue] = []
        self._check_research(ctx, issues)
        self._check_script(ctx, issues)
        self._check_scenes(ctx, issues)
        self._check_media(ctx, issues)
        self._check_production(ctx, issues)

        passed = all(issue.level != "error" for issue in issues)
        report = QualityReport(
            passed=passed,
            issues=issues,
            summary=f"{len(issues)} issue(s); passed={passed}",
        )
        return StageResult(
            stage=self.name, ok=True, output=report, artifacts_written=[self._save(ctx, "report.json", report)]
        )

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _output(ctx: JobContext, stage: Stage) -> BaseModel | None:
        result = ctx.results.get(stage)
        return result.output if result and result.ok else None

    def _check_research(self, ctx: JobContext, issues: list[QualityIssue]) -> None:
        out = self._output(ctx, Stage.RESEARCH)
        if out is None:
            issues.append(QualityIssue(level="error", stage="research", message="missing research output"))
        else:
            if not out.facts:
                issues.append(QualityIssue(level="warning", stage="research", message="no facts"))
            if not out.summary:
                issues.append(QualityIssue(level="warning", stage="research", message="empty summary"))

    def _check_script(self, ctx: JobContext, issues: list[QualityIssue]) -> None:
        out = self._output(ctx, Stage.SCRIPT)
        if out is None:
            issues.append(QualityIssue(level="error", stage="script", message="missing script output"))
        elif not out.hook or not out.ending or not out.narration:
            issues.append(
                QualityIssue(level="error", stage="script", message="script incomplete (hook/ending/narration)")
            )

    def _check_scenes(self, ctx: JobContext, issues: list[QualityIssue]) -> None:
        out = self._output(ctx, Stage.SCENES)
        if out is None:
            issues.append(QualityIssue(level="error", stage="scenes", message="missing scene plan"))
            return
        if not out.scenes:
            issues.append(QualityIssue(level="error", stage="scenes", message="empty scene plan"))
        bad = [s.scene for s in out.scenes if s.duration <= 0]
        if bad:
            issues.append(QualityIssue(level="error", stage="scenes", message=f"non-positive durations: {bad}"))

    def _check_media(self, ctx: JobContext, issues: list[QualityIssue]) -> None:
        out = self._output(ctx, Stage.MEDIA)
        if out is None:
            issues.append(QualityIssue(level="error", stage="media", message="missing media output"))
        else:
            missing = [a.scene_index for a in out.assets if a.asset.local_path is None]
            if missing:
                issues.append(
                    QualityIssue(
                        level="warning",
                        stage="media",
                        message=f"assets not downloaded (stub mode): scenes {missing}",
                    )
                )

    def _check_production(self, ctx: JobContext, issues: list[QualityIssue]) -> None:
        out = self._output(ctx, Stage.PRODUCTION)
        if out is None:
            issues.append(QualityIssue(level="error", stage="production", message="missing production output"))
            return
        if not Path(out.video_path).exists():
            issues.append(QualityIssue(level="error", stage="production", message="render artifact missing"))
        if out.subtitle_path and Path(out.subtitle_path).exists():
            cues = parse_srt(Path(out.subtitle_path))
            if not cues:
                issues.append(QualityIssue(level="warning", stage="production", message="no subtitle cues"))
            prev_end = -1.0
            for cue in cues:
                if cue.start >= cue.end or cue.start < prev_end:
                    issues.append(
                        QualityIssue(
                            level="error",
                            stage="production",
                            message=f"subtitle timing invalid at cue {cue.index}",
                        )
                    )
                    break
                prev_end = cue.end
        else:
            issues.append(QualityIssue(level="warning", stage="production", message="no subtitle file"))
