"""Research stage contracts.

The research artifact is the richest contract in the pipeline. Facts carry
their supporting sources, and `verified` reflects whether at least one of
those sources was successfully fetched during the run (verification =
live fetch, not the LLM's opinion). Downstream stages consume `topic`,
`facts[].content`, `summary`, plus the optional angles/entities/chronology.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ResearchFact(BaseModel):
    content: str
    sources: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    verified: bool = False  # True iff >=1 supporting source fetched OK this run
    verification_note: str | None = None


class ResearchSource(BaseModel):
    url: str
    title: str
    fetched: bool = False
    http_status: int | None = None
    excerpt: str | None = None
    accessed_at: str | None = None


class ResearchAngle(BaseModel):
    title: str
    description: str = ""


class Entity(BaseModel):
    name: str
    kind: Literal["person", "organization", "concept", "place", "product", "other"] = "other"


class ChronologyEvent(BaseModel):
    date: str
    title: str
    description: str = ""
    sources: list[str] = Field(default_factory=list)


class ResearchMetadata(BaseModel):
    topic: str
    instructions: list[str] = Field(default_factory=list)
    model: str = ""
    generated_at: str = ""
    fetch_summary: str = ""
    verification_summary: str = ""
    fact_count: int = 0
    source_count: int = 0


class ResearchOutput(BaseModel):
    """Structured research for a topic (JSON shape matches the master prompt)."""

    topic: str
    facts: list[ResearchFact] = Field(default_factory=list)
    sources: list[ResearchSource] = Field(default_factory=list)
    summary: str = ""
    angles: list[ResearchAngle] = Field(default_factory=list)
    entities: list[Entity] = Field(default_factory=list)
    chronology: list[ChronologyEvent] = Field(default_factory=list)
    metadata: ResearchMetadata | None = None
