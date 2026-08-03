"""ACCE command-line interface.

Commands:
    generate   run the full pipeline for a topic
    status     show a finished job's stage results
    api        run the FastAPI dashboard API
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from config.settings import Settings
from core.models import JobStatus, UserInput
from modules import build_orchestrator


def _console_progress(event) -> None:
    print(f"[{event.stage:>10}] {event.status.value:<9} {event.message} ({event.percent:4.1f}%)")


def cmd_generate(args) -> int:
    settings = Settings()
    orch = build_orchestrator(settings, on_progress=_console_progress)
    ui = UserInput(
        topic=args.topic, instructions=args.instruction, duration=args.duration, style=args.style, language=args.language
    )
    print(f"\nGenerating {ui.topic!r}\n")
    ctx = orch.run(ui)
    print(f"\njob {ctx.job_id}: {ctx.status.value}")
    if ctx.status is not JobStatus.SUCCEEDED:
        for err in ctx.errors:
            print(f"  - {err}")
        return 1
    print(f"artifacts: {(settings.paths.output_dir / ctx.job_id).resolve()}")
    return 0


def cmd_status(args) -> int:
    settings = Settings()
    job_file: Path = settings.paths.output_dir / args.job_id / "meta" / "job.json"
    if not job_file.exists():
        print(f"no job found at {job_file}")
        return 1
    data = json.loads(job_file.read_text(encoding="utf-8"))
    print(f"job {data['job_id']}: {data['status']}")
    for stage, res in data.get("results", {}).items():
        mark = "ok" if res.get("ok") else f"FAILED ({res.get('error')})"
        print(f"  {stage:<10} {mark}  {res.get('duration_ms', 0)}ms")
    print(f"artifacts: {settings.paths.output_dir / data['job_id']}")
    return 0


def cmd_api(args) -> int:
    import uvicorn

    uvicorn.run("frontend.api.app:app", host=args.host, port=args.port, reload=args.reload)
    return 0


def cmd_doctor(_args) -> int:
    from config.doctor import run_doctor

    return run_doctor()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="acce", description="Autonomous Content Creation Engine — V1")
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="run the full pipeline for a topic")
    gen.add_argument("--topic", required=True)
    gen.add_argument("--instruction", action="append", default=[], help="instruction line (repeatable)")
    gen.add_argument("--duration", type=int, default=None, help="target video length in seconds")
    gen.add_argument("--style", default=None)
    gen.add_argument("--language", default="en", help="narration/subtitle language code (e.g. hi)")
    gen.set_defaults(func=cmd_generate)

    st = sub.add_parser("status", help="show a finished job's results")
    st.add_argument("job_id")
    st.set_defaults(func=cmd_status)

    api = sub.add_parser("api", help="run the FastAPI dashboard API")
    api.add_argument("--host", default="127.0.0.1")
    api.add_argument("--port", type=int, default=8000)
    api.add_argument("--reload", action="store_true")
    api.set_defaults(func=cmd_api)

    doc = sub.add_parser("doctor", help="check production readiness (keys, ffmpeg, deps)")
    doc.set_defaults(func=cmd_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
