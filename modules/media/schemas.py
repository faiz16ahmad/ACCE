"""Media search stage contracts."""

from __future__ import annotations

from pydantic import BaseModel, Field

from providers.models import MediaHit

# The module contract reuses the provider-level hit type so there is exactly
# one definition of "a media asset".
MediaAsset = MediaHit


class MediaResult(BaseModel):
    scene_index: int
    asset: MediaAsset


class MediaOutput(BaseModel):
    assets: list[MediaResult] = Field(default_factory=list)
