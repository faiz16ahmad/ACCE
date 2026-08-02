"""Deterministic quality validation for every stage.

The Quality module is analysis/reporting only — it never modifies artifacts.
Each check classifies issues by severity (INFO / WARNING / ERROR); only ERRORs
prevent publishing. The report includes a deterministic 0-100 score (no AI), a
recommended retry stage (advisory — the orchestrator owns retry execution),
per-issue human-readable fix suggestions, and historical quality metrics in
`metadata` for future UI trends.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from config.settings import QualityConfig, TimelineConfig
from core.models import JobContext, StageResult
from core.stages import Stage
from modules.shots.template import scene_id_for

from .interface import QualityModule
from .schemas import QualityIssue, QualityReport

log = logging.getLogger(__name__)

_STAGE_ORDER = {stage.value: index for index, stage in enumerate(Stage)}
_CANONICAL_ARTIFACTS = {
    "research": "research.json",
    "script": "script.json",
    "scenes": "scene_plan.json",
    "shots": "shot_plan.json",
    "media": "media_plan.json",
    "audio": "audio.json",
}


class DefaultQualityModule(QualityModule):
    def __init__(self, config: QualityConfig | None = None, timeline_config: TimelineConfig | None = None) -> None:
        self.config = config or QualityConfig()
        self.timeline_config = timeline_config or TimelineConfig()

    def run(self, ctx: JobContext) -> StageResult:
        issues: list[QualityIssue] = []
        ctx.progress("Checking research...")
        self._check_research(ctx, issues)
        ctx.progress("Checking script...")
        self._check_script(ctx, issues)
        ctx.progress("Checking scenes...")
        self._check_scenes(ctx, issues)
        ctx.progress("Checking shots...")
        self._check_shots(ctx, issues)
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
        # Visual coverage is a Shot-level concern in architecture v2 (Phase 3);
        # scenes are narrative-only.
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

    def _check_shots(self, ctx: JobContext, issues: list[QualityIssue]) -> None:
        out = self._output(ctx, Stage.SHOTS)
        if out is None:
            self._issue(
                issues,
                "error",
                "shots",
                "missing shot plan",
                "shots.missing_output",
                "Retry the Shot Planner.",
            )
            return
        if not out.shots:
            self._issue(
                issues,
                "error",
                "shots",
                "empty shot plan",
                "shots.empty",
                "Regenerate the Shot Planner.",
            )
            return
        scenes = self._output(ctx, Stage.SCENES)
        known_ids = {scene_id_for(s.scene_number) for s in scenes.scenes} if scenes is not None else set()
        orphan = sorted({s.shot_id for s in out.shots if s.scene_id not in known_ids})
        if orphan:
            self._issue(
                issues,
                "warning",
                "shots",
                f"shots with unknown scenes: {orphan}",
                "shots.orphan_scene",
                "Regenerate the Shot Planner.",
            )
        counts = Counter(s.scene_id for s in out.shots)
        for scene_id, count in sorted(counts.items()):
            if count < self.timeline_config.min_shots or count > self.timeline_config.max_shots:
                self._issue(
                    issues,
                    "warning",
                    "shots",
                    f"scene {scene_id} has {count} shot(s), "
                    f"outside [{self.timeline_config.min_shots}, {self.timeline_config.max_shots}]",
                    "shots.count_bounds",
                    "Regenerate the Shot Planner or adjust TimelineConfig.",
                )
        empty_queries = [s.shot_id for s in out.shots if not s.search_queries]
        if empty_queries:
            self._issue(
                issues,
                "warning",
                "shots",
                f"shots with empty search queries: {empty_queries}",
                "shots.empty_queries",
                "Regenerate the Shot Planner with keywords.",
            )
        missing_visual = [s.shot_id for s in out.shots if not s.visual_description]
        if missing_visual:
            self._issue(
                issues,
                "warning",
                "shots",
                f"shots missing visual description: {missing_visual}",
                "shots.missing_visual",
                "Regenerate the Shot Planner.",
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
        # Every shot should have a media asset of its own (shot-keyed coverage).
        shots = self._output(ctx, Stage.SHOTS)
        if shots is not None and shots.shots:
            shot_ids = {s.shot_id for s in shots.shots}
            covered = {asset.shot_id for asset in out.assets if asset.shot_id}
            uncovered = sorted(shot_ids - covered)
            if uncovered:
                self._issue(
                    issues,
                    "warning",
                    "media",
                    f"shots without media assets: {uncovered}",
                    "media.shot_coverage",
                    "Run the Media stage with a real provider.",
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
        self._check_music(ctx, out, issues)

    def _check_music(self, ctx: JobContext, out, issues: list[QualityIssue]) -> None:
        """Music-plan checks (architecture-audio.md §8, Phase 3).

        Artifact-driven: they only fire when the audio stage actually saved the
        music plan (`audio_plan.json`), so legacy/plan-less runs are untouched.
        """
        if ctx.store is None:
            return
        plan_path = ctx.store.resolve(Stage.AUDIO, "audio_plan.json")
        if not plan_path.exists():
            return
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not (plan.get("music") or []):
            self._issue(
                issues,
                "info",
                "audio",
                "no music intent planned",
                "audio.missing_music_intent",
                "Run the Music Planner.",
            )
            return

        has_music = any(getattr(track, "kind", "") == "music" for track in out.tracks)
        if not has_music:
            self._issue(
                issues,
                "warning",
                "audio",
                "music planned but no asset retrieved",
                "audio.missing_music_asset",
                "Configure a music provider or add local tracks (narration-only continues).",
            )

        mix_path = ctx.store.resolve(Stage.AUDIO, "mix_plan.json")
        if not mix_path.exists():
            return
        try:
            mix = json.loads(mix_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        music_segments = [s for s in mix.get("segments", []) if s.get("kind") == "music"]
        if not music_segments:
            return
        if out.duration:
            bed_end = max(s.get("end", 0.0) for s in music_segments)
            if abs(bed_end - out.duration) / max(out.duration, 1.0) > self.config.duration_tolerance:
                self._issue(
                    issues,
                    "warning",
                    "audio",
                    f"music bed does not cover narration ({bed_end:.1f}s vs {out.duration:.1f}s)",
                    "audio.music_bed_coverage",
                    "Extend the music bed to cover the narration.",
                )
        first = music_segments[0]
        if first.get("duck") is None:
            self._issue(
                issues,
                "info",
                "audio",
                "music ducking not configured",
                "audio.music_no_duck",
                "Configure ducking for the music bed.",
            )
        if not (first.get("fade_in") or first.get("fade_out")):
            self._issue(
                issues,
                "info",
                "audio",
                "music fades not configured",
                "audio.music_no_fades",
                "Configure fade in/out for the music bed.",
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

        # Clip-level checks from the timeline artifact (analysis only — quality
        # never modifies artifacts).
        if ctx.store is not None and ctx.store.exists(Stage.PRODUCTION, "timeline.json"):
            try:
                data = json.loads(Path(ctx.store.resolve(Stage.PRODUCTION, "timeline.json")).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = {}
            clips = data.get("clips") or []
            if not clips:
                self._issue(
                    issues,
                    "warning",
                    "production",
                    "timeline has no clips",
                    "production.no_clips",
                    "Retry the Production stage.",
                )
            else:
                short = [
                    clip.get("shot_id")
                    for clip in clips
                    if (clip.get("end", 0.0) - clip.get("start", 0.0)) < self.timeline_config.min_shot_duration
                ]
                if short:
                    self._issue(
                        issues,
                        "warning",
                        "production",
                        f"clips below min duration: {short}",
                        "production.short_clips",
                        "Adjust TimelineConfig or Regenerate the Shot Planner.",
                    )

    def _check_overall(self, ctx: JobContext, issues: list[QualityIssue]) -> None:
        production = self._output(ctx, Stage.PRODUCTION)
        audio = self._output(ctx, Stage.AUDIO)
        # The measured narration is the clock (I7); fall back to the scene plan.
        reference = audio.duration if audio is not None and audio.duration else self._scene_total(ctx)
        if production is not None and reference and production.duration:
            ratio = abs(production.duration - reference) / reference
            if ratio > self.config.duration_tolerance:
                self._issue(
                    issues,
                    "warning",
                    "overall",
                    f"final duration inconsistency ({production.duration:.1f}s vs clock {reference:.1f}s)",
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
