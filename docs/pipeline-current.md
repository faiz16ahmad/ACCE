# ACCE — Current Pipeline Reference (pre-Phase-2)

> **Status:** Phase 2 has landed. This document is the **before** snapshot used
> to guide that migration; the four seams in §6 were migrated to shot-keyed
> media / `Clip` timelines / manifest v2 + id-lookup + V1 normalizer. See
> `docs/architecture-v2.md` §11 for the current state. The details below remain
> historically accurate for the pre-Phase-2 contracts.

**Purpose:** field-accurate snapshot of the end-to-end pipeline *before* the
Media / Timeline / Manifest / Renderer migration to shot-based planning
(architecture v2, Phase 2). This document is the migration reference: it names
the exact contracts and the exact seams Phase 2 changes.

**Scope:** pipeline state after V2 Phase 1 (Shot stage added, 1:1 pass-through,
not yet consumed). All stage outputs below are as they exist at this commit.

---

## 1. Pipeline flow

```
Research ──> Script ──> Scenes ──> Shots ──> Media ──> Audio ──> Production ──> Quality
   │            │            │           │          │          │           │          │
 facts,     hook/body/   narration    visual      per-scene   measured    timeline   report
 summary    ending +    blocks +     intent      asset       narration   + manifest  (score,
            style       visual plan  (1:1,       selection   durations   + render   severity)
                       (V1 fields)  unused)                                 │
```

The `PipelineOrchestrator` runs `Stage` in enum order. Each module reads prior
outputs from `ctx.results[Stage.X].output` and writes artifacts via
`ctx.store` into `out/<job_id>/<stage>/`.

## 2. Shared plumbing

- **`JobContext`** — the single object threaded through every stage. Holds
  `job_id`, `input: UserInput`, `status`, `current_stage`, `results:
  dict[Stage, StageResult]`, `store: ArtifactStore`. `ctx.progress(msg)`
  emits a timestamped `ProgressEvent` per stage.
- **`UserInput`** — `topic`, `instructions[]`, `duration` (target seconds),
  `style`.
- **`StageResult`** — `stage`, `ok`, `retries`, `artifacts_written[]`,
  `error`, `duration_ms`, `output: <concrete model>`.
- **`Stage` order** — `research, script, scenes, shots, media, audio,
  production, quality`.

## 3. Stage-by-stage contracts

### 3.1 Research → `ResearchOutput` → `out/<job>/research/research.json`

| Field | Notes |
|---|---|
| `topic: str` | The subject. |
| `facts[]` | `content`, `sources[]`, `confidence` (0–1), `verified` (≥1 source fetched), `verification_note` |
| `sources[]` | `url`, `title`, `fetched`, `http_status`, `excerpt`, `accessed_at` |
| `summary`, `angles[]`, `entities[]`, `chronology[]` | Optional enrichments. |
| `metadata` | topic, model, fetch/verification summaries, counts. |

**Ownership:** narrative. Producer: research module (LLM + live source fetch).
Consumers: script.

### 3.2 Script → `ScriptOutput` → `out/<job>/script/script.json`

| Field | Notes |
|---|---|
| `hook`, `body[]`, `ending`, `narration[NarrationBlock.paragraph]` | The narration text. |
| `style: str` | Drives music genre + title/description. |
| `metrics` | `word_count`, `estimated_duration`, `words_per_minute`, `readability`, `duration_match`. |
| `metadata` | style, requested/estimated duration, `generated_by`. |

**Ownership:** narrative. Producer: script module (LLM, template fallback).
Consumers: scenes (narration blocks), audio (style → genre), production
(title/description).

### 3.3 Scenes → `ScenePlan` → `out/<job>/scenes/scene_plan.json`

| Field | Notes |
|---|---|
| `scenes[]` | one per narration block. |
| `scene_number` *(alias `scene`)* | 1-based. |
| `narration_segment` *(alias `narration`)* | The narration text. |
| `estimated_duration` *(alias `duration`)* | **Planning aid only** (I8). |
| `visual_description`, `search_keywords[]`, `visual_type`, `transition` | **V1 legacy visual-plan fields.** Removed in Phase 3. |

