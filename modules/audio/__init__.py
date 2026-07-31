"""Audio stage: narration TTS + royalty-free background music + mixing.

V1 builds a timestamped `AudioMixPlan` and hands it to an `AudioEngine`.
Beat-synchronization is intentionally NOT implemented in V1; it slots in at
`DefaultAudioModule._build_mix_plan` in V2 without touching the engine or
downstream consumers.
"""
