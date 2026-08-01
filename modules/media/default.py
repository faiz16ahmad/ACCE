"""Default media retrieval.

Scene -> Search -> Candidate List -> Ranking -> Selection -> Download ->
MediaPlan. The chain searches, ranks, and selects (stopping at the first
provider with a satisfactory asset); downloading is a separate post-selection
step and never influences ranking. When no provider finds a suitable asset, a
structured placeholder is returned so the pipeline still passes. The module
never branches on which provider produced a hit.
"""

from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import urlparse

from config.settings import MediaConfig
from core.errors import InputValidationError
from core.models import JobContext, StageResult
from core.stages import Stage
from memory.cache import DiskCache
from providers.base import ProviderError
from providers.download import download_asset
from providers.media_chain import MediaChain

from ..scenes.schemas import Scene, ScenePlan
from .interface import MediaModule
from .schemas import MediaAssetPlan, MediaPlan

log = logging.getLogger(__name__)

_VIDEO_TYPES = {"stock_video", "animation"}
_MAX_QUERY_CHARS = 200
_QUOTE_CHARS = {"'", '"'}


def refine_query(search_keywords: list[str]) -> str:
    """Join scene keywords into a provider-friendly query.

    Slight refinement only (strip quotes, collapse whitespace, cap length);
    the visual description is never rewritten.
    """
    text = " ".join(search_keywords or [])
    for char in _QUOTE_CHARS:
        text = text.replace(char, "")
    return " ".join(text.split())[:_MAX_QUERY_CHARS]


def _media_type_for(visual_type: str) -> str:
    return "video" if visual_type in _VIDEO_TYPES else "image"


def _file_extension(url: str) -> str:
    suffix = Path(urlparse(url).path).suffix
    return suffix if suffix and len(suffix) <= 5 else ".bin"


class DefaultMediaModule(MediaModule):
    def __init__(self, media: MediaChain, cache: DiskCache | None = None, config: MediaConfig | None = None) -> None:
        self.media = media
        self.cache = cache
        self.config = config or MediaConfig()

    def validate_input(self, ctx: JobContext) -> None:
        result = ctx.results.get(Stage.SCENES)
        if result is None or result.output is None:
            raise InputValidationError("media requires a scene plan")

    def run(self, ctx: JobContext) -> StageResult:
        plan: ScenePlan = ctx.results[Stage.SCENES].output
        total = len(plan.scenes)
        assets = []
        for index, scene in enumerate(plan.scenes, start=1):
            ctx.progress(f"Searching scene {index}/{total}...")
            asset = self._retrieve(ctx, scene, index)
            assets.append(asset)
            status = "downloaded" if asset.local_path else "placeholder"
            ctx.progress(f"Scene {index}/{total}: {status}")
        output = MediaPlan(assets=assets)
        downloaded = sum(1 for a in assets if a.local_path)
        ctx.progress(f"Complete: {downloaded}/{total} assets downloaded")
        return StageResult(
            stage=self.name,
            ok=True,
            output=output,
            artifacts_written=[self._save(ctx, "media_plan.json", output)],
        )

    def _retrieve(self, ctx: JobContext, scene: Scene, index: int) -> MediaAssetPlan:
        query = refine_query(scene.search_keywords)
        asset_type = _media_type_for(scene.visual_type)
        candidates = self.media.best(
            query,
            media_type=asset_type,
            count=self.config.candidates,
            threshold=self.config.satisfactory_score,
            target_duration=scene.duration,
        )
        if not candidates and asset_type == "video":
            # Video-first scenes fall back to still images when nothing fits.
            candidates = self.media.best(
                query,
                media_type="image",
                count=self.config.candidates,
                threshold=self.config.satisfactory_score,
            )
            asset_type = "image"

        asset_id = f"asset_{index:04d}"
        if not candidates:
            log.warning("no satisfactory asset for scene %d (%r); using placeholder", index, query)
            return MediaAssetPlan(
                scene_number=index,
                asset_id=asset_id,
                selected_provider="placeholder",
                asset_type="image",
                asset_url="",
                license="placeholder",
                search_query=query,
                candidates=[],
            )

        selected = candidates[0]
        local_path: Path | None = None
        if self.config.download:
            # Try ranked candidates in order; only give up (placeholder) when
            # every candidate fails to download.
            for candidate in candidates:
                try:
                    dest = ctx.store.resolve(self.name, f"scene_{index:02d}{_file_extension(candidate.url)}")
                    cache_root = self.cache.root if self.cache is not None else ctx.store.root
                    local_path = download_asset(
                        candidate.url, dest, cache_root, timeout=self.config.download_timeout
                    )
                    selected = candidate
                    break
                except ProviderError as exc:
                    log.warning(
                        "download failed for scene %d (%s): %s", index, candidate.provider, exc
                    )

        return MediaAssetPlan(
            scene_number=index,
            asset_id=asset_id,
            selected_provider=selected.provider,
            asset_type=selected.media_type,
            asset_url=selected.url,
            local_path=local_path,
            attribution=selected.attribution,
            license=selected.license,
            search_query=query,
            candidates=candidates,
        )
