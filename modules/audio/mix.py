"""FFmpeg mix-graph builder.

Consumes only an `AudioMixPlan` and produces an ffmpeg argv: every segment is
delayed to its timeline position, volume/faded, and mixed with
`amix(duration=longest, normalize=0)` so volumes are the ones the plan
specified. When narration + music are both present, the music bed is ducked
under the narration via `sidechaincompress`, then the whole mix is loudness
normalized to the standard streaming target (-16 LUFS).

Pure function — unit-testable without a binary. The engine in `engine.py` is
the only caller.
"""

from __future__ import annotations

from pathlib import Path

from .schemas import AudioMixPlan

AUDIO_CODEC = "aac"
AUDIO_BITRATE = "192k"
LOUDNESS_TARGET = "I=-16:TP=-1.5:LRA=11"  # YouTube/iTunes streaming standard


def _silence_command(out_path: Path, ffmpeg_path: str, duration: float = 1.0) -> list[str]:
    """A short silent master — used when a plan has no playable segments."""
    return [
        ffmpeg_path,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=44100:cl=stereo",
        "-t",
        f"{duration:.3f}",
        "-c:a",
        AUDIO_CODEC,
        "-b:a",
        AUDIO_BITRATE,
        str(out_path),
    ]


def build_mix_command(
    plan: AudioMixPlan,
    out_path: Path,
    *,
    ffmpeg_path: str = "ffmpeg",
    duck: bool = True,
) -> list[str]:
    """Build the ffmpeg argv that mixes `plan` into `out_path`."""
    out_path = Path(out_path)
    cmd: list[str] = [ffmpeg_path, "-y"]
    filter_parts: list[str] = []
    narration_labels: list[str] = []
    music_labels: list[str] = []

    for index, segment in enumerate(plan.segments):
        source = segment.source_path
        if source is None or not Path(source).exists():
            continue
        cmd += ["-i", str(source)]
        chain = ["aformat=sample_fmts=fltp:channel_layouts=stereo"]
        delay_ms = int(round(segment.start * 1000))
        chain.append(f"adelay={delay_ms}|{delay_ms}")
        chain.append(f"volume={segment.volume:.4f}")
        duration = max(0.0, segment.end - segment.start)
        if segment.fade_in and segment.fade_in > 0:
            chain.append(f"afade=t=in:st=0:d={segment.fade_in:.3f}")
        if segment.fade_out and segment.fade_out > 0 and segment.fade_out < duration:
            chain.append(f"afade=t=out:st={max(0.0, duration - segment.fade_out):.3f}:d={segment.fade_out:.3f}")
        label = f"[seg{index}]"
        filter_parts.append(f"[{index}:a]{','.join(chain)}{label}")
        (music_labels if segment.kind == "music" else narration_labels).append(label)

    if not filter_parts:
        return _silence_command(out_path, ffmpeg_path)

    out_label = "[out]"
    if duck and music_labels and narration_labels:
        narr_mix, music_mix = "[narr]", "[music]"
        filter_parts.append(f"{''.join(narration_labels)}amix=inputs={len(narration_labels)}:duration=longest:normalize=0{narr_mix}")
        filter_parts.append(f"{''.join(music_labels)}amix=inputs={len(music_labels)}:duration=longest:normalize=0{music_mix}")
        # Duck the music bed under the narration (sidechain = narration).
        ducked = "[ducked]"
        filter_parts.append(
            f"{music_mix}{narr_mix}sidechaincompress="
            f"threshold=0.03:ratio=6:attack=20:release=300{ducked}"
        )
        filter_parts.append(f"{ducked}{narr_mix}amix=inputs=2:duration=longest:normalize=0{out_label}")
    else:
        mixed_labels = "".join(narration_labels + music_labels)
        mixed_inputs = len(narration_labels) + len(music_labels)
        filter_parts.append(
            f"{mixed_labels}amix=inputs={mixed_inputs}:duration=longest:normalize=0{out_label}"
        )

    # Master gain + loudness normalization to the streaming target.
    gain_label = "[gained]"
    filter_parts.append(f"{out_label}volume={plan.master_gain:.4f}{gain_label}")
    loud_label = "[loud]"
    filter_parts.append(f"{gain_label}loudnorm={LOUDNESS_TARGET}{loud_label}")

    cmd += [
        "-filter_complex",
        ";".join(filter_parts),
        "-map",
        loud_label,
        "-c:a",
        AUDIO_CODEC,
        "-b:a",
        AUDIO_BITRATE,
        "-movflags",
        "+faststart",
        str(out_path),
    ]
    return cmd
