"""Inclusive gate boundaries and the scientific contents of all five figures."""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from llm_network_bargaining.analysis import gate
from llm_network_bargaining.analysis.data import dataset_from_tables, load_dataset
from llm_network_bargaining.analysis.figures import (
    fig_dose_response, fig_learning_curves, fig_observed_vs_predicted,
    fig_parity_flip, fig_power_use, save_figure)
from llm_network_bargaining.analysis.hypotheses import run_hypotheses
from llm_network_bargaining.analysis.stats import slope_permutation_test
from phase6_helpers import tables_from_specs


def fake_gate(monkeypatch, *, completed=9, failed=1, abandoned=0, invalid=.02, perfect=.90, proposer=.5,
              length=24):
    """Inject summary tables so each boundary is independent of game behavior."""
    key = "pilot_full_map/pair/full_map/terra"
    ds = dataset_from_tables(episodes=pd.DataFrame([dict(episode_uid=f"{key}/{i:03d}",
        config_name="pilot_full_map", condition_key=key) for i in range(completed)]))
    monkeypatch.setattr(gate, "attempt_diagnostics", lambda *a, **k: pd.DataFrame([dict(
        failed_attempts=failed, abandoned_episodes=abandoned, failed_by_category={"refusal": failed}, interrupted_attempts=100)]))
    monkeypatch.setattr(gate, "invalid_action_rates", lambda *a: pd.DataFrame([
        dict(condition_key=key, model_alias="terra", n_asked=10000, n_invalid=invalid * 10000, by_reason={"bad_points": 1}),
        dict(condition_key="other", model_alias="terra", n_asked=10000, n_invalid=0, by_reason={})]))
    monkeypatch.setattr(gate, "quiz_summary", lambda *a: pd.DataFrame([dict(
        n=10000, perfect_share=perfect, q1_accuracy=perfect, q2_accuracy=1, q3_accuracy=1)]))
    monkeypatch.setattr(gate, "episode_pair_proposer_share", lambda *a: pd.DataFrame(
        dict(proposer_share=[] if proposer is None else [proposer] * 3)))
    monkeypatch.setattr(gate, "game_length_decision", lambda *a, **k: dict(decision=length, networks={}))
    return gate.pilot_gate(ds, [])


@pytest.mark.parametrize("options,key", [({}, None), ({"failed": 1001, "completed": 8999}, "G1"),
    ({"abandoned": 1}, "G1"), ({"invalid": .0201}, "G2"), ({"perfect": .8999}, "G3"),
    ({"proposer": .3499}, "G4"), ({"proposer": .6501}, "G4"),
    ({"proposer": .35}, None), ({"proposer": .65}, None), ({"length": 12}, None)])
def test_gate_boundaries(monkeypatch, options, key) -> None:
    result = fake_gate(monkeypatch, **options)
    assert result.overall == ("FAIL" if key else "PASS")
    if key:
        assert not result.checks[key].passed
        assert any(key in line for line in result.next_steps)
        assert result.next_steps[-1] == "Revise the prompt as a new prompt version and re-run the pilot."
    else:
        assert f"settings.rounds: {result.game_length}" in result.next_steps[0]
        assert "five study configs" in result.next_steps[0]


def test_gate_missing_data_and_worst_condition(monkeypatch) -> None:
    result = fake_gate(monkeypatch, proposer=None)
    assert result.checks["G4"].detail == "missing data" and result.overall == "FAIL"
    result = fake_gate(monkeypatch, invalid=.02 + 5e-10, perfect=.90 - 5e-10, proposer=.35 - 5e-10)
    assert result.overall == "PASS"
    assert result.checks["G2"].detail["worst_condition"].endswith("pair/full_map/terra")
    assert result.checks["G1"].value["failed_share"] == .1
    result = fake_gate(monkeypatch, length=None)
    assert result.overall == "PASS" and not result.checks["G5"].passed
    assert "Complete the 24-round own-links pilot" in result.next_steps[0]


