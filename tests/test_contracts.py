"""Contract tests: pydantic model shapes, serialization, and round-trips."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.models import JobContext, StageResult, UserInput
from core.stages import Stage


def test_user_input_requires_topic():
    with pytest.raises(ValidationError):
        UserInput(topic="")
    assert UserInput(topic="ok").topic == "ok"


def test_stage_enum_order():
    assert [s.value for s in Stage] == [
        "research",
        "script",
        "scenes",
        "media",
        "audio",
        "production",
        "quality",
    ]


def test_scene_contract_shape():
    from modules.scenes.schemas import Scene

    scene = Scene(scene=1, duration=5, narration="n", visual_description="v", search_keywords=["a", "b"])
    assert scene.model_dump() == {
        "scene": 1,
        "duration": 5,
        "narration": "n",
        "visual_description": "v",
        "search_keywords": ["a", "b"],
    }


def test_research_output_has_expected_keys():
    from modules.research.schemas import ResearchOutput

    assert set(ResearchOutput(topic="t").model_dump(mode="json")) == {
        "topic",
        "facts",
        "sources",
        "summary",
        "angles",
        "entities",
        "chronology",
        "metadata",
    }


def test_job_context_roundtrip_dump_load():
    ctx = JobContext(job_id="j", input=UserInput(topic="t"))
    restored = JobContext.model_validate(ctx.dump())
    assert restored.job_id == "j"
    assert restored.input.topic == "t"


def test_stage_result_serializes_output():
    from modules.script.schemas import ScriptOutput

    res = StageResult(stage=Stage.SCRIPT, output=ScriptOutput(hook="h", ending="e"))
    raw = res.model_dump(mode="json")
    assert raw["stage"] == "script"
    assert raw["output"]["hook"] == "h"
    assert raw["output"]["narration"] == []


def test_audio_track_exposes_bpm_for_beat_sync():
    from modules.audio.schemas import AudioTrack

    track = AudioTrack(kind="music", provider="stub", title="t", bpm=120)
    assert track.bpm == 120


def test_srt_build_and_parse_roundtrip(tmp_path):
    from modules.production.schemas import SubtitleCue
    from modules.production.srt import build_srt, parse_srt

    cues = [
        SubtitleCue(index=1, start=0.0, end=1.5, text="hi there"),
        SubtitleCue(index=2, start=1.5, end=3.25, text="bye"),
    ]
    path = tmp_path / "subs.srt"
    path.write_text(build_srt(cues), encoding="utf-8")

    parsed = parse_srt(path)
    assert [c.text for c in parsed] == ["hi there", "bye"]
    assert parsed[0].start == 0.0
    assert parsed[1].end == 3.25
