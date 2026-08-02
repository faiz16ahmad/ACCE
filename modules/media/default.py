"""Default media retrieval (architecture v2).

Shot -> Search -> Candidate List -> Ranking -> Selection -> Download ->
MediaPlan. The chain searches, ranks, and selects per **shot** (stopping at
the first provider with a satisfactory asset); downloading is a separate
post-selection step and never influences ranking. Media fills the visual slots
a Shot defines — it never reshapes the edit, and its output never influences
timing (invariant I6). When no provider finds a suitable asset, a structured
placeholder is returned so the pipeline still passes.
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

from ..scenes.schemas import ScenePlan
from ..shots.schemas import Shot, ShotPlan
from ..shots.template import scene_id_for
from .interface import MediaModule
from .schemas import MediaAssetPlan, MediaPlan

log = logging.getLogger(__name__)

_VIDEO_KINDS = {"stock_video"}  # content kinds that prefer moving footage
_MAX_QUERY_CHARS = 200
_QUOTE_CHARS = {"'", '"'}


def refine_query(search_keywords: list[str]) -> str:
    """Join shot/scene keywords into a provider-friendly query.

    Slight refinement only (strip quotes, collapse whitespace, cap length);
    the visual description is never rewritten.
    """
    text = " ".join(search_keywords or [])
    for char in _QUOTE_CHARS:
        text = text.replace(char, "")
    return " ".join(text.split())[:_MAX_QUERY_CHARS]


def _asset_type_for(shot: Shot) -> str:
    """Resolve the media family a shot wants.

    `content_kind` drives the base family; `media_preference` refines it
    ("video"/"image" force the family, "either" defers to the content kind).
    In the Phase 2 1:1 pass-through this reproduces the V1
    `visual_type` -> media-type mapping exactly.
    """
    if shot.media_preference == "video":
        return "video"
    if shot.media_preference == "image":
        return "image"
    return "video" if shot.content_kind in _VIDEO_KINDS else "image"


def _file_extension(url: str) -> str:
    suffix = Path(urlparse(url).path).suffix
    return suffix if suffix and len(suffix) <= 5 else ".bin"


class DefaultMediaModule(MediaModule):
    def __init__(self, media: MediaChain, cache: DiskCache | None = None, config: MediaConfig | None = None) -> None:
        self.media = media
        self.cache = cache
        self.config = config or MediaConfig()

    def validate_input(self, ctx: JobContext) -> None:
        result = ctx.results.get(Stage.SHOTS)
        if result is None or result.output is None:
            raise InputValidationError("media requires a shot plan")

    def run(self, ctx: JobContext) -> StageResult:
        shot_plan: ShotPlan = ctx.results[Stage.SHOTS].output
        scenes = ctx.results[Stage.SCENES].output if ctx.results.get(Stage.SCENES) else None
        # Per-scene context (scene number + estimated duration) keyed by the
        # shot's scene id. Durations are a *search hint* for video providers
        # only — they never enter the Timeline (I6, I8).
        scene_ctx = (
            {scene_id_for(scene.scene_number): (scene.scene_number, scene.estimated_duration) for scene in scenes.scenes}
            if scenes is not None
            else {}
        )
        total = len(shot_plan.shots)
        assets = []
        for index, shot in enumerate(shot_plan.shots, start=1):
            ctx.progress(f"Searching shot {index}/{total}...")
            asset = self._retrieve(ctx, shot, index, scene_ctx)
            assets.append(asset)
            status = "downloaded" if asset.local_path else "placeholder"
            ctx.progress(f"Shot {index}/{total}: {status}")
        output = MediaPlan(assets=assets)
        downloaded = sum(1 for a in assets if a.local_path)
        ctx.progress(f"Complete: {downloaded}/{total} assets downloaded")
        return StageResult(
            stage=self.name,
            ok=True,
            output=output,
            artifacts_written=[self._save(ctx, "media_plan.json", output)],
        )

    def _retrieve(
        self,
        ctx: JobContext,
        shot: Shot,
        index: int,
        scene_ctx: dict[str, tuple[int, float | None]],
    ) -> MediaAssetPlan:
        query = refine_query(shot.search_queries)
        asset_type = _asset_type_for(shot)
        scene_number, target_duration = scene_ctx.get(shot.scene_id, (index, None))
        candidates = self.media.best(
            query,
            media_type=asset_type,
            count=self.config.candidates,
            threshold=self.config.satisfactory_score,
            target_duration=target_duration,
        )
        if not candidates and asset_type == "video":
            # Video-first shots fall back to still images when nothing fits.
            candidates = self.media.best(
                query,
                media_type="image",
                count=self.config.candidates,
                threshold=self.config.satisfactory_score,
            )
            asset_type = "image"

        asset_id = f"asset_{index:04d}"
        if not candidates:
            log.warning("no satisfactory asset for shot %d (%r); using placeholder", index, query)
            return MediaAssetPlan(
                scene_number=scene_number,
                shot_id=shot.shot_id,
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
                        "download failed for shot %d (%s): %s", index, candidate.provider, exc
                    )

        return MediaAssetPlan(
            scene_number=scene_number,
            shot_id=shot.shot_id,
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