def test_figures_contents_and_bytes(report_logs: Path, tmp_path: Path) -> None:
    ds = load_dataset([report_logs], include_dry=True)
    f1 = fig_observed_vs_predicted(ds, n_boot=30)
    assert len(f1.axes) == 8
    assert all(ax.get_ylim() == (0, 24) for ax in f1.axes)
    legend_markers = {handle.get_marker() for handle in f1.legends[0].legend_handles if hasattr(handle, "get_marker")}
    assert {"o", "^", "D", "*"}.issubset(legend_markers)
    f2 = fig_power_use(ds, n_boot=30)
    ax = f2.axes[0]
    assert len(ax.get_xticks()) == 6
    assert any(np.all(np.asarray(line.get_ydata()) == 0) for line in ax.lines)
    assert any(np.all(np.asarray(line.get_ydata()) == 1) for line in ax.lines)
    assert len([artist for artist in [*ax.lines, *ax.patches] if (artist.get_gid() or "").startswith("human_anchor:")]) == 3
    f3 = fig_dose_response(ds, n_boot=30)
    assert set(f3.axes[0].get_xticks()) == {2, 3, 4}
    f4 = fig_parity_flip(ds, n_boot=30)
    for line in f4.axes[0].lines:
        if line.get_label() in {"Equal split", "Myerson", "Position value", "Balanced"}:
            assert list(line.get_xdata()) == list(range(2, 8))
    observed = [artist for artist in f4.axes[0].collections if (artist.get_gid() or "").startswith("episodes:F4/")]
    assert len(observed) == 4
    p1 = fig_learning_curves(ds, n_boot=30)
    assert len(p1.axes) == 6
    assert all({patch.get_label() for patch in ax.patches} == {"rounds 7–12", "rounds 13–24"} for ax in p1.axes)
    for fig in (f1, f2, f3, f4, p1):
        plt.close(fig)
    # Both repeated saves and separately rebuilt figures must be deterministic.
    for index in range(2):
        figure = fig_dose_response(ds, seed=8, n_boot=30)
        save_figure(figure, tmp_path / f"dose{index}")
        plt.close(figure)
    assert (tmp_path / "dose0.svg").read_bytes() == (tmp_path / "dose1.svg").read_bytes()
    assert (tmp_path / "dose0.png").read_bytes() == (tmp_path / "dose1.png").read_bytes()
    save_figure(f3, tmp_path / "same0")
    save_figure(f3, tmp_path / "same1")
    assert (tmp_path / "same0.svg").read_bytes() == (tmp_path / "same1.svg").read_bytes()


def test_h3_registered_values_and_line3_inclusion(analysis_logs: Path) -> None:
    first = slope_permutation_test([.6, .7, .8], [2, 3, 4])
    second = slope_permutation_test([.6, .6, .7, .7, .8, .8], [2, 2, 3, 3, 4, 4])
    assert first.statistic == pytest.approx(.1) and first.p_value == 1/6
    assert second.statistic == pytest.approx(.1) and second.p_value == 1/90
    ds = load_dataset([analysis_logs], include_dry=True)
    result = run_hypotheses(ds, n_boot=20).results["H3"]
    assert {row["k"] for row in result["per_network"].values()} == {2, 3, 4}
    ds = gate.select_configs(ds, ["minimum_study"])
    ds.episodes = ds.episodes[ds.episodes.network_id.isin(["line3", "star3"])]
    ids = set(ds.episodes.episode_uid)
    ds.node_rounds = ds.node_rounds[ds.node_rounds.episode_uid.isin(ids)]
    assert run_hypotheses(ds, n_boot=20).results["H3"]["status"] == "run"
    ds.episodes = ds.episodes[ds.episodes.network_id == "line3"]
    ds.node_rounds = ds.node_rounds[ds.node_rounds.network_id == "line3"]
    assert run_hypotheses(ds, n_boot=20).results["H3"]["status"] == "not_run"


def test_h3_three_groups_use_monte_carlo() -> None:
    ds = tables_from_specs([
        dict(network="line3", points=[dict(A=0, B=14.4, C=0)] * 10),
        dict(network="star3", points=[dict(H=16.8, L1=0, L2=0, L3=0)] * 10),
        dict(network="star4", points=[dict(H=19.2, L1=0, L2=0, L3=0, L4=0)] * 10)])
    result = run_hypotheses(ds, n_boot=20).results["H3"]
    assert result["method"] == "monte_carlo" and result["n_resamples"] == 200000
    assert result["statistic"] == pytest.approx(.1)
