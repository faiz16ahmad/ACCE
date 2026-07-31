# ACCE Studio (web UI)

Next.js (App Router) + Tailwind CSS + TypeScript dashboard for the ACCE
pipeline. Turns a topic into a narrated, illustrated video through the
existing FastAPI backend in `../api`.

## Views

| View            | What it does                                                       |
| --------------- | ------------------------------------------------------------------ |
| `/`             | Projects — every run, with status and quality score                |
| `/generate`     | New project — topic, duration, style, instructions                 |
| `/runs/[id]`    | Run workspace — live progress, preview, artifacts, quality, logs   |
| `/settings`     | API base URL + connection test, light/dark theme                   |

## Development

```bash
# 1. Backend (project root)
uv run python main.py api          # http://127.0.0.1:8000

# 2. Frontend (this directory)
npm install
npm run dev                        # http://127.0.0.1:3000
```

Point the UI at a different backend with `NEXT_PUBLIC_API_URL` (or via the
Settings page, persisted in `localStorage`).

## Scripts

```bash
npm run dev    # dev server
npm run build  # production build (includes type check)
npm run lint   # eslint
npm test       # vitest (lib helpers)
```

## Backend contract

The UI consumes the FastAPI app in `../api`:

- `GET /api/health`
- `POST /api/jobs` — start a job `{topic, instructions, duration, style}`
- `GET /api/jobs` — project list (in-memory + durable `out/` scan)
- `GET /api/jobs/{id}` — live job snapshot (`ctx.dump()`); falls back to
  `out/<id>/meta/job.json` for runs from before an API restart
- `GET /api/jobs/{id}/logs`
- `GET /api/jobs/{id}/artifacts` — per-stage file tree with URLs
- `/artifacts/...` — static file serving of `out/`

## Design

Dark-first theme (class toggle, persisted), hand-rolled Tailwind primitives,
single accent color, generous whitespace — modelled on Cursor / Linear rather
than an admin dashboard. See `app/globals.css` for the semantic color tokens.
