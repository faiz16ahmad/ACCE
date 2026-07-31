"""Milestone 10: styled ASS subtitle tests."""

from __future__ import annotations

from modules.production.ass import _ass_time, build_ass
from modules.production.schemas import SubtitleCue


def test_ass_time_formatting():
    assert _ass_time(0.0) == "0:00:00.00"
    assert _ass_time(5.25) == "0:00:05.25"
    assert _ass_time(61.1) == "0:01:01.10"
    assert _ass_time(3661.999) == "1:01:02.00"


def test_build_ass_includes_style_and_events():
    cues = [SubtitleCue(index=1, start=0.0, end=5.0, text="Hello, world.")]
    doc = build_ass(cues, width=1920, height=1080)
    assert "[V4+ Styles]" in doc
    assert "Fontsize" in doc
    assert "Dialogue: 0,0:00:00.00,0:00:05.00,Default,,0,0,0,,Hello, world." in doc
    assert "Inter" in doc
    assert "PlayResX: 1920" in doc


def test_escape_override_tags_and_newlines():
    cues = [SubtitleCue(index=1, start=0.0, end=1.0, text="a {b} c\nd")]
    doc = build_ass(cues)
    assert "a (b) c" in doc
    assert "\\N" in doc
