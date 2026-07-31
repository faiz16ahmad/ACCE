"""Tiny shared HTTP helper for provider integrations (stdlib only)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from .base import ProviderError

_USER_AGENT = "ACCE/0.1"


def get_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 15.0,
    max_bytes: int = 2_000_000,
) -> dict:
    """GET `url` and parse a JSON object; raise `ProviderError` on failure."""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - callers build http(s) URLs
            raw = resp.read(max_bytes + 1)
    except urllib.error.HTTPError as exc:
        raise ProviderError(f"HTTP {exc.code} from {url}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise ProviderError(f"{type(exc).__name__}: {exc}") from exc

    try:
        data = json.loads(raw[:max_bytes].decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise ProviderError(f"malformed JSON from {url}: {exc}") from exc
    if not isinstance(data, dict):
        raise ProviderError(f"unexpected response shape from {url}")
    return data
