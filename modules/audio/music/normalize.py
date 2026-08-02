"""Music intent normalizer — the enforcement boundary (architecture-audio.md §3).

The LLM proposes; the normalizer enforces (A7): emotion belongs to the
controlled vocabulary, energy/intensity/curve values are clamped to [0,1],
tempo falls inside the configured window, fade preferences are clamped to
[0, max_fade], and the curve is capped in length with strictly increasing `at`.
Deterministic; never invents intent.

Phase 1: implemented and unit-tested, but not yet wired into the audio module.
"""

from __future__ import annotations

from config.settings import MusicConfig

from .schemas import AudioPlan, CurvePoint, FadePreferences, MusicIntent

# Default controlled vocabulary, matching `MusicConfig.emotions` (kept here so
# the module works standalone in tests before config is plumbed through).
DEFAULT_EMOTIONS = ("calm", "uplifting", "tense", "hopeful", "serious", "playful", "melancholic")

_MAX_CURVE_POINTS = 16


def normalize_music_intent(intent: MusicIntent, config: MusicConfig | None = None) -> MusicIntent:
    """Clamp/coerce/fill a proposed intent into a valid, bounded one.

    Never changes *meaning* — a tense intent stays tense; only out-of-contract
    values are repaired.
    """
    cfg = config or MusicConfig()
    emotions = cfg.emotions or DEFAULT_EMOTIONS
    return MusicIntent(
        emotion=_coerce_emotion(intent.emotion, emotions),
        energy=_clamp01(intent.energy),
        tempo_bpm=_coerce_tempo(intent.tempo_bpm, cfg),
        intensity=_clamp01(intent.intensity),
        intensity_curve=_coerce_curve(intent.intensity_curve),
        style=(intent.style or "documentary").strip() or "documentary",
        fade_preferences=_coerce_fades(intent.fade_preferences, cfg.max_fade_seconds),
    )


def normalize_audio_plan(plan: AudioPlan, config: MusicConfig | None = None) -> AudioPlan:
    """Normalize every music segment of an `AudioPlan`."""
    return AudioPlan(music=[normalize_music_intent(intent, config) for intent in plan.music])


def _clamp01(value: float) -> float:
    return round(max(0.0, min(1.0, float(value))), 3)


def _coerce_emotion(emotion: str, emotions: tuple[str, ...]) -> str:
    return emotion if emotion in emotions else (emotions[0] if emotions else DEFAULT_EMOTIONS[0])


def _coerce_tempo(tempo: int | None, cfg: MusicConfig) -> int | None:
    if tempo is None:
        return None
    return max(cfg.tempo_min, min(cfg.tempo_max, int(tempo)))


def _coerce_fades(prefs: FadePreferences, max_fade: float) -> FadePreferences:
    def bound(value: float | None) -> float | None:
        if value is None:
            return None
        return round(max(0.0, min(max_fade, float(value))), 3)

    return FadePreferences(fade_in=bound(prefs.fade_in), fade_out=bound(prefs.fade_out), crossfade=bool(prefs.crossfade))


def _coerce_curve(points: list[CurvePoint]) -> list[CurvePoint]:
    """Clamp values, enforce strictly increasing `at`, cap the length."""
    cleaned: list[CurvePoint] = []
    last_at = -1.0
    for point in sorted(points, key=lambda p: p.at):
        at = _clamp01(point.at)
        if at <= last_at:  # keep the first of any duplicate/regressing position
            continue
        cleaned.append(CurvePoint(at=at, value=_clamp01(point.value)))
        last_at = at
        if len(cleaned) >= _MAX_CURVE_POINTS:
            break
    return cleaned
