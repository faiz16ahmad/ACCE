"""A tiny JSON-on-disk cache.

Used to cache research, media hits, music selections, generated audio
metadata, and subtitles. Keys are hashed so any string (URLs, prompts) is
safe as a filename. Namespaces keep purposes isolated (e.g. `media` vs
`research`).
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


class DiskCache:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _path(self, namespace: str, key: str) -> Path:
        digest = hashlib.sha256(f"{namespace}:{key}".encode()).hexdigest()
        return self.root / namespace / f"{digest}.json"

    def has(self, namespace: str, key: str) -> bool:
        return self._path(namespace, key).exists()

    def get(self, namespace: str, key: str) -> Any | None:
        path = self._path(namespace, key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            log.warning("cache read failed for %s:%s", namespace, key)
            return None

    def set(self, namespace: str, key: str, value: Any) -> None:
        path = self._path(namespace, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.write_text(json.dumps(value, default=str, ensure_ascii=False), encoding="utf-8")
        except OSError as exc:  # pragma: no cover - defensive
            log.warning("cache write failed for %s:%s: %s", namespace, key, exc)

    def delete(self, namespace: str, key: str) -> None:
        path = self._path(namespace, key)
        if path.exists():
            path.unlink()
