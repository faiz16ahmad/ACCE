# ACCE Development Roadmap

Status legend: ✅ done · 🔜 in progress · ⏳ not started

| # | Milestone | Scope | Status |
| - | --------- | ----- | ------ |
| 1 | Skeleton project | Folders, orchestrator, interfaces, stub modules, pydantic contracts, config, docs | ✅ |
| 2 | Research module | Real LLM research (Gemini provider) + live-fetch fact verification | ✅ |
| 3 | Script module | Real LLM scriptwriting (hook/body/ending/narration) + quality metrics | ✅ |
| 4 | Scene planner | Pacing + visual/keyword choices per scene | ✅ |
| 5 | Media search | Pexels/Pixabay/Wikimedia providers + asset downloads + license handling | ✅ |
| 6 | Audio | TTS narration, music by style (Pixabay Music / Local / Stub), narration+music mix, sentence subtitles | ✅ |
| 7 | Production | ffmpeg rendering (timeline assembly) + thumbnail | ✅ |
| 8 | Quality | Hard failures + optional re-render of failing stages | ⏳ |
| 9 | UI | Next.js + Tailwind dashboard (stage, logs, progress, preview, download) | ⏳ |
| 10 | End-to-end | Publishable MP4 from a topic with minimal manual work | ⏳ |

## Milestone 1 — done (this deliverable)

- Fully runnable 7-stage pipeline on **stub providers** (no external calls).
- `python main.py generate --topic X` writes artifacts to `out/<job_id>/`.
- Every module: `validate_input` / `run` / `validate_output`, unit-tested
  standalone.
- Cache-first media chain + JSON cache + per-job artifact store.
- FastAPI API (`/api/health`, `/api/jobs`, `/api/jobs/{id}`, `/api/jobs/{id}/logs`).

## Milestone 2 — research (done)

- `GeminiProvider` (first real LLM; free tier) via `ACCE_LLM__PROVIDER=gemini`;
  the stub stays the default. OpenAI/Anthropic/GLM/DeepSeek/OpenRouter are
  drop-in later — implement `LLMProvider` + register.
- `DefaultResearchModule` drafts structured JSON (facts, angles, entities,
  chronology, sources, summary), then **fetches every cited URL** and stamps
  facts `verified` only when a supporting source fetched OK; untraceable
  facts are dropped. An optional, non-authoritative refine pass polishes
  wording.
- Rich `research.json`: facts + verification, fetched source statuses,
  angles, entities, chronology, and metadata.
- **Definition of done:** research.json contains fetch-verified, attributed
  facts that downstream modules consume.
- **TODO (later milestone):** obtain source URLs from a dedicated
  SearchProvider instead of relying on LLM-generated URLs.

## Milestone 3 — script (done)

- LLM-written Hook → Body → Ending narration from `ResearchOutput` only
  (never research/fetch/search); deterministic template fallback when the
  provider is the stub, so the demo runs without an API key.
- Six configurable styles (educational, documentary, storytelling, news,
  top10, explainer) via `ACCE_SCRIPT__STYLE` / `UserInput.style`.
- Quality metrics on every script: word count, estimated duration at
  `ACCE_SCRIPT__WORDS_PER_MINUTE`, Flesch readability, and `duration_match`
  against the requested duration.
- **Definition of done:** narration reads naturally, follows the research,
  and reports pacing/readability metrics.

## Milestone 4 — scene planner (done)

- Converts `ScriptOutput` narration into a timed `ScenePlan` — one scene per
  narration block, durations proportional to each segment's word share of the
  script's estimated length.
- Per-scene `visual_description`, `search_keywords`, `visual_type`
  (stock_video|stock_image|animation|infographic|map|text_overlay), and
  `transition` — LLM-written when a real provider is configured, deterministic
  template as the stub/offline fallback and safety net. Only plans visuals:
  no research, media retrieval, or rendering.
- New artifact: `scene_plan.json` (fields: scene_number, narration_segment,
  estimated_duration, visual_description, search_keywords, visual_type,
  transition). Older names `scene`/`narration`/`duration` kept as read-only
  aliases so media/audio/quality need no changes.
- **Definition of done:** scenes map 1:1 onto narration beats.

## Milestone 5 — media (done)

