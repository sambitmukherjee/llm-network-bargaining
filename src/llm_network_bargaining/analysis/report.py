"""Reproducible Markdown reports and an output-free analysis notebook."""

import argparse
from collections.abc import Sequence
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ..runlog import read_attempt_logs
from .cli import main as analyse_main
from .data import Dataset, load_dataset
from .figures import (fig_dose_response, fig_learning_curves, fig_observed_vs_predicted,
                      fig_parity_flip, fig_power_use, save_figure)
from matplotlib.figure import Figure
from .gate import GateResult, pilot_gate
from .stats import json_ready

DRY_BANNER = "**Dry-run data (scripted bots, simulated costs): not study results.**"


def _format(value: Any, *, p_value: bool = False) -> str:
    """Format numerical report values without requiring the tabulate package."""
    if value is None or (isinstance(value, (float, np.floating)) and not np.isfinite(value)):
        return "—"
    if isinstance(value, (bool, np.bool_)):
        return "yes" if value else "no"
    if isinstance(value, (int, float, np.number)):
        return format(value, ".4g" if p_value else ".2f")
    if isinstance(value, (dict, list)):
        return json.dumps(json_ready(value), sort_keys=True, ensure_ascii=False)
    return str(value)


def markdown_table(table: pd.DataFrame, columns: dict[str, str] | None = None,
                    p_columns: Sequence[str] = ()) -> str:
    """Write a plain Markdown table, escaping the pipes in node-class labels."""
    if columns is not None:
        table = table.reindex(columns=list(columns)).rename(columns=columns)
        p_columns = [columns.get(name, name) for name in p_columns]
    if not len(table.columns):
        return "No data."

    def escape(value: str) -> str:
        """Keep literal class-label pipes inside one Markdown cell."""
        return value.replace("|", "\\|").replace("\n", " ")

    lines = ["| " + " | ".join(map(escape, table.columns)) + " |",
             "| " + " | ".join("---" for _ in table.columns) + " |"]
    for row in table.to_dict("records"):
        lines.append("| " + " | ".join(escape(_format(row[column], p_value=column in p_columns)) for column in table.columns) + " |")
    if table.empty:
        lines.append("| " + " | ".join(["No data", *["—"] * (len(table.columns) - 1)]) + " |")
    return "\n".join(lines)


def gate_table(result: GateResult) -> str:
    """Present the gate's own values, without calculating a new gate statistic."""
    rows = []
    for key, check in result.checks.items():
        value = (f"{check.value['abandoned']:.2f} abandoned; failed share {_format(check.value['failed_share'])}"
                 if key == "G1" else _format(check.value))
        rows.append(dict(check=f"{key}: {check.name}", measure=check.measure, threshold=check.threshold,
                         value=value, decision="PASS" if check.passed else "FAIL"))
    return markdown_table(pd.DataFrame(rows), {"check": "Check", "measure": "Measure", "threshold": "Threshold",
                                               "value": "Value", "decision": "PASS/FAIL"})


def hypothesis_table(report: dict) -> str:
    """Format the Phase 6 primary test results in the registered family order."""
    rows = []
    for name in ("H1", "H3", "H4", "H5", "H6"):
        result = report["results"][name]
        inputs = result.get("per_network", {})
        description = "; ".join(f"{network} (n = {row.get('n', row.get('full_map', {}).get('n', '—'))})"
                                 for network, row in inputs.items())
        rows.append(dict(hypothesis=name, data=description or "not run", statistic=result.get("statistic"),
                         p=result.get("p_value"), adjusted=result.get("p_adjusted"),
                         decision=result.get("decision", "not_run").replace("_", " ")))
    return markdown_table(pd.DataFrame(rows), {"hypothesis": "Hypothesis", "data": "Data", "statistic": "Statistic",
                                               "p": "p", "adjusted": "Holm-adjusted p", "decision": "Decision"},
                          p_columns=("p", "adjusted"))


