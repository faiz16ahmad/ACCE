"""Deterministic script template — the offline fallback.

Used only when the LLM provider is the stub, so the pipeline stays runnable
without an API key. The primary path is LLM-driven (see `default.py`); this
module just guarantees a valid Hook → Body → Ending structure.
"""

from __future__ import annotations

import logging
import re

from ..research.schemas import ResearchOutput
from .schemas import NarrationBlock, ScriptOutput

log = logging.getLogger(__name__)

STYLES = ("educational", "documentary", "storytelling", "news", "top10", "explainer")

# Style guidance given to the LLM on the primary path.
STYLE_DIRECTIVES = {
    "educational": "Adopt a clear, instructive tone that explains concepts step by step.",
    "documentary": "Adopt a documentary tone with measured, narrative pacing and context.",
    "storytelling": "Adopt a storytelling tone: a compelling narrative arc with vivid language.",
    "news": "Adopt a news-briefing tone: tight, factual, direct sentences.",
    "top10": "Present the main body as a countdown of distinct numbered points.",
    "explainer": "Adopt a friendly explainer tone: simple, relatable, conversational.",
}

# Hook openers and ending closers used by the template fallback.
_HOOKS = {
    "educational": "Let's learn what {topic} is really about.",
    "documentary": "The story of {topic} is bigger than most people realize.",
    "storytelling": "It begins, as most stories do, with {topic}.",
    "news": "Here is what you need to know about {topic}.",
    "top10": "We are counting down the most important things about {topic}.",
    "explainer": "Ever wondered how {topic} actually works?",
}

_ENDINGS = {
    "educational": "So the next time you think about {topic}, remember how the pieces fit together.",
    "documentary": "That is the story of {topic} — and it is still being written.",
    "storytelling": "And that is how the story of {topic} unfolds.",
    "news": "That is the current picture on {topic}. Stay informed.",
    "top10": "Those were the highlights on {topic} — which one surprised you most?",
    "explainer": "Now you know the basics of {topic} — and that is a great place to start.",
}

_BODY_FACTS_PER_PARAGRAPH = 2


def resolve_style(requested: str | None, default: str = "explainer") -> str:
    """Map a user-requested style to one of the known styles.

    Case-insensitive and tolerant of separators ("Top 10", "top-10") and
    partials ("edu"); anything unrecognized falls back to `default`.
    """
    if not requested:
        return default
    normalized = re.sub(r"[\s\-_]", "", requested.strip().lower())
    if normalized in STYLES:
        return normalized
    for candidate in STYLES:
        if candidate in normalized or normalized in candidate:
            return candidate
    log.warning("unknown script style %r; using %r", requested, default)
    return default


def _hook(topic: str, style: str) -> str:
    return _HOOKS.get(style, _HOOKS["explainer"]).format(topic=topic)


def _ending(topic: str, style: str) -> str:
    return _ENDINGS.get(style, _ENDINGS["explainer"]).format(topic=topic)


def _body(research: ResearchOutput, style: str) -> list[str]:
    facts = research.facts
    if style == "top10":
        return [f"{index}. {fact.content}" for index, fact in enumerate(facts, start=1)]
    paragraphs: list[str] = []
    for start in range(0, len(facts), _BODY_FACTS_PER_PARAGRAPH):
        chunk = facts[start : start + _BODY_FACTS_PER_PARAGRAPH]
        paragraphs.append(" ".join(fact.content for fact in chunk))
    if not paragraphs and research.summary:
        paragraphs = [research.summary]
    return paragraphs


def template_script(research: ResearchOutput, style: str = "explainer") -> ScriptOutput:
    topic = research.topic
    hook = _hook(topic, style)
    body = _body(research, style)
    ending = _ending(topic, style)
    return ScriptOutput(
        hook=hook,
        body=body,
        ending=ending,
        narration=[NarrationBlock(paragraph=p) for p in [hook, *body, ending]],
        style=style,
    )