**Ownership:** narrative *(visual fields are V1 legacy; the Shot is their V2
home)*. Producer: scenes module. Consumers: **shots**, **media** (this is the
scene-keyed seam), **audio** (durations/cues), **production** (timeline,
manifest text), quality.

### 3.4 Shots → `ShotPlan` → `out/<job>/shots/shot_plan.json`  *(Phase 1, not yet consumed)*

| Field | Notes |
|---|---|
| `shots[]` | Phase 1: exactly 1 per scene. |
| `shot_id`, `scene_id`, `position` | Identity + ownership (I9). |
| `purpose`, `visual_description`, `search_queries[]` | Visual intent. |
| `content_kind`, `media_preference`, `motion_intent`, `importance`, `transition_out` | V2 edit vocabulary. |

**Ownership:** edit (visual intent only — no durations, no files). Producer:
shots module (deterministic template). Consumers: **none yet** — Phase 2 wires
media + timeline to it.

### 3.5 Media → `MediaPlan` → `out/<job>/media/media_plan.json`  *(the primary Phase-2 seam)*

| Field | Notes |
|---|---|
| `assets[]` | **keyed by `scene_number`** (alias `scene_index`). |
| `asset_id` | `asset_0001`… (index == scene number today). |
| `selected_provider`, `asset_type` (image/video), `asset_url`, `local_path`, `attribution`, `license` | The chosen asset. |
| `search_query`, `candidates[]` | Query + full ranked `MediaHit[]` list. |

`MediaHit` = `provider`, `media_type`, `url`, `local_path`, `license`,
`attribution`, `width`, `height`, `duration`, `title`.

**Ownership:** asset. Producer: media module (Cache → Pexels → Pixabay →
Wikimedia chain, rank → select → download). Consumers: production (timeline,
manifest), quality.

> **Seam A:** assets carry `scene_number`, not `shot_id`. Media iterates
> `ScenePlan.scenes` and derives query/type from the *scene's* legacy visual
> fields. Phase 2 migrates this to `shot_id` + shot's `search_queries` /
> `content_kind` / `media_preference`.

### 3.6 Audio → `AudioOutput` → `out/<job>/audio/audio.json` (+ narration files, `master_audio.*`, `subtitles.srt`, `mix_plan.json`)

| Field | Notes |
|---|---|
| `narration_path`, `music_path`, `mixed_audio_path`, `subtitle_path` | Files. |
| `duration` | Master mix length (the clock). |
| `metadata` | `narration_duration`, `music_provider`, `music_title`, `style_genre`, `engine`, `voice`, `cue_count`. |
| `cues[AudioCue]` | `cue_id`, `index`, `start`, `end`, `text`. |
| `master_path` *(compat)*, `tracks[]`, `mix_plan_path` | `tracks[kind,provider,title,url,local_path,duration,bpm,license]`. |

`AudioMixPlan` (→ `mix_plan.json`): `segments[MixSegment{kind, source_path,
start, end, volume, fade_in, fade_out}]`, `master_gain`.

**Ownership:** narration/mix — orthogonal to the edit layer (I10). Producer:
audio module (per-scene TTS, music chain, mix engine, sentence subtitles).
Consumers: production (mixed audio, subtitle path, **measured narration
durations**), quality.

> **Seam B:** production reads narration durations from `AudioOutput.tracks`
> (`kind == "narration"`) to build the timeline. This is the authoritative
> clock (I7/I8).

### 3.7 Production → `out/<job>/production/`

Inputs: `ScenePlan` (required), `MediaPlan` (required), `AudioOutput`
(required), `ResearchOutput` (optional).

Builds, in order:
1. **`timeline.json`** — `Timeline { scenes[TimelineScene{scene_number,
   asset_id, start_time, end_time, transition}], duration }`. Durations come
   from measured narration, falling back to scene estimates. **Keyed by
   scene_number, 1 clip per scene.**
2. **Subtitles** — reuses the audio SRT (`subtitles.srt`); writes a styled
   `subtitles.ass` for burn-in.
