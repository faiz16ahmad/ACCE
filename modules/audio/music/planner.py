"""Music Planner — the LLM proposes *intent*, never files or time (A1).

The planner reads narration/scenes/rhythm/style only and emits a
`MusicIntent`. A deterministic template is the key-free fallback. Either way
the normalizer owns enforcement (A7): this module never selects a file, knows
a filename, or assigns a timestamp.

Phase 2: wired into the Audio stage; V1 emits exactly one whole-document
intent (the one-continuous-bed decision).
"""

from __future__ import annotations

import json
import logging

from config.settings import AudioConfig, MusicConfig
from core.errors import StageRetryableError
from providers.base import LLMProvider

from ...scenes.schemas import ScenePlan
from .normalize import normalize_audio_plan, normalize_music_intent
from .schemas import AudioPlan, CurvePoint, FadePreferences, MusicIntent

log = logging.getLogger(__name__)

# Deterministic genre -> emotion map for the key-free fallback (and as a
# prior for the LLM prompt's examples). Kept small and explicit.
_GENRE_EMOTION = {
    "calm": "calm",
    "ambient": "calm",
    "cinematic": "serious",
    "neutral": "calm",
    "atmospheric": "serious",
    "upbeat": "uplifting",
    "documentary": "serious",
}


def build_music_prompt(scenes: ScenePlan, topic: str, style: str, duration: int | None) -> str:
    """Instruction for the LLM: return one `MusicIntent` as JSON."""
    scene_lines = "\n".join(
        f"Scene {scene.scene_number} (rhythm {scene.rhythm}): {scene.narration_segment}"
        for scene in scenes.scenes
    )
    return (
        f"Choose one background-music intent for a {duration or '?'}-second documentary "
        f"titled '{topic}' in the '{style}' style.\n"
        f"Scene narration:\n{scene_lines}\n\n"
        "Return ONLY JSON matching this schema (all numbers 0-1, intensity_curve "
        "positions are RELATIVE 0-1 across the video, never seconds):\n"
        "{\n"
        '  "emotion": "calm|uplifting|tense|hopeful|serious|playful|melancholic",\n'
        '  "energy": 0.0,\n'
        '  "tempo_bpm": 120 | null,\n'
        '  "intensity": 0.5,\n'
        '  "intensity_curve": [{"at": 0.0, "value": 0.3}, {"at": 0.5, "value": 0.8}] | [],\n'
        '  "style": "documentary",\n'
        '  "fade_preferences": {"fade_in": 1.0, "fade_out": 2.0, "crossfade": false}\n'
        "}"
    )


def fallback_intent(style: str, audio_config: AudioConfig | None) -> MusicIntent:
    """Deterministic intent from the legacy style->genre mapping.

    The genre stays a *hint*; the emotion is derived deterministically so the
    key-free pipeline still exercises the full intent path.
    """
    style = style or "explainer"
    genre = (audio_config.style_genres or {}).get(style, "ambient") if audio_config else "ambient"
    emotion = _GENRE_EMOTION.get(genre, "calm")
    return MusicIntent(
        emotion=emotion,
        energy=0.5,
        tempo_bpm=None,
        intensity=0.5,
        style=style,
        fade_preferences=FadePreferences(fade_in=audio_config.music_fade if audio_config else 1.0),
    )


def plan_music(
    scenes: ScenePlan,
    *,
    topic: str = "",
    style: str = "explainer",
    duration: int | None = None,
    llm: LLMProvider | None = None,
    audio_config: AudioConfig | None = None,
    music_config: MusicConfig | None = None,
) -> AudioPlan:
    """Produce a normalized `AudioPlan` (V1: exactly one intent)."""
    if llm is not None and llm.name != "stub":
        proposed = _llm_intent(llm, scenes, topic, style, duration)
    else:
        proposed = fallback_intent(style, audio_config)
    intent = normalize_music_intent(proposed, music_config)
    return AudioPlan(music=[intent])


def _llm_intent(
    llm: LLMProvider, scenes: ScenePlan, topic: str, style: str, duration: int | None
) -> MusicIntent:
    system = "You are a music supervisor for short documentaries. Return ONLY valid JSON matching the requested schema."
    raw = llm.complete(build_music_prompt(scenes, topic, style, duration), system=system)
    try:
        data = _extract_json(raw)
        intent = MusicIntent.model_validate(data)
    except Exception as exc:  # noqa: BLE001 - one repair, then retryable failure
        log.warning("music intent parse failed; attempting one repair: %s", exc)
        repair = (
            f"Your previous response was not valid ({exc}). Respond with ONLY JSON matching "
            f"the requested schema. Previous response:\n{raw[:2000]}"
        )
        try:
            intent = MusicIntent.model_validate(_extract_json(llm.complete(repair, system=system)))
        except Exception as exc2:  # noqa: BLE001 - surfaced as a retryable stage failure
            raise StageRetryableError(f"music intent not valid after repair: {exc2}") from exc
    return intent


def _extract_json(text: str) -> dict:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found in LLM response")
    import re

    return json.loads(re.sub(r"```(?:json)?", "", text[start : end + 1]))
