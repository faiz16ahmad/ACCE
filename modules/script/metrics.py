"""Script quality metrics — profile-driven tokenization (frozen architecture §3).

Word/sentence/syllable counting, Flesch Reading Ease + Flesch-Kincaid Grade
Level, and a duration estimate at a configurable speaking rate. The English
tokenizer (`MetricsProfile()` defaults) is byte-for-byte the old behavior; a
language pack's `script` + `punctuation` + `readability` selects a different
word regex, sentence terminators, and whether Flesch applies at all (e.g.
Hindi: `script=devanagari`, `punctuation=["।"]`, `readability=none`).

These are heuristics — accurate enough for pacing and quality signals, nothing
more. `words_per_minute` also comes from the pack so the pacing estimate and
the script prompt's word budget speak the right language.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .schemas import ReadabilityStats, ScriptMetrics

_WORD_RES = {
    "latin": re.compile(r"[A-Za-z']+"),
    "devanagari": re.compile(r"[ऀ-ॿ]+"),
}
# Devanagari syllable proxy: vowel marks (matras) + standalone vowels.
_DEV_VOWEL_RE = re.compile(r"[अ-औऺ-ौॢॣ॰]+")
_LATIN_VOWEL_GROUPS_RE = re.compile(r"[aeiouy]+")
_BASE_SENTENCE_TERMS = (".", "!", "?")


@dataclass(frozen=True)
class MetricsProfile:
    """Everything tokenization needs, derived from a language pack."""

    script: str = "latin"
    punctuation: tuple[str, ...] = ()  # sentence terminators beyond .!?
    readability: str = "flesch"  # "flesch" | "none"
    words_per_minute: int = 150


def count_words(text: str, script: str = "latin") -> int:
    return len(_WORD_RES.get(script, _WORD_RES["latin"]).findall(text))


def count_sentences(text: str, punctuation: tuple[str, ...] = ()) -> int:
    terms = "".join(re.escape(t) for t in (*_BASE_SENTENCE_TERMS, *punctuation))
    return max(1, len(re.findall(rf"[^{terms}]+[{terms}]+", text)))


def _syllables_latin(word: str) -> int:
    word = word.lower()
    if len(word) > 2 and word.endswith("e"):
        word = word[:-1]  # drop silent trailing 'e'
    groups = _LATIN_VOWEL_GROUPS_RE.findall(word)
    return max(1, len(groups))


def _syllables_devanagari(word: str) -> int:
    groups = _DEV_VOWEL_RE.findall(word)
    return max(1, len(groups))


def readability_stats(text: str, script: str = "latin") -> ReadabilityStats:
    words = max(1, count_words(text, script))
    sentences = max(1, count_sentences(text))
    syllables = max(
        1,
        sum(
            (_syllables_devanagari(w) if script == "devanagari" else _syllables_latin(w))
            for w in _WORD_RES.get(script, _WORD_RES["latin"]).findall(text)
        ),
    )

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


def compute_metrics(
    narration_text: str,
    requested_duration: int | None,
    words_per_minute: int,
    profile: MetricsProfile | None = None,
) -> ScriptMetrics:
    profile = profile or MetricsProfile()
    word_count = count_words(narration_text, profile.script)
    estimated = estimate_duration(word_count, words_per_minute)
    readability = (
        readability_stats(narration_text, profile.script)
        if profile.readability != "none"
        else None  # Flesch is English-only; hi computes no readability
    )
    return ScriptMetrics(
        word_count=word_count,
        estimated_duration=round(estimated, 1),
        words_per_minute=words_per_minute,
        readability=readability,
        duration_match=duration_match(estimated, requested_duration),
    )
