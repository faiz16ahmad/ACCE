# ACCE Development Roadmap

Status legend: ✅ done · 🔜 in progress · ⏳ not started

| # | Milestone | Scope | Status |
| - | --------- | ----- | ------ |
| 1 | Skeleton project | Folders, orchestrator, interfaces, stub modules, pydantic contracts, config, docs | ✅ |
| 2 | Research module | Real LLM research (Gemini provider) + live-fetch fact verification | ✅ |
| 3 | Script module | Real LLM scriptwriting (hook/body/ending/narration) + quality metrics | ✅ |
| 4 | Scene planner | Pacing + visual/keyword choices per scene | ✅ |
| 5 | Media search | Pexels/Pixabay/Wikimedia providers + asset downloads + license handling | ⏳ |
| 6 | Production | TTS (real), music (Pixabay Music), ffmpeg mixing & rendering, thumbnail | ⏳ |
| 7 | Quality | Hard failures + optional re-render of failing stages | ⏳ |
| 8 | UI | Next.js + Tailwind dashboard (stage, logs, progress, preview, download) | ⏳ |
| 9 | End-to-end | Publishable MP4 from a topic with minimal manual work | ⏳ |

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

## Milestone 5 — media

- `PexelsProvider`, `PixabayProvider`, `WikimediaProvider` (registered per
  the chain in `providers/media_chain.py`).
- Actual asset download into `out/<job_id>/media/`; record license + attribution.
- **Definition of done:** every scene has a locally-downloaded, license-clean asset.

## Milestone 6 — production (incl. audio)

- Real TTS (e.g. ElevenLabs / Google) writing narration audio.
- Music via Pixabay Music; `FfmpegAudioEngine` mixing per `AudioMixPlan`.
- ffmpeg timeline assembly → final.mp4; thumbnail frame extraction.
- **Dependency:** install ffmpeg on the host.
- **Note:** beat-sync is V2; `AudioMixPlan` + `AudioEngine` seam is already in place.

## Milestone 7 — quality

- Treat warnings/errors as gating signals; re-render only the failing stage
  (orchestrator already retries only the failing stage).
- **Definition of done:** a job either ships or reports exactly which stage to fix.

## Milestone 8 — UI

- Next.js + Tailwind dashboard in `frontend/web/` consuming the FastAPI API.
- Views: current stage, live logs, progress bar, preview, final download.

## Milestone 9 — end-to-end

- One command from topic → publishable MP4 with minimal manual work.
- E2E test that exercises every stage against real providers.