def _analyse(roots: Sequence[str | Path], out: Path, include_dry: bool, seed: int,
              n_boot: int, configs: Sequence[str] | None = None) -> tuple[Dataset, dict]:
    """Run the existing analysis CLI once, then read precisely its saved results."""
    folder = out / "analysis"
    argv = [*map(str, roots), "--out", str(folder), "--seed", str(seed), "--boot", str(n_boot)]
    if include_dry:
        argv.append("--include-dry")
    if configs is not None:
        argv.extend(["--configs", *configs])
    output = io.StringIO()
    with redirect_stdout(output):
        status = analyse_main(argv)
    if status:
        raise ValueError(output.getvalue().strip())
    data = load_dataset(roots, configs=configs, include_dry=include_dry)
    results = {name: json.loads((folder / f"{name}.json").read_text())
               for name in ("hypotheses", "hypotheses_no_last", "benchmark_errors", "ordering_accuracy", "diagnostics")}
    for name in ("class_summary", "class_summary_no_last", "mixed_models"):
        results[name] = pd.read_csv(folder / f"{name}.csv")
    return data, results


def _provenance(ds: Dataset, roots: Sequence[str | Path], configs: Sequence[str] | None = None) -> str:
    """Describe source headers and their dates; never add a generation timestamp."""
    headers = [record.header for _, record in read_attempt_logs(roots)
               if configs is None or record.header["config_name"] in configs]
    dates = sorted(header["started_at"] for header in headers)
    fields = {
        "Configs": sorted({header["config_name"] for header in headers}),
        "Prompt versions": sorted({header["prompt_version"] for header in headers}),
        "Quiz versions": sorted({header["quiz_version"] for header in headers}),
        "Model IDs": sorted({model["model_id"] for header in headers for model in header["models"].values()}),
        "Git commits": sorted({header["git_commit"] or "uncommitted" for header in headers}),
        "Dates (source started_at range)": f"{dates[0]} to {dates[-1]}" if dates else "missing data",
    }
    text = markdown_table(pd.DataFrame([dict(field=key, value=value) for key, value in fields.items()]))
    counts = ds.episodes.groupby(["config_name", "condition_key"], as_index=False).agg(episodes=("episode_uid", "count"))
    return text + "\n\n" + markdown_table(counts)


def _figure(fig: Figure, out: Path, stem: str, caption: str) -> str:
    """Save both figure formats and return a portable relative Markdown image."""
    try:
        save_figure(fig, out / "figures" / stem)
    finally:
        plt.close(fig)
    return f"![{stem.replace('_', ' ')}](figures/{stem}.png)\n\n{caption}"


def _diagnostics(diagnostics: dict) -> str:
    """Render the saved Phase 6 diagnostics, keeping non-completed costs separate."""
    sections = []
    for name, key in [("Invalid moves and reasons", "invalid_actions"), ("Rules quiz", "quizzes"),
                      ("Attempts and failure categories", "attempts"), ("Costs and usage by alias and attempt status", "costs"),
                      ("Pair proposer share (two-sided test)", "proposer_share"), ("Triangle lock-in", "triangle_lock_in"),
                      ("Efficiency", "efficiency")]:
        sections.extend([f"### {name}", markdown_table(pd.DataFrame(diagnostics[key]), p_columns=("p_value",))])
    cost_label = "simulated" if diagnostics["dry_run"] else "actual"
    return f"Costs below are {cost_label}; completed and non-completed attempts are separate rows.\n\n" + "\n\n".join(sections)


def _flatten_inputs(inputs: dict) -> pd.DataFrame:
    """Expose nested per-network inputs as named numerical table columns."""
    rows = []
    for network, values in inputs.items():
        row = {"network/cell": network}
        for key, value in values.items():
            if isinstance(value, dict):
                row.update({f"{key}.{subkey}": number for subkey, number in value.items()})
            else:
                row[key] = value
        rows.append(row)
    return pd.DataFrame(rows)


