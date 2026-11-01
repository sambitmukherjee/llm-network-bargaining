"""End-to-end numerical analysis and reproducible output files."""

import json
from pathlib import Path

import numpy as np
import pytest

from llm_network_bargaining.analysis.benchmarks import benchmark_errors, ordering_accuracy
from llm_network_bargaining.analysis.cli import main
from llm_network_bargaining.analysis.data import dataset_from_tables, load_dataset
from llm_network_bargaining.analysis.game_length import game_length_decision
from llm_network_bargaining.analysis.hypotheses import run_hypotheses
from llm_network_bargaining.analysis.mixed import fit_mixed_models
from llm_network_bargaining.analysis.predictions import BENCHMARKS, PREDICTORS

OUTPUTS = {"episodes.csv", "node_rounds.csv.gz", "deals.csv.gz", "turns.csv.gz", "quizzes.csv",
    "class_summary.csv", "power_use.csv", "learning_curves.csv", "benchmark_errors.json",
    "ordering_accuracy.json", "hypotheses.json", "mixed_models.csv", "diagnostics.json",
    "game_length.json", "hypotheses_no_last.json", "class_summary_no_last.csv"}


def test_end_to_end_statistics(analysis_logs: Path) -> None:
    ds = load_dataset([analysis_logs], include_dry=True)
    report = run_hypotheses(ds, n_boot=40)
    assert report.results["H6"]["status"] == "not_run"
    assert set(report.family) == {"H1", "H3", "H4", "H5"}
    assert all(0 <= row["p_value"] <= 1 for row in report.results.values() if row["status"] == "run")
    json.dumps(report.to_dict(), allow_nan=False)
    errors = benchmark_errors(ds, n_boot=40)
    assert {row["predictor"] for row in errors["overall"]} == set(BENCHMARKS)
    assert all(np.isfinite(row["rmse"]) for row in errors["overall"])
    assert "triangle" not in errors["overall_networks"]
    assert len([row for row in errors["per_network"] if row["network_id"] == "triangle"]) == 3
    orders = ordering_accuracy(ds, n_boot=40)
    assert {row["predictor"] for row in orders["overall"]} == set(PREDICTORS)
    assert all(0 <= row["accuracy"] <= 1 for row in orders["overall"])
    mixed = fit_mixed_models(ds)
    assert set(mixed.predictor) == set(BENCHMARKS)
    assert mixed.error.isna().all(), mixed[["predictor", "error"]].to_dict("records")
    assert np.isfinite(mixed.aic).all()
    assert mixed.n_obs.nunique() == mixed.n_groups.nunique() == 1
    expected_rows = ds.node_rounds[(ds.node_rounds.config_name == "minimum_study") &
        (ds.node_rounds.network_id != "triangle") & (ds.node_rounds["round"] >= 7)]
    assert (mixed.n_obs == len(expected_rows)).all()
    assert game_length_decision(ds)["decision"] in (12, 24)


def test_cli_outputs_byte_identical(analysis_logs: Path, tmp_path: Path, capsys) -> None:
    folders = [tmp_path / "first", tmp_path / "second"]
    for folder in folders:
        assert main([str(analysis_logs), "--out", str(folder), "--include-dry", "--boot", "40", "--seed", "7"]) == 0
    assert {path.name for path in folders[0].iterdir()} == OUTPUTS
    for filename in OUTPUTS:
        assert (folders[0] / filename).read_bytes() == (folders[1] / filename).read_bytes(), filename
        if filename.endswith(".json"):
            json.loads((folders[0] / filename).read_text(), parse_constant=lambda value: pytest.fail(value))
    stdout = capsys.readouterr().out
    assert "minimum_study: 16 completed episodes" in stdout
    assert "H6: not_run" in stdout and "H2 best benchmark:" in stdout


def test_cli_config_filter_and_bad_input(analysis_logs: Path, tmp_path: Path) -> None:
    assert main([str(analysis_logs), "--out", str(tmp_path / "error")]) == 1
    out = tmp_path / "filtered"
    assert main([str(analysis_logs), "--out", str(out), "--configs", "pilot_own_links",
                 "--include-dry", "--boot", "10"]) == 0
    assert json.loads((out / "hypotheses.json").read_text())["family"] == {}
    assert json.loads((out / "benchmark_errors.json").read_text())["status"] == "not_run"


def test_empty_dataset_and_mixed_model_failure_are_reported(monkeypatch, analysis_logs: Path) -> None:
    ds = dataset_from_tables()
    assert run_hypotheses(ds, n_boot=10).family == {}
    assert fit_mixed_models(ds).empty
    assert benchmark_errors(ds, n_boot=10)["status"] == "not_run"
    from llm_network_bargaining.analysis import mixed

    def fail(*args, **kwargs):
        raise ValueError("Injected singular fit")

    monkeypatch.setattr(mixed.MixedLM, "from_formula", fail)
    result = fit_mixed_models(load_dataset([analysis_logs], include_dry=True))
    assert len(result) == 4
    assert all("Injected singular fit" in error for error in result.error)
