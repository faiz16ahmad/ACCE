"""Per-job artifact storage.

Every stage writes its output into `out/<job_id>/<stage>/`. The store is the
single place that knows how artifacts are laid out on disk, so modules never
touch paths directly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.models import Artifact
from core.stages import Stage

JSON_MODE = "json"


class ArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    @classmethod
    def create(cls, job_id: str, output_root: Path) -> ArtifactStore:
        return cls(Path(output_root) / job_id)

    def dir_for(self, stage: Stage | str) -> Path:
        directory = self.root / str(stage)
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def resolve(self, stage: Stage | str, name: str) -> Path:
        return self.dir_for(stage) / name

    def exists(self, stage: Stage | str, name: str) -> bool:
        return self.resolve(stage, name).exists()

    def save_json(self, stage: Stage | str, name: str, data: Any) -> Artifact:
        if hasattr(data, "model_dump"):
            data = data.model_dump(mode=JSON_MODE)
        path = self.resolve(stage, name)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return Artifact(stage=str(stage), name=name, path=path)

    def save_text(self, stage: Stage | str, name: str, text: str) -> Artifact:
        path = self.resolve(stage, name)
        path.write_text(text, encoding="utf-8")
        return Artifact(stage=str(stage), name=name, path=path)

    def save_bytes(self, stage: Stage | str, name: str, data: bytes) -> Artifact:
        path = self.resolve(stage, name)
        path.write_bytes(data)
        return Artifact(stage=str(stage), name=name, path=path)
