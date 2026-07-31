"""Lightweight source fetching for fact verification.

A fact counts as *verified* only when one of its cited sources is fetched
successfully during the run. This layer keeps that to a bare minimum: stdlib
`urllib`, a timeout, a couple of retries, a size cap, and basic HTML title /
plain-text extraction. Deliberately not a crawler — no JS, no sitemaps, no
link following.
"""

from __future__ import annotations

import html as html_module
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

log = logging.getLogger(__name__)

_USER_AGENT = "ACCE-research/0.1 (+https://example.com/acce)"
_MAX_BODY_BYTES = 1_000_000
_MAX_EXCERPT_CHARS = 2_000

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)


@dataclass
class FetchResult:
    url: str
    ok: bool = False
    http_status: int | None = None
    title: str | None = None
    excerpt: str | None = None
    error: str | None = None


class SourceFetcher:
    """Fetch one page with a timeout, retries, size cap, and basic parsing."""

    def __init__(
        self,
        timeout: float = 8.0,
        retries: int = 2,
        max_excerpt_chars: int = _MAX_EXCERPT_CHARS,
        max_body_bytes: int = _MAX_BODY_BYTES,
    ) -> None:
        self.timeout = timeout
        self.retries = retries
        self.max_excerpt_chars = max_excerpt_chars
        self.max_body_bytes = max_body_bytes

    def fetch(self, url: str) -> FetchResult:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return FetchResult(url=url, error=f"unsupported scheme: {parsed.scheme!r}")

        last_error: str | None = None
        for attempt in range(self.retries + 1):
            try:
                return self._fetch_once(url)
            except urllib.error.HTTPError as exc:
                # 4xx/5xx are authoritative — no retry.
                return FetchResult(url=url, http_status=exc.code, error=f"HTTP {exc.code}")
            except (urllib.error.URLError, OSError, ValueError) as exc:  # TimeoutError is an OSError subclass
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt < self.retries:
                    log.warning("fetch %s failed (attempt %d/%d): %s", url, attempt + 1, self.retries + 1, last_error)
        return FetchResult(url=url, error=last_error or "fetch failed")

    def _fetch_once(self, url: str) -> FetchResult:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310 - http(s) checked above
            http_status = resp.status
            raw = resp.read(self.max_body_bytes + 1)
            body = raw[: self.max_body_bytes]
            charset = _charset_of(resp, body)
            text = body.decode(charset, errors="replace")
        return FetchResult(
            url=url,
            ok=True,
            http_status=http_status,
            title=extract_title(text),
            excerpt=extract_excerpt(text, self.max_excerpt_chars),
        )


def _charset_of(resp: urllib.request.Request, body: bytes) -> str:
    header_charset = re.search(r"charset=([\w-]+)", resp.headers.get("Content-Type", ""), re.IGNORECASE)
    if header_charset:
        return header_charset.group(1)
    meta_charset = re.search(rb'<meta[^>]+charset=["\']?([\w-]+)', body[:4096], re.IGNORECASE)
    return meta_charset.group(1).decode("ascii", "ignore") if meta_charset else "utf-8"


def extract_title(html_text: str) -> str | None:
    match = _TITLE_RE.search(html_text)
    if not match:
        return None
    title = _TAG_RE.sub("", match.group(1))
    title = html_module.unescape(title).strip()
    return title or None


def extract_excerpt(html_text: str, max_chars: int = _MAX_EXCERPT_CHARS) -> str | None:
    """First `max_chars` of visible text, HTML stripped and whitespace collapsed."""
    text = _SCRIPT_STYLE_RE.sub(" ", html_text)
    text = _TAG_RE.sub(" ", text)
    text = html_module.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars] if text else None
