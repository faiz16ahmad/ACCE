"""Quality check stage contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class QualityIssue(BaseModel):
    level: Literal["info", "warning", "error"]
    stage: str
    message: str


class QualityReport(BaseModel):
    passed: bool
    issues: list[QualityIssue] = Field(default_factory=list)
    summary: str = ""
