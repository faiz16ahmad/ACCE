"""Auto-caching asset downloads.

Downloads are strictly a post-selection concern — the downloader never
participates in ranking. Binary files are cached under
`<cache_root>/media_files/<sha256(url)><ext>` so re-runs skip the network.
Skipped URLs (non-http or placeholder hosts) return None without error.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .base import ProviderError

log = logging.getLogger(__name__)

_PLACEHOLDER_HOSTS = {"placeholder.example"}
_DEFAULT_UA = "ACCE/0.1"
_CHUNK = 64 * 1024


def download_asset(
    url: str,
    dest: Path,
    cache_root: Path,
    *,
    timeout: float = 15.0,
    max_bytes: int = 50_000_000,
) -> Path | None:
    """Download `url` into `dest`, caching the binary by URL.

    Returns `dest` on success, `None` when the URL is not downloadable, and
    raises `ProviderError` if the network/stream fails.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or parsed.netloc in _PLACEHOLDER_HOSTS:
        return None

    suffix = Path(parsed.path).suffix
    suffix = suffix if suffix and len(suffix) <= 5 else ".bin"
    cache_file = cache_root / "media_files" / f"{hashlib.sha256(url.encode()).hexdigest()}{suffix}"
    cache_root.mkdir(parents=True, exist_ok=True)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    dest.parent.mkdir(parents=True, exist_ok=True)

    if not cache_file.exists():
        _stream(url, cache_file, timeout, max_bytes)
        log.info("downloaded %s -> %s", url, cache_file)
    else:
        log.debug("media file cache hit: %s", cache_file)
    shutil.copyfile(cache_file, dest)
    return dest


def _stream(url: str, dest: Path, timeout: float, max_bytes: int) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": _DEFAULT_UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - http(s) checked by caller
            with open(dest, "wb") as out:
                remaining = max_bytes
                while True:
                    chunk = resp.read(min(_CHUNK, remaining))
                    if not chunk:
                        break
                    out.write(chunk)
                    remaining -= len(chunk)
                    if remaining <= 0:
                        raise ProviderError(f"asset exceeds {max_bytes} bytes: {url}")
    except Exception as exc:
        dest.unlink(missing_ok=True)
        raise ProviderError(f"download failed for {url}: {exc}") from exc