3. **`render_manifest.json`** — `RenderManifest (version=1) { timeline,
   assets[ManifestAsset{scene_number, asset_id, asset_type, local_path, url,
   text}], audio_path, subtitle_path, settings, transitions{scene_number →
   transition} }`.
4. **Render** — `final_video.mp4` via a `Renderer` (stub default, or FFmpeg).
   Renderers consume **only** the manifest.
5. **`thumbnail.jpg`**, **`render_log.json`** (`RenderLog{renderer, duration,
   log}`), **`output.json`** (`ProductionOutput{video_path, timeline_path,
   render_manifest_path, render_log_path, subtitle_path, thumbnail_path,
   duration, title, description, metadata}`).

**FFmpeg renderer behavior (v1):** iterates
`zip(manifest.timeline.scenes, manifest.assets, strict=True)` — *positional*
pairing. Each scene is one input (video → `-stream_loop -1` + trim; image →
`-loop 1` + trim; text/placeholder → solid color + drawtext). When xfade is
usable, a sequential xfade chain uses **`timeline.scenes[i].start_time`** as
each offset and the scene's `transition`; otherwise per-scene fade filters +
concat. Single subtitle burn + single mixed-audio input.

**Ownership:** render. Timeline owns time (I4); renderer owns pixels (I5) and
never plans (I12).

> **Seam C:** `timeline.json` and `render_manifest.json` are keyed by
> `scene_number`, and the renderer pairs scenes↔assets **by position
> (strict zip)**. Phase 2 migrates all three to `shot_id` + id-lookup.

### 3.8 Quality → `QualityReport` → `out/<job>/quality/quality.json`

| Field | Notes |
|---|---|
| `passed`, `score` (0–100) | Deterministic; only errors fail. |
| `issues[QualityIssue]` | `level` (info/warning/error), `stage`, `message`, `code`, `suggested_fix`. |
| `warnings`, `errors`, `recommended_retry_stage`, `metadata`, `summary` | Aggregates + history. |

**Ownership:** analysis only — never modifies artifacts. Producer: quality
module (deterministic checks per stage). Consumers: UI, API.

## 4. Ownership map

| Layer | Object | Owns | Never owns |
|---|---|---|---|
| Narrative | `ResearchOutput`, `ScriptOutput`, `ScenePlan` | ideas, narration, scene timing estimate | files, queries, durations (authoritative) |
| Edit | `ShotPlan`, `Timeline` | visual intent, ordering, time | files, narration |
| Asset | `MediaPlan` | a found/downloaded file | editing, narrative |
| Render | `RenderManifest`, renderers | pixel realization | planning |
| Orthogonal | `AudioOutput`, `SubtitleCue`, `AudioMixPlan` | narration/mix/subtitles — follow narration only | edit structure |

## 5. Backward-compatibility aliases in use

- `Scene`: `scene_number`↔`scene`, `narration_segment`↔`narration`,
  `estimated_duration`↔`duration` (`populate_by_name`).
- `MediaAssetPlan`: `scene_number`↔`scene_index`; `.asset` compat view.
- `AudioOutput`: `master_path` ↔ `mixed_audio_path`; `tracks` alongside cues.
- `RenderManifest` `version=1`; `transitions` dict mirrors
  `TimelineScene.transition`.

## 6. Phase-2 migration surface (what this doc exists to guide)

| # | Seam | Today | Phase 2 |
|---|---|---|---|
| A | Media planning | iterates `ScenePlan`, keyed by `scene_number` | consumes `ShotPlan`, emits per-`shot_id` assets |
| B | Timeline durations | measured narration → per-scene `TimelineScene` | same durations → per-shot **`Clip`** |
| C | Manifest + renderer | `TimelineScene` ↔ `ManifestAsset` via strict `zip` | **`Clip` ↔ asset by `asset_id` id-lookup**; manifest `version=2` + V1 normalizer |
| D | Motion | none | `MotionDescriptor` plumbed (no-op while None) |

Invariants that must hold throughout Phase 2: **I6** (media never affects
timing), **I7/I8** (measured narration only), **I9** (shots stay in their
scene), **I5/I12** (renderer consumes manifest only), **I10** (audio/subtitles
follow narration). See `docs/architecture-v2.md` §3.
