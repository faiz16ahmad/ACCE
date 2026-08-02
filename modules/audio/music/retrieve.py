"""Music retrieval — deterministic ranking (architecture-audio.md §3.5).

The planner never selects files (A1) and never knows filenames. This module
maps a normalized `MusicSelection` to ranked candidates from a local library
via an additive weighted score. The same selection + same library always
yields the same order (A8): weights are config, the tie-break is a stable
asset id, and each candidate records per-criterion `reasons` for
explainability.

Phase 1: implemented and unit-tested, but not yet wired into the audio module.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path

from config.settings import MusicConfig

from .schemas import MusicAsset, MusicSelection, RankedAsset

log = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def rank_assets(
    candidates: list[MusicAsset],
    selection: MusicSelection,
    config: MusicConfig | None = None,
) -> list[RankedAsset]:
    """Score and sort candidates deterministically, rejecting poor matches.

    Returns ranked `RankedAsset`s (best first). Candidates whose total score is
    below `satisfactory_score` are dropped so a weak match cannot win by
    default.
    """
    cfg = config or MusicConfig()
    scored = [rank_one(asset, selection, cfg) for asset in candidates]
    scored = [r for r in scored if r.score >= cfg.music_satisfactory_score]
    # Deterministic order: score desc, then stable asset_id asc (A8).
    scored.sort(key=lambda r: (-r.score, r.asset.asset_id))
    return scored


def rank_one(asset: MusicAsset, selection: MusicSelection, config: MusicConfig) -> RankedAsset:
    """Weighted additive score with per-criterion reasons (§3.5)."""
    reasons = {
        "duration": _duration_reason(asset, selection.duration_hint),
        "tempo": _tempo_reason(asset, selection.intent.tempo_bpm, config),
        "energy": 0.5,  # neutral in V1 (assets carry no energy metadata yet)
        "keyword": _keyword_reason(asset, selection),
    }
    weights = {
        "duration": config.music_rank_duration,
        "tempo": config.music_rank_tempo,
        "energy": config.music_rank_energy,
        "keyword": config.music_rank_keyword,
    }
    total = sum(weights.values()) or 1.0
    score = round(sum(reasons[k] * weights[k] for k in reasons) / total, 4)
    return RankedAsset(asset=asset, score=score, reasons=reasons)


def _duration_reason(asset: MusicAsset, duration_hint: float) -> float:
    """Loop-aware coverage (the timeline loops beds, §5).

    1.0 when the bed covers the clock without looping; below that, degradation
    is proportional to how many loops would be needed — a shorter bed is never a
    total mismatch, so it can still be selected over silence (A10) when it
    clears the satisfactory threshold. Unknown duration is neutral (0.5), not
    disqualifying (the retriever measures local files where possible)."""
    if duration_hint <= 0:
        return 1.0
    if not asset.duration:
        return 0.5
    if asset.duration >= duration_hint:
        return 1.0
    return round(0.5 + 0.5 * (asset.duration / duration_hint), 4)


def _tempo_reason(asset: MusicAsset, tempo_bpm: int | None, config: MusicConfig) -> float:
    """Distance-based fit; neutral (0.5) when either bpm is unknown."""
    if tempo_bpm is None or not asset.bpm:
        return 0.5
    tolerance = max(config.tempo_tolerance, 1.0)
    return max(0.0, 1.0 - abs(asset.bpm - tempo_bpm) / tolerance)


def _keyword_reason(asset: MusicAsset, selection: MusicSelection) -> float:
    """Normalized token overlap between the asset title/path and the query
    (genre_hint + emotion + style words) — the existing local-provider
    relevance, made explicit and bounded."""
    query = " ".join(
        token for token in (selection.genre_hint, selection.intent.emotion, selection.intent.style) if token
    )
    query_tokens = set(_TOKEN_RE.findall(query.lower()))
    if not query_tokens:
        return 0.5
    name = asset.title or (asset.local_path.stem if asset.local_path else "")
    name_tokens = set(_TOKEN_RE.findall(name.lower()))
    if not name_tokens:
        return 0.0
    hits = len(query_tokens & name_tokens)
    return round(hits / len(query_tokens), 4)


def stable_cache_key(selection: MusicSelection, library: list[MusicAsset]) -> str:
    """Deterministic cache key: the selection plus the library's stable
    identity (asset ids sorted), so identical requests never re-rank."""
    payload = {
        "selection": selection.model_dump(mode="json"),
        "assets": sorted(asset.asset_id for asset in library),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _music_assets_in(directory: Path) -> list[Path]:
    """Flat listing helper (the audio stage will own real library scanning;
    kept here so the ranking can be unit-tested against a temp dir)."""
    suffixes = {".mp3", ".wav", ".ogg", ".m4a", ".flac"}
    return sorted(p for p in directory.rglob("*") if p.suffix.lower() in suffixes)
