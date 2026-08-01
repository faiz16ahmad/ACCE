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

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def split_sentences(text: str) -> list[str]:
    text = " ".join(text.split())
    if not text:
        return []
    return [sentence.strip() for sentence in _SENTENCE_SPLIT_RE.split(text) if sentence.strip()]


def build_cues(
    scenes: ScenePlan,
    narration_durations: dict[int, float] | None = None,
) -> list[AudioCue]:
    """Sentence-timed cues from the scene narration, back-to-back.

    *narration_durations* maps scene_number → actual measured duration.
    When provided, these override the LLM estimates for subtitle timing.
    """
    narration_durations = narration_durations or {}
    cues: list[AudioCue] = []
    cursor = 0.0
    cue_no = 0
    for scene in scenes.scenes:
        sentences = split_sentences(scene.narration_segment)
        if not sentences:
            continue
        words = [count_words(sentence) for sentence in sentences]
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
