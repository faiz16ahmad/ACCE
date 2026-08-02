"""Shot plan normalizer — the enforcement boundary (architecture v2, Phase 3).

The Shot Planner (LLM or template) *proposes*; this normalizer *owns*
enforcement of limits and schema validity. It is fully deterministic and
config-driven: it clamps the per-scene shot count to `TimelineConfig` bounds,
repairs invalid enum values, fills empty search queries / descriptions,
guarantees contiguous positions, assigns stable global shot ids, and
synthesizes a single fallback shot for any scene the planner skipped. Both the
LLM output (raw dicts, not yet validated) and the template `ShotPlan` pass
through it, so one code path enforces the rules.
"""

from __future__ import annotations

import logging

from config.settings import TimelineConfig
from modules.scenes.schemas import ScenePlan

from ..scenes.template import keywords_for
from .schemas import CONTENT_KINDS, MEDIA_PREFERENCES, MOTION_INTENTS, Shot, ShotPlan
from .template import scene_id_for, shot_id_for

log = logging.getLogger(__name__)

_IMPORTANCES = ("low", "medium", "high", "critical")
_PURPOSES = ("establish", "action", "reaction", "detail", "main", "closing")


def _coerce(value: object, allowed: tuple[str, ...], default: str) -> str:
    return value if isinstance(value, str) and value in allowed else default


def _purpose_for(index: int, count: int) -> str:
    if count <= 1:
        return "main"
    if index == 0:
        return "establish"
    if index == count - 1:
        return "closing"
    return "main"


def _empty_entry(scene) -> dict:
    return {
        "shot_id": "",
        "scene_id": scene_id_for(scene.scene_number),
        "position": 0,
        "purpose": "",
        "visual_description": "",
        "search_queries": [],
        "content_kind": "",
        "media_preference": "",
        "motion_intent": "",
        "importance": "",
        "transition_out": "",
    }


def _repair(entry: dict, scene, index: int, count: int, topic: str) -> dict:
    """Repair one proposed shot entry: valid enums, non-empty text, order."""
    narration = scene.narration_segment
    purpose = _purpose_for(index, count)
    visual = str(entry.get("visual_description") or "").strip()
    if not visual:
        visual = f"visual of {topic}: {' '.join(narration.split())[:160]}"
    queries = [str(q).strip() for q in entry.get("search_queries") or [] if str(q).strip()]
    if not queries:
        queries = keywords_for(narration, topic)
    return {
        "shot_id": "",
        "scene_id": scene_id_for(scene.scene_number),
        "position": index + 1,
        "purpose": _coerce(entry.get("purpose"), _PURPOSES, purpose),
        "visual_description": visual,
        "search_queries": queries[:8],
        "content_kind": _coerce(entry.get("content_kind"), CONTENT_KINDS, "stock_video"),
        "media_preference": _coerce(entry.get("media_preference"), MEDIA_PREFERENCES, "either"),
        "motion_intent": _coerce(entry.get("motion_intent"), MOTION_INTENTS, "none"),
        "importance": _coerce(entry.get("importance"), _IMPORTANCES, "medium"),
        "transition_out": str(entry.get("transition_out") or "").strip() or "cut",
    }


def normalize_shot_plan(
    proposed: ShotPlan | list[dict],
    scenes: ScenePlan,
    config: TimelineConfig,
    topic: str = "",
) -> ShotPlan:
    """Return a schema-valid `ShotPlan` bounded by `config` limits.

    Accepts either a template `ShotPlan` or raw LLM entries (dicts). Unknown
    scenes are dropped; empty scenes get one synthesized shot; excess shots
    per scene are clamped; ids and positions are reassigned deterministically.
    """
    if isinstance(proposed, ShotPlan):
        entries: list[dict] = [shot.model_dump() for shot in proposed.shots]
    else:
        entries = [dict(entry) for entry in proposed if isinstance(entry, dict)]

    scene_numbers = [scene.scene_number for scene in scenes.scenes]
    number_by_id = {scene_id_for(number): number for number in scene_numbers}
    by_number: dict[int, list[dict]] = {number: [] for number in scene_numbers}
    for entry in entries:
        number = number_by_id.get(str(entry.get("scene_id", "")))
        if number is None:
            candidate = entry.get("scene", entry.get("scene_number"))
            number = candidate if isinstance(candidate, int) and candidate in by_number else None
        if number is None:
            log.warning("dropping shot with unknown scene: %r", entry.get("scene_id"))
            continue
        by_number[number].append(entry)

    max_shots = max(config.min_shots, config.max_shots)
    normalized: list[dict] = []
    for number in scene_numbers:
        scene = next(s for s in scenes.scenes if s.scene_number == number)
        group = by_number[number][:max_shots]
        if not group:
            group = [_empty_entry(scene)]
        for index, entry in enumerate(group):
            normalized.append(_repair(entry, scene, index, len(group), topic))

    shots = [Shot(**entry) for entry in normalized]
    for i, shot in enumerate(shots):
        shot.shot_id = shot_id_for(i + 1)
    return ShotPlan(shots=shots)
