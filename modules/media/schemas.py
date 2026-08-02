"""Media retrieval stage contracts.

A `MediaPlan` holds one `MediaAssetPlan` per scene: the full ranked candidate
list plus which candidate was selected (and optionally downloaded). Assets are
referenced by a stable `asset_id` so later stages avoid depending on file
paths. The older `scene_index` / `asset.local_path` access patterns are kept
as read-only views so the quality stage works unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from providers.models import MediaHit


class _SelectedAsset(BaseModel):
    """Compat view of the selected asset for earlier consumers (e.g. quality)."""

    provider: str
    media_type: Literal["image", "video"]
    url: str
    local_path: Path | None = None
    license: str
    attribution: str | None = None


class MediaAssetPlan(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    scene_number: int = Field(alias="scene_index")
    shot_id: str = ""  # owning shot (architecture v2); "" for legacy/1:1 assets
    asset_id: str
    selected_provider: str
    asset_type: Literal["image", "video"]
    asset_url: str
    local_path: Path | None = None
    attribution: str | None = None
    license: str = "unknown"
    search_query: str = ""
    candidates: list[MediaHit] = Field(default_factory=list)

    @property
    def scene_index(self) -> int:
        """Back-compat: old name for `scene_number`."""
        return self.scene_number

    @property
    def asset(self) -> _SelectedAsset:
        """Back-compat view of the selected asset for earlier consumers."""
        return _SelectedAsset(
            provider=self.selected_provider,
            media_type=self.asset_type,
            url=self.asset_url,
            local_path=self.local_path,
            license=self.license,
            attribution=self.attribution,
        )


class MediaPlan(BaseModel):
    assets: list[MediaAssetPlan] = Field(default_factory=list)
