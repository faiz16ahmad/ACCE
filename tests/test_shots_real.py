"""Shot planner tests (architecture v2, Phase 3).

Multi-shot generation: the deterministic template proposes 1-3 shots per scene
by narration length; the LLM proposes 2-5. Either way the *normalizer* owns
enforcement of limits and schema validity (clamps, coerce, fill, drop, stable
ids). No media retrieval, timing, or rendering is involved.
"""

from __future__ import annotations

import json

import pytest

from config.settings import TimelineConfig
from core.errors import InputValidationError, StageRetryableError
from core.models import JobContext, StageResult, UserInput
from core.stages import Stage
from memory.store import ArtifactStore
from modules.scenes.schemas import Scene, ScenePlan
from modules.shots.default import DefaultShotsModule, build_shot_prompt, extract_json
from modules.shots.normalize import normalize_shot_plan
from modules.shots.schemas import Shot, ShotPlan
from modules.shots.template import plan_shots, scene_id_for, shot_id_for
from providers.base import LLMProvider


class FakeLLM(LLMProvider):
    name = "fake"

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls = 0

    def complete(self, prompt: str, *, system: str | None = None, **kwargs: object) -> str:
        self.calls += 1
        return self.responses.pop(0) if self.responses else "{}"


def _scenes() -> ScenePlan:
    """Narrative-only scenes; lengths chosen to yield 2/1/2 shots."""
    return ScenePlan(
        scenes=[
            Scene(
                scene=1,
                duration=20,
                narration="The rocket lifts off from the pad and climbs steadily. "
                "Engines roar as the sky turns bright orange. "
                "The launch is flawless from the first second.",
                rhythm="high",
            ),
            Scene(
                scene=2,
                duration=20,
                narration="The capsule re-enters the atmosphere and the heat shield glows red hot.",
                rhythm="medium",
            ),
            Scene(
                scene=3,
                duration=20,
                narration="A giant parachute opens above the capsule and slows its fall. "
                "The crew lands safely on the desert floor. "
                "They wave to the cameras and everyone cheers for the mission.",
                rhythm="low",
            ),
        ]
    )


# -- template (multi-shot fallback) --------------------------------------------


def test_template_multi_shot_by_narration_length():
    plan = plan_shots(_scenes(), topic="Rockets")
    # scene 1 -> 2 shots, scene 2 -> 1 shot, scene 3 -> 2 shots
    assert len(plan.shots) == 5
    assert [s.scene_id for s in plan.shots] == ["scene_0001", "scene_0001", "scene_0002", "scene_0003", "scene_0003"]
    assert [s.position for s in plan.shots] == [1, 2, 1, 1, 2]
    assert [s.shot_id for s in plan.shots] == [f"shot_{i:04d}" for i in range(1, 6)]


def test_template_derives_queries_and_description_from_narration():
    plan = plan_shots(_scenes(), topic="Rockets", style="explainer")
    for shot in plan.shots:
        assert shot.search_queries, shot.shot_id
        assert shot.visual_description
    # Queries come from the narration chunk, not from scene keywords (none exist).
    assert all(isinstance(q, str) and q.strip() for s in plan.shots for q in s.search_queries)


def test_template_emits_only_valid_enums():
    kinds = {"stock_video", "stock_image", "text", "chart", "map"}
    prefs = {"video", "image", "either"}
    motions = {"none", "zoom_in", "zoom_out", "pan"}
    importances = {"low", "medium", "high", "critical"}
    plan = plan_shots(_scenes(), topic="Rockets")
    for shot in plan.shots:
        assert shot.content_kind in kinds
        assert shot.media_preference in prefs
        assert shot.motion_intent in motions
        assert shot.importance in importances
        assert shot.transition_out


def test_template_last_shot_per_scene_fades_to_black():
    plan = plan_shots(_scenes(), topic="Rockets")
    closing = [s for s in plan.shots if s.scene_id == "scene_0003"]
    assert closing[-1].transition_out == "fade_to_black"
    assert closing[-1].purpose == "closing"


def test_template_empty_plan_is_empty():
    assert plan_shots(ScenePlan(scenes=[])).shots == []


# -- normalizer (enforcement boundary) -----------------------------------------


def test_normalize_clamps_excess_shots_per_scene():
    scenes = ScenePlan(scenes=[Scene(scene=1, narration="word " * 40)])
    entries = [{"scene_id": "scene_0001", "search_queries": ["q"], "visual_description": "d"} for _ in range(20)]
    plan = normalize_shot_plan(entries, scenes, TimelineConfig(max_shots=3))
    assert len(plan.shots) == 3  # clamped to max_shots
    assert [s.position for s in plan.shots] == [1, 2, 3]


def test_normalize_coerces_invalid_enums_and_fills_empties():
    scenes = ScenePlan(scenes=[Scene(scene=1, narration="The neural network learns from data and improves over time")])
    entries = [
        {
            "scene_id": "scene_0001",
            "content_kind": "hologram",
            "media_preference": "vertical",
            "motion_intent": "kenburns",
            "importance": "critical",
            "purpose": "reaction",
            "search_queries": ["", "  "],
            "visual_description": "",
            "transition_out": "",
        }
    ]
    plan = normalize_shot_plan(entries, scenes, TimelineConfig())
    shot = plan.shots[0]
    assert shot.content_kind == "stock_video"  # invalid -> default
    assert shot.media_preference == "either"
    assert shot.motion_intent == "none"
    assert shot.importance == "critical"  # valid -> kept
    assert shot.purpose == "reaction"  # valid -> kept
    assert shot.search_queries  # empty -> filled from narration
    assert shot.visual_description  # empty -> filled
    assert shot.transition_out == "cut"


