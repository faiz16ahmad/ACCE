"""Scene planner stage contracts."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Scene(BaseModel):
    """One timed scene (JSON shape matches the master prompt)."""

    scene: int
    duration: int
    narration: str = ""
    visual_description: str = ""
    search_keywords: list[str] = Field(default_factory=list)


class ScenePlan(BaseModel):
    scenes: list[Scene] = Field(default_factory=list)
