"""Scene planner tests (milestone 4): template + LLM modes, schema compat.

The stub provider drives the deterministic template; a fake LLM drives the
LLM-visuals path. No media retrieval, search providers, or network involved.
"""

from __future__ import annotations

import json

import pytest

from core.errors import StageRetryableError
from core.stages import Stage
from modules.scenes.default import DefaultScenesModule, build_visuals_prompt, extract_json
from modules.scenes.schemas import Scene, ScenePlan
from modules.scenes.template import keywords_for, plan_scenes, transition_for, visual_type_for
from modules.script.schemas import NarrationBlock, ScriptOutput
from providers.base import LLMProvider
from providers.stubs.llm import StubLLMProvider


class FakeLLM(LLMProvider):
    name = "fake"

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls = 0

    def complete(self, prompt: str, *, system: str | None = None, **kwargs: object) -> str:
        self.calls += 1
        return self.responses.pop(0) if self.responses else "{}"


def _ctx_with_script(make_ctx, script):
    return make_ctx(**{Stage.SCRIPT: script})


# -- template (fallback) mode -------------------------------------------------


def test_template_mode_one_scene_per_narration_block(make_ctx, script):
    ctx = _ctx_with_script(make_ctx, script)
    result = DefaultScenesModule(StubLLMProvider()).run(ctx)

    plan = result.output
    assert isinstance(plan, ScenePlan)
    assert len(plan.scenes) == len(script.narration)
    assert [s.scene_number for s in plan.scenes] == list(range(1, len(plan.scenes) + 1))
    assert all(s.narration_segment for s in plan.scenes)
    assert all(s.estimated_duration > 0 for s in plan.scenes)
    assert ctx.store.exists(Stage.SCENES, "scene_plan.json")


def test_template_durations_sum_to_target(make_ctx, script):
    ctx = _ctx_with_script(make_ctx, script)
    plan = DefaultScenesModule(StubLLMProvider()).run(ctx).output
    total = sum(s.estimated_duration for s in plan.scenes)
    assert abs(total - 60) < 1.5  # make_ctx input duration


def test_compat_properties_and_ending_visual(make_ctx, script):
    ctx = _ctx_with_script(make_ctx, script)
    plan = DefaultScenesModule(StubLLMProvider()).run(ctx).output
    for scene in plan.scenes:
        assert scene.scene == scene.scene_number
        assert scene.narration == scene.narration_segment
        assert scene.duration == scene.estimated_duration
    assert plan.scenes[-1].visual_type == "text_overlay"
    assert plan.scenes[-1].transition == "fade_to_black"


def test_template_keywords_avoid_generic(make_ctx, script):
    ctx = _ctx_with_script(make_ctx, script)
    plan = DefaultScenesModule(StubLLMProvider()).run(ctx).output
    for scene in plan.scenes:
        assert "technology" not in scene.search_keywords
        assert "history" not in scene.search_keywords
        assert all(len(kw) >= 3 for kw in scene.search_keywords)


# -- LLM visuals (primary) mode -----------------------------------------------


def test_llm_visuals_applied_per_scene(make_ctx, script):
    ctx = _ctx_with_script(make_ctx, script)
    visuals = {
        "visuals": [
            {"visual_description": "Close-up of neurons firing", "search_keywords": ["neuron", "synapse", "brain"],
             "visual_type": "animation", "transition": "dissolve"},
            {"visual_description": "Diagram of a network", "search_keywords": ["layers", "nodes"],
             "visual_type": "infographic", "transition": "cut"},
            {"visual_description": "Call to action", "search_keywords": ["learning", "AI"],
             "visual_type": "text_overlay", "transition": "fade_to_black"},
        ]
    }
    llm = FakeLLM([json.dumps(visuals)])
    out = DefaultScenesModule(llm).run(ctx).output

    assert llm.calls == 1
    assert out.scenes[0].visual_description == "Close-up of neurons firing"
    assert out.scenes[0].visual_type == "animation"
    assert out.scenes[0].transition == "dissolve"
    assert "neuron" in out.scenes[0].search_keywords
    assert out.scenes[1].visual_type == "infographic"
    assert out.scenes[2].visual_type == "text_overlay"


