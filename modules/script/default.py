"""Default script implementation.

Milestone 3: an LLM writes the narration script (Hook → Main Body → Ending)
from `ResearchOutput` only. The module never performs research, fetches URLs,
or calls search functionality. When the LLM provider is the stub, it falls
back to the deterministic template so the pipeline stays runnable without an
API key.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable

from pydantic import ValidationError

from config.settings import ScriptConfig
from core.errors import InputValidationError, StageRetryableError
from core.models import JobContext, Locale, StageResult
from core.stages import Stage
from providers.base import LLMProvider

from ..research.schemas import ResearchOutput
from .interface import ScriptModule
from .metrics import MetricsProfile, compute_metrics
from .schemas import NarrationBlock, ScriptMetadata, ScriptOutput
from .template import STYLE_DIRECTIVES, resolve_style, template_script

log = logging.getLogger(__name__)


def extract_json(text: str) -> dict:
    """Pull the outermost JSON object out of an LLM response."""
    text = re.sub(r"```(?:json)?", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found in LLM response")
    return json.loads(text[start : end + 1])


def build_script_prompt(
    research: ResearchOutput,
    style: str,
    requested_duration: int | None,
    words_per_minute: int,
    language: str = "en",
) -> str:
    target = requested_duration or 180
    word_budget = max(30, round(target * words_per_minute / 60))
    facts = "\n".join(f"- {fact.content}" for fact in research.facts) or "- (no facts)"
    language_directive = ""
    if language != "en":
        # Narration is written in the chosen language; queries stay English.
        # English skips the directive so V1 LLM output is byte-identical.
        language_directive = (
            f"Write the narration in the language with code {language!r} (not English). "
            "Every value in the JSON (hook, body paragraphs, ending) must be in that language.\n"
        )
    return (
        f"Write a narration script about: {research.topic}\n"
        f"Style: {style}. {STYLE_DIRECTIVES[style]}\n"
        f"Target duration: {target} seconds (~{word_budget} words at {words_per_minute} wpm).\n\n"
        f"Summary: {research.summary}\n"
        f"Key facts:\n{facts}\n\n"
        f"{language_directive}"
        'Return ONLY JSON: {"hook": str, "body": [str, ...], "ending": str}.\n'
        "The hook is the opening line, the body is 2 to 4 spoken paragraphs, and the ending wraps up. "
        "Write narration for speaking — no scene descriptions, camera directions, visual prompts, "
        "transitions, or asset search keywords."
    )


def finalize(
    script: ScriptOutput,
    style: str,
    requested_duration: int | None,
    words_per_minute: int,
    generated_by: str,
    profile: MetricsProfile | None = None,
    language: str = "en",
) -> ScriptOutput:
    """Derive narration + quality metrics + metadata onto a raw script."""
    script.narration = [NarrationBlock(paragraph=p) for p in [script.hook, *script.body, script.ending]]
    script.style = style
    script.language = language
    narration_text = " ".join(block.paragraph for block in script.narration)
    script.metrics = compute_metrics(narration_text, requested_duration, words_per_minute, profile)
    script.metadata = ScriptMetadata(
        style=style,
        requested_duration=requested_duration,
        estimated_duration=script.metrics.estimated_duration,
        word_count=script.metrics.word_count,
        generated_by=generated_by,
        language=language,
    )
    return script


class DefaultScriptModule(ScriptModule):
    def __init__(
        self,
        llm: LLMProvider,
        config: ScriptConfig | None = None,
        metrics_resolver: Callable[[Locale], MetricsProfile] | None = None,
    ) -> None:
        self.llm = llm
        self.config = config or ScriptConfig()
        # Per-language tokenizer/pacing profile (frozen §3): defaults to the
        # English MetricsProfile when no resolver is wired (tests, back-compat).
        self.metrics_resolver = metrics_resolver

    def validate_input(self, ctx: JobContext) -> None:
        result = ctx.results.get(Stage.RESEARCH)
        if result is None or result.output is None:
            raise InputValidationError("script requires a research output")

    def run(self, ctx: JobContext) -> StageResult:
        research: ResearchOutput = ctx.results[Stage.RESEARCH].output
        style = resolve_style(ctx.input.style, self.config.style)
        duration = ctx.input.duration
        profile = self.metrics_resolver(ctx.locale) if self.metrics_resolver else MetricsProfile()
        wpm = profile.words_per_minute
        language = ctx.locale.script_language

        if self.llm.name == "stub":
            ctx.progress("Generating script from template...")
            script = template_script(research, style)
            generated_by = "template"
        else:
            ctx.progress("Generating narration script...")
            script = self._llm_script(research, style, duration, language)
            generated_by = f"llm:{self.llm.name}"

        finalize(script, style, duration, wpm, generated_by, profile, language)
        wc = script.metrics.word_count if script.metrics else 0
        est = script.metrics.estimated_duration if script.metrics else 0
        ctx.progress(f"Script: {wc} words, ~{est:.0f}s estimated ({language})")
        return StageResult(
            stage=self.name, ok=True, output=script, artifacts_written=[self._save(ctx, "script.json", script)]
        )

    def _llm_script(
        self, research: ResearchOutput, style: str, duration: int | None, language: str = "en"
    ) -> ScriptOutput:
        system = "You are a video narration scriptwriter. Return ONLY valid JSON matching the requested schema."
        raw = self.llm.complete(
            build_script_prompt(research, style, duration, self.config.words_per_minute, language), system=system
        )
        try:
            return self._parse_draft(raw)
        except (KeyError, ValueError, ValidationError, TypeError) as exc:
            log.warning("script draft parse failed; attempting one repair: %s", exc)
            repair = (
                f"Your previous response was not valid JSON ({exc}). Respond with ONLY JSON: "
                f'{{"hook": str, "body": [str, ...], "ending": str}}. Previous response:\n{raw[:2000]}'
            )
            try:
                return self._parse_draft(self.llm.complete(repair, system=system))
            except Exception as exc2:  # noqa: BLE001 - surfaced as a retryable stage failure
                raise StageRetryableError(f"script draft not valid JSON after repair: {exc2}") from exc

    @staticmethod
    def _parse_draft(raw: str) -> ScriptOutput:
        data = extract_json(raw)
        return ScriptOutput(hook=data["hook"], body=list(data.get("body") or []), ending=data["ending"])
