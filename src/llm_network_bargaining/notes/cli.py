"""Estimate or run blind note coding, with explicit live-call confirmation."""

import argparse
import asyncio
from collections.abc import Sequence
from pathlib import Path
import os
import sys

from ..analysis.data import load_dataset
from ..fake_client import FakeChatClient
from ..model_client import FatalAPIError, OpenAIChatClient
from .judge import JudgeRun, KeywordResponder, code_notes, estimate_notes, load_judge_config
from .compare import compare_labels


def print_estimate(estimate: dict) -> None:
    """Print the specified primary-batch estimate and its reasoning caveat."""
    print(f"Non-empty notes: {estimate['non_empty']}; empty: {estimate['empty']}")
    print(f"Unique notes: {estimate['unique']}; already cached: {estimate['already_cached']}; new: {estimate['new']}")
    print(f"Estimated primary calls: {estimate['estimated_calls']}; cost: ${estimate['estimated_cost_usd']:.6f}")
    print(f"Estimated time: about {estimate['estimated_minutes']} minutes at concurrency {estimate['concurrency']} (about 20 s per batch).")
    print("Reasoning makes actual cost uncertain; repeat-consistency calls are additional.")


def main(argv: Sequence[str] | None = None) -> int:
    """Do no live work before a key and an exact yes/--yes confirmation."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    compare = commands.add_parser("compare")
    compare.add_argument("labels_a", type=Path)
    compare.add_argument("labels_b", type=Path)
    for name in ("estimate", "code"):
        command = commands.add_parser(name)
        command.add_argument("roots", nargs="+", type=Path)
        command.add_argument("--configs", nargs="+")
        command.add_argument("--include-dry", action="store_true")
        command.add_argument("--concurrency", type=int, default=8)
        command.add_argument("--judge-config", type=Path, default=Path("configs/note_judge.yaml"))
        command.add_argument("--out", type=Path, required=name == "code", default=Path("notes_out"))
        if name == "code":
            mode = command.add_mutually_exclusive_group(required=True)
            mode.add_argument("--dry-run", action="store_true")
            mode.add_argument("--live", action="store_true")
            command.add_argument("--yes", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "compare":
        try:
            print(compare_labels(args.labels_a, args.labels_b))
            return 0
        except (OSError, ValueError, KeyError) as exc:
            print(f"ERROR: {exc}")
            return 2
    if args.concurrency < 1:
        parser.error("--concurrency must be at least 1.")
    live = args.command == "code" and args.live
    if live and not os.environ.get("OPENAI_API_KEY"):
        print("Set OPENAI_API_KEY before live note coding.")
        return 1
    try:
        config = load_judge_config(args.judge_config)
        ds = load_dataset(args.roots, configs=args.configs, include_dry=args.include_dry)
        estimate = estimate_notes(ds, config, args.out, dry_run=None if args.command == "estimate" else not live,
                                  concurrency=args.concurrency)
        print_estimate(estimate)
        if args.command == "estimate":
            return 0
        if live and not args.yes:
            if not sys.stdin.isatty():
                print("Live note coding not confirmed: use --yes or run interactively.")
                return 3
            if input(f"Type yes to spend about ${estimate['estimated_cost_usd']:.4f} plus repeat checks: ").strip() != "yes":
                print("Live note coding not confirmed.")
                return 3

        async def run() -> JudgeRun:
            """Own and close a live client only after confirmation."""
            client = OpenAIChatClient() if live else FakeChatClient(KeywordResponder())
            try:
                return await code_notes(ds, config, out=args.out, client=client, dry_run=not live,
                                        concurrency=args.concurrency)
            finally:
                if live:
                    await client.aclose()

        result = asyncio.run(run())
        label = "Actual" if live else "Simulated"
        print(f"{result.labels.status.value_counts().to_dict()}")
        print(f"{label} cumulative judge cost: ${result.costs['total_cost_usd']:.6f}")
        return 0
    except (OSError, ValueError, KeyError, FatalAPIError) as exc:
        print(f"ERROR: {exc}")
        return 1
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("Interrupted. Cached note labels are retained for resuming.")
        return 1
