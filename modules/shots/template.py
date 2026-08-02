"""Deterministic shot planning — the key-free fallback (architecture v2).

Phase 3: converts `ScenePlan` narration into a multi-shot `ShotPlan`. The
template is the offline fallback for the LLM Shot Planner: it proposes 1-3
shots per scene (proportional to narration length), derives search queries and
content kinds from the narration text, and stays fully deterministic. It only
*plans* shots — never retrieves media, times clips, or renders.
"""

from __future__ import annotations

import re

from ..scenes.schemas import ScenePlan
from ..scenes.template import keywords_for, transition_for, visual_type_for
from .schemas import ContentKind, MediaPreference, Shot, ShotPlan

# V1 visual_type -> V2 content_kind. Real content providers (animation,
# infographic, AI media) land later; these mappings keep the fallback faithful.
_CONTENT_KIND_BY_VISUAL_TYPE: dict[str, ContentKind] = {
    "stock_video": "stock_video",
    "stock_image": "stock_image",
    "animation": "stock_video",  # no animation kind yet; motion video is closest
    "infographic": "chart",  # no infographic kind yet; chart is closest
    "map": "map",
    "text_overlay": "text",
}

_MEDIA_PREFERENCE_BY_VISUAL_TYPE: dict[str, MediaPreference] = {
    "stock_video": "video",
    "animation": "video",
    "stock_image": "image",
    "infographic": "image",
    "map": "image",
    "text_overlay": "either",  # text scenes carry no media
}

_MAX_SHOTS_PER_SCENE = 3


def scene_id_for(scene_number: int) -> str:
    """Stable edit-layer id for a scene (matches the V2 id scheme)."""
    return f"scene_{scene_number:04d}"


def shot_id_for(index: int) -> str:
    """Global, zero-padded shot id (`shot_0001`, …)."""
    return f"shot_{index:04d}"


def _purpose_for(index: int, count: int) -> str:
    if count <= 1:
        return "main"
    if index == 0:
        return "establish"
    if index == count - 1:
        return "closing"
    return "main"


def _shot_count_for(word_count: int, max_shots: int = _MAX_SHOTS_PER_SCENE) -> int:
    if word_count <= 25:
        return 1
    if word_count <= 60:
        return min(2, max_shots)
    return min(3, max_shots)


def _group_sentences(sentences: list[str], count: int) -> list[str]:
    """Pack sentences into `count` contiguous, word-balanced groups."""
    lengths = [len(s.split()) for s in sentences]
    total = sum(lengths) or 1
    groups: list[list[str]] = [[] for _ in range(count)]
    group = 0
    acc = 0
    for i, sentence in enumerate(sentences):
        groups[group].append(sentence)
        acc += lengths[i]
        if group < count - 1 and i < len(sentences) - 1 and acc >= total * (group + 1) / count:
            group += 1
    return [" ".join(g) for g in groups if g]


def _chunk_text(text: str, count: int) -> list[str]:
    """Split narration into `count` contiguous chunks, preferring sentence bounds."""
    text = " ".join(text.split())
    if count <= 1 or not text:
        return [text] if text else [""]
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    if len(sentences) >= count:
        return _group_sentences(sentences, count)
    # Word-level fallback for very short text.
    words = text.split()
    chunks: list[str] = []
    for i in range(count):
        lo = len(words) * i // count
        hi = len(words) * (i + 1) // count
        chunk = " ".join(words[lo:hi]).strip()
        if chunk:
            chunks.append(chunk)
    return chunks


def _shot_intent(
    chunk: str,
    index: int,
    count: int,
    scene_number: int,
    topic: str,
    style: str,
    is_last_scene: bool,
) -> Shot:
    # The text-overlay / fade-to-black closer belongs to the *final scene's*
    # last shot only, not to every single-shot scene.
    is_last = is_last_scene and index == count - 1
    visual_type = visual_type_for(chunk, index, is_last, style)
    excerpt = " ".join(chunk.split())[:160]
    return Shot(
        shot_id=shot_id_for(index + 1),
        scene_id=scene_id_for(scene_number),
        position=index + 1,
        purpose=_purpose_for(index, count),
        visual_description=f"{style} visual of {topic}: {excerpt}".strip(),
        search_queries=keywords_for(chunk, topic),
        content_kind=_CONTENT_KIND_BY_VISUAL_TYPE.get(visual_type, "stock_video"),
        media_preference=_MEDIA_PREFERENCE_BY_VISUAL_TYPE.get(visual_type, "either"),
        motion_intent="none",
        importance="high" if index in (0, count - 1) else "medium",
        transition_out=transition_for(index, is_last),
    )


def plan_shots(
    scenes: ScenePlan,
    topic: str = "",
    style: str = "explainer",
    max_shots_per_scene: int = _MAX_SHOTS_PER_SCENE,
) -> ShotPlan:
    """Propose a multi-shot plan from scene narration (deterministic)."""
    shots: list[Shot] = []
    scene_list = scenes.scenes
    for scene_index, scene in enumerate(scene_list):
        is_last_scene = scene_index == len(scene_list) - 1
        word_count = len(scene.narration_segment.split())
        count = _shot_count_for(word_count, max_shots_per_scene)
        chunks = _chunk_text(scene.narration_segment, count)
        for index, chunk in enumerate(chunks):
            shot = _shot_intent(
                chunk, index, len(chunks), scene.scene_number, topic, style, is_last_scene
            )
            shot.shot_id = shot_id_for(len(shots) + 1)  # global counter
            shots.append(shot)
    return ShotPlan(shots=shots)
