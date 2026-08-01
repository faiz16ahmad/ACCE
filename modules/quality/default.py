"""Deterministic quality validation for every stage.

The Quality module is analysis/reporting only — it never modifies artifacts.
Each check classifies issues by severity (INFO / WARNING / ERROR); only ERRORs
prevent publishing. The report includes a deterministic 0-100 score (no AI), a
recommended retry stage (advisory — the orchestrator owns retry execution),
per-issue human-readable fix suggestions, and historical quality metrics in
`metadata` for future UI trends.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from config.settings import QualityConfig
from core.models import JobContext, StageResult
from core.stages import Stage

from .interface import QualityModule
from .schemas import QualityIssue, QualityReport

log = logging.getLogger(__name__)

_STAGE_ORDER = {stage.value: index for index, stage in enumerate(Stage)}
_CANONICAL_ARTIFACTS = {
    "research": "research.json",
    "script": "script.json",
    "scenes": "scene_plan.json",
    "media": "media_plan.json",
    "audio": "audio.json",
}


class DefaultQualityModule(QualityModule):
    def __init__(self, config: QualityConfig | None = None) -> None:
        self.config = config or QualityConfig()

    def run(self, ctx: JobContext) -> StageResult:
        issues: list[QualityIssue] = []
        ctx.progress("Checking research...")
        self._check_research(ctx, issues)
        ctx.progress("Checking script...")
        self._check_script(ctx, issues)
        ctx.progress("Checking scenes...")
        self._check_scenes(ctx, issues)
        ctx.progress("Checking media...")
        self._check_media(ctx, issues)
        ctx.progress("Checking audio...")
        self._check_audio(ctx, issues)
        ctx.progress("Checking production...")
        self._check_production(ctx, issues)
        self._check_overall(ctx, issues)

        errors = [issue for issue in issues if issue.level == "error"]
        warnings = [issue for issue in issues if issue.level == "warning"]
        passed = not errors
        score = self._score(issues)
        report = QualityReport(
            passed=passed,
            score=score,
            issues=issues,
            warnings=len(warnings),
            errors=len(errors),
            recommended_retry_stage=self._recommend_retry(errors),
            metadata=self._metadata(ctx, passed, score, errors, warnings, issues),
            summary=(f"{len(issues)} issue(s): {len(errors)} error(s), {len(warnings)} warning(s); passed={passed}"),
        )
        ctx.progress(f"Score: {score:.0f}/100 — {'PASSED' if passed else 'FAILED'}")
        return StageResult(
            stage=self.name,
            ok=True,
            output=report,
            artifacts_written=[self._save(ctx, "quality.json", report)],
        )

    # -- report helpers ------------------------------------------------------

    @staticmethod
    def _metadata(ctx: JobContext, passed: bool, score: float, errors: list, warnings: list, issues: list) -> dict:
        """Historical quality summary so future UI versions can visualize trends."""
        stage_counts = {stage: 0 for stage in _STAGE_ORDER}
        for issue in issues:
            if issue.stage in stage_counts:
                stage_counts[issue.stage] += 1
        return {
            "score": score,
            "warnings": len(warnings),
            "errors": len(errors),
            "passed": passed,
            "pipeline_complete": bool(ctx.results.get(Stage.PRODUCTION)),
            "generated_at": datetime.now(UTC).isoformat(),
            "stage_counts": stage_counts,
        }

    def _score(self, issues: list[QualityIssue]) -> float:
        score = 100.0
        for issue in issues:
            score -= getattr(self.config, f"penalty_{issue.level}")
        return round(max(0.0, score), 1)

    @staticmethod
    def _recommend_retry(errors: list[QualityIssue]) -> str | None:
        stages = sorted(
            {error.stage for error in errors if error.stage in _STAGE_ORDER},
            key=lambda stage: _STAGE_ORDER[stage],
        )
        return stages[0] if stages else None

    @staticmethod
    def _output(ctx: JobContext, stage: Stage):
        result = ctx.results.get(stage)
        return result.output if result and result.ok else None

    @staticmethod
    def _path(path) -> bool:
        return path is not None and Path(path).exists()

    def _issue(
        self,
        issues: list[QualityIssue],
        level: str,
        stage: str,
        message: str,
        code: str,
        fix: str | None = None,
    ) -> None:
        issues.append(QualityIssue(level=level, stage=stage, message=message, code=code, suggested_fix=fix))

    def _scene_total(self, ctx: JobContext) -> float:
        scenes = self._output(ctx, Stage.SCENES)
        if scenes is None:
            return 0.0
        return sum(max(0.0, scene.duration) for scene in scenes.scenes)

    # -- per-stage checks -----------------------------------------------------

    def _check_research(self, ctx: JobContext, issues: list[QualityIssue]) -> None:
        out = self._output(ctx, Stage.RESEARCH)
        if out is None:
            self._issue(
                issues,
                "error",
                "research",
                "missing research output",
                "research.missing_output",
                "Retry the Research stage.",
            )
            return
        if not out.facts and not out.summary:
            self._issue(
                issues,
                "error",
                "research",
                "empty research output",
                "research.empty_output",
                "Retry the Research stage.",
            )
            return
        if not out.facts:
            self._issue(
                issues,
                "warning",
                "research",
                "no facts in research",
                "research.no_facts",
                "Regenerate the Research with source-backed facts.",
            )
        elif not any(fact.verified for fact in out.facts):
            self._issue(
                issues,
                "warning",
                "research",
                "no verified facts",
                "research.unverified_facts",
                "Enable source fetching or retry Research to verify facts.",
            )
        if not out.summary:
            self._issue(
                issues,
                "info",
                "research",
                "empty research summary",
                "research.empty_summary",
                "Regenerate the Research summary.",
            )

    def _check_script(self, ctx: JobContext, issues: list[QualityIssue]) -> None:
        out = self._output(ctx, Stage.SCRIPT)
        if out is None:
            self._issue(
                issues, "error", "script", "missing script output", "script.missing_output", "Retry the Script stage."
            )
            return
        if not out.hook or not out.ending or not out.narration:
            self._issue(
                issues,
                "error",
                "script",
                "script incomplete (hook/ending/narration)",
                "script.empty_sections",
                "Regenerate the Script.",
            )
        metrics = out.metrics
        if metrics is not None:
            requested = ctx.input.duration
            if requested and metrics.estimated_duration:
                ratio = abs(metrics.estimated_duration - requested) / max(float(requested), 1.0)
                if ratio > self.config.duration_tolerance:
                    self._issue(
                        issues,
                        "warning",
                        "script",
                        f"duration mismatch (estimated {metrics.estimated_duration:.0f}s vs requested {requested}s)",
                        "script.duration_mismatch",
                        "Regenerate the Script with the requested duration.",
                    )
            if metrics.readability is not None:
                ease = metrics.readability.reading_ease
                if ease < self.config.readability_min or ease > self.config.readability_max:
                    self._issue(
                        issues,
                        "warning",
                        "script",
                        f"readability outside thresholds (reading ease {ease:.1f})",
                        "script.readability",
                        "Adjust the Script tone to hit the configured readability range.",
                    )

    def _check_scenes(self, ctx: JobContext, issues: list[QualityIssue]) -> None:
        out = self._output(ctx, Stage.SCENES)
        if out is None:
            self._issue(
                issues, "error", "scenes", "missing scene plan", "scenes.missing_output", "Retry the Scene Planner."
            )
            return
        if not out.scenes:
            self._issue(issues, "error", "scenes", "empty scene plan", "scenes.empty", "Regenerate the Scene Planner.")
            return
        bad = [scene.scene for scene in out.scenes if scene.duration <= 0]
        if bad:
            self._issue(
                issues,
                "error",
                "scenes",
                f"non-positive durations: {bad}",
                "scenes.invalid_duration",
                "Regenerate the Scene Planner.",
            )
        missing_visual = [scene.scene for scene in out.scenes if not scene.visual_description]
        if missing_visual:
            self._issue(
                issues,
                "warning",
                "scenes",
                f"missing visual descriptions: {missing_visual}",
                "scenes.missing_visual",
                "Regenerate the Scene Planner with visual descriptions.",
            )
        missing_keywords = [scene.scene for scene in out.scenes if not scene.search_keywords]
        if missing_keywords:
            self._issue(
                issues,
                "warning",
                "scenes",
                f"missing search keywords: {missing_keywords}",
                "scenes.missing_keywords",
                "Regenerate the Scene Planner with keywords.",
            )
        numbers = sorted(scene.scene for scene in out.scenes)
        if numbers != list(range(1, len(numbers) + 1)):
            self._issue(
                issues,
                "warning",
                "scenes",
                "scene numbers not contiguous (timeline continuity)",
                "scenes.timeline_continuity",
                "Regenerate the Scene Planner.",
            )

    def _check_media(self, ctx: JobContext, issues: list[QualityIssue]) -> None:
        out = self._output(ctx, Stage.MEDIA)
        if out is None:
            self._issue(
                issues, "error", "media", "missing media output", "media.missing_output", "Retry the Media stage."
            )
            return
        if not out.assets:
            self._issue(
                issues,
                "warning",
                "media",
                "no media assets planned",
                "media.empty",
                "Run the Media stage with a real provider.",
            )
            return
        placeholders = [
            asset.scene_index for asset in out.assets if asset.selected_provider == "placeholder" or not asset.asset_url
        ]
        if placeholders:
            self._issue(
                issues,
                "warning",
                "media",
                f"placeholder assets for scenes: {placeholders}",
                "media.placeholder_asset",
                "Configure a real media provider or retry Media.",
            )
        missing_local = [asset.scene_index for asset in out.assets if asset.local_path is None]
        if missing_local:
            self._issue(
                issues,
                "warning",
                "media",
                f"assets not downloaded: {missing_local}",
                "media.missing_local",
                "Enable downloads or retry Media with real assets.",
            )
        no_license = [
            asset.scene_index
            for asset in out.assets
            if not asset.license or asset.license.lower() in ("unknown", "none")
        ]
        if no_license:
            self._issue(
                issues,
                "info",
                "media",
                f"missing license info: {no_license}",
                "media.missing_license",
                "Re-fetch assets with license metadata.",
            )
        urls = [asset.asset_url for asset in out.assets if asset.asset_url]
        if len(urls) != len(set(urls)):
            self._issue(
                issues,
                "warning",
                "media",
                "duplicate assets used across scenes",
                "media.duplicate_asset",
                "Choose distinct assets per scene.",
            )

    def _check_audio(self, ctx: JobContext, issues: list[QualityIssue]) -> None:
        out = self._output(ctx, Stage.AUDIO)
        if out is None:
            self._issue(
                issues, "error", "audio", "missing audio output", "audio.missing_output", "Retry the Audio stage."
            )
            return
        if not self._path(out.narration_path):
            self._issue(
                issues, "error", "audio", "missing narration", "audio.missing_narration", "Regenerate the Audio stage."
            )
        if not self._path(out.subtitle_path):
            self._issue(
                issues, "error", "audio", "missing subtitles", "audio.missing_subtitles", "Regenerate the Audio stage."
            )
        scene_total = self._scene_total(ctx)
        if (
            scene_total
            and out.duration
            and abs(out.duration - scene_total) / scene_total > self.config.duration_tolerance
        ):
            self._issue(
                issues,
                "warning",
                "audio",
                f"audio duration mismatch ({out.duration:.1f}s vs scenes {scene_total:.1f}s)",
                "audio.duration_mismatch",
                "Regenerate the Audio stage.",
            )
        if not any(getattr(track, "kind", "") == "music" for track in out.tracks):
            self._issue(
                issues,
                "warning",
                "audio",
                "no background music",
                "audio.missing_music",
                "Add a music provider (Pixabay Music / Local / Stub).",
            )

    def _check_production(self, ctx: JobContext, issues: list[QualityIssue]) -> None:
        out = self._output(ctx, Stage.PRODUCTION)
        if out is None:
            self._issue(
                issues,
                "error",
                "production",
                "missing production output",
                "production.missing_output",
                "Retry the Production stage.",
            )
            return
        for attr, code, label in (
            ("video_path", "production.missing_video", "final video"),
            ("timeline_path", "production.missing_timeline", "timeline"),
            ("render_manifest_path", "production.missing_manifest", "render manifest"),
            ("render_log_path", "production.missing_render_log", "render log"),
        ):
            if not self._path(getattr(out, attr)):
                self._issue(issues, "error", "production", f"missing {label}", code, "Retry the Production stage.")

    def _check_overall(self, ctx: JobContext, issues: list[QualityIssue]) -> None:
        production = self._output(ctx, Stage.PRODUCTION)
        scene_total = self._scene_total(ctx)
        if production is not None and scene_total and production.duration:
            ratio = abs(production.duration - scene_total) / scene_total
            if ratio > self.config.duration_tolerance:
                self._issue(
                    issues,
                    "warning",
                    "overall",
                    f"final duration inconsistency ({production.duration:.1f}s vs scenes {scene_total:.1f}s)",
                    "overall.duration_consistency",
                    "Regenerate the affected stage to align durations.",
                )
        if ctx.store is not None:
            missing = [
                stage for stage, name in _CANONICAL_ARTIFACTS.items() if not ctx.store.exists(Stage(stage), name)
            ]
            if missing:
                self._issue(
                    issues,
                    "warning",
                    "overall",
                    f"missing artifacts: {', '.join(missing)}",
                    "overall.artifact_completeness",
                    "Re-run the pipeline for the missing stages.",
                )
