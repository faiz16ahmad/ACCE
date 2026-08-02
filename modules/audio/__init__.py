"""Audio stage: narration TTS + background music + mixing.

Music is a sub-pipeline (architecture-audio.md): Planner (LLM intent) →
Normalizer → Retriever (deterministic ranking) → Audio Timeline (owns all
music timing) → flattens to the stable `AudioMixPlan` handed to an
`AudioEngine`. Beat-synchronization is intentionally NOT implemented; it slots
in at `modules.audio.music.timeline` without touching the engine or downstream
consumers.
"""
