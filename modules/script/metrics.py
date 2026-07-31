"""Simple script quality metrics.

Word/sentence/syllable counting, Flesch Reading Ease + Flesch-Kincaid Grade
Level, and a duration estimate at a configurable speaking rate. These are
heuristics — accurate enough for pacing and quality signals, nothing more.
"""

from __future__ import annotations

import re

from .schemas import ReadabilityStats, ScriptMetrics

_WORD_RE = re.compile(r"[A-Za-z']+")
_SENTENCE_RE = re.compile(r"[^.!?]+[.!?]+")
_VOWEL_GROUPS_RE = re.compile(r"[aeiouy]+")


def count_words(text: str) -> int:
    return len(_WORD_RE.findall(text))


def count_sentences(text: str) -> int:
    return max(1, len(_SENTENCE_RE.findall(text)))


def _syllables(word: str) -> int:
    word = word.lower()
    if len(word) > 2 and word.endswith("e"):
        word = word[:-1]  # drop silent trailing 'e'
    groups = _VOWEL_GROUPS_RE.findall(word)
    return max(1, len(groups))


def readability_stats(text: str) -> ReadabilityStats:
    words = count_words(text)
    sentences = count_sentences(text)
    syllables = sum(_syllables(w) for w in _WORD_RE.findall(text))

    words = max(words, 1)
    sentences = max(sentences, 1)
    syllables = max(syllables, 1)

    reading_ease = 206.835 - 1.015 * (words / sentences) - 84.6 * (syllables / words)
    grade_level = 0.39 * (words / sentences) + 11.8 * (syllables / words) - 15.59

    return ReadabilityStats(
        words=words,
        sentences=sentences,
        syllables=syllables,
        reading_ease=round(min(100.0, max(0.0, reading_ease)), 2),
        grade_level=round(max(0.0, grade_level), 2),
    )


def estimate_duration(word_count: int, words_per_minute: int) -> float:
    """Seconds to speak `word_count` words at the given rate."""
    if words_per_minute <= 0:
        return 0.0
    return word_count / words_per_minute * 60.0


def duration_match(estimated: float, requested: int | None) -> float | None:
    """How well the estimated duration fits the request (0..1); None if none requested."""
    if not requested or requested <= 0:
        return None
    return round(max(0.0, 1.0 - abs(estimated - requested) / requested), 3)


def compute_metrics(narration_text: str, requested_duration: int | None, words_per_minute: int) -> ScriptMetrics:
    word_count = count_words(narration_text)
    estimated = estimate_duration(word_count, words_per_minute)
    return ScriptMetrics(
        word_count=word_count,
        estimated_duration=round(estimated, 1),
        words_per_minute=words_per_minute,
        readability=readability_stats(narration_text),
        duration_match=duration_match(estimated, requested_duration),
    )