def write_pilot_report(roots: Sequence[str | Path], out: str | Path, *, include_dry: bool = False,
                        seed: int = 1, n_boot: int = 2000) -> Path:
    """Write one pilot Markdown report plus its analysis files and learning figure."""
    out = Path(out)
    configs = ["pilot_full_map", "pilot_own_links"]
    ds, result = _analyse(roots, out, include_dry, seed, n_boot, configs)
    gate = pilot_gate(ds, roots)
    length = gate.game_length_detail.get("networks", {})
    length_table = pd.DataFrame([dict(network=network, **values) for network, values in length.items()])
    sections = [DRY_BANNER if ds.dry_run else "", "# Pilot report", "## Provenance", _provenance(ds, roots, configs),
        "## Gate", gate_table(gate), f"Overall: **{gate.overall}**. Game length: **{gate.game_length or 'missing data'} rounds**.",
        "\n".join(f"- {step}" for step in gate.next_steps), "## Learning curves",
        _figure(fig_learning_curves(ds, seed=seed, n_boot=n_boot), out, "pilot_learning_curves",
                "Advantaged-class power use by round, with episode-bootstrap 95% intervals and the two game-length windows."),
        markdown_table(length_table), "## Outcomes", "### Class earnings, shares and predictions"]
    summary = result["class_summary"]
    for network, table in summary.groupby("network_id", sort=False):
        columns = ["condition_key", "node_class", "n_episodes", "points_mean", "points_mean_ci_low", "points_mean_ci_high",
                   "share_mean", "share_mean_ci_low", "share_mean_ci_high", "equal_split", "myerson", "position_value", "balanced"]
        sections.extend([f"### {network}", markdown_table(table[columns])])
    sections.extend(["### Power-use index", markdown_table(pd.DataFrame(result["diagnostics"]["power_use"])),
                     "## Diagnostics", _diagnostics(result["diagnostics"])])
    path = out / "pilot_report.md"
    path.write_text("\n\n".join(section for section in sections if section) + "\n", encoding="utf-8")
    return path


def label_prevalence(labels: pd.DataFrame) -> pd.DataFrame:
    """Describe per-turn coded-label prevalence per condition and node class."""
    from ..notes import LABELS

    rows = labels[labels.status == "coded"].copy()
    rows["condition_key"] = rows.episode_uid.map(lambda uid: uid.rsplit("/", 1)[0])
    keys = ["condition_key", "config_name", "network_id", "knowledge", "node_class"]
    if rows.empty:
        return pd.DataFrame(columns=[*keys, "n_notes", *LABELS])
    for label in LABELS:
        converted = rows[label].map(lambda value: str(value).lower()).map({"true": True, "false": False})
        if converted.isna().any():
            raise ValueError("A coded note has a missing or non-boolean label.")
        rows[label] = converted
    means = rows.groupby(keys, as_index=False)[list(LABELS)].mean()
    counts = rows.groupby(keys, as_index=False).agg(n_notes=("note_id", "count"))
    return counts.merge(means, on=keys)


def _notes_section(path: Path, ds: Dataset) -> str:
    """Show descriptive label prevalence, repeat agreement and quote-check misses."""
    from ..notes import LABELS

    labels = pd.read_csv(path)
    if "dry_run" in labels and len(labels) and labels.dry_run.astype(str).str.lower().eq("true").any() and not ds.dry_run:
        raise ValueError("Keyword dry-run labels cannot be included as live study results.")
    paired_path = path.parent / "consistency.json"
    repeat = json.loads(paired_path.read_text()) if paired_path.exists() else {}
    table = pd.DataFrame([dict(label=label, **row) for label, row in repeat.get("labels", {}).items()])
    n_quotes = n_missed = 0
    for row in labels[labels.status == "coded"].to_dict("records"):
        flags = json.loads(row["flags"]) if isinstance(row.get("flags"), str) else []
        for label in LABELS:
            if pd.notna(row[f"{label}_quote"]):
                n_quotes += 1
                n_missed += f"quote_not_found:{label}" in flags
    share = n_missed / n_quotes if n_quotes else None
    return "\n\n".join(["## Notes", markdown_table(label_prevalence(labels)), "### Repeat consistency",
        markdown_table(table), "Repeat consistency measures consistency, not correctness. Validation against hand labels is future work.",
        f"Quotes not found in their notes: {_format(share)} ({n_missed} of {n_quotes} quotes)."])