def test_normalize_drops_unknown_scenes_and_synthesizes_missing():
    scenes = ScenePlan(scenes=[Scene(scene=1, narration="short text"), Scene(scene=2, narration="more text here")])
    entries = [{"scene_id": "scene_9999", "search_queries": ["x"], "visual_description": "v"}]
    plan = normalize_shot_plan(entries, scenes, TimelineConfig())
    assert plan.shots  # scene 1 synthesized
    assert all(shot.scene_id in ("scene_0001", "scene_0002") for shot in plan.shots)
    assert [shot.scene_id for shot in plan.shots] == ["scene_0001", "scene_0002"]
    assert [shot.shot_id for shot in plan.shots] == ["shot_0001", "shot_0002"]
    assert all(shot.search_queries for shot in plan.shots)


def test_normalize_is_stable_for_template_output():
    template = plan_shots(_scenes(), topic="Rockets")
    normalized = normalize_shot_plan(template, _scenes(), TimelineConfig())
    assert len(normalized.shots) == len(template.shots)
    assert [s.shot_id for s in normalized.shots] == [s.shot_id for s in template.shots]


# -- module -------------------------------------------------------------------


def test_module_requires_scenes(make_ctx):
    ctx = make_ctx()
    with pytest.raises(InputValidationError):
        DefaultShotsModule().validate_input(ctx)


def test_module_template_fallback_writes_artifact(make_ctx):
    ctx = make_ctx(**{Stage.SCENES: _scenes()})
    result = DefaultShotsModule(config=TimelineConfig()).run(ctx)
    assert result.ok
    assert isinstance(result.output, ShotPlan)
    assert len(result.output.shots) == 5
    assert ctx.store.exists(Stage.SHOTS, "shot_plan.json")


def test_module_llm_mode_proposes_then_normalizes(make_ctx):
    ctx = make_ctx(**{Stage.SCENES: _scenes()})
    llm = FakeLLM(
        [
            json.dumps(
                {
                    "shots": [
                        {"scene": 1, "visual_description": "Close-up of engines", "search_queries": ["engine", "fire"]},
                        {"scene": 1, "content_kind": "hologram", "search_queries": []},
                        {"scene": 2, "search_queries": ["reentry", "heat"]},
                    ]
                }
            )
        ]
    )
    result = DefaultShotsModule(llm, config=TimelineConfig()).run(ctx)
    assert llm.calls == 1
    plan = result.output
    # scene 3 had no proposal -> synthesized; invalid enum repaired.
    assert all(shot.content_kind in ("stock_video", "stock_image", "text", "chart", "map") for shot in plan.shots)
    assert {shot.scene_id for shot in plan.shots} == {"scene_0001", "scene_0002", "scene_0003"}
    assert plan.shots[0].search_queries == ["engine", "fire"]


def test_module_llm_repairs_on_garbage(make_ctx):
    ctx = make_ctx(**{Stage.SCENES: _scenes()})
    good = json.dumps({"shots": [{"scene": 1, "search_queries": ["ok"]}]})
    llm = FakeLLM(["garbage", good])
    DefaultShotsModule(llm, config=TimelineConfig()).run(ctx)
    assert llm.calls == 2


def test_module_llm_unparseable_raises_retryable(make_ctx):
    ctx = make_ctx(**{Stage.SCENES: _scenes()})
    with pytest.raises(StageRetryableError):
        DefaultShotsModule(FakeLLM(["bad", "worse"]), config=TimelineConfig()).run(ctx)


def test_module_emits_progress(tmp_path):
    store = ArtifactStore(tmp_path / "out" / "job-test")
    ctx = JobContext(job_id="job-test", input=UserInput(topic="Neural Networks"), store=store)
    ctx.results[Stage.SCENES] = StageResult(stage=Stage.SCENES, ok=True, output=_scenes())
    events = []
    ctx.current_stage = Stage.SHOTS
    ctx._progress_cb = lambda e: events.append(e)

    DefaultShotsModule(config=TimelineConfig()).run(ctx)

    assert events
    assert all(e.stage == "shots" for e in events)
    assert any(e.message.startswith("Shot shot_0001") for e in events)
    assert any("5 shot(s)" in e.message for e in events)


# -- prompt + schema -----------------------------------------------------------


def test_build_shot_prompt_includes_narration_and_rhythm():
    prompt = build_shot_prompt(_scenes())
    assert "The rocket lifts off" in prompt
    assert "rhythm high" in prompt
    assert "content_kind" in prompt


def test_extract_json():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    with pytest.raises(ValueError):
        extract_json("nothing here")


def test_shot_schema_serializes_cleanly():
    shot = Shot(shot_id="shot_0001", scene_id="scene_0001", position=1)
    dumped = shot.model_dump(mode="json")
    assert dumped["shot_id"] == "shot_0001"
    assert dumped["scene_id"] == "scene_0001"
    assert dumped["position"] == 1


def test_id_helpers():
    assert scene_id_for(3) == "scene_0003"
    assert shot_id_for(12) == "shot_0012"