def test_llm_invalid_visual_type_falls_back_to_template(make_ctx, script):
    ctx = _ctx_with_script(make_ctx, script)
    visuals = {"visuals": [{"visual_type": "hologram"}, {"visual_type": "map"}, {"visual_type": "stock_video"}]}
    out = DefaultScenesModule(FakeLLM([json.dumps(visuals)])).run(ctx).output
    assert out.scenes[0].visual_type == "stock_video"  # invalid -> template default
    assert out.scenes[1].visual_type == "map"
    assert out.scenes[2].visual_type == "stock_video"


def test_llm_visuals_repair_on_garbage(make_ctx, script):
    ctx = _ctx_with_script(make_ctx, script)
    good = json.dumps({"visuals": [{"visual_type": "map", "search_keywords": ["map"]}]})
    llm = FakeLLM(["garbage", good])
    out = DefaultScenesModule(llm).run(ctx).output
    assert llm.calls == 2
    assert out.scenes[0].visual_type == "map"


def test_llm_visuals_unparseable_raises_retryable(make_ctx, script):
    ctx = _ctx_with_script(make_ctx, script)
    with pytest.raises(StageRetryableError):
        DefaultScenesModule(FakeLLM(["bad", "worse"])).run(ctx)


# -- schema + helpers ---------------------------------------------------------


def test_scene_schema_accepts_old_and_new_kwargs():
    old = Scene(scene=1, duration=20, narration="n", search_keywords=["a"])
    assert old.scene_number == 1
    assert old.estimated_duration == 20.0
    assert old.narration_segment == "n"

    new = Scene(scene_number=2, estimated_duration=30.0, narration_segment="m")
    assert new.scene == 2
    assert new.duration == 30.0
    assert new.narration == "m"

    dumped = new.model_dump(mode="json")
    assert {"scene_number", "narration_segment", "estimated_duration", "visual_type", "transition"} <= set(dumped)
    assert "scene" not in dumped  # serialized under the new field names


def test_visual_type_rules():
    assert visual_type_for("It grew 3x", 1, False, "explainer") == "infographic"
    assert visual_type_for("Located in France", 1, False, "explainer") == "map"
    assert visual_type_for("plain text here", 1, False, "explainer") == "stock_video"
    assert visual_type_for("plain", 3, True, "explainer") == "text_overlay"
    assert visual_type_for("anything", 0, False, "top10") == "text_overlay"


def test_transition_rules():
    assert transition_for(0, False) == "cut"
    assert transition_for(1, False) == "dissolve"
    assert transition_for(2, False) == "fade"
    assert transition_for(0, True) == "fade_to_black"


# -- milestone 10: pacing rhythm + visual variety -----------------------------


def test_template_pacing_rhythm():
    blocks = [NarrationBlock(paragraph="word " * 10) for _ in range(5)]
    plan = plan_scenes(ScriptOutput(hook="h", body=["b"], ending="e", narration=blocks), 60, "topic")
    durations = [scene.estimated_duration for scene in plan.scenes]
    assert abs(sum(durations) - 60) < 1.5
    # Equal word counts -> the rhythm multipliers make hook and ending shorter
    # than the body scenes.
    assert durations[0] < durations[1]
    assert durations[-1] < durations[1]


def test_template_visual_variety_includes_still_and_motion():
    paragraphs = [
        "plain words here alpha",
        "plain words here beta",
        "plain words here gamma",
        "plain words here delta",
        "plain words here epsilon",
        "plain words here zeta",
    ]
    plan = plan_scenes(
        ScriptOutput(
            hook="h", body=["b"], ending="e", narration=[NarrationBlock(paragraph=p) for p in paragraphs]
        ),
        60,
        "topic",
        style="explainer",
    )
    types = [scene.visual_type for scene in plan.scenes]
    assert "stock_image" in types
    assert "stock_video" in types
    assert plan.scenes[-1].visual_type == "text_overlay"


def test_keywords_for_concrete_and_topic_first():
    keywords = keywords_for("The neural network processes data at scale", "Neural Networks")
    assert keywords and "neural" in keywords
    assert "the" not in keywords
    assert "at" not in keywords


def test_build_visuals_prompt_includes_segments_and_constraints(script):
    plan = plan_scenes(script, 60, "Neural Networks", style="explainer")
    prompt = build_visuals_prompt("Neural Networks", "explainer", plan)
    assert "Hook!" in prompt
    assert "avoid generic keywords" in prompt
    assert "stock_video" in prompt


def test_extract_json():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    with pytest.raises(ValueError):
        extract_json("nothing here")
