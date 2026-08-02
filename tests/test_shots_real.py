"""Shot planner tests (architecture v2, Phase 1): pass-through template + module.

Phase 1 produces exactly one shot per scene, mirroring the scene's existing
visual plan. No media retrieval, timing, or rendering is involved; the
`ShotPlan` is written as an artifact but is not yet consumed downstream.
"""

from __future__ import annotations

import pytest

from core.errors import InputValidationError
from core.models import JobContext, StageResult, UserInput
from core.stages import Stage
from memory.store import ArtifactStore
from modules.scenes.schemas import Scene, ScenePlan
from modules.shots.default import DefaultShotsModule
from modules.shots.schemas import Shot, ShotPlan
from modules.shots.template import plan_shots, scene_id_for, shot_id_for


def _scenes() -> ScenePlan:
    return ScenePlan(
        scenes=[
            Scene(
                scene=1,
                duration=20,
                narration="n1",
                visual_description="rocket closeup",
                search_keywords=["rocket", "launch"],
                visual_type="stock_video",
                transition="cut",
            ),
            Scene(
                scene=2,
                duration=20,
                narration="n2",
                visual_description="earth from orbit",
                search_keywords=["earth", "orbit"],
                visual_type="stock_image",
                transition="dissolve",
            ),
            Scene(
                scene=3,
                duration=20,
                narration="n3",
                visual_description="moon landing",
                search_keywords=["moon", "landing"],
                visual_type="map",
                transition="fade_to_black",
            ),
        ]
    )


# -- template (pass-through) mode --------------------------------------------


def test_template_one_shot_per_scene():
    plan = plan_shots(_scenes())
    assert len(plan.shots) == 3
    assert [s.position for s in plan.shots] == [1, 1, 1]
    assert [s.shot_id for s in plan.shots] == ["shot_0001", "shot_0002", "shot_0003"]
    assert [s.scene_id for s in plan.shots] == ["scene_0001", "scene_0002", "scene_0003"]


def test_template_copies_scene_visual_plan():
    plan = plan_shots(_scenes())
    assert plan.shots[0].visual_description == "rocket closeup"
    assert plan.shots[0].search_queries == ["rocket", "launch"]
    assert plan.shots[0].transition_out == "cut"
    assert plan.shots[1].search_queries == ["earth", "orbit"]
    assert plan.shots[1].transition_out == "dissolve"


def test_template_maps_visual_type_to_content_kind_and_preference():
    plan = plan_shots(_scenes())
    assert plan.shots[0].content_kind == "stock_video"
    assert plan.shots[0].media_preference == "video"
    assert plan.shots[1].content_kind == "stock_image"
    assert plan.shots[1].media_preference == "image"
    assert plan.shots[2].content_kind == "map"
    assert plan.shots[2].media_preference == "image"
    assert plan.shots[2].transition_out == "fade_to_black"


def test_template_maps_every_v1_visual_type():
    from modules.scenes.template import VISUAL_TYPES

    valid_kinds = {"stock_video", "stock_image", "text", "chart", "map"}
    valid_prefs = {"video", "image", "either"}
    for index, visual_type in enumerate(VISUAL_TYPES, start=1):
        scene = Scene(scene=index, narration=f"n{index}", visual_type=visual_type)
        shot = plan_shots(ScenePlan(scenes=[scene])).shots[0]
        assert shot.content_kind in valid_kinds, visual_type
        assert shot.media_preference in valid_prefs, visual_type


def test_template_derives_purpose_from_scene_position():
    plan = plan_shots(_scenes())
    assert [s.purpose for s in plan.shots] == ["establish", "main", "closing"]
    single = plan_shots(ScenePlan(scenes=[_scenes().scenes[0]]))
    assert single.shots[0].purpose == "main"


def test_template_empty_plan_is_empty():
    assert plan_shots(ScenePlan(scenes=[])).shots == []


# -- module ------------------------------------------------------------------


def test_module_requires_scenes(make_ctx):
    ctx = make_ctx()
    with pytest.raises(InputValidationError):
        DefaultShotsModule().validate_input(ctx)


def test_module_writes_shot_plan_artifact(make_ctx):
    ctx = make_ctx(**{Stage.SCENES: _scenes()})
    result = DefaultShotsModule().run(ctx)
    assert result.ok
    assert isinstance(result.output, ShotPlan)
    assert len(result.output.shots) == 3
    assert ctx.store.exists(Stage.SHOTS, "shot_plan.json")


def test_module_emits_progress(tmp_path):
    store = ArtifactStore(tmp_path / "out" / "job-test")
    ctx = JobContext(job_id="job-test", input=UserInput(topic="Neural Networks"), store=store)
    ctx.results[Stage.SCENES] = StageResult(stage=Stage.SCENES, ok=True, output=_scenes())
    events = []
    ctx.current_stage = Stage.SHOTS
    ctx._progress_cb = lambda e: events.append(e)

    DefaultShotsModule().run(ctx)

    assert events
    assert all(e.stage == "shots" for e in events)
    assert any(e.message.startswith("Shot shot_0001") for e in events)
    assert any("3 shot(s)" in e.message for e in events)


# -- schema ------------------------------------------------------------------


def test_shot_schema_serializes_cleanly():
    shot = Shot(shot_id="shot_0001", scene_id="scene_0001", position=1)
    dumped = shot.model_dump(mode="json")
    assert dumped["shot_id"] == "shot_0001"
    assert dumped["scene_id"] == "scene_0001"
    assert dumped["content_kind"] == "stock_video"
    assert dumped["media_preference"] == "either"
    assert dumped["motion_intent"] == "none"
    assert dumped["importance"] == "medium"
    assert dumped["transition_out"] == "cut"
    assert {
        "shot_id",
        "scene_id",
        "position",
        "purpose",
        "visual_description",
        "search_queries",
        "content_kind",
        "media_preference",
        "motion_intent",
        "importance",
        "transition_out",
    } <= set(dumped)


def test_shot_plan_roundtrip():
    plan = plan_shots(_scenes())
    restored = ShotPlan.model_validate(plan.model_dump(mode="json"))
    assert restored == plan


def test_id_helpers():
    assert scene_id_for(1) == "scene_0001"
    assert scene_id_for(123) == "scene_0123"
    assert shot_id_for(1) == "shot_0001"
    assert shot_id_for(42) == "shot_0042"
