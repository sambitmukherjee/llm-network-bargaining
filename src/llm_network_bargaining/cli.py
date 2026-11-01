"""Command-line planning, experiment execution, status and replay."""

import argparse
import asyncio
from collections.abc import Sequence
import os
from pathlib import Path
import sys

from .config import load_configs
from .model_client import FatalAPIError
from .replay import main as replay_main
from .runner import Job, estimate_cost, job_status, plan_jobs, run_jobs, validate_logs


def _print_plan(jobs: list[Job], root: Path) -> float:
    print("condition | todo | interrupted | done | abandoned | estimated_remaining_usd")
    groups: dict[str, list[Job]] = {}
    for job in jobs:
        groups.setdefault(job.condition.key, []).append(job)
    total = 0.0
    for key, group in groups.items():
        counts = dict(todo=0, interrupted=0, done=0, abandoned=0)
        for job in group:
            counts[job_status(job, root)] += 1
        cost = (counts["todo"] + counts["interrupted"]) * estimate_cost(group[0], group[0].config.models)
        total += cost
        print(f"{key} | {counts['todo']} | {counts['interrupted']} | {counts['done']} | {counts['abandoned']} | {cost:.7f}")
    print(f"Estimated remaining cost: ${total:.7f}")
    return total


def main(argv: Sequence[str] | None = None) -> int:
    """Parse the CLI and require explicit confirmation before creating a live client."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("estimate", "run", "status"):
        command = commands.add_parser(name)
        command.add_argument("configs", nargs="+")
        if name in ("estimate", "run"):
            command.add_argument("--conditions")
            command.add_argument("--max-episodes", type=int)
        if name in ("run", "status"):
            command.add_argument("--out", type=Path)
        if name == "run":
            command.add_argument("--concurrency", type=int, default=8)
            command.add_argument("--dry-run", choices=("pass", "equal_split", "aspiration", "random"))
            command.add_argument("--yes", action="store_true")
    replay = commands.add_parser("replay")
    replay.add_argument("paths", nargs="+")
    args = parser.parse_args(argv)
    if args.command == "replay":
        return replay_main(args.paths)
    if args.command == "run" and args.dry_run is None and not os.environ.get("OPENAI_API_KEY"):
        print("Set OPENAI_API_KEY before running a live experiment.")
        return 1
    try:
        configs = load_configs(args.configs)
        jobs = plan_jobs(configs, conditions=getattr(args, "conditions", None),
                         max_episodes=getattr(args, "max_episodes", None))
        if args.command == "estimate":
            print("condition | episodes | cost_per_attempt_usd | subtotal_usd")
            total = 0.0
            for condition in dict.fromkeys(job.condition.key for job in jobs):
                group = [job for job in jobs if job.condition.key == condition]
                cost = estimate_cost(group[0], group[0].config.models)
                subtotal = cost * len(group)
                total += subtotal
                print(f"{condition} | {len(group)} | {cost:.7f} | {subtotal:.7f}")
            print(f"Estimated total: ${total:.7f}")
            return 0
        root = args.out or Path("runs_dry" if args.command == "run" and args.dry_run else "runs")
        dry = args.dry_run is not None if args.command == "run" else None
        validate_logs(configs, root, dry)
        if dry:
            print("Dry run: all costs are simulated; no API key or confirmation is needed.")
        estimated = _print_plan(jobs, root)
        if args.command == "status":
            return 4 if any(job_status(job, root) == "abandoned" for job in jobs) else 0
        if args.concurrency < 1:
            raise ValueError("concurrency must be positive.")
        remaining = any(job_status(job, root) in ("todo", "interrupted") for job in jobs)
        if args.dry_run is None and remaining and not args.yes:
            if not sys.stdin.isatty():
                print("Live run not confirmed: use --yes or run interactively.")
                return 3
            answer = input(f"Type yes to spend about ${estimated:.4f}: ").strip()
            if answer != "yes":
                print("Live run not confirmed.")
                return 3
        summary = asyncio.run(run_jobs(jobs, out_root=root, dry_run_bot=args.dry_run,
                                       concurrency=args.concurrency))
        label = "Simulated" if summary.dry_run else "Actual"
        print(f"Requested jobs: done={summary.done} abandoned={summary.abandoned} "
              f"todo={summary.todo} interrupted={summary.interrupted}")
        print(f"{label} cost across saved logs: ${summary.cost_usd:.6f}")
        return 4 if summary.abandoned else 0
    except (FatalAPIError, OSError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}")
        return 1
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("Interrupted. Partial logs are available for resuming.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
