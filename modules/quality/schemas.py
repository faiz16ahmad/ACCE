"""Quality check stage contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

IssueLevel = Literal["info", "warning", "error"]


class QualityIssue(BaseModel):
    level: IssueLevel
    stage: str
    message: str
    code: str = ""  # stable machine-readable code, e.g. "audio.missing_narration"
    suggested_fix: str | None = None  # advisory, human-readable — never executed


class QualityReport(BaseModel):
    passed: bool
    score: float = 0.0
    issues: list[QualityIssue] = Field(default_factory=list)
    warnings: int = 0
    errors: int = 0
    recommended_retry_stage: str | None = None
    metadata: dict = Field(default_factory=dict)
    summary: str = ""
