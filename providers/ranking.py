"""Deterministic V1 asset ranking heuristics (no AI).

Scores a `MediaHit` against the search query and desired media type on
resolution, orientation, duration (video), license, and keyword match.
Lower-ranked candidates are preserved in the MediaPlan for review and future
AI ranking — selection here is only an ordering, never a deletion.
"""

from __future__ import annotations

import re

from .models import MediaHit

_WORD_RE = re.compile(r"[a-z0-9']+")

_PERMISSIVE_LICENSES = {"pexels", "pixabay", "wikimedia", "royalty-free"}


def _tokens(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def _license_score(license: str) -> float:
    lic = (license or "").strip().lower()
    if not lic or lic == "unknown":
        return 0.4
    if lic in _PERMISSIVE_LICENSES or "cc" in lic or "public domain" in lic:
        return 1.0
    return 0.7


def _resolution_score(hit: MediaHit) -> float:
    if hit.width and hit.height:
        return min(1.0, (hit.width * hit.height) / (1920 * 1080))
    return 0.3


def _orientation_score(hit: MediaHit) -> float:
    if not (hit.width and hit.height):
        return 0.5
    if hit.width >= hit.height:
        return 1.0
    return 0.4 if hit.height > hit.width * 1.4 else 0.7


def _duration_score(hit: MediaHit, media_type: str) -> float:
    if media_type != "video" or hit.duration is None:
        return 1.0
    return 1.0 if 5 <= hit.duration <= 60 else 0.3


def _keyword_score(hit: MediaHit, query: str) -> float:
    tokens = _tokens(query)
    if not tokens:
        return 1.0
    hay = _tokens(f"{hit.title or ''} {hit.attribution or ''}")
    if not hay:
        return 0.3
    return len(tokens & hay) / len(tokens)


def rank_hit(hit: MediaHit, query: str, media_type: str) -> float:
    """Deterministic quality score in [0, 1]."""
    res = _resolution_score(hit)
    orient = _orientation_score(hit)
    lic = _license_score(hit.license)
    kw = _keyword_score(hit, query)
    if media_type == "video":
        dur = _duration_score(hit, media_type)
        return round(0.30 * res + 0.20 * orient + 0.20 * dur + 0.15 * lic + 0.15 * kw, 3)
    return round(0.35 * res + 0.25 * orient + 0.20 * lic + 0.20 * kw, 3)


def rank_hits(hits: list[MediaHit], query: str, media_type: str) -> list[MediaHit]:
    """Return `hits` ordered best-first (stable for ties)."""
    return sorted(hits, key=lambda hit: rank_hit(hit, query, media_type), reverse=True)


def is_satisfactory(score: float, threshold: float = 0.6) -> bool:
    return score >= threshold
