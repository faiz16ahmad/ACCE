"""Default media search implementation.

Queries the cache-first media chain for each scene (video preferred, image as
fallback) and records the best hit per scene. Downloads happen in the media
milestone — V1 stubs return URL-only hits.
"""

from __future__ import annotations

import logging

from core.errors import InputValidationError
from core.models import JobContext, StageResult
from core.stages import Stage
from memory.cache import DiskCache
from providers.media_chain import MediaChain
from providers.models import MediaHit

from ..scenes.schemas import ScenePlan
from .interface import MediaModule
from .schemas import MediaOutput, MediaResult

log = logging.getLogger(__name__)


class DefaultMediaModule(MediaModule):
    def __init__(self, media: MediaChain, cache: DiskCache | None = None) -> None:
        self.media = media
        self.cache = cache

    def validate_input(self, ctx: JobContext) -> None:
        result = ctx.results.get(Stage.SCENES)
        if result is None or result.output is None:
            raise InputValidationError("media requires a scene plan")

    def _best(self, query: str) -> MediaHit:
        hits = self.media.search(query, media_type="video", count=1)
        if hits:
            return hits[0]
        hits = self.media.search(query, media_type="image", count=1)
        if hits:
            return hits[0]
        log.warning("no media hit for %r; using placeholder", query)
        return MediaHit(provider="placeholder", media_type="image", url="", license="placeholder")

    def run(self, ctx: JobContext) -> StageResult:
        plan: ScenePlan = ctx.results[Stage.SCENES].output
        assets: list[MediaResult] = []
        written = []
        for scene in plan.scenes:
            query = " ".join(scene.search_keywords) or scene.narration
            media_result = MediaResult(scene_index=scene.scene, asset=self._best(query))
            assets.append(media_result)
            written.append(self._save(ctx, f"scene_{scene.scene:02d}.json", media_result))

        output = MediaOutput(assets=assets)
        written.append(self._save(ctx, "media.json", output))
        return StageResult(stage=self.name, ok=True, output=output, artifacts_written=written)
