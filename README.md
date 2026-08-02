# ACCE — Autonomous Content Creation Engine (V1)

Turn a topic + a few instructions into a video's full production package:
research report, script, scene timeline, media assets, narration, subtitles,
thumbnail, title, and description.

**V1 status:** the full pipeline is real and production-ready:
**Research → Script → Scene Planner → Shot Planner → Media → Audio → Production → Quality**.
Research drafts and verifies facts via **Gemini** or **OpenRouter** + live
source fetch; the **Script** stage writes Hook → Body → Ending narration
(LLM-written, template fallback) with quality metrics; the **Scene Planner**
converts that narration into a timed `scene_plan.json`; the **Shot Planner**
converts each scene into an ordered visual shot plan (`shot_plan.json`); the
**Media** stage retrieves the best visual asset per scene through a **Cache → Pexels → Pixabay
→ Wikimedia** chain with deterministic ranking and auto-caching downloads
(`media_plan.json`); the **Audio** stage generates narration (configured TTS),
selects background music by script style (**Pixabay Music → Local → Stub**),
mixes with volume + fades, and writes sentence-based subtitles (`audio.json` +
`subtitles.srt`); the **Production** stage builds an explicit timeline from
actual narration durations and a self-contained **render manifest**
(`render_manifest.json`) and renders through an isolated Renderer interface —
**stub** (default, no FFmpeg) or **FFmpeg** — with xfade transitions, burning
in subtitles and syncing the mixed audio (`final_video.mp4` + `timeline.json` +
`render_log.json`); the **Quality** stage runs deterministic validation over
every stage output, classifies issues INFO/WARNING/ERROR, scores the job
0–100, and recommends (never performs) the stage to retry (`quality.json`).
LLM + provider-driven, with deterministic fallbacks so the key-free stub demo
still runs end-to-end. **ACCE Studio** (`frontend/web/`, Next.js + Tailwind +
TypeScript) is a dark-first dashboard on top of the API: project list, a
Generate flow (topic → duration → style), live stage-by-stage pipeline
progress with timestamps, a per-stage **artifact explorer**, **video preview
+ download**, **audio preview** (master mix + per-scene narrations), a
**quality panel** (score, warnings/errors, suggested fixes, retry advice), and
logs.

Real providers are selected through `.env`, never code changes. The stub
remains the default so the pipeline runs without keys.

## Supported LLM Providers

| Provider | Key Required | Notes |
|----------|-------------|-------|
| `stub` | No | Deterministic template fallback |
| `gemini` | Yes | Google Gemini (free tier available) |
| `openrouter` | Yes | OpenRouter API (access to 300+ models) |
| `openai` | — | Not yet implemented |
| `anthropic` | — | Not yet implemented |

## Pipeline

```
Research → Script → Scene Planner → Shot Planner → Media Search → Audio → Production → Quality → Output
```

Every stage emits timestamped progress events so you can watch the pipeline
in real time via the Studio UI or API logs.

## Quickstart

Requires Python 3.11+ and (recommended) [uv](https://docs.astral.sh/uv/).

```bash
uv sync --extra dev        # or: pip install -e ".[dev]"

# Run the whole pipeline with stub providers (no keys needed):
uv run python main.py generate --topic "How neural networks learn" \
    --instruction "keep it beginner friendly" --duration 120

# Real research + script via Gemini: set ACCE_LLM__PROVIDER=gemini
# and an API key (ACCE_LLM__API_KEY or GEMINI_API_KEY), install the extra:
uv sync --extra gemini

# Or use OpenRouter (300+ models, some free):
# set ACCE_LLM__PROVIDER=openrouter and ACCE_LLM__API_KEY=<your-key>

# Real, key-free narration via Edge TTS (optional extra):
uv sync --extra tts
# then set ACCE_TTS__PROVIDER=edge in .env (voice: ACCE_TTS__VOICE=en-US-AriaNeural)

# Inspect a finished job:
uv run python main.py status <job_id>

# Run the dashboard API:
uv run python main.py api           # then GET http://127.0.0.1:8000/api/health

# Run the ACCE Studio web UI (separate terminal):
cd frontend/web && npm install && npm run dev   # http://127.0.0.1:3000
```

## Configuration

All settings live in `.env` (see [.env.example](.env.example)), prefix
`ACCE_`. Defaults run entirely on stubs.

```env
# LLM
ACCE_LLM__PROVIDER=gemini          # or: openrouter, stub
ACCE_LLM__MODEL=gemini-2.5-flash   # model ID for the provider
ACCE_LLM__API_KEY=your-key-here

# Media
ACCE_MEDIA__PROVIDERS=["pexels","wikimedia"]

# TTS
ACCE_TTS__PROVIDER=edge
ACCE_TTS__VOICE=en-US-AriaNeural

# Production
ACCE_PRODUCTION__RENDERER=ffmpeg
ACCE_PRODUCTION__FFMPEG_PATH=/path/to/ffmpeg
```

Every stage writes its output under `out/<job_id>/<stage>/` — e.g.
`out/job-abc123/research/research.json`, `.../production/subtitles.srt`.

## Layout

```
core/        domain models, stages, orchestrator
modules/     one module per stage (schemas / interface / default)
providers/   interfaces + registry + stubs (cache-first media chain)
memory/      DiskCache + per-job ArtifactStore
config/      pydantic-settings (.env)
frontend/    FastAPI API + Next.js web dashboard
tests/       contracts, cache, per-module, orchestrator
docs/        architecture (V1) + architecture-v2 (frozen V2 reference) + roadmap
main.py      CLI: generate / status / api
```

## Design rules

- One responsibility per module; one module per stage.
- No module calls external APIs directly — only provider interfaces.
- Dependency injection via `modules.factory.build_orchestrator`.
- Pydantic models for every contract; type hints throughout.
- A failed stage is retried on its own; then the job fails with a clear error.
- Timeline durations use actual measured narration output, not LLM estimates.

See [docs/architecture.md](docs/architecture.md) for diagrams and the
beat-sync-ready audio seam.

## Tests

```bash
uv run pytest
```

## Milestones

| Status | Milestone |
| ------ | --------- |
| ✅ | 1 · Skeleton |
| ✅ | 2 · Research (Gemini + live-fetch verification) |
| ✅ | 3 · Script (LLM Hook→Body→Ending + metrics) |
| ✅ | 4 · Scene planner (LLM visuals, paced scene_plan.json) |
| ✅ | 5 · Media retrieval (Pexels/Pixabay/Wikimedia, ranking, downloads) |
| ✅ | 6 · Audio (TTS narration, style music, mix, sentence subtitles) |
| ✅ | 7 · Production (timeline + render manifest, FFmpeg renderer, xfade transitions) |
| ✅ | 8 · Quality (deterministic validation, severity, score, retry recommendation) |
| ✅ | 9 · ACCE Studio UI (projects, generate, live progress, artifacts, video + audio preview, quality, logs) |
| ✅ | 10 · End-to-end publishable MP4 with full pipeline debugging |
