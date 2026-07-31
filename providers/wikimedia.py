"""Wikimedia Commons image/video providers (keyless).

Uses the Commons API search generator (`action=query&generator=search`).
No API key required.
"""

from __future__ import annotations

import re
from urllib.parse import urlencode

from ._http import get_json
from .base import ImageProvider, VideoProvider
from .models import MediaHit

_BASE = "https://commons.wikimedia.org/w/api.php"
_LICENSE_MARKERS = ("cc", "public domain", "pd", "attribution")


class _WikimediaBase:
    def __init__(self, api_key: str | None = None, timeout: float = 15.0, **_: object) -> None:
        self.timeout = timeout


class WikimediaImageProvider(_WikimediaBase, ImageProvider):
    name = "wikimedia"

    def search(self, query: str, *, count: int = 1) -> list[MediaHit]:
        return _parse_pages(_search(query, count, ""), provider=self.name, media_type="image")


class WikimediaVideoProvider(_WikimediaBase, VideoProvider):
    name = "wikimedia"

    def search(self, query: str, *, count: int = 1) -> list[MediaHit]:
        return _parse_pages(_search(query, count, "filetype:video"), provider=self.name, media_type="video")


def _search(query: str, count: int, extra: str) -> dict:
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": f"{query} {extra}".strip(),
        "gsrnamespace": "6",
        "gsrlimit": count,
        "prop": "imageinfo",
        "iiprop": "url|extmetadata",
        "iiurlwidth": 1920,
    }
    return get_json(f"{_BASE}?{urlencode(params)}")


def _parse_pages(data: dict, *, provider: str, media_type: str) -> list[MediaHit]:
    pages = (data.get("query") or {}).get("pages") or {}
    hits = []
    for page in pages.values():
        infos = page.get("imageinfo") or []
        if not infos:
            continue
        info = infos[0]
        extmeta = info.get("extmetadata") or {}
        hits.append(
            MediaHit(
                provider=provider,
                media_type=media_type,
                url=info.get("thumburl") or info.get("url") or "",
                license=_license(_value(extmeta, "LicenseShortName")),
                attribution=_clean(_value(extmeta, "Artist")) or None,
                width=info.get("width"),
                height=info.get("height"),
                title=_clean(_value(extmeta, "ImageDescription")) or page.get("title"),
            )
        )
    return hits


def _value(extmeta: dict, key: str) -> str:
    entry = extmeta.get(key) or {}
    return entry.get("value") or ""


def _license(name: str) -> str:
    if not name:
        return "unknown"
    low = name.lower()
    return name if any(marker in low for marker in _LICENSE_MARKERS) else "unknown"


def _clean(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()
