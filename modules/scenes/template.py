"""Deterministic scene planning — the offline fallback.

Splits the script narration into timed scenes and assigns a visual plan
(description, search keywords, visual type, transition) by rule. Used when
the LLM provider is the stub, and as the safety net for any per-field LLM
visuals output that can't be applied. Only *plans* visuals — never retrieves
media or renders.
"""

from __future__ import annotations

import logging
import re

from ..script.metrics import count_words
from ..script.schemas import NarrationBlock, ScriptOutput
from .schemas import Rhythm, Scene, ScenePlan

log = logging.getLogger(__name__)

VISUAL_TYPES = ("stock_video", "stock_image", "animation", "infographic", "map", "text_overlay")

_MAX_SCENES = 8

# Words that make poor stock-search keywords (too generic or grammatical).
_GENERIC_WORDS = {
    "a", "an", "the", "and", "or", "but", "of", "in", "on", "at", "to", "for",
    "with", "about", "from", "by", "is", "are", "was", "were", "be", "been",
    "it", "its", "this", "that", "these", "those", "there", "they", "you",
    "we", "he", "she", "his", "her", "their", "our", "your", "will", "would",
    "can", "could", "should", "not", "have", "has", "had", "also", "very",
    "just", "more", "most", "some", "any", "each", "many", "how", "what",
    "why", "when", "where", "who", "video", "videos", "technology", "history",
    "information", "world", "people", "today", "time", "thing", "things",
}

_WORD_RE = re.compile(r"[A-Za-z']+")
_NUMBER_RE = re.compile(r"\d|percent|per\s?cent|million|billion|trillion|ratio|increase|decrease|average", re.I)
_MAP_RE = re.compile(r"\bmap\b|\bgeograph|located in|capital of|borders\b|region\b", re.I)
_TRANSITIONS = ("cut", "dissolve", "fade")


def keywords_for(text: str, topic: str, max_kw: int = 8) -> list[str]:
    """Concrete, stock-search-friendly keywords: topic words then content words."""
    keywords: list[str] = []
    seen: set[str] = set()
    for word in _WORD_RE.findall(topic) + _WORD_RE.findall(text):
        key = word.lower()
        if len(word) < 3 or key in _GENERIC_WORDS or key in seen:
            continue
        seen.add(key)
        keywords.append(key)
        if len(keywords) >= max_kw:
            break
    return keywords


def visual_type_for(segment: str, index: int, is_last: bool, style: str) -> str:
    if is_last:
        return "text_overlay"
    if style == "top10" and index == 0:
        return "text_overlay"
    if _NUMBER_RE.search(segment):
        return "infographic"
    if _MAP_RE.search(segment):
        return "map"
    # Deliberate variety for generic scenes (milestone 10): mostly motion
    # video, with stills and the occasional animation for visual rhythm.
    if index % 4 == 3:
        return "stock_image"
    if index % 4 == 2 and style in ("storytelling", "documentary"):
        return "animation"
    return "stock_video"


def transition_for(index: int, is_last: bool) -> str:
    if is_last:
        return "fade_to_black"
    return _TRANSITIONS[index % len(_TRANSITIONS)]


def _rhythm_for(index: int, count: int) -> Rhythm:
    """Deterministic rhythm hint: punchy hook and ending, steady body."""
    if count <= 1:
        return "medium"
    if index == 0 or index == count - 1:
        return "high"
    return "medium"


def visual_description_for(topic: str, segment: str, style: str) -> str:
    excerpt = " ".join(segment.split())[:160]
    return f"{style} visual of {topic}: {excerpt}".strip()


def plan_scenes(
    script: ScriptOutput,
    total_seconds: int,
    topic: str,
    style: str = "explainer",
    max_scenes: int = _MAX_SCENES,
) -> ScenePlan:
    blocks = list(script.narration)
    if not blocks:
        blocks = [NarrationBlock(paragraph=script.hook or script.summary or "")]
    scenes = blocks[:max_scenes]

    # Pacing follows the narration's own length when the script reports it,
    # so scene durations match the narration timing.
    total_target = float(total_seconds)
    if script.metrics is not None and script.metrics.estimated_duration > 0:
        total_target = script.metrics.estimated_duration

    words = [count_words(block.paragraph) for block in scenes]
    total_words = sum(words) or 1
    durations = [total_target * w / total_words for w in words]
    # Pacing rhythm (milestone 10): punchy hook and ending, fuller body —
    # then renormalize so the total still hits the target.
    count = len(durations)
    multipliers = [0.9 if i == 0 else (0.85 if i == count - 1 else 1.05) for i in range(count)]
    weighted = [d * m for d, m in zip(durations, multipliers, strict=True)]
    scale = total_target / (sum(weighted) or 1.0)
    durations = [round(w * scale, 1) for w in weighted]
    durations[-1] = round(total_target - sum(durations[:-1]), 1)  # last absorbs rounding

    plan: list[Scene] = []
    for index, (block, dur) in enumerate(zip(scenes, durations, strict=True)):
        segment = block.paragraph
        plan.append(
            Scene(
                scene_number=index + 1,
                narration_segment=segment,
                estimated_duration=max(1.0, dur),
                rhythm=_rhythm_for(index, count),
                metadata={"style": style, "topic": topic},
            )
        )
    return ScenePlan(scenes=plan)
