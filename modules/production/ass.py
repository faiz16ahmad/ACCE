"""Styled ASS subtitle generation.

The contract artifact stays `subtitles.srt`; this module produces a styled
`subtitles.ass` (same cues) that the renderer burns in so published videos have
legible captions — larger font, black outline + drop shadow, bottom margin.
ASS is chosen because ffmpeg's `subtitles` filter applies its styles natively.
"""

from __future__ import annotations

from .schemas import SubtitleCue

_FORMAT_LINE = (
    "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
    "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
    "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
    "MarginL, MarginR, MarginV, Encoding"
)
_EVENTS_FORMAT = "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"


def _ass_time(seconds: float) -> str:
    total_cs = int(round(max(0.0, seconds) * 100))
    hours, rem = divmod(total_cs, 3600 * 100)
    minutes, rem = divmod(rem, 60 * 100)
    secs, centis = divmod(rem, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def _escape_text(text: str) -> str:
    # `{`/`}` are ASS override-tag delimiters; newlines are hard breaks.
    return text.replace("{", "(").replace("}", ")").replace("\n", "\\N")


def _dialogue(cue: SubtitleCue) -> str:
    return (
        f"Dialogue: 0,{_ass_time(cue.start)},{_ass_time(cue.end)},"
        f"Default,,0,0,0,,{_escape_text(cue.text)}"
    )


def build_ass(
    cues: list[SubtitleCue],
    *,
    width: int = 1920,
    height: int = 1080,
    font: str = "Inter",
    outline: int = 2,
    shadow: int = 1,
    margin_v: int | None = None,
) -> str:
    """Render `cues` as a styled ASS subtitle document."""
    font_size = max(32, int(height * 0.05))  # ~54px at 1080p
    margin_v = margin_v if margin_v is not None else max(30, int(height * 0.045))
    style_line = (
        f"Style: Default,{font}, {font_size}, &H00FFFFFF, &H000000FF, "
        "&H00101010, &H80000000, 0, 0, 0, 0, 100, 100, 0, 0, 1, "
        f"{outline}, {shadow}, 2, 48, 48, {margin_v}, 1"
    )
    events = [_dialogue(cue) for cue in cues]
    return "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            f"PlayResX: {width}",
            f"PlayResY: {height}",
            "WrapStyle: 0",
            "ScaledBorderAndShadow: yes",
            "",
            "[V4+ Styles]",
            _FORMAT_LINE,
            style_line,
            "",
            "[Events]",
            _EVENTS_FORMAT,
            *events,
        ]
    )
