# ACCE — Autonomous Content Creation Engine (V1)

Turn a topic + a few instructions into a video's full production package:
research report, script, scene timeline, media assets, narration, subtitles,
thumbnail, title, and description.

**V1 status:** milestone 5 — the skeleton (milestone 1) is frozen, and the
**Research → Script → Scene Planner → Media** chain is real: research drafts
and verifies facts via **Gemini** + live source fetch; the **Script** stage
writes Hook → Body → Ending narration (LLM-written, template fallback) with
quality metrics; the **Scene Planner** converts that narration into a timed
`scene_plan.json`; the **Media** stage retrieves the best visual asset per
scene through a **Cache → Pexels → Pixabay → Wikimedia** chain with
deterministic ranking and auto-caching downloads, writing `media_plan.json`
(per-scene `asset_id`, provider, URL, license, ranked candidates). LLM +
provider-driven, with deterministic fallbacks so the key-free stub demo still
runs end-to-end. Audio / production stages still run on stubs; real
integrations land in milestones 6–9 ([roadmap](docs/roadmap.md)).

Real providers are selected through `.env`, never code changes. The stub
remains the default so the pipeline runs without keys; OpenAI / Anthropic /
GLM / DeepSeek / OpenRouter are drop-in later behind the same `LLMProvider`
interface.

## Pipeline

```
Research → Script → Scene Planner → Media Search → Audio → Production → Quality → Output
```

## Quickstart

Requires Python 3.11+ and (recommended) [uv](https://docs.astral.sh/uv/).

```bash
uv sync --extra dev        # or: pip install -e ".[dev]"

# Run the whole pipeline with stub providers (no keys needed):
uv run python main.py generate --topic "How neural networks learn" \
    --instruction "keep it beginner friendly" --duration 120

# Real research + script via Gemini (free tier): set ACCE_LLM__PROVIDER=gemini
# and an API key (ACCE_LLM__API_KEY or GEMINI_API_KEY), install the extra:
uv sync --extra gemini

# Inspect a finished job:
uv run python main.py status <job_id>

# Run the dashboard API:
uv run python main.py api           # then GET http://127.0.0.1:8000/api/health
```

Every stage writes its output under `out/<job_id>/<stage>/` — e.g.
`out/job-abc123/research/research.json`, `.../production/subtitles.srt`.

Configuration is via `.env` (see [.env.example](.env.example)), prefix
`ACCE_`. Defaults run entirely on stubs; setting `ACCE_LLM__PROVIDER=openai`
fails with a clear "not implemented in V1" error until that milestone ships.

## Layout

```
core/        domain models, stages, orchestrator
modules/     one module per stage (schemas / interface / default)
providers/   interfaces + registry + stubs (cache-first media chain)
memory/      DiskCache + per-job ArtifactStore
config/      pydantic-settings (.env)
frontend/    FastAPI API + web dashboard placeholder (milestone 8)
tests/       contracts, cache, per-module, orchestrator
docs/        architecture (Mermaid) + development roadmap
main.py      CLI: generate / status / api
```

## Design rules

- One responsibility per module; one module per stage.
- No module calls external APIs directly — only provider interfaces.
- Dependency injection via `modules.factory.build_orchestrator`.
- Pydantic models for every contract; type hints throughout.
- A failed stage is retried on its own; then the job fails with a clear error.

See [docs/architecture.md](docs/architecture.md) for diagrams and the
beat-sync-ready audio seam.

## Tests

```bash
uv run pytest
```

## Milestones

| Status | Milestone |
| ------ | --------- |
| ✅     | 1 · Skeleton |
| ✅     | 2 · Research (Gemini + live-fetch verification) |
| ✅     | 3 · Script (LLM Hook→Body→Ending + metrics) |
| ✅     | 4 · Scene planner (LLM visuals, paced scene_plan.json) |
| ✅     | 5 · Media retrieval (Pexels/Pixabay/Wikimedia, ranking, downloads) |
| ⏳     | 6–9 · Production, quality, UI, e2e |
