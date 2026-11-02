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

from ..networks import list_networks
from ..runlog import read_attempt_logs
from ..structure import class_label, node_classes
from .cli import main as analyse_main
from .data import Dataset, load_dataset
from .figures import (fig_dose_response, fig_learning_curves, fig_observed_vs_predicted,
                      fig_parity_flip, fig_power_use, save_figure)
from matplotlib.figure import Figure
from .gate import STUDY_CONFIGS, GateResult, pilot_gate
from .benchmarks import benchmark_errors, ordering_accuracy
from .cli import _write_json
from .predictions import PREDICTORS

DRY_BANNER = "**Dry-run data (scripted bots, simulated costs): not study results.**"


# Explicit column lists make the report layout independent of JSON key order.
CLASS_COLUMNS = "condition_key node_class n_episodes points_mean points_mean_ci_low points_mean_ci_high share_mean share_mean_ci_low share_mean_ci_high equal_split myerson position_value balanced".split()
RMSE_COLUMNS = "predictor n_classes rmse ci_low ci_high p_best".split()
ORDER_COLUMNS = "predictor n_pairs n_tied_observed correct accuracy ci_low ci_high".split()
COST_COLUMNS = "config_name model_alias status dry_run calls prompt_tokens cached_tokens cache_write_tokens completion_tokens reasoning_tokens cost_usd".split()
DIAGNOSTIC_COLUMNS = {
    "invalid_actions": "condition_key model_alias n_asked n_invalid invalid_rate by_reason".split(),
    "quizzes": "condition_key model_alias n mean_score perfect_share q1_accuracy q2_accuracy q3_accuracy".split(),
    "attempts": "condition_key abandoned_episodes failed_attempts interrupted_attempts failed_by_category non_completed_cost_usd".split(),
    "costs": COST_COLUMNS,
    "proposer_share": "condition_key n_episodes n_test proposer_share proposer_share_ci_low proposer_share_ci_high method p_value".split(),
    "triangle_lock_in": "condition_key n_episodes lock_in lock_in_ci_low lock_in_ci_high".split(),
    "efficiency": "condition_key n_episodes efficiency efficiency_ci_low efficiency_ci_high".split(),
    "power_use": "condition_key n_episodes pui pui_ci_low pui_ci_high".split(),
}
INPUT_COLUMNS = {
    "H1": "network n mean ci_low ci_high method alternative n_resamples statistic p_value".split(),
    "H3": "network k n mean ci_low ci_high".split(),
    "H4": "network n mean ci_low ci_high".split(),
}


def _is_count(column: str) -> bool:
    """Recognise count names, including counts inside flattened group columns."""
    name = column.rsplit(".", 1)[-1]
    return (name in {"n", "k", "calls", "episodes"} or name.startswith("n_")
            or name.endswith(("_episodes", "_attempts", "_tokens")))


def _format(value: Any, *, column: str = "", p_value: bool = False) -> str:
    """Render report cells with explicit count, cost and missing-value rules."""
    if value is None or (isinstance(value, (float, np.floating)) and not np.isfinite(value)):
        return "—"
    if isinstance(value, (bool, np.bool_)):
        return "yes" if value else "no"
    if isinstance(value, (int, float, np.number)):
        if _is_count(column):
            if not float(value).is_integer():
                raise ValueError(f"Non-integral count in {column}: {value}")
            return str(int(value))
        precision = ".4g" if p_value else ".1f" if column == "correct" else ".4f" if column.endswith("cost_usd") else ".2f"
        return format(value, precision)
    if isinstance(value, dict):
        return "; ".join(f"{key}: {_format(number, column='n' if isinstance(number, int) else key)}"
                         for key, number in sorted(value.items())) or "—"
    if isinstance(value, (list, tuple)):
        return ", ".join(_format(item) for item in value) or "—"
    return str(value)


