"""Wiring: build a fully-injected pipeline from settings.

All dependencies (providers, cache, engine, config) are resolved here and
handed to modules via constructors — modules never resolve globals.
"""

from __future__ import annotations

from collections.abc import Callable

from config.settings import Settings
from core.models import ProgressEvent
from core.orchestrator import PipelineOrchestrator
from core.stages import Stage
from memory.cache import DiskCache
from providers.media_chain import build_media_chain
from providers.registry import get_provider

from .audio.default import DefaultAudioModule
from .audio.engine import build_audio_engine
from .media.default import DefaultMediaModule
from .production.default import DefaultProductionModule
from .quality.default import DefaultQualityModule
from .research.default import DefaultResearchModule
from .scenes.default import DefaultScenesModule
from .script.default import DefaultScriptModule


def build_orchestrator(
    settings: Settings,
    on_progress: Callable[[ProgressEvent], None] | None = None,
) -> PipelineOrchestrator:
    cache = DiskCache(settings.paths.cache_dir)
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
    engine = build_audio_engine(settings.audio.engine, settings.production.ffmpeg_path)

    modules = {
        Stage.RESEARCH: DefaultResearchModule(llm, cache, config=settings.research),
        Stage.SCRIPT: DefaultScriptModule(llm, config=settings.script),
        Stage.SCENES: DefaultScenesModule(llm),
        Stage.MEDIA: DefaultMediaModule(media, cache, config=settings.media),
        Stage.AUDIO: DefaultAudioModule(
            tts=get_provider("tts", settings.tts.provider),
            music=get_provider("music", settings.music.provider),
            engine=engine,
            cache=cache,
            config=settings.audio,
            voice=settings.tts.voice,
        ),
        Stage.PRODUCTION: DefaultProductionModule(settings.production),
        Stage.QUALITY: DefaultQualityModule(),
    }
    return PipelineOrchestrator(
        modules,
        retries=settings.pipeline.retries,
        on_progress=on_progress,
        output_root=settings.paths.output_dir,
    )
