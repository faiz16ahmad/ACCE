# ACCE Dashboard (placeholder — milestone 8)

The V1 skeleton ships the backend only. This directory is where the
**Next.js + Tailwind** dashboard lands in milestone 8.

## Planned UI (from the master prompt)

| View        | Shows                                                        |
| ----------- | ------------------------------------------------------------ |
| Dashboard   | Start a new job (topic, instructions, duration, style)       |
| Progress    | Current stage + live log stream                              |
| Preview     | Scene thumbnails, narration, selected assets                  |
| Download    | Final MP4, subtitles, thumbnail, title, description           |

## Backend contract

The dashboard talks to the FastAPI app in `../api`:

- `POST /api/jobs`  — start a job (`{topic, instructions, duration, style}`)
- `GET /api/jobs/{id}` — status, current stage, result snapshot
- `GET /api/jobs/{id}/logs` — recent log lines

## Getting started (when implemented)

```bash
npx create-next-app@latest . --ts --tailwind --eslint
```

Point `NEXT_PUBLIC_API_URL` at the FastAPI origin (default `http://127.0.0.1:8000`).
