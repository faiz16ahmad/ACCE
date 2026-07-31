"""Default audio implementation.

Steps: synthesize per-scene narration via TTS -> select royalty-free
background music via MusicProvider (cache-first) -> build a timestamped
`AudioMixPlan` -> let the `AudioEngine` produce the master track.
"""

from __future__ import annotations

import logging

from config.settings import AudioConfig
from core.errors import InputValidationError
from core.models import Artifact, JobContext, StageResult
from core.stages import Stage
from memory.cache import DiskCache
from providers.base import MusicProvider, TTSProvider
from providers.models import MusicHit

from ..scenes.schemas import ScenePlan
from .engine import AudioEngine
from .interface import AudioModule
from .schemas import AudioMixPlan, AudioOutput, AudioTrack, MixSegment

log = logging.getLogger(__name__)

MUSIC_CACHE_NAMESPACE = "audio"


class DefaultAudioModule(AudioModule):
    def __init__(
        self,
        tts: TTSProvider,
        music: MusicProvider,
        engine: AudioEngine,
        cache: DiskCache | None = None,
        config: AudioConfig | None = None,
        voice: str = "en-US-Wavenet-D",
    ) -> None:
        self.tts = tts
        self.music = music
        self.engine = engine
        self.cache = cache
        self.config = config or AudioConfig()
        self.voice = voice

    def validate_input(self, ctx: JobContext) -> None:
        result = ctx.results.get(Stage.SCENES)
        if result is None or result.output is None:
            raise InputValidationError("audio requires a scene plan")

    def run(self, ctx: JobContext) -> StageResult:
        plan: ScenePlan = ctx.results[Stage.SCENES].output
        if ctx.store is None:
            raise RuntimeError("JobContext.store is not set — run through the orchestrator")

        narration_tracks, written = self._narration(ctx, plan)
        music_track = self._select_music(ctx)
        mix_plan = self._build_mix_plan(narration_tracks, music_track)  # V2 beat-sync seam

        master = ctx.store.resolve(self.name, "master_audio.txt")
        self.engine.mix(mix_plan, master)
        written.append(Artifact(stage=self.name.value, name=master.name, path=master))

        mix_plan_artifact = self._save(ctx, "mix_plan.json", mix_plan)
        written.append(mix_plan_artifact)

        output = AudioOutput(
            master_path=master,
            tracks=[*narration_tracks, music_track] if music_track else narration_tracks,
            mix_plan_path=mix_plan_artifact.path,
        )
        written.append(self._save(ctx, "audio.json", output))
        return StageResult(stage=self.name, ok=True, output=output, artifacts_written=written)

    def _narration(self, ctx: JobContext, plan: ScenePlan) -> tuple[list[AudioTrack], list[Artifact]]:
        tracks: list[AudioTrack] = []
        written: list[Artifact] = []
        for scene in plan.scenes:
            out = ctx.store.resolve(self.name, f"narration_scene_{scene.scene:02d}.txt")
            self.tts.synthesize(scene.narration, voice=self.voice, out_path=out)
            tracks.append(
                AudioTrack(
                    kind="narration",
                    provider=self.tts.name,
                    title=f"narration scene {scene.scene}",
                    local_path=out,
                    duration=float(scene.duration),
                )
            )
            written.append(Artifact(stage=self.name.value, name=out.name, path=out))
        return tracks, written

    def _select_music(self, ctx: JobContext) -> AudioTrack | None:
        query = f"{self.config.music_style} for {ctx.input.topic}"
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
            return None
        return AudioTrack(
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
        """Build a timestamped mix plan.

        **V2 seam**: beat-synchronization replaces this method's timing logic
        (beats per minute -> beat-aligned segment boundaries) without changing
        the `AudioMixPlan` contract, the engine, or any consumer.
        """
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
                    fade_in=0.2,
                    fade_out=0.2,
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
                    fade_in=1.0,
                    fade_out=1.0,
                ),
            )
        return AudioMixPlan(segments=segments, master_gain=self.config.master_gain)
