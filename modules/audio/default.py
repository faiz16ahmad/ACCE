"""Default audio implementation.

Pipeline (milestone 6):
Narration (per-scene TTS) -> Music Selection (style->genre, provider chain) ->
Mix Plan (narration + music underlay with volume and fades) -> Audio Mixing
(engine) -> Subtitle Generation (sentence-based, from scene timing) ->
AudioOutput.

Subtitles are generated from the narration/script timing, never from the mixed
audio, so subtitle generation stays independent of the mixer/engine. V1 mixing
is configurable volume + fade in/out only — no beat sync, ducking, dynamic
changes, or emotion-aware soundtracks (those are future milestones).
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

from config.settings import AudioConfig, MusicConfig
from core.errors import InputValidationError
from core.models import Artifact, JobContext, StageResult
from core.stages import Stage
from memory.cache import DiskCache
from providers.base import LLMProvider, TTSProvider
from providers.models import MusicHit
from providers.music_chain import MusicChain

from ..scenes.schemas import ScenePlan
from ..script.schemas import ScriptOutput
from .engine import AudioEngine
from .interface import AudioModule
from .music.planner import plan_music
from .music.retrieve import rank_assets
from .music.schemas import MusicAsset, MusicIntent, MusicSelection, RankedAsset
from .music.timeline import build_audio_timeline, flatten_timeline
from .schemas import AudioMetadata, AudioMixPlan, AudioOutput, AudioTrack
from .subtitles import build_cues, cues_to_srt


def _measure_audio_duration(path: Path, ffmpeg_path: str = "ffmpeg") -> float:
    """Measure actual audio file duration via ffprobe, falling back to 0 on failure."""
    # Try ffprobe next to the ffmpeg binary first
    ffprobe_path = Path(ffmpeg_path)
    if ffprobe_path.is_file():
        ffprobe = ffprobe_path.parent / "ffprobe.exe"
    else:
        ffprobe = Path("ffprobe")
    try:
        proc = subprocess.run(
            [str(ffprobe), "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=10,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return float(proc.stdout.strip())
    except Exception:
        pass
    # Fallback: use ffmpeg -i to parse Duration line
    try:
        proc = subprocess.run(
            [ffmpeg_path, "-hide_banner", "-i", str(path), "-f", "null", "-"],
            capture_output=True, text=True, timeout=10,
        )
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", proc.stderr)
        if m:
            return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    except Exception:
        pass
    return 0.0

log = logging.getLogger(__name__)

MUSIC_CACHE_NAMESPACE = "audio"


class DefaultAudioModule(AudioModule):
    def __init__(
        self,
        tts: TTSProvider,
        music: MusicChain,
        engine: AudioEngine,
        cache: DiskCache | None = None,
        config: AudioConfig | None = None,
        voice: str = "en-US-AriaNeural",
        ffmpeg_path: str | None = None,
        llm: LLMProvider | None = None,
        music_config: MusicConfig | None = None,
    ) -> None:
        self.tts = tts
        self.music = music
        self.engine = engine
        self.cache = cache
        self.config = config or AudioConfig()
        self.voice = voice
        self.ffmpeg_path = ffmpeg_path or (config.ffmpeg_path if config else None) or "ffmpeg"
        self.llm = llm
        self.music_config = music_config or MusicConfig()

    def validate_input(self, ctx: JobContext) -> None:
        result = ctx.results.get(Stage.SCENES)
        if result is None or result.output is None:
            raise InputValidationError("audio requires a scene plan")

    def run(self, ctx: JobContext) -> StageResult:
        plan: ScenePlan = ctx.results[Stage.SCENES].output
        script = ctx.results[Stage.SCRIPT].output if ctx.results.get(Stage.SCRIPT) else None
        if ctx.store is None:
            raise RuntimeError("JobContext.store is not set — run through the orchestrator")

        # 1. Narration (the clock)
        ctx.progress("Generating narration...")
        narration_tracks, written = self._narration(ctx, plan)
        for i, track in enumerate(narration_tracks, 1):
            ctx.progress(f"Scene {i} narration: {track.duration:.1f}s")
        narration_total = sum(track.duration or 0.0 for track in narration_tracks)

        # 2. Music planning (LLM proposes intent; normalizer enforces)
        ctx.progress("Planning background music...")
        style = getattr(script, "style", "") or ctx.input.style or "explainer"
        audio_plan = plan_music(
            plan,
            topic=ctx.input.topic,
            style=style,
            duration=ctx.input.duration,
            llm=self.llm,
            audio_config=self.config,
            music_config=self.music_config,
        )
        intent = audio_plan.music[0] if audio_plan.music else None
        genre_hint = (self.config.style_genres or {}).get(style, "ambient")  # legacy hint only
        ctx.progress(f"Music intent: {intent.emotion if intent else 'none'}")

        # 3. Music retrieval (deterministic ranking, §3.5)
        selected: MusicAsset | None = None
        ranked: list[RankedAsset] = []
        if intent is not None:
            ctx.progress("Retrieving background music...")
            selected, ranked = self._retrieve_music(intent, genre_hint, narration_total)
            if selected is None:
                log.warning("no satisfactory music asset; continuing with narration only")
            else:
                ctx.progress(f"Music: {selected.title} ({selected.provider})")

        # 4. Audio timeline (owns ALL music timing)
        ctx.progress("Building audio timeline...")
        timeline = build_audio_timeline(
            audio_plan, selected, narration_total, self.config, self.music_config
        )
        mix_plan = flatten_timeline(
            timeline,
            narration_tracks,
            {selected.asset_id: selected} if selected is not None else {},
            self.config,
        )

        # 5. Audio mixing
        ctx.progress("Mixing audio...")
        suffix = ".m4a" if getattr(self.engine, "name", "stub") == "ffmpeg" else ".txt"
        mixed = ctx.store.resolve(self.name, f"master_audio{suffix}")
        self.engine.mix(mix_plan, mixed)
        written.append(Artifact(stage=self.name.value, name=mixed.name, path=mixed))

        mix_plan_artifact = self._save(ctx, "mix_plan.json", mix_plan)
        written.append(mix_plan_artifact)
        written.append(self._save(ctx, "audio_plan.json", audio_plan))
        if ranked:
            written.append(
                self._save(ctx, "music_assets.json", [entry.model_dump(mode="json") for entry in ranked])
            )

        # 5. Subtitle generation — use actual narration durations for timing.
        narr_durations = {
            i + 1: t.duration
            for i, t in enumerate(narration_tracks)
            if t.duration
        }
        cues = build_cues(plan, narr_durations)
        srt_path = ctx.store.resolve(self.name, "subtitles.srt")
        srt_path.write_text(cues_to_srt(cues), encoding="utf-8")
        written.append(Artifact(stage=self.name.value, name=srt_path.name, path=srt_path))

        narration_path = self._combine_narration(ctx, narration_tracks)
        written.append(Artifact(stage=self.name.value, name=narration_path.name, path=narration_path))

        duration = self._plan_duration(mix_plan)
        ctx.progress(f"Master audio: {duration:.1f}s")
        music_track = self._music_track(selected) if selected is not None else None
        tracks = [*narration_tracks, music_track] if music_track else narration_tracks
        output = AudioOutput(
            narration_path=narration_path,
            music_path=music_track.local_path if music_track else None,
            mixed_audio_path=mixed,
            subtitle_path=srt_path,
            duration=duration,
            metadata=AudioMetadata(
                duration=duration,
                narration_duration=duration,
                music_provider=music_track.provider if music_track else None,
                music_title=music_track.title if music_track else None,
                style_genre=genre_hint,
                engine=self.config.engine,
                voice=self.voice,
                cue_count=len(cues),
            ),
            cues=cues,
            master_path=mixed,
            tracks=tracks,
            mix_plan_path=mix_plan_artifact.path,
        )
        written.append(self._save(ctx, "audio.json", output))
        return StageResult(stage=self.name, ok=True, output=output, artifacts_written=written)

    # -- internal stages ------------------------------------------------------

    def _narration(self, ctx: JobContext, plan: ScenePlan) -> tuple[list[AudioTrack], list[Artifact]]:
        tracks: list[AudioTrack] = []
        written: list[Artifact] = []
        for scene in plan.scenes:
            suffix = ".mp3" if getattr(self.tts, "name", "stub") == "edge" else ".txt"
            out = ctx.store.resolve(self.name, f"narration_scene_{scene.scene:02d}{suffix}")
            self.tts.synthesize(scene.narration, voice=self.voice, out_path=out)
            # Measure actual TTS output duration, not the LLM estimate.
            actual_dur = _measure_audio_duration(out, self.ffmpeg_path)
            dur = actual_dur if actual_dur > 0 else float(scene.duration)
            tracks.append(
                AudioTrack(
                    kind="narration",
                    provider=self.tts.name,
                    title=f"narration scene {scene.scene}",
                    local_path=out,
                    duration=dur,
                )
            )
            written.append(Artifact(stage=self.name.value, name=out.name, path=out))
        return tracks, written

    def _retrieve_music(
        self, intent: MusicIntent, genre_hint: str, narration_total: float
    ) -> tuple[MusicAsset | None, list[RankedAsset]]:
        """Deterministic retrieval (§3.5): rank chain hits, pick the best.

        The planner never selects files (A1); the retriever never changes
        emotion/intent (A2). No asset passes the threshold -> narration-only
        (A10).
        """
        query = self._music_query(genre_hint, intent)
        hits = self._search_hits(query)
        if not hits:
            return None, []
        assets = [self._to_asset(hit, f"music_{i:04d}") for i, hit in enumerate(hits)]
        selection = MusicSelection(intent=intent, duration_hint=narration_total, genre_hint=genre_hint)
        ranked = rank_assets(assets, selection, self.music_config)
        return (ranked[0].asset if ranked else None), ranked

    def _search_hits(self, query: str) -> list[MusicHit]:
        cached = self.cache.get(MUSIC_CACHE_NAMESPACE, query) if self.cache is not None else None
        if cached is not None:
            log.info("audio: music selection cache hit")
            return [MusicHit.model_validate(item) for item in cached]
        hits = self.music.search(query, count=self.music_config.music_candidates)
        if hits and self.cache is not None:
            self.cache.set(MUSIC_CACHE_NAMESPACE, query, [hit.model_dump(mode="json") for hit in hits])
        return hits

    @staticmethod
    def _music_query(genre_hint: str, intent: MusicIntent) -> str:
        """Deterministic query from the hint + intent (genre_hint is a hint, not
        the decision — the ranking decides)."""
        return f"{genre_hint} {intent.emotion} background music".strip()

    def _to_asset(self, hit: MusicHit, asset_id: str) -> MusicAsset:
        """Map a provider hit to a `MusicAsset`.

        The retriever owns "measured file duration" (architecture-audio.md §3):
        when a provider returns a local file without a duration, measure it so
        the §3.5 `duration` reason is meaningful instead of 0 (which would drop
        every real local track below the satisfactory threshold).
        """
        duration = hit.duration
        if not duration and hit.local_path is not None and Path(hit.local_path).exists():
            duration = _measure_audio_duration(Path(hit.local_path), self.ffmpeg_path)
        return MusicAsset(
            asset_id=asset_id,
            provider=hit.provider,
            title=hit.title,
            url=hit.url,
            local_path=hit.local_path,
            duration=duration or 0.0,
            bpm=hit.bpm,
            license=hit.license,
        )

    @staticmethod
    def _music_track(asset: MusicAsset) -> AudioTrack:
        return AudioTrack(
            kind="music",
            provider=asset.provider,
            title=asset.title,
            url=asset.url,
            local_path=asset.local_path,
            duration=asset.duration or None,
            bpm=asset.bpm,
            license=asset.license,
        )

    def _combine_narration(self, ctx: JobContext, tracks: list[AudioTrack]) -> object:
        combined = ctx.store.resolve(self.name, "narration.txt")
        parts = []
        for track in tracks:
            if track.local_path and track.local_path.exists():
                try:
                    parts.append(track.local_path.read_text(encoding="utf-8").strip())
                except UnicodeDecodeError:
                    # Real TTS (edge-tts) writes binary audio, not text — keep a
                    # readable pointer instead of crashing the pipeline.
                    parts.append(f"[audio narration] {track.local_path.name}")
        combined.write_text("\n\n".join(parts), encoding="utf-8")
        return combined

    @staticmethod
    def _plan_duration(plan: AudioMixPlan) -> float:
        ends = [segment.end for segment in plan.segments if segment.kind == "narration"]
        return round(max(ends) if ends else 0.0, 3)
