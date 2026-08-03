"""Sentence-based subtitle timing.

Subtitle cues derive from the narration/script timing (scene durations), NOT
from the mixed audio — so subtitle generation is independent of the mixer and
engine, and can be replaced without touching the audio pipeline. Each cue
carries a stable `cue_id` (`cue_0001`, …) as an internal reference for future
editing, translation, word-level alignment, or karaoke features.
"""

from __future__ import annotations

import re

from ..production.schemas import SubtitleCue
from ..production.srt import build_srt
from ..scenes.schemas import ScenePlan
from ..script.metrics import count_words
from .schemas import AudioCue

_BASE_TERMS = (".", "!", "?")


def split_sentences(text: str, punctuation: tuple[str, ...] = ()) -> list[str]:
    """Split narration into subtitle-sized sentences.

    Terminators are the usual .!? plus the language pack's extra punctuation
    (Hindi: the danda ।). Defaults to English-only so the contract is unchanged
    for existing callers.
    """
    text = " ".join(text.split())
    if not text:
        return []
    terms = "".join(re.escape(p) for p in (*_BASE_TERMS, *punctuation))
    pattern = re.compile(rf"(?<=[{terms}])\s+")
    return [sentence.strip() for sentence in pattern.split(text) if sentence.strip()]


def build_cues(
    scenes: ScenePlan,
    narration_durations: dict[int, float] | None = None,
    punctuation: tuple[str, ...] = (),
    script: str = "latin",
) -> list[AudioCue]:
    """Sentence-timed cues from the scene narration, back-to-back.

    *narration_durations* maps scene_number → actual measured duration.
    When provided, these override the LLM estimates for subtitle timing.
    *punctuation* carries the language pack's extra sentence terminators
    (e.g. the Hindi danda) so Devanagari narration splits correctly.
    *script* is the tokenizer name ("latin" | "devanagari") — the word counts
    that proportion each scene's duration across its sentences must use the
    narration's script, or non-Latin text counts as zero words and every cue
    collapses to zero duration.
    """
    narration_durations = narration_durations or {}
    cues: list[AudioCue] = []
    cursor = 0.0
    cue_no = 0
    for scene in scenes.scenes:
        sentences = split_sentences(scene.narration_segment, punctuation)
        if not sentences:
            continue
        words = [count_words(sentence, script) for sentence in sentences]
        total_words = sum(words) or 1
        scene_duration = narration_durations.get(
            scene.scene_number, scene.estimated_duration
        )
        scene_duration = max(0.0, scene_duration)
        for sentence, word_count in zip(sentences, words, strict=True):
            cue_no += 1
            end = cursor + scene_duration * word_count / total_words
            cues.append(
                AudioCue(
                    cue_id=f"cue_{cue_no:04d}",
                    index=cue_no,
                    start=round(cursor, 3),
                    end=round(end, 3),
                    text=sentence,
                )
            )
            cursor = end
    return cues


def cues_to_srt(cues: list[AudioCue]) -> str:
    subtitles = [
        SubtitleCue(index=cue.index, start=cue.start, end=cue.end, text=cue.text) for cue in cues
    ]
    return build_srt(subtitles)
