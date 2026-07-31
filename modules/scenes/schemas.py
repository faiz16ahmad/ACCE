"""Scene planner stage contracts.

A scene is one timed narration segment plus its visual plan. Field names
match the master prompt (`scene_number`, `narration_segment`,
`estimated_duration`, `visual_type`, `transition`); the older names
`scene` / `narration` / `duration` remain available as read-only aliases so
downstream modules (audio, media, quality) keep working unchanged. This stage
only *plans* visuals — it never retrieves media or renders.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

VisualType = Literal[
    "stock_video", "stock_image", "animation", "infographic", "map", "text_overlay"
]


class Scene(BaseModel):
    """One timed scene with a visual plan."""

    model_config = ConfigDict(populate_by_name=True)

    scene_number: int = Field(alias="scene")
    narration_segment: str = Field(default="", alias="narration")
    estimated_duration: float = Field(default=0.0, alias="duration")
    visual_description: str = ""
    search_keywords: list[str] = Field(default_factory=list)
    visual_type: VisualType = "stock_video"
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
