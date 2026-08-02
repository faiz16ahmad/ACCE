# Background Music — Architecture

**Status: APPROVED & FROZEN** (2026-08-02). The Shot-style three-phase
migration in §8 is **complete** (Phases 1–3 implemented). Contracts are
frozen; future work (multi-track, SFX/ambient, beat sync) extends the plan —
it never reshapes these models.

**Philosophy (same as the Shot architecture):** LLMs make planning decisions;
structured plans are normalized; retrieval is deterministic; renderers only
render; timing is owned by a timeline; components have a single responsibility.

Music is **not** a media asset. It is a separate sub-pipeline inside the Audio
stage (mirroring how the Production stage is one stage with an internal
pipeline: timeline → manifest → renderer). Music planning is an LLM decision;
music *files* are a retrieval decision; music *time* is a timeline decision.

---

## 0. The one-track vs multi-track decision (read this first)

**Decision: one continuous primary bed, expressed as exactly one music segment
in a segment-based Audio Timeline.**

| | **A. One continuous track** | **B. Multiple scene-level tracks** |
|---|---|---|
| **Quality** | Seamless, cohesive, the documentary norm. Evolution = volume/intensity automation over one bed. Can't re-theme a scene's *instrumentation*; a short track must loop. | Per-scene emotional fidelity; matches scene rhythm. Risk of a "playlist" feel without careful crossfades; a clip shorter than its scene must loop/fade awkwardly. |
| **Complexity** | 1 LLM intent, 1 retrieval, 1 music segment, trivial timeline. Closest to today's code. | N intents (or 1 multi-scene intent), N retrievals, N segments + crossfades + per-segment duration fitting + more normalization. |
| **Future scale** | Emotional arcs limited to automation unless reworked later. | Naturally extends to SFX/ambient/arcs (all segment-based). |

**Key insight:** the *architecture* is segment-based either way — the Audio
Timeline owns a **list** of music segments. "One vs many" is therefore a
**planner decision, not an architecture decision.**

Why this wins for the current architecture:
1. **It matches the product.** A 60–120s documentary under a single cinematic
   bed is the norm; per-scene switches read as "playlist", not "documentary".
2. **It is the smallest change from today** (the current mix already lays one
   bed `[0, narration_end]`) — but routed through the new
   planner/normalizer/retriever/timeline so the architecture is real.
3. **It is future-proof by construction.** The Audio Timeline's segment list
   means moving to N tracks later is a *planner + retriever-count* change —
   "evolve the planner, not the timeline." Zero timeline/renderer changes.
4. **Evolution is a timeline responsibility.** The single track's
   "evolution" (intensity ramp over the documentary) is delivered via the
   timeline's volume automation + ducking + fades — a free demonstration of
   exactly the responsibility boundary this design defines.

Accepted trade-off: emotional *arcs* in V1 are automation-based (intensity
ramps over one bed) rather than re-themed per scene. Upgradable to per-scene
tracks later with no redesign.

---

## 1. Responsibilities

| Component | Owns | Never does |
|---|---|---|
| **Music Planner** (LLM) | structured *intent*: emotion, energy, tempo, intensity (+ optional intensity curve), style, fade preferences. Reads narration/scenes/rhythm/style only. | selects a file, knows a filename, assigns a timestamp, chooses a song. |
| **Music Normalizer** (deterministic) | enforcement of limits + schema validity on the intent (bounded vocabulary, clamped ranges, filled prefs). LLM proposes → normalizer enforces. | changes meaning; invents intent; knows files/time. |
| **Music Retriever** (deterministic) | maps normalized intent + a duration hint to concrete files from the local library (provider chain), ranked deterministically by the §3.5 policy, cached. | changes emotion/intent; assigns time; plans. Returns `RankedAsset`s. |
| **Music Asset** | a file + factual metadata: provider, title, path, measured duration, bpm, license, tags. | narrative info; intent/emotion; timestamps. |
| **Audio Timeline** (deterministic) | ALL music timing: segment start/end, fades, ducking, looping, volume automation (mapping relative curve points to absolute time), silence. Derives placement from the measured narration clock + video timeline. | selects files; invents intent; changes narration. |
| **Audio Renderer** (mixer) | mixes a plan to a master file: position, levels, fades, ducking, loudness normalization. | plans; selects; times. |