def markdown_table(table: pd.DataFrame, columns: dict[str, str] | Sequence[str] | None = None,
                    p_columns: Sequence[str] = ()) -> str:
    """Write a Markdown table with fixed columns and escaped node-class pipes."""
    if columns is not None:
        table = table.reindex(columns=list(columns))
        if isinstance(columns, dict):
            table = table.rename(columns=columns)
            p_columns = [columns.get(name, name) for name in p_columns]
    if not len(table.columns):
        return "No data."

    def escape(value: str) -> str:
        """Keep literal pipes inside one Markdown cell."""
        return value.replace("|", "\\|").replace("\n", " ")

    lines = ["| " + " | ".join(map(escape, table.columns)) + " |",
             "| " + " | ".join("---" for _ in table.columns) + " |"]
    for row in table.to_dict("records"):
        lines.append("| " + " | ".join(escape(_format(row[column], column=column,
                     p_value=column in p_columns or column.rsplit(".", 1)[-1] in {"p_value", "p_adjusted"}))
                     for column in table.columns) + " |")
    return "\n".join(lines)


def _ordered(table: pd.DataFrame, configs: Sequence[str] = ()) -> pd.DataFrame:
    """Sort configs, registry networks, node classes and predictors explicitly."""
    networks = {net.id: i for i, net in enumerate(list_networks())}
    classes = {net.id: {class_label(nodes): i for i, nodes in enumerate(node_classes(net))}
               for net in list_networks() if net.kind == "exchange"}
    config_order = {name: i for i, name in enumerate(configs)}

    def key(row: dict) -> tuple:
        """Recover redundant identifiers from a condition key when necessary."""
        parts = str(row.get("condition_key", "")).split("/")
        config = row.get("config_name", parts[0])
        network = row.get("network_id", row.get("network", parts[1] if len(parts) > 1 else ""))
        predictor = row.get("predictor", "")
        return (config_order.get(config, len(config_order)), networks.get(network, len(networks)),
                classes.get(network, {}).get(row.get("node_class"), -1),
                PREDICTORS.index(predictor) if predictor in PREDICTORS else -1,
                str(row.get("condition_key", "")), str(row.get("model_alias", "")))

    return pd.DataFrame(sorted(table.to_dict("records"), key=key), columns=table.columns)


def gate_table(result: GateResult) -> str:
    """Present the gate's own values, without calculating a new gate statistic."""
    rows = []
    for key, check in result.checks.items():
        value = (f"{check.value['abandoned']} abandoned; failed share {_format(check.value['failed_share'])}"
                 if key == "G1" else _format(check.value))
        threshold = check.threshold
        decision = "PASS" if check.passed else "FAIL"
        if key == "G5":
            value = f"{check.value} rounds" if check.value is not None else "missing data"
            threshold = "gap ≤ 0.1 on line3 and star3 → 12 rounds, otherwise 24"
            decision = "INFO"
        rows.append(dict(check=f"{key}: {check.name}", measure=check.measure, threshold=threshold,
                         value=value, decision=decision))
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
    # Phase 6 serialises structured CSV cells as JSON; restore them for rendering.
    mixed = results["mixed_models"]
    mixed["warnings"] = mixed.warnings.map(lambda value: json.loads(value) if isinstance(value, str) else value)
    return data, results


class UnknownConfigs(ValueError):
    """A requested config was absent from all source headers."""


def _select_study_configs(roots: Sequence[str | Path], configs: Sequence[str] | None) -> list[str]:
    """Validate requested names before writing any analysis outputs."""
    found = {record.header["config_name"] for _, record in read_attempt_logs(roots)}
    selected = list(configs) if configs is not None else [name for name in STUDY_CONFIGS if name in found]
    missing = set(selected) - found
    if missing:
        raise UnknownConfigs(f"Unknown configs: {', '.join(sorted(missing))}. Configs found: {', '.join(sorted(found)) or 'none'}.")
    return list(dict.fromkeys(selected))


