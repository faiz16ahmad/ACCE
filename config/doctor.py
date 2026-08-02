"""`python main.py doctor` — production-readiness checks.

Every check reports PASS / FAIL / SKIP (not enabled in current config),
plus a one-line fix hint when FAIL. Live API probes are stdlib GETs with
explicit timeouts, gated by the provider chain you actually configured.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from providers._http import get_json
from providers.base import ProviderError

from .settings import Settings

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"

_CORE_DEPS = ["pydantic", "pydantic_settings", "fastapi", "uvicorn"]
_EXTRA_HINTS: dict[str, str] = {
    "google.genai": "uv sync --extra gemini   (or: pip install -e .[gemini])",
    "edge_tts": "uv sync --extra tts   (or: pip install edge-tts)",
}
_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str = ""


# ---------------------------------------------------------------------------
# Pure helpers (easily unit-testable)
# ---------------------------------------------------------------------------

def _module_importable(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ModuleNotFoundError, ValueError):
        return False


def _ffmpeg_install_hint() -> str:
    if sys.platform == "win32":
        return "winget install Gyan.FFmpeg  (then reopen your terminal)"
    if sys.platform == "darwin":
        return "brew install ffmpeg"
    return "sudo apt install ffmpeg  (or your distro's package)"


def _effective_key(*candidates: str | None) -> str:
    """Return the first truthy value (env vars / config fields)."""
    for key in candidates:
        if key:
            return key
    return ""


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_ffmpeg(ffmpeg_path: str | None = None, name: str = "ffmpeg") -> CheckResult:
    binary = ffmpeg_path or "ffmpeg"
    found = shutil.which(binary)
    if found is None:
        return CheckResult(name, FAIL, f"{binary!r} not found on PATH — install: {_ffmpeg_install_hint()}")
    try:
        proc = subprocess.run([found, "-version"], capture_output=True, text=True, timeout=15)
        ok = proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        ok = False
    if not ok:
        return CheckResult(name, FAIL, f"{found} present but won't run — reinstall ffmpeg")
    return CheckResult(name, PASS, found)


def check_dependencies(settings: Settings) -> CheckResult:
    missing = [dep for dep in _CORE_DEPS if not _module_importable(dep)]
    if settings.llm.provider == "gemini" and not _module_importable("google.genai"):
        missing.append("google.genai")
    if settings.tts.provider == "edge" and not _module_importable("edge_tts"):
        missing.append("edge_tts")
    if missing:
        hints = "; ".join(
            f"{name} -> {_EXTRA_HINTS.get(name, f'pip install {name}')}" for name in missing
        )
        return CheckResult("python deps", FAIL, f"missing {', '.join(missing)} — {hints}")
    installed = [dep for dep in _CORE_DEPS if _module_importable(dep)]
    return CheckResult("python deps", PASS, ", ".join(installed))


def check_dotenv(env_file: Path = Path(".env")) -> CheckResult:
    if env_file.is_file():
        return CheckResult(".env loaded", PASS, str(env_file.resolve()))
    return CheckResult(
        ".env loaded",
        FAIL,
        f"{env_file} not found — cp .env.example {env_file} and set your keys",
    )


# ---------------------------------------------------------------------------
# Live API probes (stdlib, no extra deps)
# ---------------------------------------------------------------------------

def probe_gemini(settings: Settings) -> CheckResult:
    key = _effective_key(settings.llm.api_key, os.environ.get("GEMINI_API_KEY"))
    if not key:
        return CheckResult("llm/gemini", FAIL, "no API key — set ACCE_LLM__API_KEY (or GEMINI_API_KEY)")
    base = (settings.llm.base_url or _GEMINI_BASE).rstrip("/")
    try:
        get_json(f"{base}/models?key={quote(key)}", timeout=10)
    except ProviderError as exc:
        return CheckResult("llm/gemini", FAIL, f"{exc} — check ACCE_LLM__API_KEY")
    return CheckResult("llm/gemini", PASS, "key valid")


def probe_pexels(settings: Settings) -> CheckResult:
    key = _effective_key(settings.media.pexels_api_key, os.environ.get("PEXELS_API_KEY"))
    if not key:
        return CheckResult("media/pexels", FAIL, "no API key — set ACCE_MEDIA__PEXELS_API_KEY (or PEXELS_API_KEY)")
    try:
        get_json(
            "https://api.pexels.com/v1/search?query=sky&per_page=1",
            headers={"Authorization": key},
            timeout=10,
        )
    except ProviderError as exc:
        return CheckResult("media/pexels", FAIL, f"{exc} — check ACCE_MEDIA__PEXELS_API_KEY")
    return CheckResult("media/pexels", PASS, "key valid")


def probe_pixabay(settings: Settings) -> CheckResult:
    key = _effective_key(settings.media.pixabay_api_key, os.environ.get("PIXABAY_API_KEY"))
    if not key:
        return CheckResult(
            "media/pixabay", FAIL, "no API key — set ACCE_MEDIA__PIXABAY_API_KEY + ACCE_MUSIC__PIXABAY_API_KEY"
        )
    try:
        data = get_json(
            f"https://pixabay.com/api/?key={quote(key)}&q=sky&per_page=1&image_type=photo",
            timeout=10,
        )
    except ProviderError as exc:
        return CheckResult("media/pixabay", FAIL, f"{exc} — check ACCE_MEDIA__PIXABAY_API_KEY")
    if data.get("error"):
        return CheckResult("media/pixabay", FAIL, f"API error: {data['error']}")
    return CheckResult("media/pixabay", PASS, "key valid")


# ---------------------------------------------------------------------------
# Gate checks (SKIP when not configured; probe when enabled)
# ---------------------------------------------------------------------------

def check_llm(settings: Settings) -> CheckResult:
    if settings.llm.provider == "gemini":
        return probe_gemini(settings)
    return CheckResult("llm/gemini", SKIP, "provider is stub — set ACCE_LLM__PROVIDER=gemini to enable")


def check_pexels(settings: Settings) -> CheckResult:
    if "pexels" in settings.media.providers:
        return probe_pexels(settings)
    return CheckResult("media/pexels", SKIP, "not in ACCE_MEDIA__PROVIDERS — add 'pexels' to enable")


def check_pixabay(settings: Settings) -> CheckResult:
    if "pixabay" in settings.media.providers or "pixabay" in settings.music.providers:
        return probe_pixabay(settings)
    return CheckResult("media/pixabay", SKIP, "not in ACCE_MEDIA__PROVIDERS / ACCE_MUSIC__PROVIDERS — add 'pixabay'")


def check_renderer(settings: Settings) -> CheckResult:
    if settings.production.renderer == "ffmpeg":
        return check_ffmpeg(settings.production.ffmpeg_path, name="renderer/ffmpeg")
    return CheckResult("renderer", SKIP, "stub renderer — set ACCE_PRODUCTION__RENDERER=ffmpeg for a real MP4")


def check_audio_engine(settings: Settings) -> CheckResult:
    if settings.audio.engine == "ffmpeg":
        return check_ffmpeg(settings.production.ffmpeg_path, name="audio/ffmpeg")
    return CheckResult("audio engine", SKIP, "stub engine — set ACCE_AUDIO__ENGINE=ffmpeg for real mixing")


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def run_checks(settings: Settings) -> list[CheckResult]:
    return [
        check_ffmpeg(settings.production.ffmpeg_path),
        check_dependencies(settings),
        check_dotenv(),
        check_llm(settings),
        check_pexels(settings),
        check_pixabay(settings),
        check_renderer(settings),
        check_audio_engine(settings),
    ]


def run_doctor(settings: Settings | None = None) -> int:
    settings = settings or Settings()
    results = run_checks(settings)
    width = max(len(result.name) for result in results) + 2
    print("ACCE doctor")
    print("-" * 48)
    for result in results:
        print(f"  {result.name:<{width}} {result.status:<5} {result.detail}")
    passed = sum(r.status == PASS for r in results)
    failed = sum(r.status == FAIL for r in results)
    skipped = sum(r.status == SKIP for r in results)
    print("-" * 48)
    print(f"{passed} passed · {failed} failed · {skipped} skipped")
    return 1 if failed else 0
