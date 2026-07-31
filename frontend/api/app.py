"""FastAPI application entry point.

Run from the project root: `uv run uvicorn frontend.api.app:app --reload`
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config.settings import Settings

from .routes import router

settings = Settings()

app = FastAPI(title="ACCE API", version=settings.app_version)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # dev only; tighten before serving the dashboard
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)

# Serve per-job artifacts (out/<job_id>/<stage>/<file>) at /artifacts/<job_id>/<stage>/<file>.
settings.paths.output_dir.mkdir(parents=True, exist_ok=True)
app.mount("/artifacts", StaticFiles(directory=str(settings.paths.output_dir)), name="artifacts")
