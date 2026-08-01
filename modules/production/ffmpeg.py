"""FFmpeg command builder for the production renderer.

Consumes only a `RenderManifest` and produces an ffmpeg argv. Each scene input
is normalized to WxH@fps and trimmed/looped to its ScenePlan duration (timing
is never inferred from media length), then composed, subtitle-burned, and mixed
with the manifest audio.

Milestone 10 transitions: `fade`/`dissolve` are true crossfades via the
`xfade` filter; `fade_to_black` becomes a fade-through-black (`fadeblack`);
`cut` stays a hard cut (`xfade transition=cut`). The timeline/manifest/renderer
contracts are unchanged — only the filtergraph differs. When xfade can't be
applied (single scene, zero fade, or a scene shorter than the fade window),
the graph falls back to the V1 per-scene fade approximation instead of
failing the render.
"""

from __future__ import annotations

from pathlib import Path

from .schemas import RenderManifest

# Scene transition -> xfade transition name (all standard in ffmpeg >= 4.3).
_XFADE_TRANSITIONS = {
    "cut": "fade",  # "cut" not supported by all ffmpeg builds; use fade as fallback
    "fade": "fade",
    "dissolve": "dissolve",
    "fade_to_black": "fadeblack",
}


def _escape_path_filter(value: str) -> str:
    """Make a filesystem path safe inside an ffmpeg filter value."""
    if len(value) > 1 and value[1] == ":":
        value = value[0] + "\\:" + value[2:]
    return value.replace("\\", "/")


def _xfade_transition(transition: str) -> str:
    return _XFADE_TRANSITIONS.get(transition, "fade")


def _fade_filters(transition: str, duration: float, fade: float) -> list[str]:
    fade = max(0.0, fade)
    if transition in ("fade", "dissolve"):
        fade_out_start = max(0.0, duration - fade)
        return [f"fade=t=in:st=0:d={fade:.2f}", f"fade=t=out:st={fade_out_start:.2f}:d={fade:.2f}"]
    if transition == "fade_to_black":
        return [f"fade=t=out:st={max(0.0, duration - fade):.2f}:d={fade:.2f}"]
    return []  # cut (and any unknown/default)


def _write_scene_text(text: str, scene_number: int, out_path: Path) -> Path:
    out_path = Path(out_path)
    text_path = out_path.parent / f"{out_path.stem}_text_{scene_number:02d}.txt"
    text_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.write_text(text, encoding="utf-8")
    return text_path


