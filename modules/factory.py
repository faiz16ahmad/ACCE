"""Wiring: build a fully-injected pipeline from settings.

All dependencies (providers, cache, engine, config) are resolved here and
handed to modules via constructors — modules never resolve globals.
"""

from __future__ import annotations

from collections.abc import Callable

from config.languages import LanguageRegistry
from config.settings import Settings
from core.models import Locale, Narrator, ProgressEvent
from core.orchestrator import PipelineOrchestrator
from core.stages import Stage
from memory.cache import DiskCache
from providers.base import TTSProvider
from providers.media_chain import build_media_chain
from providers.music_chain import build_music_chain
from providers.registry import get_provider
from providers.stubs.tts import StubTTSProvider
from providers.tts_router import build_tts_router

from .audio.default import DefaultAudioModule
from .audio.engine import build_audio_engine
from .media.default import DefaultMediaModule
from .production.default import DefaultProductionModule
from .quality.default import DefaultQualityModule
from .research.default import DefaultResearchModule
from .scenes.default import DefaultScenesModule
from .script.default import DefaultScriptModule
from .script.metrics import MetricsProfile
from .shots.default import DefaultShotsModule


def build_orchestrator(
    settings: Settings,
    on_progress: Callable[[ProgressEvent], None] | None = None,
) -> PipelineOrchestrator:
    cache = DiskCache(settings.paths.cache_dir)
    languages = LanguageRegistry()

    def resolve_tts(locale: Locale, narrator: Narrator) -> TTSProvider:
        """Per-job TTS (§5/§7): pack preference + configured provider + voice
        from the Narrator. The audio module calls this; it never sees providers."""
        profile = languages.profile(locale.narration_language)
        voice = narrator.voice_id or profile.default_voice
        return build_tts_router(settings.tts, profile, voice=voice)

    def metrics_profile(locale: Locale) -> MetricsProfile:
        """Tokenizer/pacing profile for the script stage (§3)."""
        pack = languages.profile(locale.script_language)
        return MetricsProfile(
            script=pack.script,
            punctuation=pack.punctuation,
            readability=pack.readability,
            words_per_minute=pack.words_per_minute,
        )
    llm = get_provider(
        "llm",
        settings.llm.provider,
        model=settings.llm.model,
        api_key=settings.llm.api_key,
        temperature=settings.llm.temperature,
        max_output_tokens=settings.llm.max_output_tokens,
        base_url=settings.llm.base_url,
    )
    media = build_media_chain(
        settings.media.providers,
        cache,
        api_keys={"pexels": settings.media.pexels_api_key, "pixabay": settings.media.pixabay_api_key},
    )
    engine = build_audio_engine(
        settings.audio.engine, settings.production.ffmpeg_path, duck=settings.audio.music_duck
    )
    music = build_music_chain(
        settings.music.providers,
        api_keys={"pixabay": settings.music.pixabay_api_key},
        local_dir=settings.music.local_dir,
    )

    modules = {
        Stage.RESEARCH: DefaultResearchModule(llm, cache, config=settings.research),
        Stage.SCRIPT: DefaultScriptModule(llm, config=settings.script, metrics_resolver=metrics_profile),
        Stage.SCENES: DefaultScenesModule(),
        Stage.SHOTS: DefaultShotsModule(llm, config=settings.timeline),
        Stage.MEDIA: DefaultMediaModule(media, cache, config=settings.media),
        Stage.AUDIO: DefaultAudioModule(
            tts=StubTTSProvider(),
            music=music,
            engine=engine,
            cache=cache,
            config=settings.audio,
            voice=settings.tts.voice,
            ffmpeg_path=settings.production.ffmpeg_path,
            llm=llm,
            music_config=settings.music,
            tts_resolver=resolve_tts,
            subtitle_punctuation_resolver=lambda locale: languages.profile(locale.subtitle_language).punctuation,
            subtitle_script_resolver=lambda locale: languages.profile(locale.subtitle_language).script,
        ),
        Stage.PRODUCTION: DefaultProductionModule(
            settings.production,
            timeline_config=settings.timeline,
            burn_font_resolver=lambda locale: languages.profile(locale.subtitle_language).burn_font,
        ),
        Stage.QUALITY: DefaultQualityModule(config=settings.quality, timeline_config=settings.timeline),
    }
    return PipelineOrchestrator(
        modules,
        retries=settings.pipeline.retries,
        on_progress=on_progress,
        output_root=settings.paths.output_dir,
        locale_resolver=languages.resolve,
        narrator_resolver=languages.default_narrator,
    )