def _provenance(ds: Dataset, roots: Sequence[str | Path], configs: Sequence[str]) -> str:
    """Describe selected source headers, excluded configs and source dates."""
    all_headers = [record.header for _, record in read_attempt_logs(roots)]
    headers = [header for header in all_headers if header["config_name"] in configs]
    dates = sorted(header["started_at"] for header in headers)
    fields = {
        "Configs": list(configs),
        "Configs excluded": sorted({header["config_name"] for header in all_headers} - set(configs)),
        "Prompt versions": sorted({header["prompt_version"] for header in headers}),
        "Quiz versions": sorted({header["quiz_version"] for header in headers}),
        "Model IDs": sorted({model["model_id"] for header in headers for model in header["models"].values()}),
        "Git commits": sorted({header["git_commit"] or "uncommitted" for header in headers}),
        "Dates (source started_at range)": f"{dates[0]} to {dates[-1]}" if dates else "missing data",
    }
    text = markdown_table(pd.DataFrame([dict(field=key, value=value) for key, value in fields.items()]), ["field", "value"])
    counts = ds.episodes.groupby(["config_name", "condition_key"], as_index=False).agg(episodes=("episode_uid", "count"))
    return text + "\n\n" + markdown_table(_ordered(counts, configs), ["condition_key", "episodes"])


def _figure(fig: Figure, out: Path, stem: str, caption: str) -> str:
    """Save both figure formats and return a portable relative Markdown image."""
    try:
        save_figure(fig, out / "figures" / stem)
    finally:
        plt.close(fig)
    return f"![{stem.replace('_', ' ')}](figures/{stem}.png)\n\n{caption}"


def _diagnostics(diagnostics: dict, configs: Sequence[str]) -> str:
    """Render saved diagnostics and append the sums of the cost-table columns."""
    sections = []
    for name, key in [("Invalid moves and reasons", "invalid_actions"), ("Rules quiz", "quizzes"),
                      ("Attempts and failure categories", "attempts"), ("Costs and usage", "costs"),
                      ("Pair proposer share", "proposer_share"), ("Triangle lock-in", "triangle_lock_in"),
                      ("Efficiency", "efficiency")]:
        table = _ordered(pd.DataFrame(diagnostics[key]), configs)
        if key == "costs":
            total = dict(config_name="total", model_alias="", status="", dry_run="")
            total.update({column: table[column].sum() if column in table else 0 for column in COST_COLUMNS[4:]})
            table = pd.concat([table, pd.DataFrame([total])], ignore_index=True)
        sections.extend([f"### {name}", markdown_table(table, DIAGNOSTIC_COLUMNS[key])])
    cost_label = "simulated" if diagnostics["dry_run"] else "actual"
    return f"Costs below are {cost_label}; completed and non-completed attempts are separate rows.\n\n" + "\n\n".join(sections)


def _flatten_inputs(inputs: dict) -> pd.DataFrame:
    """Expose nested per-network inputs without changing their values."""
    rows = []
    for network, values in inputs.items():
        row = {"network": network}
        for key, value in values.items():
            if isinstance(value, dict):
                row.update({f"{key}.{subkey}": number for subkey, number in value.items()})
            else:
                row[key] = value
        rows.append(row)
    return _ordered(pd.DataFrame(rows))


def _group_inputs(result: dict, name: str) -> tuple[pd.DataFrame, list[str]]:
    """Lay out H5/H6 group summaries and verify their saved sample counts."""
    groups = ("full_map", "own_links") if name == "H5" else ("terra_hub", "luna_hub")
    if name == "H5":
        inputs = result.get("per_network", {})
    else:
        inputs = {}
        for cell, values in result.get("per_network", {}).items():
            network, assignment = cell.split("/")
            inputs.setdefault(network, {})[assignment] = values
        for network, difference in result.get("assignment_differences", {}).items():
            inputs[network].update(difference)
    for values in inputs.values():
        if "n_a" in values:
            # Phase 6's difference is first group minus second: a is second, b first.
            assert values["n_a"] == values[groups[1]]["n"]
            assert values["n_b"] == values[groups[0]]["n"]
    table = _flatten_inputs(inputs).rename(columns={"ci_low": "difference_ci_low", "ci_high": "difference_ci_high"})
    columns = ["network", *(f"{group}.{field}" for group in groups for field in ("n", "mean", "ci_low", "ci_high")),
               "difference", "difference_ci_low", "difference_ci_high"]
    if name == "H6":
        columns += [f"{group}.{field}" for group in groups for field in
                    ("method", "alternative", "n_resamples", "statistic", "p_value")]
    return table, columns


