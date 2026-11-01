"""Write the Phase 6 analysis tables and numerical results, entirely offline."""

import argparse
import gzip
import json
from pathlib import Path
from collections.abc import Sequence
from typing import Any

import pandas as pd

from ..runlog import read_attempt_logs
from .benchmarks import benchmark_errors, ordering_accuracy
from .data import load_dataset
from .game_length import game_length_decision
from .hypotheses import run_hypotheses
from .metrics import (attempt_diagnostics, condition_class_summary, cost_summary,
                      invalid_action_rates, learning_curves, power_use, quiz_summary,
                      summarise_efficiency, summarise_pair_proposer_share,
                      summarise_power_use, summarise_triangle_lock_in)
from .mixed import fit_mixed_models
from .stats import json_ready


def _write_json(path: Path, value: Any) -> None:
    """Write sorted, strict JSON with missing numerical values as null."""
    path.write_text(json.dumps(json_ready(value), sort_keys=True, indent=2,
                                ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def _write_csv(path: Path, table: pd.DataFrame) -> None:
    """Write a stable CSV, including reproducible gzip headers where requested."""
    table = table.copy()
    # Keep list/dict fields unambiguous for readers of the tidy CSV files.
    for column in table.columns:
        if any(isinstance(value, (list, dict)) for value in table[column]):
            table[column] = table[column].map(
                lambda value: json.dumps(json_ready(value), sort_keys=True) if isinstance(value, (list, dict)) else value)
    data = table.to_csv(index=False, lineterminator="\n").encode("utf-8")
    if path.suffix == ".gz":
        with path.open("wb") as output:
            with gzip.GzipFile(filename="", fileobj=output, mode="wb", mtime=0) as compressed:
                compressed.write(data)
    else:
        path.write_bytes(data)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the primary analysis and a separate last-round sensitivity check."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="+", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--configs", nargs="+")
    parser.add_argument("--include-dry", action="store_true")
    parser.add_argument("--window", choices=("second_half", "second_half_no_last", "all"), default="second_half")
    parser.add_argument("--boot", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args(argv)
    if args.boot < 1:
        parser.error("--boot must be positive.")
    try:
        ds = load_dataset(args.roots, configs=args.configs, include_dry=args.include_dry)
        args.out.mkdir(parents=True, exist_ok=True)
        for table, filename in [("episodes", "episodes.csv"), ("node_rounds", "node_rounds.csv.gz"),
                                 ("deals", "deals.csv.gz"), ("turns", "turns.csv.gz"), ("quizzes", "quizzes.csv")]:
            _write_csv(args.out / filename, getattr(ds, table))
        options = dict(window=args.window, n_boot=args.boot, seed=args.seed)
        _write_csv(args.out / "class_summary.csv", condition_class_summary(ds, **options))
        _write_csv(args.out / "power_use.csv", power_use(ds, args.window))
        _write_csv(args.out / "learning_curves.csv", learning_curves(ds, n_boot=args.boot, seed=args.seed))
        errors = benchmark_errors(ds, **options)
        _write_json(args.out / "benchmark_errors.json", errors)
        _write_json(args.out / "ordering_accuracy.json", ordering_accuracy(ds, **options))
        hypotheses = run_hypotheses(ds, **options)
        _write_json(args.out / "hypotheses.json", hypotheses)
        _write_csv(args.out / "mixed_models.csv", fit_mixed_models(ds, window=args.window))
        no_last = dict(options, window="second_half_no_last")
        _write_csv(args.out / "class_summary_no_last.csv", condition_class_summary(ds, **no_last))
        _write_json(args.out / "hypotheses_no_last.json", run_hypotheses(ds, **no_last))
        # Include failed-only configs when no filter was supplied.
        configs = args.configs if args.configs is not None else sorted({
            records.header["config_name"] for _, records in read_attempt_logs(args.roots)})
        _write_json(args.out / "diagnostics.json", dict(
            dry_run=ds.dry_run, invalid_actions=invalid_action_rates(ds), quizzes=quiz_summary(ds),
            attempts=attempt_diagnostics(args.roots, configs=configs), costs=cost_summary(ds, args.roots, configs=configs),
            efficiency=summarise_efficiency(ds, **options), proposer_share=summarise_pair_proposer_share(ds, **options),
            triangle_lock_in=summarise_triangle_lock_in(ds, **options), power_use=summarise_power_use(ds, **options)))
        pilot = ds.episodes[ds.episodes.config_name == "pilot_own_links"]
        decision = None
        if len(pilot) and (pilot.n_rounds == 24).all():
            try:
                decision = game_length_decision(ds)
            except ValueError as exc:
                decision = dict(status="not_run", reason=str(exc))
            _write_json(args.out / "game_length.json", decision)
        else:
            # Do not retain an earlier pilot decision when reusing an output folder.
            (args.out / "game_length.json").unlink(missing_ok=True)
        print("Dry-run analysis (simulated costs)." if ds.dry_run else "Live-log analysis (no API calls).")
        for config, count in ds.episodes.groupby("config_name").size().items():
            print(f"{config}: {count} completed episodes")
        for name, result in hypotheses.results.items():
            if result["status"] == "not_run":
                print(f"{name}: not_run")
            else:
                print(f"{name}: {result['decision']} (p={result['p_value']:.6g}, Holm={result['p_adjusted']:.6g})")
        print(f"H2 best benchmark: {errors['best'] or 'not_run'}")
        if decision:
            print(f"Game length: {decision['decision']} rounds" if "decision" in decision else
                  f"Game length: not_run ({decision['reason']})")
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}")
        return 1
