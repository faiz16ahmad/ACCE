"""FastAPI application entry point.

Run from the project root: `uv run uvicorn frontend.api.app:app --reload`
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