- Provider abstraction as designed: independent `ImageProvider` /
  `VideoProvider` implementations (Pexels, Pixabay, Wikimedia) registered in
  `providers/registry.py`; the module never branches on which provider is used.
- Chain priority **Cache → Pexels → Pixabay → Wikimedia** in
  `MediaChain.best()`: rank each provider's candidates, stop at the first
  satisfactory top hit, return the **full ranked candidate list** (selection is
  `candidates[0]`). A failing provider never breaks the chain.
- Deterministic V1 ranking (`providers/ranking.py`): resolution, orientation,
  video duration, license, keyword match — no AI.
- Downloads (`providers/download.py`) are a separate post-selection step,
  auto-cached by URL, and never influence ranking. No suitable asset → a
  structured placeholder, pipeline still passes.
- New artifact `media_plan.json`: per scene `scene_number`, stable `asset_id`
  (`asset_0001`…), `selected_provider`, `asset_type`, `asset_url`, `local_path`,
  `attribution`, `license`, `search_query`, and `candidates`.
- **Definition of done:** every scene has a selected, license-attributed asset
  (locally downloaded when a real provider/key is configured).

## Milestone 6 — audio (done)

- **Narration** per scene through the configured `TTSProvider` (stub default,
  key-free; real TTS vendors drop in behind the same interface).
- **Music selection** through a provider chain — priority **Pixabay Music →
  Local assets → Stub** (`MusicChain`) — driven by script style via a
  configurable style→genre map (educational→calm, storytelling→cinematic,
  news→neutral, documentary→atmospheric, …).
- **Mix plan** (volume + fade in/out only in V1 — no beat sync, ducking,
  dynamic/emotion-aware changes) → engine mix → master audio.
- **Subtitles** generated from scene/narration timing (sentence-based, no
  word-level alignment), independent of the mixer/engine, each cue with a
  stable `cue_id` (`cue_0001`…).
- `audio.json` contains `narration_path`, `music_path`, `mixed_audio_path`,
  `subtitle_path`, `duration`, `metadata` (plus back-compat `master_path`,
  `tracks`, `mix_plan_path`).
- **Definition of done:** every scene has narration audio; a style-appropriate
  music track is selected and mixed; sentence-timed subtitles ship with the
  audio package.

## Milestone 7 — production (done)

- **Timeline builder**: explicit timeline (per scene `scene_number`, `asset_id`,
  `start_time`, `end_time`, `transition`) from ScenePlan durations — timing is
  never inferred from media length.
- **Render manifest**: the renderer's complete, self-contained input
  (`render_manifest.json`): timeline, per-scene asset references, audio +
  subtitle references, render settings (resolution, fps, codec), and transition
  metadata. Renderers consume only the manifest — no ScenePlan / MediaPlan /
  AudioOutput — keeping backends isolated, replaceable, and renders replayable.
- **Renderer interface**: `StubRenderer` (keeps the pipeline runnable without
  FFmpeg) and `FFmpegRenderer` (image scenes via `-loop`, video scenes via
  `-stream_loop -1` + `trim` to the planned duration, text-overlay/placeholder
  scenes via a color source + `drawtext`), subtitle burn-in, and audio mapped
  from `mixed_audio_path` for exact timeline sync.
- **Transitions** (V1): `cut`, `fade`, `dissolve` (fade-through-black), and
  `fade_to_black`.
- Outputs: `final_video.mp4`, `timeline.json`, `render_manifest.json`,
  `render_log.json`; `ProductionOutput` carries `video_path`, `timeline_path`,
  `render_manifest_path`, `render_log_path`, `duration`, `metadata`.
- **Definition of done:** a render job is fully described by its manifest; the
  stub stays key-free/runnable, and the FFmpeg renderer is unit-testable
  without the binary (command generation + failure handling).

## Milestone 8 — quality

- Treat warnings/errors as gating signals; re-render only the failing stage
  (orchestrator already retries only the failing stage).
- **Definition of done:** a job either ships or reports exactly which stage to fix.

## Milestone 9 — UI

- Next.js + Tailwind dashboard in `frontend/web/` consuming the FastAPI API.
- Views: current stage, live logs, progress bar, preview, final download.

## Milestone 10 — end-to-end

- One command from topic → publishable MP4 with minimal manual work.
- E2E test that exercises every stage against real providers.