---

## 2. Data flow

```
Scenes + Narration (measured TTS durations — the clock)
      │
      ▼
┌────────────────────┐   MusicIntent    ┌────────────────────┐
│   Music Planner    │ ───────────────▶ │  Music Normalizer  │
│   (LLM: emotion,   │                  │  (clamp, coerce,   │
│   energy, tempo,   │                  │   fill — the bound)│
│   intensity, fades)│                  └─────────┬──────────┘
└────────────────────┘                            │ AudioPlan
                                                  ▼
                        ┌─────────────────────────────────────┐
                        │         Music Retriever             │
                        │  deterministic (§3.5), local        │
                        │  library, duration hint (from the   │
                        │  clock, NOT the planner)            │
                        └──────────────┬──────────────────────┘
                                       │ RankedAsset(s): files + scores
                                       ▼
┌────────────────────┐   AudioMixPlan  ┌────────────────────┐
│   Audio Timeline   │ ──────────────▶ │   Audio Renderer   │
│   start/end, fades,│                 │   (mix → master)   │
│   duck, loop, auto │                 └────────────────────┘
│   narration refs   │
└────────────────────┘
```

Same shape as the shot architecture — plan (LLM) → normalize → retrieve
(deterministic) → timeline (time) → renderer (files/pixels/audio).

---

## 3. Object model + data schemas

```python
# --- Music Planner output: pure intent (no files, no time) -------------------
class MusicIntent(BaseModel):
    emotion: str            # controlled vocabulary (see normalizer):
                            # "calm" | "uplifting" | "tense" | "hopeful" |
                            # "serious" | "playful" | "melancholic"
    energy: float           # 0.0..1.0
    tempo_bpm: int | None   # target BPM, or None for "any"
    intensity: float        # 0.0..1.0 overall arc intensity
    intensity_curve: list[CurvePoint]   # OPTIONAL (default empty). Relative
                            # shape of the arc: `at` ∈ [0.0, 1.0] is a position
                            # *within the documentary*, never an absolute
                            # second, so the planner never assigns timestamps;
                            # the Audio Timeline maps `at` → seconds using the
                            # measured narration total.
    style: str              # documentary style echo, e.g. "documentary"
    fade_preferences: FadePreferences

class CurvePoint(BaseModel):
    at: float               # relative position 0.0..1.0 within the documentary
    value: float            # intensity 0.0..1.0

class FadePreferences(BaseModel):
    fade_in: float | None   # seconds — a *preference*, not a timestamp
    fade_out: float | None
    crossfade: bool = False # prefer crossfade between music segments (future)

# --- Normalized plan (the enforcement boundary) -------------------------------
class AudioPlan(BaseModel):
    """Future-proof planning object. V1 carries *music* intents only; future
    kinds (ambient, sfx) are added as sibling fields, never by reshaping.
    `MusicIntent` is the music-specific subset of this plan."""
    music: list[MusicIntent] = Field(default_factory=list)  # V1: exactly 1

# --- Retrieval request (derived by the retriever entry point) -----------------
class MusicSelection(BaseModel):
    intent: MusicIntent
    duration_hint: float    # seconds the bed must cover — computed from the
                            # measured narration by the audio stage, NOT the planner
    genre_hint: str | None  # legacy style→genre mapping retained as a *hint*
                            # (deterministic), not the decision maker

# --- Retrieval result: a file + factual metadata -------------------------------
class MusicAsset(BaseModel):
    asset_id: str           # music_0001
    provider: str
    title: str
    local_path: Path
    duration: float         # measured file duration
    bpm: int | None
    license: str
    tags: list[str]         # retriever-side metadata used for ranking
    # NO narrative text, NO emotion, NO timestamps

class RankedAsset(BaseModel):
    asset: MusicAsset
    score: float            # 0.0..1.0, deterministic (§3.5)
    reasons: dict[str, float]  # per-criterion scores — explainability

# --- Audio Timeline: owns ALL music timing -------------------------------------
class VolumePoint(BaseModel):
    at: float               # seconds within the music segment
    value: float            # 0.0..1.0 (intensity ramp)

class MusicSpan(BaseModel):
    asset_id: str
    start: float            # seconds on the master clock
    end: float
    volume: float
    fade_in: float
    fade_out: float
    duck: DuckSpec
    loop: LoopSpec | None
    automation: list[VolumePoint]

class AudioTimeline(BaseModel):
    narration_spans: list[tuple[float, float]]  # from measured TTS (the clock)
    music_spans: list[MusicSpan]
    master_gain: float
```

