"""Shot planner stage contracts (architecture v2).

The edit layer separates concerns by object: a **Scene** is narrative, a
**Shot** is an editing intent, a `MediaAsset` is a file. A Shot names *what*
the viewer should see and *how* it should be treated — content kind, media
preference, motion intent, importance — never *which file* backs it and never
a duration. Media Retrieval fills the shot; the Timeline later binds it to a
concrete time (invariants I2, I6).

Phase 1 (pass-through) produces exactly one shot per scene; multi-shot
planning with pacing lands in Phase 3.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Bounded enums so the LLM (Phase 3) and the deterministic template stay stable.
ShotImportance = Literal["low", "medium", "high", "critical"]
ContentKind = Literal["stock_video", "stock_image", "text", "chart", "map"]
MediaPreference = Literal["video", "image", "either"]
MotionIntent = Literal["none", "zoom_in", "zoom_out", "pan"]

CONTENT_KINDS: tuple[str, ...] = ("stock_video", "stock_image", "text", "chart", "map")
MEDIA_PREFERENCES: tuple[str, ...] = ("video", "image", "either")
MOTION_INTENTS: tuple[str, ...] = ("none", "zoom_in", "zoom_out", "pan")


class Shot(BaseModel):
    """One ordered visual intent within a scene."""

    shot_id: str
    scene_id: str  # owner; a shot never leaves its scene (I9)
    position: int  # ordering within the scene
    purpose: str = "main"  # "establish" | "action" | "reaction" | "detail" | ...
    visual_description: str = ""
    search_queries: list[str] = Field(default_factory=list)
    content_kind: ContentKind = "stock_video"
    media_preference: MediaPreference = "either"
    motion_intent: MotionIntent = "none"
    importance: ShotImportance = "medium"
    transition_out: str = "cut"


class ShotPlan(BaseModel):
    shots: list[Shot] = Field(default_factory=list)