def _class_tables(summary: pd.DataFrame, configs: Sequence[str], *, heading: str = "###") -> list[str]:
    """Render one class table per registry network for the requested configs."""
    summary = _ordered(summary[summary.config_name.isin(configs)], configs)
    sections = []
    for network, table in summary.groupby("network_id", sort=False):
        sections.extend([f"{heading} {network}", markdown_table(table, CLASS_COLUMNS)])
    return sections


def _rmse_section(errors: dict) -> list[str]:
    """Show saved RMSEs, their common class set and the existing ranking."""
    if not errors["overall"]:
        return ["No classes where all four benchmarks are defined."]
    n_classes = errors["overall"][0]["n_classes"]
    excluded = _ordered(pd.DataFrame(errors["core_distances"]))
    excluded = list(dict.fromkeys(excluded.loc[~excluded.network_id.isin(errors["overall_networks"]), "network_id"]))
    reasons = [f"{network} (no balanced outcome)" for network in excluded]
    sentence = f"RMSE over the {n_classes} classes where all four benchmarks are defined; left out: {', '.join(reasons) or 'none'}."
    return [markdown_table(_ordered(pd.DataFrame(errors["overall"])), RMSE_COLUMNS), sentence,
            f"Ranking: {', '.join(errors['ranking'])}. Best benchmark: **{errors['best']}**."]


def _ordering_section(orders: dict, filename: str = "ordering_accuracy.json") -> list[str]:
    """Pivot saved accuracies; keep per-network intervals in the analysis JSON."""
    per_network = pd.DataFrame(orders["per_network"])
    rows, excluded = [], []
    if not per_network.empty:
        for network, group in _ordered(per_network).groupby("network_id", sort=False):
            if group.n_pairs.max() == 0:
                excluded.append(network)
                continue
            row = dict(network_id=network, n_pairs=int(group.n_pairs.max()))
            row.update({record.predictor: record.accuracy for record in group.itertuples()})
            rows.append(row)
    return [markdown_table(_ordered(pd.DataFrame(orders["overall"])), ORDER_COLUMNS),
            markdown_table(pd.DataFrame(rows), ["network_id", "n_pairs", *PREDICTORS]),
            f"Networks with a single class have no pairs and are left out: {', '.join(excluded) or 'none'}. "
            f"Per-network intervals are in `analysis/{filename}`."]


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
        markdown_table(length_table, {"network": "network", "n_episodes": "n_episodes", "w_early": "w_early",
                       "w_late": "w_late", "gap": "gap", "passed": "within 0.1"}),
        "w_early and w_late are the advantaged class's mean power-use index over rounds 7–12 and 13–24. The game stays at 12 rounds only if both gaps are within 0.1.", "## Outcomes", "### Class earnings, shares and predictions"]
    sections.extend(_class_tables(result["class_summary"], configs))
    sections.extend(["### Power-use index", markdown_table(_ordered(pd.DataFrame(result["diagnostics"]["power_use"]), configs), DIAGNOSTIC_COLUMNS["power_use"]),
                     "## Diagnostics", _diagnostics(result["diagnostics"], configs)])
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
    labels = labels[labels.episode_uid.isin(ds.episodes.episode_uid)]
    if "dry_run" in labels and len(labels) and labels.dry_run.astype(str).str.lower().eq("true").any() and not ds.dry_run:
        raise ValueError("Keyword dry-run labels cannot be included as live study results.")
    paired_path = path.parent / "consistency.json"
    repeat = json.loads(paired_path.read_text()) if paired_path.exists() else {}
    selected_ids = set(labels.loc[labels.status == "coded", "note_id"])
    sample = [key for key in repeat.get("sample_ids", []) if key in selected_ids]
    if len(sample) != repeat.get("n_selected", 0):
        # Reuse the same agreement function on the selected part of the saved sample.
        from ..notes.consistency import consistency_summary

        cache_path = path.parent / "consistency_cache.jsonl"
        if cache_path.exists():
            cached = [json.loads(line) for line in cache_path.read_text().splitlines()]
            cached = {row["note_id"]: row for row in cached if row["judge_version"] == repeat["judge_version"]}
            main = {row["note_id"]: {label: str(row[label]).lower() == "true" for label in LABELS}
                    for row in labels[labels.status == "coded"].to_dict("records")}
            repeat = consistency_summary(main, cached, sample, dry_run=repeat["dry_run"])
        else:
            # A global summary alone cannot identify the selected repeat judgments.
            repeat = {}
    table = pd.DataFrame([dict(label=label, **row) for label, row in repeat.get("labels", {}).items()])
    n_quotes = n_missed = 0
    for row in labels[labels.status == "coded"].to_dict("records"):
        flags = json.loads(row["flags"]) if isinstance(row.get("flags"), str) else []
        for label in LABELS:
            if pd.notna(row[f"{label}_quote"]):
                n_quotes += 1
                n_missed += f"quote_not_found:{label}" in flags
    share = n_missed / n_quotes if n_quotes else None
    return "\n\n".join(["## Notes", markdown_table(_ordered(label_prevalence(labels), list(ds.episodes.config_name.unique())), ["condition_key", "node_class", "n_notes", *LABELS]), "### Repeat consistency",
        markdown_table(table, "label n agreement yes_rate_a yes_rate_b expected_agreement kappa reason".split()), "Repeat consistency measures consistency, not correctness. Validation against hand labels is future work.",
        f"Quotes not found in their notes: {_format(share)} ({n_missed} of {n_quotes} quotes)."])