**Renderer boundary stays stable:** the Audio Timeline **flattens to the
existing `AudioMixPlan` / `MixSegment`** (the documented architecture-stable
seam). Narration segments are unchanged; music becomes `MixSegment(kind="music")`
with start/end/volume/fades; `duck` is an additive field on music segments.
Looping is already *resolved* by the timeline (source repeated with a seam
crossfade → a single segment), so the renderer never loops.

### 3.5 Deterministic retrieval ranking policy (explainable + reproducible)

The Music Retriever scores every candidate asset with an **additive weighted
model**; the same intent + same library always yields the same order.

```
score(asset) = Σ_k reason_k(asset) × weight_k  /  Σ_k weight_k
```

| Criterion | Weight (config) | reason_k (deterministic) |
|---|---|---|
| `duration` | 0.40 | `1.0` if asset.duration ≥ duration_hint (bed covers the clock, no loop); else loop-aware `0.5 + 0.5 × asset.duration/duration_hint` — the timeline loops beds (§5), so a shorter bed degrades smoothly toward neutral instead of being disqualified |
| `tempo` | 0.30 | `max(0, 1 − |asset.bpm − intent.tempo_bpm| / tempo_tolerance)` when both known; `0.5` (neutral) when bpm or target is unknown |
| `energy` | 0.10 | `0.5` neutral in V1 (assets carry no energy metadata); set to a distance-based score once tags exist — the *formula* is fixed, only the input source changes |
| `keyword` | 0.20 | filename/path token overlap with the query (`genre_hint` + emotion + style words), the existing local-provider relevance, normalized to `[0,1]` |

**Determinism guarantees:**
- **Stable tie-break:** equal `score` → ascending `asset_id` (assigned from a
  sorted list of candidates). Never relies on dict order, filesystem order, or
  network order.
- **Threshold:** candidates below `satisfactory_score` (reuse `MediaConfig`
  semantics as a config value) are rejected before selection, so a poor match
  cannot win by default.
- **Cache:** the scored selection is cached keyed by a hash of
  `(intent, duration_hint, library state)` so identical requests return
  byte-identical results without re-ranking.
- **Explainability:** each candidate records its `reasons` dict (the
  per-criterion scores), so quality/UI can report *why* a track was chosen.

---

## 4. Pipeline diagram

```
Stage: AUDIO
  ┌─────────────── internal music pipeline ───────────────┐
  │ 1. narration (TTS) ──▶ measured durations (the clock) │
  │ 2. Music Planner (LLM)   ──▶ MusicIntent              │
  │ 3. Music Normalizer      ──▶ AudioPlan                │
  │ 4. Music Retriever       ──▶ RankedAsset(s) (local)   │
  │ 5. Audio Timeline        ──▶ AudioMixPlan  (stable)   │
  │ 6. Audio Renderer        ──▶ master_audio             │
  └───────────────────────────────────────────────────────┘
Artifacts: audio.json, mix_plan.json, audio_plan.json, music_assets.json,
           narration_*.mp3, subtitles.srt
```

Music planning is a **sub-pipeline of the Audio stage** — exactly like the
Production stage is one stage with an internal pipeline. This avoids a
pipeline reorder (no `Stage` enum change, no frontend stage-list change) while
still giving music first-class contracts. If a future milestone wants the
planner as its own `Stage.MUSIC`, the artifacts already exist — it's a
reordering, not a redesign.

---

## 5. Mixing design

- **Narration is the clock.** Narration segments are sequential, placed from
  measured TTS durations. Music never moves them (invariant A9).
