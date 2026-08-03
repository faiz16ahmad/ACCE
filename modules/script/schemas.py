"""Script stage contracts.

The script is Hook → Main Body → Ending narration, written from ResearchOutput
only. `metrics` carries simple quality signals (word count, estimated
duration, readability, duration match); `metadata` records how it was made
(style, durations, generator). Scene-level concerns (visuals, camera,
keywords) belong to the Scene Planner stage, never here.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class NarrationBlock(BaseModel):
    paragraph: str


class ReadabilityStats(BaseModel):
    words: int
    sentences: int
    syllables: int
    reading_ease: float  # Flesch Reading Ease (0–100, higher = easier)
    grade_level: float  # Flesch-Kincaid Grade Level


class ScriptMetrics(BaseModel):
    word_count: int
    estimated_duration: float  # seconds
    words_per_minute: int
    # None when the language's pack says `readability: none` (Flesch is
    # English-only; e.g. Hindi). Quality skips the readability check then.
    readability: ReadabilityStats | None = None
    duration_match: float | None = None  # 0..1; None when no duration requested


class ScriptMetadata(BaseModel):
    style: str
    requested_duration: int | None = None
    estimated_duration: float = 0.0
    word_count: int = 0
    generated_by: str = "template"  # "template" | "llm:<provider>"
    language: str = "en"


class ScriptOutput(BaseModel):
    hook: str
    body: list[str] = Field(default_factory=list)
    ending: str
    narration: list[NarrationBlock] = Field(default_factory=list)
    style: str = "explainer"
    language: str = "en"  # script_language from ctx.locale
    metrics: ScriptMetrics | None = None
    metadata: ScriptMetadata | None = None
