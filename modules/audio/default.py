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

from config.settings import AudioConfig
from core.errors import InputValidationError
from core.models import Artifact, JobContext, StageResult
from core.stages import Stage
from memory.cache import DiskCache
from providers.base import TTSProvider
from providers.models import MusicHit
from providers.music_chain import MusicChain

from ..scenes.schemas import ScenePlan
from ..script.schemas import ScriptOutput
from .engine import AudioEngine
from .interface import AudioModule
from .schemas import AudioMetadata, AudioMixPlan, AudioOutput, AudioTrack, MixSegment
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
DEFAULT_GENRE = "ambient"


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
    ) -> None:
        self.tts = tts
        self.music = music
        self.engine = engine
        self.cache = cache
        self.config = config or AudioConfig()
        self.voice = voice
        self.ffmpeg_path = ffmpeg_path or (config.ffmpeg_path if config else None) or "ffmpeg"

    def validate_input(self, ctx: JobContext) -> None:
        result = ctx.results.get(Stage.SCENES)
        if result is None or result.output is None:
            raise InputValidationError("audio requires a scene plan")

    def run(self, ctx: JobContext) -> StageResult:
        plan: ScenePlan = ctx.results[Stage.SCENES].output
        script = ctx.results[Stage.SCRIPT].output if ctx.results.get(Stage.SCRIPT) else None
        if ctx.store is None:
            raise RuntimeError("JobContext.store is not set — run through the orchestrator")

        # 1. Narration
        narration_tracks, written = self._narration(ctx, plan)

        # 2. Music selection (driven by script style)
        genre, music_track = self._select_music(ctx, script)

        # 3. Mix plan
        mix_plan = self._build_mix_plan(narration_tracks, music_track)

        # 4. Audio mixing
        suffix = ".m4a" if getattr(self.engine, "name", "stub") == "ffmpeg" else ".txt"
        mixed = ctx.store.resolve(self.name, f"master_audio{suffix}")
        self.engine.mix(mix_plan, mixed)
        written.append(Artifact(stage=self.name.value, name=mixed.name, path=mixed))

        mix_plan_artifact = self._save(ctx, "mix_plan.json", mix_plan)
        written.append(mix_plan_artifact)

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
                style_genre=genre,
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

    def _select_music(self, ctx: JobContext, script: ScriptOutput | None) -> tuple[str, AudioTrack | None]:
        style = getattr(script, "style", "") or ctx.input.style or "explainer"
        genre = self.config.style_genres.get(style, DEFAULT_GENRE)
        query = f"{genre} {self.config.music_style}".strip()

        hit: MusicHit | None = None
        if self.cache is not None and (cached := self.cache.get(MUSIC_CACHE_NAMESPACE, query)):
            log.info("audio: music selection cache hit")
            hit = MusicHit.model_validate(cached)
        else:
            hits = self.music.search(query, count=1)
            hit = hits[0] if hits else None
            if hit is None:
                log.warning("no background music hit; continuing with narration only")
            elif self.cache is not None:
                self.cache.set(MUSIC_CACHE_NAMESPACE, query, hit.model_dump(mode="json"))
        if hit is None:
            return genre, None
        return genre, AudioTrack(
            kind="music",
            provider=hit.provider,
            title=hit.title,
            url=hit.url,
            local_path=hit.local_path,
            duration=hit.duration,
            bpm=hit.bpm,
            license=hit.license,
        )

    def _build_mix_plan(self, narration_tracks: list[AudioTrack], music_track: AudioTrack | None) -> AudioMixPlan:
        """Timestamped mix plan; V2 beat-sync only replaces this timing logic."""
        segments: list[MixSegment] = []
        cursor = 0.0
        for track in narration_tracks:
            end = cursor + (track.duration or 5.0)
            segments.append(
                MixSegment(
                    kind="narration",
                    source_path=track.local_path,
                    start=cursor,
                    end=end,
                    volume=self.config.narration_volume,
                    fade_in=self.config.narration_fade,
                    fade_out=self.config.narration_fade,
                )
            )
            cursor = end
        if music_track is not None:
            segments.insert(
                0,
                MixSegment(
                    kind="music",
                    source_path=music_track.local_path,
                    start=0.0,
                    end=cursor,
                    volume=self.config.music_volume,
                    fade_in=self.config.music_fade,
                    fade_out=self.config.music_fade,
                ),
            )
        return AudioMixPlan(segments=segments, master_gain=self.config.master_gain)

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