- **Music placement.** The bed's start/end is derived from the narration span
  it must cover (V1: `[0, narration_total]`). The timeline owns this.
- **Ducking.** Under narration, the bed drops by `duck.depth_db` with
  attack/release. The engine already implements ducking; the timeline owns the
  parameters per music segment.
- **Fades.** `fade_in` at bed start, `fade_out` at bed end (no clicks). Owned
  by the timeline.
- **Crossfades.** Relevant when ≥2 music segments exist (future): overlapping
  segments with `fade_out` → `fade_in`; the engine's adelay+amix mixes
  overlap. Nothing new in the renderer.
- **Loudness normalization.** Renderer concern — `loudnorm` + `master_gain`
  already live in `modules/audio/mix.py`.
- **Silence.** Deliberate gaps = spans with no music segment (the timeline
  simply doesn't cover them). Modeled by the segment list, not a special
  construct.
- **Looping.** If the chosen track is shorter than its span, the timeline
  loops it with a short seam crossfade (owned by the timeline). If longer, the
  timeline takes the first `span` seconds (or a chosen window).
- **Intensity curve → automation.** The timeline converts relative
  `intensity_curve` points to absolute `automation` points
  (`at_seconds = at × narration_total`) and samples them onto the bed as
  volume automation.

---

## 6. Future expansion (no redesign)

| Future capability | How the architecture already covers it |
|---|---|
| **Ambient / SFX** | New `AudioPlan` sibling fields + segment *kinds* (widen `MixSegment.kind`); a retriever per kind; same timeline placement. |
| **Multiple music tracks** | `AudioPlan.music` is a list; retriever returns N assets; timeline places N spans with crossfades. |
| **Emotional arcs** | Per-scene intents → timeline automation (V1) or per-arc tracks (later); both are timeline/planner decisions. |
| **Adaptive / runtime music** | The plan schema is the contract; only the renderer changes (runtime vs pre-render). |
| **Beat sync** | `MusicAsset.bpm` already exists (the documented seam); the timeline can align span boundaries to beats; renderer unchanged. |
| **Curated library metadata** | Sidecar tags feed the `energy` criterion (§3.5); planner/normalizer/timeline unchanged. |

---

## 7. Invariants (mirroring the Shot architecture)

- **A1** — Music Planner produces intent only: never filenames, never
  timestamps (the `intensity_curve` uses relative positions, never seconds),
  never actual tracks.
- **A2** — Music Retriever never changes emotion/intent: it maps intent to a
  file deterministically; it cannot alter the intent fields.
- **A3** — Music assets contain no narrative information: a `MusicAsset` is a
  file + factual metadata; no narration text, no scene references, no intent.
- **A4** — Audio Timeline owns all music timing: start/end, fades, ducking,
  looping, automation, silence are decided only there (including mapping
  relative curve positions to absolute time).
- **A5** — Narration owns the clock: music placement derives from measured
  narration durations; narration timing is never derived from music.
- **A6** — Audio Renderer only renders: consumes a plan; performs no
  selection, no intent, no timing changes.
- **A7** — Intent is normalized, never invented: the normalizer
  clamps/coerces/fills the LLM proposal within configured bounds; no component
  invents music choices. (LLM proposes, normalizer enforces.)
- **A8** — Retrieval is deterministic: same intent + same library → same
  asset order (weighted ranking + stable tie-break + cache).
- **A9** — Music never changes narration timing: ducking/fades/loops affect
  the music bed only; master duration and narration placement are invariant.
- **A10** — Missing music degrades, never fails: no matching track → the
  pipeline proceeds narration-only (as today) with a warning, not an error.
- **A11** — Beat data is metadata, not timing: `bpm` is informational for
  future sync; the timeline decides whether/when to use it.
- **A12** — Single responsibility: each component (planner/normalizer/
  retriever/timeline/renderer) does exactly one thing and consumes/produces
  structured contracts.

---

## 8. Migration strategy (additive, Shot-style)

**Phase 1 — Structures. No behavior changes.** ✅ implemented
- `modules/audio/music/` package: `schemas.py` (`AudioPlan`, `MusicIntent`,
  `CurvePoint`, `FadePreferences`, `MusicSelection`, `MusicAsset`,
  `RankedAsset`, timeline-owned `MusicSpan`/`AudioTimeline`),
  `normalize.py` (normalizer), `retrieve.py` (deterministic ranking §3.5).
- `MusicConfig` gains the ranking/normalizer knobs (§3.5 weights, emotion
  vocabulary, tempo window/tolerance, max fade, curve cap) — additive, unused.
- Nothing is wired: the Audio module still uses the `style_genres` path, so
  the mix output is **byte-identical** to today.
- Tests cover the schemas, normalizer, and ranking determinism.

**Phase 2 — Connect pipeline.** ✅ implemented
- Audio module: run Planner → Normalizer → Retriever, replacing
  `_select_music`'s config-genre decision with an LLM intent + deterministic
  retrieval. `style→genre` becomes the `genre_hint`, not the decision.
- Audio Timeline (`modules/audio/music/timeline.py`) replaces
  `_build_mix_plan`: computes music placement (fades/duck/loop/automation)
  from the plan + assets + measured narration, then flattens to the stable
  `AudioMixPlan`. New artifacts: `audio_plan.json`, `music_assets.json`.
- Additive `duck` field on music `MixSegment`s (single `DuckSpec` on the
  stable seam); renderer unchanged (still adelay+volume+fades+duck+loudnorm).
- `AudioOutput` keeps `music_title`/`music_provider` as derived summaries for
  the UI/quality, sourced from the `MusicAsset`.
- Factory wires the new modules. V1 default = one continuous bed → the mix
  *sounds* similar; the *source* of the choice changed.

**Phase 3 — Remove legacy behavior.** ✅ implemented
- Deleted the `style_genres` decision path and `_select_music` (and the unused
  `DEFAULT_GENRE` / `music_style` query string). `AudioMetadata.style_genre`
  is kept only as the `genre_hint` echo.
- Music metadata lives on `MusicAsset`/`music_assets.json`; `AudioOutput`
  summary fields are derived.
- Quality adds music checks (`audio.missing_music_asset`,
  `audio.music_bed_coverage`, `audio.music_no_duck`, `audio.music_no_fades`,
  `audio.missing_music_intent`) — artifact-driven, so legacy runs without the
  plan artifacts are untouched. Tests updated.

---

## 9. Risks

| Risk | Mitigation |
|---|---|
| LLM intent drift | Normalizer's controlled vocabulary + clamped ranges (A7). |
| Local library can't match intent | Deterministic fallback ranking; narration-only if nothing fits (A10). |
| Audible loop seam | Timeline picks the loop point + short crossfade; quality flags it. |
| Ducking artifacts (pumping) | Attack/release owned by the timeline; engine already implements. |
| Second LLM call latency (free models) | Cache intent by (topic, style, duration); optional; cheap. |
| Two "timelines" (video + audio) drift | Audio timeline derives from the *same* measured narration clock (A5). |
| Non-atomic `.cache` writes | Same as today — degraded refetch, never corruption. |

---

## 10. Frozen decisions (resolved during review)

1. **Planning object** → **`AudioPlan`** (future-proof; music is its V1
   subset). `MusicIntent` is the music-specific segment type.
2. **Intensity** → `intensity` scalar **+ optional `intensity_curve`** of
   relative `(at, value)` points; the timeline owns the absolute-time mapping.
3. **Energy** → float `0.0..1.0` (not an enum); emotion uses the 7-value
   controlled vocabulary.
4. **V1 scope** → single whole-document intent / one continuous bed.
5. **Promoting to `Stage.MUSIC`** → not in V1; the artifacts exist so it is a
   future reordering, not a redesign.
6. **Library metadata** → V1 ranking uses filename-token + factual fields;
   `tags` field is the extension point for curated sidecar metadata (feeds the
   `energy` criterion later).
7. **Loop seam** → crossfade, timeline-owned (no hard cuts).
8. **Retrieval ranking** → deterministic weighted model per §3.5, with stable
   tie-break, threshold, and cache — explainable via per-criterion `reasons`.
