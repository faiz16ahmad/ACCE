"""Scene planning contracts (architecture v2, Phase 3).

Scenes own the *narrative*: the narration text, its estimated duration (a
planning aid only — the measured narration is the clock), and a rhythm hint.
Visual planning moved to the ShotPlan in Phase 2. The V1 visual fields below
are kept as **deprecated aliases** so legacy `scene_plan.json` files still
parse during migration; new consumers must read the ShotPlan instead.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Rhythm = Literal["low", "medium", "high", "intense"]


class Scene(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    scene_number: int = Field(alias="scene")
    narration_segment: str = Field(default="", alias="narration")
    estimated_duration: float = Field(default=0.0, alias="duration")
    rhythm: Rhythm = "medium"
    metadata: dict = Field(default_factory=dict)

    # --- Deprecated V1 visual fields (Phase 3: narrative-only) ---
    # Kept so old scene_plan.json files validate and lazy readers survive;
    # the ShotPlan is the single source of visual intent.
    visual_description: str = ""
    search_keywords: list[str] = Field(default_factory=list)
    visual_type: str = "stock_video"
    transition: str = "cut"

    @property
    def scene(self) -> int:
        """Back-compat: old name for `scene_number`."""
        return self.scene_number

    @property
    def narration(self) -> str:
        """Back-compat: old name for `narration_segment`."""
        return self.narration_segment

    @property
    def duration(self) -> float:
        """Back-compat: old name for `estimated_duration`."""
        return self.estimated_duration


class ScenePlan(BaseModel):
    scenes: list[Scene] = Field(default_factory=list)