def write_study_report(roots: Sequence[str | Path], out: str | Path, *, include_dry: bool = False,
                        seed: int = 1, n_boot: int = 2000, notes: str | Path | None = None) -> Path:
    """Write the study's existing statistical results and four headline figures."""
    out = Path(out)
    ds, result = _analyse(roots, out, include_dry, seed, n_boot)
    tests, errors, orders = result["hypotheses"], result["benchmark_errors"], result["ordering_accuracy"]
    sections = [DRY_BANNER if ds.dry_run else "", "# Study report", "## Provenance", _provenance(ds, roots),
                "## Hypotheses", hypothesis_table(tests), "### H1 secondary per-network analysis"]
    secondary = pd.DataFrame([dict(network=network, **row) for network, row in tests["h1_per_network"].items()])
    sections.append(markdown_table(secondary, {name: name for name in
        ("network", "n", "mean", "ci_low", "ci_high", "p_value", "p_adjusted", "decision")}, p_columns=("p_value", "p_adjusted")))
    for name, values in tests["results"].items():
        sections.extend([f"### {name} per-network inputs", markdown_table(_flatten_inputs(values.get("per_network", {})),
                                                                      p_columns=("p_value",))])
    sections.extend(["## H2: benchmark comparison", "### Overall RMSE and P(best)", markdown_table(pd.DataFrame(errors["overall"])),
        "### Per-network RMSE", markdown_table(pd.DataFrame(errors["per_network"])),
        f"Ranking: {', '.join(errors['ranking']) or 'not run'}. Best benchmark: **{errors['best'] or 'not run'}**.",
        "### Distance to the core", markdown_table(pd.DataFrame(errors["core_distances"])),
        "### Ordering accuracy (four benchmarks, degree and betweenness)", markdown_table(pd.DataFrame(orders["overall"])),
        markdown_table(pd.DataFrame(orders["per_network"])), "## Figures"])
    options = dict(seed=seed, n_boot=n_boot)
    plots = [
        (fig_observed_vs_predicted(ds, **options), "observed_vs_predicted", "F1. Episode class earnings and their mean/95% CI beside the four point benchmarks and core intervals."),
        (fig_power_use(ds, **options), "power_use", "F2. Power use by knowledge setting, with theory and human anchors: [Borch & Girard](https://www.cmu.edu/joss/content/articles/volume10/Borch) (3-line and 5-line), and [Kleinberg & Tardos (2008)](https://cs.cornell.edu/info/people/kleinber/stoc08-exchange.pdf) (4-line)."),
        (fig_dose_response(ds, **options), "dose_response", "F3. Hub share versus leaf count, including the 3-line at k = 2, with Myerson, equal-split/position-value and core references."),
        (fig_parity_flip(ds, **options), "parity_flip", "F4. End-agent earnings for observed lines and all four point predictions for lengths 2–7."),
    ]
    for fig, stem, caption in plots:
        sections.append(_figure(fig, out, stem, caption))
    sections.extend(["## Mixed models", markdown_table(result["mixed_models"]),
        "## Robustness: excluding the last round", hypothesis_table(result["hypotheses_no_last"]),
        markdown_table(result["class_summary_no_last"]), "## Diagnostics", _diagnostics(result["diagnostics"])])
    if notes is not None:
        sections.append(_notes_section(Path(notes), ds))
    path = out / "study_report.md"
    path.write_text("\n\n".join(section for section in sections if section) + "\n", encoding="utf-8")
    return path


