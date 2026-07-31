"""Script module tests (milestone 3): template + LLM modes, styles, metrics.

The stub provider drives the deterministic template fallback; a fake LLM
drives the primary (LLM-written) path. No real providers or network needed.
"""

from __future__ import annotations

import json

import pytest

from config.settings import ScriptConfig
from core.errors import InputValidationError, StageRetryableError
from core.stages import Stage
from modules.script.default import DefaultScriptModule, build_script_prompt, extract_json, finalize
from modules.script.metrics import compute_metrics, count_words, duration_match, estimate_duration
from modules.script.schemas import ScriptOutput
from modules.script.template import STYLES, resolve_style, template_script
from providers.base import LLMProvider
from providers.stubs.llm import StubLLMProvider


class FakeLLM(LLMProvider):
    name = "fake"

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls = 0
        self.model = "fake-model"

    def complete(self, prompt: str, *, system: str | None = None, **kwargs: object) -> str:
        self.calls += 1
        return self.responses.pop(0) if self.responses else "{}"


DRAFT = {"hook": "Hooked.", "body": ["Body one.", "Body two."], "ending": "Wrapped up."}


# -- template (fallback) mode -------------------------------------------------


def test_template_script_structure(research):
    script = template_script(research, "explainer")
    assert script.hook
    assert script.ending
    assert script.body
    assert script.style == "explainer"
    assert script.narration[0].paragraph == script.hook
    assert script.narration[-1].paragraph == script.ending
    assert len(script.narration) == len(script.body) + 2


def test_template_module_writes_artifact_with_metrics(make_ctx, research):
    ctx = make_ctx(**{Stage.RESEARCH: research})
    result = DefaultScriptModule(StubLLMProvider(), config=ScriptConfig(style="explainer")).run(ctx)

    out = result.output
    assert out.metrics is not None
    assert out.metrics.word_count > 0
    assert out.metrics.estimated_duration > 0
    assert out.metadata.generated_by == "template"
    assert out.metadata.requested_duration == 60  # from the make_ctx input
    assert out.metadata.style == "explainer"
    assert ctx.store.exists(Stage.SCRIPT, "script.json")


def test_all_styles_resolve_and_render(research):
    for style in STYLES:
        assert resolve_style(style) == style
        assert template_script(research, style).style == style
    assert resolve_style("EDUCATIONAL") == "educational"
    assert resolve_style("Top 10") == "top10"
    assert resolve_style("news-brief") == "news"
    assert resolve_style("banana", default="explainer") == "explainer"


def test_top10_numbers_facts(research):
    script = template_script(research, "top10")
    assert script.body and script.body[0].startswith("1.")


# -- LLM (primary) mode -------------------------------------------------------


def test_llm_mode_applies_draft_and_metrics(make_ctx, research):
    ctx = make_ctx(**{Stage.RESEARCH: research})
    result = DefaultScriptModule(FakeLLM([json.dumps(DRAFT)]), config=ScriptConfig(style="storytelling")).run(ctx)

    out = result.output
    assert out.hook == "Hooked."
    assert out.body == ["Body one.", "Body two."]
    assert out.ending == "Wrapped up."
    assert [b.paragraph for b in out.narration] == ["Hooked.", "Body one.", "Body two.", "Wrapped up."]
    assert out.style == "storytelling"
    assert out.metadata.generated_by == "llm:fake"
    assert out.metrics.word_count == count_words(" ".join(b.paragraph for b in out.narration))


def test_llm_repairs_unparseable_first_try(make_ctx, research):
    ctx = make_ctx(**{Stage.RESEARCH: research})
    llm = FakeLLM(["not json at all", json.dumps(DRAFT)])
    out = DefaultScriptModule(llm).run(ctx).output
    assert out.hook == "Hooked."
    assert llm.calls == 2


def test_llm_unparseable_raises_retryable(make_ctx, research):
    ctx = make_ctx(**{Stage.RESEARCH: research})
    llm = FakeLLM(["nope", "still no"])
    with pytest.raises(StageRetryableError):
        DefaultScriptModule(llm).run(ctx)


def test_validate_input_requires_research(make_ctx):
    with pytest.raises(InputValidationError):
        DefaultScriptModule(StubLLMProvider()).validate_input(make_ctx())


# -- helpers ------------------------------------------------------------------


def test_finalize_populates_metrics_and_narration():
    script = ScriptOutput(hook="H", body=["B"], ending="E")
    finalize(script, "news", 120, 150, "llm:x")
    assert [b.paragraph for b in script.narration] == ["H", "B", "E"]
    assert script.style == "news"
    assert script.metrics is not None
    assert script.metadata.generated_by == "llm:x"


def test_build_script_prompt_carries_style_budget_and_constraints(research):
    prompt = build_script_prompt(research, "explainer", 120, 150)
    assert "Neural Networks" in prompt
    assert "explainer" in prompt
    assert "300 words" in prompt  # 120s * 150wpm / 60
    assert "no scene descriptions" in prompt


def test_extract_json():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Here you go: {"a": 2}. Thanks') == {"a": 2}
    with pytest.raises(ValueError):
        extract_json("no object here")


def test_metrics_math():
    assert count_words("the cat sat") == 3
    assert estimate_duration(150, 150) == 60.0
    assert duration_match(120, 120) == 1.0
    assert duration_match(240, 120) == 0.0
    assert duration_match(180, 120) == 0.5
    assert duration_match(120, None) is None

    m = compute_metrics("The cat sat on the mat.", requested_duration=60, words_per_minute=150)
    assert m.word_count == 6
    assert m.readability.sentences == 1
    assert m.estimated_duration > 0
    assert m.duration_match is not None
