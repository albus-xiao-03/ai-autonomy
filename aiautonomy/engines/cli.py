"""Command-line entry point `aia` (docs/engine-plan.md §6).

`serve`, `run --headless`, `replay`, `trace`; `compare`, `bench` and `map build` arrive in
later milestones.

REQ: ARCH-01, SIM-01, SIM-04, EVAL-04
"""

import argparse
import logging
import sys
from collections.abc import Callable
from pathlib import Path

from aiautonomy.engines import trace
from aiautonomy.engines.core.datafiles import DataFileError
from aiautonomy.engines.core.paths import runs_dir
from aiautonomy.engines.sim.config import RunOverrides, resolve_run_config

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787


def _runs_dir(args: argparse.Namespace) -> Path:
    return Path(args.runs_dir).resolve() if args.runs_dir else runs_dir()


def _overrides(args: argparse.Namespace) -> RunOverrides:
    return RunOverrides(scenario=args.scenario, seed=args.seed, duration=args.duration)


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from aiautonomy.engines.api.app import create_app, is_loopback_host
    from aiautonomy.engines.api.session import SessionOptions
    from aiautonomy.engines.sim.driver import ArtificialInferenceWait

    if not is_loopback_host(args.host):
        print(f"error: refusing to listen on non-loopback host {args.host!r}", file=sys.stderr)
        return 2
    overrides = _overrides(args)
    try:
        resolve_run_config(overrides)
        wait = ArtificialInferenceWait(
            args.artificial_inference_wait_ms, args.artificial_inference_wait_every
        )
    except (DataFileError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    options = SessionOptions(
        runs_dir=_runs_dir(args),
        overrides=overrides,
        inference_wait=wait,
        maps_dir=Path(args.maps_dir).resolve() if args.maps_dir else None,
    )
    uvicorn.run(create_app(options), host=args.host, port=args.port, log_level=args.log_level)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    from aiautonomy.engines.record.recorder import Recorder, make_run_id, relabel_stale_runs
    from aiautonomy.engines.sim.run import Run, run_headless

    if not args.headless:
        print(
            "error: only `aia run --headless` exists; use `aia serve` for the browser",
            file=sys.stderr,
        )
        return 2
    try:
        resolved = resolve_run_config(_overrides(args))
    except (DataFileError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    directory = _runs_dir(args)
    relabel_stale_runs(directory)
    config = resolved.config
    run = Run(
        resolved,
        run_id=make_run_id(config.scenario, config.seed),
        sinks=[Recorder(directory)],
    )
    final = run_headless(run)
    print(f"run_id:   {run.run_id}")
    print(f"outcome:  {run.state} at tick {final.tick}/{config.duration}")
    print(f"hash:     {final.state_hash.value}")
    for name, value in sorted(final.metrics.items()):
        print(f"metric:   {name} = {value!r}")
    print(f"record:   {directory / run.run_id}")
    return 0


def cmd_replay(args: argparse.Namespace) -> int:
    from aiautonomy.engines.record.hybrid_replay import HybridReplayReport
    from aiautonomy.engines.record.replay import ReplayError, replay_any, resolve_run_dir

    maps_dir = Path(args.maps_dir).resolve() if args.maps_dir else None
    try:
        report = replay_any(resolve_run_dir(args.run, _runs_dir(args)), maps_dir)
    except ReplayError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for warning in report.warnings:
        print(f"warning: {warning}")
    if isinstance(report, HybridReplayReport):
        if report.divergence is not None:
            print(f"DIVERGED at tick {report.divergence_tick}: {report.divergence}")
            return 1
        print(
            f"replay OK: {report.run_id}: {report.ticks_compared} ticks identical (state hashes "
            f"and outcomes); outcome recorded {report.recorded_outcome}, replayed "
            f"{report.replayed_outcome}; final hash {report.final_hash}"
        )
        return 0
    if report.divergence is not None:
        divergence = report.divergence
        print(
            f"DIVERGED at tick {divergence.tick} in {', '.join(divergence.subsystems)}: "
            f"{divergence.detail}"
        )
        return 1
    print(
        f"replay OK: {report.run_id}: {report.ticks_compared} ticks identical; "
        f"outcome recorded {report.recorded_outcome}, replayed {report.replayed_outcome}; "
        f"final hash {report.final_hash}"
    )
    return 0


def _not_yet(milestone: str) -> Callable[[argparse.Namespace], int]:
    def handler(args: argparse.Namespace) -> int:
        print(f"aia {args.command}: not implemented until {milestone}", file=sys.stderr)
        return 2

    return handler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aia", description="AI Autonomy engine")
    commands = parser.add_subparsers(dest="command", required=True)

    def run_options(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("--scenario", default=None, help="scenario id (default: engine default)")
        sub.add_argument("--seed", type=int, default=None, help="run seed")
        sub.add_argument("--duration", type=int, default=None, help="run length in ticks")
        sub.add_argument("--runs-dir", default=None, help="run records (default: <root>/runs)")
        sub.add_argument("--maps-dir", default=None, help="user map saves (default: <root>/maps)")

    serve = commands.add_parser("serve", help="run the engine server (loopback only)")
    serve.add_argument("--host", default=DEFAULT_HOST)
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve.add_argument(
        "--artificial-inference-wait-ms",
        type=int,
        default=0,
        help="await this long before phase 4 of every K-th tick (0 = off)",
    )
    serve.add_argument(
        "--artificial-inference-wait-every", type=int, default=1, metavar="K", help="default 1"
    )
    serve.add_argument("--log-level", default="info")
    run_options(serve)
    serve.set_defaults(func=cmd_serve)

    run = commands.add_parser("run", help="run a scenario")
    run.add_argument("--headless", action="store_true", help="max speed, no server")
    run_options(run)
    run.set_defaults(func=cmd_run)

    replay = commands.add_parser("replay", help="replay a recorded run without inference")
    replay.add_argument("run", help="run id or run directory")
    replay.add_argument("--runs-dir", default=None)
    replay.add_argument("--maps-dir", default=None, help="user map saves (hybrid runs)")
    replay.set_defaults(func=cmd_replay)

    trace_parser = commands.add_parser("trace", help="write docs/traceability.md")
    trace.add_arguments(trace_parser)
    trace_parser.set_defaults(func=trace.run)

    compare = commands.add_parser("compare", help="compare matched run variants (M5)")
    compare.add_argument("args", nargs="*")
    compare.set_defaults(func=_not_yet("M5"))
    bench = commands.add_parser("bench", help="hardware and model benchmarks (M4, M9)")
    bench.add_argument("args", nargs="*")
    bench.set_defaults(func=_not_yet("M4"))
    map_parser = commands.add_parser("map", help="map tools (M1)")
    map_parser.add_argument("action", choices=["build"])
    map_parser.set_defaults(func=_not_yet("M1"))
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = build_parser().parse_args(argv)
    handler: Callable[[argparse.Namespace], int] = args.func
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