def write_notebook(path: str | Path = "notebooks/analysis.ipynb") -> Path:
    """Write nbformat-4 JSON with stable cell IDs and no execution outputs."""
    cells = []

    def cell(kind: str, source: str) -> None:
        """Append one deterministic Markdown or unexecuted code cell."""
        source = source.strip() + "\n"
        record = dict(cell_type=kind, id=hashlib.sha256((str(len(cells)) + source).encode()).hexdigest()[:12],
                      metadata={}, source=source.splitlines(keepends=True))
        if kind == "code":
            record.update(execution_count=None, outputs=[])
        cells.append(record)

    cell("markdown", "# Network bargaining analysis\nRebuild the saved tables and figures from logs. Dry runs are scripted-bot checks, not study results. No API calls are made.")
    cell("code", '''import json, os
from pathlib import Path
PROJECT = Path.cwd()
if not (PROJECT / "pyproject.toml").exists() and (PROJECT.parent / "pyproject.toml").exists():
    PROJECT = PROJECT.parent
raw_roots = os.environ.get("LNB_ROOTS", str(PROJECT / "runs"))
ROOTS = json.loads(raw_roots) if raw_roots.lstrip().startswith("[") else raw_roots.split(os.pathsep)
OUT = Path(os.environ.get("LNB_OUT", str(PROJECT / "analysis_notebook")))
INCLUDE_DRY = os.environ.get("LNB_INCLUDE_DRY", "0").lower() in ("1", "true", "yes")
SEED, BOOT = 1, 2000
display = globals().get("display", print)''')
    cell("markdown", "## Source tables\nEpisodes are the independent observations. The command also writes every Phase 6 table and the no-last-round check.")
    cell("code", '''from llm_network_bargaining.analysis import load_dataset
from llm_network_bargaining.analysis.cli import main as analyse
args = [*ROOTS, "--out", str(OUT / "analysis"), "--seed", str(SEED), "--boot", str(BOOT)]
if INCLUDE_DRY:
    args.append("--include-dry")
assert analyse(args) == 0
data = load_dataset(ROOTS, include_dry=INCLUDE_DRY)
display(data.episodes)''')
    cell("markdown", "## Registered hypotheses and predictor comparisons\nH2 ranks the four point benchmarks. Centrality enters ordering accuracy only.")
    cell("code", '''from llm_network_bargaining.analysis.hypotheses import run_hypotheses
from llm_network_bargaining.analysis.benchmarks import benchmark_errors, ordering_accuracy
from llm_network_bargaining.analysis.mixed import fit_mixed_models
display(run_hypotheses(data, seed=SEED, n_boot=BOOT).to_dict())
display(benchmark_errors(data, seed=SEED, n_boot=BOOT))
display(ordering_accuracy(data, seed=SEED, n_boot=BOOT))
display(fit_mixed_models(data))''')
    cell("markdown", "## Figures\nEpisode dots accompany the means and bootstrap intervals. Human anchors are references from other protocols, not matched controls.")
    cell("code", '''from llm_network_bargaining.analysis.figures import (
    fig_observed_vs_predicted, fig_power_use, fig_dose_response,
    fig_parity_flip, fig_learning_curves, save_figure)
import matplotlib.pyplot as plt
for name, function in [("observed_vs_predicted", fig_observed_vs_predicted),
                       ("power_use", fig_power_use), ("dose_response", fig_dose_response),
                       ("parity_flip", fig_parity_flip), ("learning_curves", fig_learning_curves)]:
    figure = function(data, seed=SEED, n_boot=BOOT)
    save_figure(figure, OUT / "figures" / name)
    display(figure)
    plt.close(figure)''')
    cell("markdown", "## Diagnostics and pilot gate\nFailed and interrupted costs remain separate from completed-episode outcomes. The game-length decision is informational in the gate.")
    cell("code", '''from llm_network_bargaining.analysis.gate import pilot_gate
display(json.loads((OUT / "analysis" / "diagnostics.json").read_text()))
display(pilot_gate(data, ROOTS).to_dict())''')
    notebook = dict(cells=cells, metadata=dict(kernelspec=dict(display_name="Python 3", language="python", name="python3"),
                                             language_info=dict(name="python")), nbformat=4, nbformat_minor=5)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(notebook, sort_keys=True, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def main(argv: Sequence[str] | None = None) -> int:
    """Generate a pilot report, study report or the unexecuted notebook."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("pilot", "study"):
        command = commands.add_parser(name)
        command.add_argument("roots", nargs="+", type=Path)
        command.add_argument("--out", required=True, type=Path)
        command.add_argument("--include-dry", action="store_true")
        command.add_argument("--seed", type=int, default=1)
        command.add_argument("--boot", type=int, default=2000)
        if name == "study":
            command.add_argument("--notes", type=Path)
    notebook = commands.add_parser("notebook")
    notebook.add_argument("--out", type=Path, default=Path("notebooks/analysis.ipynb"))
    args = parser.parse_args(argv)
    try:
        if args.command == "notebook":
            path = write_notebook(args.out)
        else:
            function = write_pilot_report if args.command == "pilot" else write_study_report
            options = dict(include_dry=args.include_dry, seed=args.seed, n_boot=args.boot)
            if args.command == "study":
                options["notes"] = args.notes
            path = function(args.roots, args.out, **options)
        print(f"Wrote {path}")
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}")
        return 1
