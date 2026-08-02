"""Scene planner tests (architecture v2, Phase 3): narrative-only scenes.

Scenes carry narration, an estimated duration, and a rhythm hint — no visual
fields (visual intent lives in the ShotPlan). The module is fully deterministic
(no LLM). Compatibility aliases (scene/narration/duration), the pacing rules,
and the surviving template helpers are covered here; the visual-rules and
multi-shot tests live in `test_shots_real.py`.
"""

from __future__ import annotations

from core.stages import Stage
from modules.scenes.default import DefaultScenesModule
from modules.scenes.schemas import Scene, ScenePlan
from modules.scenes.template import keywords_for, plan_scenes, transition_for, visual_type_for
from modules.script.schemas import NarrationBlock, ScriptOutput


# -- module (deterministic, narrative-only) ------------------------------------


def test_module_one_scene_per_narration_block(make_ctx, script):
    ctx = make_ctx(**{Stage.SCRIPT: script})
    result = DefaultScenesModule().run(ctx)

    plan = result.output
    assert isinstance(plan, ScenePlan)
    assert len(plan.scenes) == len(script.narration)
    assert [s.scene_number for s in plan.scenes] == list(range(1, len(plan.scenes) + 1))
    assert all(s.narration_segment for s in plan.scenes)
    assert all(s.estimated_duration > 0 for s in plan.scenes)
    assert ctx.store.exists(Stage.SCENES, "scene_plan.json")


def test_module_durations_sum_to_target(make_ctx, script):
    ctx = make_ctx(**{Stage.SCRIPT: script})
    plan = DefaultScenesModule().run(ctx).output
    total = sum(s.estimated_duration for s in plan.scenes)
    assert abs(total - 60) < 1.5  # make_ctx input duration


def test_scenes_are_narrative_only(make_ctx, script):
    ctx = make_ctx(**{Stage.SCRIPT: script})
    plan = DefaultScenesModule().run(ctx).output
    for scene in plan.scenes:
        assert scene.visual_description == ""
        assert scene.search_keywords == []
        assert scene.rhythm in ("low", "medium", "high", "intense")
        assert "topic" in scene.metadata


def test_rhythm_hook_and_ending_high(make_ctx, script):
    ctx = make_ctx(**{Stage.SCRIPT: script})
    plan = DefaultScenesModule().run(ctx).output
    if len(plan.scenes) > 1:
        assert plan.scenes[0].rhythm == "high"
        assert plan.scenes[-1].rhythm == "high"
        assert all(s.rhythm == "medium" for s in plan.scenes[1:-1])


# -- schema + aliases ----------------------------------------------------------


def test_scene_schema_accepts_old_and_new_kwargs():
    old = Scene(scene=1, duration=20, narration="n", search_keywords=["a"])
    assert old.scene_number == 1
    assert old.estimated_duration == 20.0
    assert old.narration_segment == "n"

    new = Scene(scene_number=2, estimated_duration=30.0, narration_segment="m", rhythm="high")
    assert new.scene == 2
    assert new.duration == 30.0
    assert new.narration == "m"
    assert new.rhythm == "high"

    dumped = new.model_dump(mode="json")
    assert {"scene_number", "narration_segment", "estimated_duration", "rhythm"} <= set(dumped)
    assert "scene" not in dumped  # serialized under the new field names


# -- pacing + surviving helpers ------------------------------------------------


def test_template_pacing_rhythm():
    blocks = [NarrationBlock(paragraph="word " * 10) for _ in range(5)]
    plan = plan_scenes(ScriptOutput(hook="h", body=["b"], ending="e", narration=blocks), 60, "topic")
    durations = [scene.estimated_duration for scene in plan.scenes]
    assert abs(sum(durations) - 60) < 1.5
    # Equal word counts -> the rhythm multipliers make hook and ending shorter
    # than the body scenes.
    assert durations[0] < durations[1]
    assert durations[-1] < durations[1]


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


def test_keywords_for_concrete_and_topic_first():
    keywords = keywords_for("The neural network processes data at scale", "Neural Networks")
    assert keywords and "neural" in keywords
    assert "the" not in keywords
    assert "at" not in keywords
