"""SRT subtitle helpers, shared by production (write) and quality (validate)."""

from __future__ import annotations

from pathlib import Path

from .schemas import SubtitleCue


def timestamp(seconds: float) -> str:
    total_ms = int(round(max(0.0, seconds) * 1000))
    ms = total_ms % 1000
    total_s = total_ms // 1000
    hours, rem = divmod(total_s, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def parse_timestamp(text: str) -> float:
    hms, ms = text.strip().split(",")
    hours, minutes, secs = (float(part) for part in hms.split(":"))
    return hours * 3600 + minutes * 60 + secs + float(ms) / 1000.0


def build_srt(cues: list[SubtitleCue]) -> str:
    blocks = [
        f"{cue.index}\n{timestamp(cue.start)} --> {timestamp(cue.end)}\n{cue.text}\n"
        for cue in cues
    ]
    return "\n".join(blocks)


def parse_srt(path: Path) -> list[SubtitleCue]:
    text = Path(path).read_text(encoding="utf-8")
    cues: list[SubtitleCue] = []
    index = 0
    start = end = 0.0
    lines: list[str] = []

    def flush() -> None:
        nonlocal lines
        if lines and index:
            cues.append(SubtitleCue(index=index, start=start, end=end, text=" ".join(lines)))
        lines = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            flush()
        elif line.isdigit():
            index = int(line)
        elif "-->" in line:
            left, right = line.split("-->")
            start, end = parse_timestamp(left), parse_timestamp(right)
        else:
            lines.append(line)
    flush()
    return cues