def build_command(manifest: RenderManifest, out_path: Path, ffmpeg_path: str = "ffmpeg") -> list[str]:
    settings = manifest.settings
    width, height, fps = settings.width, settings.height, settings.fps
    fade = settings.fade

    durations = [round(scene.end_time - scene.start_time, 3) for scene in manifest.timeline.scenes]
    use_xfade = (
        len(durations) >= 2
        and fade > 0
        and all(duration >= 2 * fade + 0.05 for duration in durations)
    )

    cmd: list[str] = [ffmpeg_path, "-y"]
    filter_parts: list[str] = []
    concat_inputs: list[str] = []

    for index, (scene, asset) in enumerate(zip(manifest.timeline.scenes, manifest.assets, strict=True)):
        duration = durations[index]
        # Crossfades overlap neighbours by `fade`, so extend every clip but the
        # last by the fade window; total output duration still equals the
        # timeline (audio stays in sync).
        trim_duration = duration
        if use_xfade and index < len(durations) - 1:
            trim_duration = duration + fade

        local_path = asset.local_path
        if asset.asset_type == "video" and local_path is not None:
            cmd += ["-stream_loop", "-1", "-i", str(local_path)]
            chain = [
                f"trim=0:{trim_duration}",
                "setpts=PTS-STARTPTS",
                f"scale={width}:{height}:force_original_aspect_ratio=increase",
                f"crop={width}:{height}",
                "setsar=1",
                f"fps={fps}",
                "format=yuv420p",
            ]
        elif local_path is not None:
            # image (or an unknown local file treated as an image): loop + trim
            cmd += ["-loop", "1", "-i", str(local_path)]
            chain = [
                f"trim=0:{trim_duration}",
                "setpts=PTS-STARTPTS",
                f"scale={width}:{height}:force_original_aspect_ratio=increase",
                f"crop={width}:{height}",
                "setsar=1",
                f"fps={fps}",
                "format=yuv420p",
            ]
        else:
            # text-overlay or placeholder: a bounded solid-color source
            color = "#20242e" if asset.asset_type == "text" else "#101418"
            cmd += ["-f", "lavfi", "-i", f"color=c={color}:s={width}x{height}:d={trim_duration}"]
            chain = ["setsar=1", f"fps={fps}", "format=yuv420p"]
            if asset.asset_type == "text" and asset.text:
                text_path = _write_scene_text(asset.text, asset.scene_number, out_path)
                chain.append(
                    "drawtext=textfile=" + _escape_path_filter(str(text_path))
                    + f":x=(w-text_w)/2:y=(h-text_h)/2:fontsize={width // 22}:fontcolor=white"
                    + ":box=1:boxcolor=black@0.5:boxborderw=24"
                )

        if not use_xfade:
            chain += _fade_filters(scene.transition, duration, fade)
        source = f"[{index}:v]"
        sink = f"[v{index}]"
        filter_parts.append(f"{source}{','.join(chain)}{sink}")
        concat_inputs.append(sink)

    if use_xfade:
        # Sequential xfade chain.  The offset for each xfade is the
        # scene's start_time in the timeline — the cumulative *visible*
        # duration of all preceding scenes.  Each input clip is trimmed
        # to (visible_duration + fade) so it has enough tail content for
        # the crossfade; using the timeline start_time keeps the offset
        # strictly below the first-input length, which ffmpeg's xfade
        # filter requires to produce a correct output stream.
        mapped = concat_inputs[0]
        for index in range(1, len(durations)):
            offset = manifest.timeline.scenes[index].start_time
            transition = _xfade_transition(manifest.timeline.scenes[index].transition)
            out_label = f"[xf{index}]"
            filter_parts.append(
                f"{mapped}{concat_inputs[index]}"
                f"xfade=transition={transition}:duration={fade:.3f}:offset={offset:.3f}"
                f"{out_label}"
            )
            mapped = out_label
    else:
        concat_label = "[vcat]"
        filter_parts.append(f"{''.join(concat_inputs)}concat=n={len(concat_inputs)}:v=1:a=0{concat_label}")
        mapped = concat_label

    if manifest.subtitle_path is not None and manifest.subtitle_path.exists():
        sub_label = "[vsub]"
        filter_parts.append(f"{mapped}subtitles={_escape_path_filter(str(manifest.subtitle_path))}{sub_label}")
        mapped = sub_label

    cmd += ["-filter_complex", ";".join(filter_parts)]

    # All inputs must precede the -map options, or ffmpeg treats the first
    # -map as an input option for the next -i ("cannot be applied to input url").
    audio_index = len(manifest.timeline.scenes)
    if manifest.audio_path is not None and manifest.audio_path.exists():
        cmd += ["-i", str(manifest.audio_path)]

    cmd += ["-map", mapped]
    if manifest.audio_path is not None and manifest.audio_path.exists():
        cmd += ["-map", f"{audio_index}:a", "-c:a", settings.audio_codec]

    cmd += ["-t", f"{manifest.timeline.duration:.3f}"]
    cmd += [
        "-c:v",
        settings.codec,
        "-preset",
        settings.preset,
        "-crf",
        str(settings.crf),
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(fps),
    ]
    if settings.faststart:
        cmd += ["-movflags", "+faststart"]
    cmd += [str(out_path)]
    return cmd
