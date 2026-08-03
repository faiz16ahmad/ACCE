"""Language packs and the per-language registry (frozen architecture).

A language is **data** — one YAML pack under `config/languages/{code}.yaml`.
Adding a language is adding a file: no module change, no pipeline branch.
The registry scans the packs directory, validates each against
`LanguageProfile`, and derives the per-job `Locale` (language only) and the
default `Narrator` (voice identity, separate from Locale).

Reference: `docs/language-architecture.md` (frozen).
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from core.models import Locale, Narrator

log = logging.getLogger(__name__)

DEFAULT_LANGUAGES_DIR = Path(__file__).resolve().parent / "languages"


class LanguageProfile(BaseModel):
    """Everything the pipeline needs to behave correctly in one language."""

    code: str
    native_name: str  # shown in the UI radio (e.g. "हिन्दी")
    english_name: str
    script: str = "latin"  # "latin" | "devanagari" | … → tokenizer + burn-in font
    words_per_minute: int = 150  # narration speaking rate
    punctuation: tuple[str, ...] = ()  # sentence terminators beyond .!?
    readability: str = "flesch"  # "flesch" | "none" (V1: hi → none, Flesch is English-only)
    tts_preference: list[str] = Field(default_factory=lambda: ["stub"])  # provider order, stub last
    default_voice: str | None = None  # seeds the default Narrator (§6)
    retrieval_language: str = "en"  # visual queries stay English (see §4)
    burn_font: str = ""  # ASS font-family for subtitle burn-in


class LanguageRegistry:
    """Loads + validates packs and derives Locale / default Narrator."""

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = Path(directory) if directory is not None else DEFAULT_LANGUAGES_DIR

    def languages(self) -> list[LanguageProfile]:
        if not self.directory.is_dir():
            return []
        profiles = []
        for path in sorted(self.directory.glob("*.yaml")):
            try:
                profiles.append(self._load(path))
            except (ValueError, yaml.YAMLError) as exc:
                log.warning("skipping invalid language pack %s: %s", path.name, exc)
        return profiles

    def profile(self, code: str) -> LanguageProfile:
        path = self.directory / f"{code}.yaml"
        if not path.is_file():
            known = ", ".join(sorted(p.code for p in self.languages())) or "(none)"
            raise ValueError(f"unknown language {code!r} — installed packs: {known}")
        return self._load(path)

    def resolve(self, pick: str) -> Locale:
        """A simple radio pick → the five-dimension Locale (all collapse in V1)."""
        profile = self.profile(pick)
        return Locale(
            language=profile.code,
            script_language=profile.code,
            narration_language=profile.code,
            subtitle_language=profile.code,
            metadata_language=profile.code,
            retrieval_language=profile.retrieval_language,
        )

    def default_narrator(self, code: str) -> Narrator:
        """The voice that speaks when the user picks a language and nothing else."""
        return Narrator(voice_id=self.profile(code).default_voice)

    @staticmethod
    def _load(path: Path) -> LanguageProfile:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return LanguageProfile.model_validate(data)


registry = LanguageRegistry()