def write_study_report(roots: Sequence[str | Path], out: str | Path, *, include_dry: bool = False,
                        seed: int = 1, n_boot: int = 2000, notes: str | Path | None = None,
                        configs: Sequence[str] | None = None) -> Path:
    """Write selected study results, main class outcomes and exploratory tables."""
    out = Path(out)
    configs = _select_study_configs(roots, configs)
    ds, result = _analyse(roots, out, include_dry, seed, n_boot, configs)
    tests, errors, orders = result["hypotheses"], result["benchmark_errors"], result["ordering_accuracy"]
    sections = [DRY_BANNER if ds.dry_run else "", "# Study report", "## Provenance", _provenance(ds, roots, configs),
                "## Hypotheses", hypothesis_table(tests), "### H1 secondary per-network analysis"]
    secondary = pd.DataFrame([dict(network=network, **row) for network, row in tests["h1_per_network"].items()])
    sections.append(markdown_table(_ordered(secondary),
        "network n mean ci_low ci_high p_value p_adjusted decision".split()))
    for name in ("H1", "H3", "H4", "H5", "H6"):
        values = tests["results"][name]
        if name == "H6" and values["status"] != "run":
            continue
        table, columns = (_group_inputs(values, name) if name in {"H5", "H6"}
                          else (_flatten_inputs(values.get("per_network", {})), INPUT_COLUMNS[name]))
        sections.extend([f"### {name} per-network inputs", markdown_table(table, columns)])
    main_configs = [name for name in ("minimum_study", "own_links_arm") if name in configs]
    sections.extend(["## Class outcomes (second half)",
        "Observed points per round and per-deal share by node class, with episode-bootstrap 95% intervals, beside the four benchmarks.",
        *_class_tables(result["class_summary"], main_configs),
        "## H2: benchmark comparison", "### Overall RMSE and P(best)", *_rmse_section(errors),
        "### Per-network RMSE", markdown_table(_ordered(pd.DataFrame(errors["per_network"]), configs),
            "condition_key predictor n_episodes n_classes rmse ci_low ci_high".split()),
        "### Distance to the core", markdown_table(_ordered(pd.DataFrame(errors["core_distances"])),
            "network_id node_class observed core_min core_max distance".split()),
        "### Ordering accuracy (four benchmarks, degree and betweenness)", *_ordering_section(orders), "## Figures"])
    options = dict(seed=seed, n_boot=n_boot)
    plots = [
        (fig_observed_vs_predicted(ds, **options), "observed_vs_predicted", "F1. Episode class earnings and their mean/95% CI beside the four point benchmarks and core intervals."),
        (fig_power_use(ds, **options), "power_use", "F2. Power use by knowledge setting, with theory and human anchors: [Borch & Girard](https://www.cmu.edu/joss/content/articles/volume10/Borch) (3-line and 5-line), and [Kleinberg & Tardos (2008)](https://cs.cornell.edu/info/people/kleinber/stoc08-exchange.pdf) (4-line)."),
        (fig_dose_response(ds, **options), "dose_response", "F3. Hub share versus leaf count, including the 3-line at k = 2, with Myerson, equal-split/position-value and core references."),
        (fig_parity_flip(ds, **options), "parity_flip", "F4. End-agent earnings for observed lines and all four point predictions for lengths 2–7."),
    ]
    for fig, stem, caption in plots:
        sections.append(_figure(fig, out, stem, caption))
    sections.extend(["## Mixed models", markdown_table(_ordered(result["mixed_models"]),
        "predictor n_obs n_groups intercept intercept_se pred pred_se slot1_norm slot1_norm_se log_likelihood aic converged warnings error".split()),
        "## Exploratory: stretch configs", "Descriptive results for the stretch configs, outside the Holm family. H6 is in the hypothesis table."])
    stretch = [name for name in STUDY_CONFIGS[2:] if name in configs]
    if not stretch:
        sections.append("No stretch configs in these logs.")
    for config in stretch:
        sections.extend([f"### {config}", *_class_tables(result["class_summary"], [config], heading="####")])
        if config == "stretch_2f_h6":
            continue
        for function, stem in [(benchmark_errors, "benchmark_errors"), (ordering_accuracy, "ordering_accuracy")]:
            saved = out / "analysis" / f"{stem}_{config}.json"
            _write_json(saved, function(ds, config=config, **options))
            values = json.loads(saved.read_text())
            sections.extend([f"#### {stem.replace('_', ' ').capitalize()}",
                             *(_rmse_section(values) if stem == "benchmark_errors" else _ordering_section(values, saved.name))])
        sections.append(_figure(fig_observed_vs_predicted(ds, config=config, **options), out,
            f"observed_vs_predicted_{config}", f"Exploratory {config}: class earnings and 95% intervals beside the four benchmarks."))
    sections.extend(["## Robustness", hypothesis_table(result["hypotheses_no_last"]),
        "### Class outcomes without the last round", *_class_tables(result["class_summary_no_last"], main_configs, heading="####"),
        "## Diagnostics", _diagnostics(result["diagnostics"], configs)])
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
    cell("code", '''for config in ("stretch_2c_sweep", "stretch_2d_control"):
    if config in set(data.episodes.config_name):
        display(benchmark_errors(data, config=config, seed=SEED, n_boot=BOOT))
        display(ordering_accuracy(data, config=config, seed=SEED, n_boot=BOOT))
        figure = fig_observed_vs_predicted(data, config=config, seed=SEED, n_boot=BOOT)
        save_figure(figure, OUT / "figures" / f"observed_vs_predicted_{config}")
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
            command.add_argument("--configs", nargs="+")
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
                options["configs"] = args.configs
            path = function(args.roots, args.out, **options)
        print(f"Wrote {path}")
        return 0
    except UnknownConfigs as exc:
        print(f"ERROR: {exc}")
        return 2
    except (OSError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}")
        return 1
