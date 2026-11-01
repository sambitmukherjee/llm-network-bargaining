"""Independent reference values for predictions, windows and outcome metrics."""

import numpy as np
import pandas as pd
import pytest

from llm_network_bargaining.analysis import window_rounds
from llm_network_bargaining.analysis.benchmarks import benchmark_errors, ordering_accuracy
from llm_network_bargaining.analysis.game_length import game_length_decision
from llm_network_bargaining.analysis.metrics import (condition_class_summary, episode_class_metrics,
    episode_efficiency, episode_node_metrics, episode_triangle_lock_in, learning_curves, power_use,
    summarise_pair_proposer_share, summarise_power_use)
from llm_network_bargaining.analysis.predictions import advantaged_class, class_predictions
from phase6_helpers import tables_from_specs

EXPECTED = {
    "pair": {"A|B": (12, 1, 0)},
    "line3": {"A|C": (6, 1, 0), "B": (12, 2, 1)},
    "line4": {"A|D": (12, 1, 0), "B|C": (12, 2, 2/3)},
    "line5": {"A|E": (8, 1, 0), "B|D": (12, 2, .5), "C": (8, 2, 2/3)},
    "star3": {"L1|L2|L3": (4, 1, 0), "H": (12, 3, 1)},
    "star4": {"L1|L2|L3|L4": (3, 1, 0), "H": (12, 4, 1)},
    "stem": {"A": (12, 1, 0), "B": (12, 3, 2/3), "C|D": (12, 2, 0)},
    "triangle": {"A|B|C": (8, 2, 0)},
}


@pytest.mark.parametrize("network", EXPECTED)
def test_registered_predictions(network: str) -> None:
    table = class_predictions(network).set_index("node_class")
    assert set(table.index) == set(EXPECTED[network])
    for label, values in EXPECTED[network].items():
        assert table.loc[label, ["equal_split", "degree", "betweenness"]].to_numpy(dtype=float) == pytest.approx(values)
    if network == "triangle":
        assert table[["balanced", "core_min", "core_max"]].isna().all().all()
    table.iloc[0, 0] = "changed"
    assert class_predictions(network).network_id.iloc[0] == network


def test_windows() -> None:
    assert window_rounds(12) == range(7, 13)
    assert window_rounds(24) == range(13, 25)
    assert window_rounds(12, "second_half_no_last") == range(7, 12)
    assert window_rounds(12, "all") == range(1, 13)
    assert list(window_rounds(1, "second_half_no_last")) == []
    with pytest.raises(ValueError):
        window_rounds(12, "later")


def test_power_use_and_equal_member_weight() -> None:
    ds = tables_from_specs([
        dict(network="line3", points=[dict(A=0, B=18, C=6)]),
        dict(network="line4", points=[dict(A=10, B=12, C=16, D=10)]),
        dict(network="stem", points=[dict(A=9, B=15, C=12, D=12)]),
        dict(network="pair", points=[dict(A=12, B=12)]),
        dict(network="triangle", points=[dict(A=8, B=8, C=8)])])
    assert power_use(ds).pui.to_numpy() == pytest.approx([.5, .5, .5])
    assert set(power_use(ds).network_id) == {"line3", "line4", "stem"}
    assert advantaged_class("sweep0") is None
    assert summarise_power_use(ds, n_boot=10).pui_ci_low.to_numpy() == pytest.approx([.5] * 3)
    nodes = episode_node_metrics(ds)
    assert nodes[(nodes.network_id == "line3") & (nodes.node == "A")].share_mean.isna().all()
    classes = episode_class_metrics(ds)
    ends = classes[(classes.network_id == "line3") & (classes.node_class == "A|C")].iloc[0]
    assert ends.points_mean == 3 and ends.share_mean == .25 and ends.deal_rate == .5
    # Only the second half contributes, and the last-round check really drops it.
    ds.node_rounds.loc[ds.node_rounds["round"] == 12, "points"] += 6
    assert power_use(ds).pui.iloc[0] != power_use(ds, "second_half_no_last").pui.iloc[0]


def test_triangle_lock_in_and_efficiency() -> None:
    ds = tables_from_specs([dict(network="triangle", rounds=6,
        points=[dict(A=[0]*5+[12], B=[12]*5+[0], C=12)],
        dealt=dict(A=[False]*5+[True], B=[True]*5+[False], C=True))])
    assert episode_triangle_lock_in(ds, "all").lock_in.iloc[0] == pytest.approx(5/6)
    assert episode_efficiency(ds, "all").efficiency.iloc[0] == 1
    ds.node_rounds["dealt"] = True
    assert np.isnan(episode_triangle_lock_in(ds, "all").lock_in.iloc[0])


def test_registered_rmse_and_core_distance() -> None:
    ds = tables_from_specs([dict(network="line3", points=[dict(A=1.5, B=21, C=1.5)] * 3)])
    result = benchmark_errors(ds, n_boot=30)
    expected = dict(equal_split=7.115125, myerson=3.952847, position_value=7.115125, balanced=2.371708)
    for row in result["per_network"]:
        assert row["rmse"] == pytest.approx(expected[row["predictor"]], abs=1e-6)
        assert row["ci_low"] == row["ci_high"] == row["rmse"]
    assert result["best"] == "balanced"
    assert sum(row["p_best"] for row in result["overall"]) == pytest.approx(1)
    distances = {row["node_class"]: row["distance"] for row in result["core_distances"]}
    assert distances == {"A|C": 1.5, "B": 3.0}


def test_registered_ordering_and_observed_ties() -> None:
    ds = tables_from_specs([dict(network="line5", points=[dict(A=4, B=15, C=10, D=15, E=4)])])
    result = ordering_accuracy(ds, n_boot=20)
    expected = dict(equal_split=2.5/3, myerson=1, position_value=1, balanced=2.5/3, degree=2.5/3, betweenness=2/3)
    for row in result["overall"]:
        assert row["accuracy"] == pytest.approx(expected[row["predictor"]])
        assert row["n_pairs"] == 3 and row["n_tied_observed"] == 0
    ds.node_rounds["points"] = 12
    for row in ordering_accuracy(ds, n_boot=20)["overall"]:
        assert row["n_pairs"] == 0 and row["n_tied_observed"] == 3
        assert row["accuracy"] is None


def test_summary_bootstrap_unit_and_pair_proposer_test() -> None:
    ds = tables_from_specs([dict(network="pair", points=[dict(A=14, B=10)] * 3)])
    records = [dict(episode_uid=uid, round=r, phase=2, maker="A", recipient="B", maker_points=14,
                    recipient_points=10, maker_class="A|B", recipient_class="A|B")
               for uid in ds.episodes.episode_uid for r in range(1, 13)]
    ds.deals = pd.DataFrame(records)
    proposer = summarise_pair_proposer_share(ds, n_boot=20).iloc[0]
    assert proposer.proposer_share == pytest.approx(14/24)
    assert proposer.p_value == 2/8 and proposer.n_test == 3
    summary = condition_class_summary(ds, n_boot=20)
    assert summary.points_mean.iloc[0] == 12
    assert summary.points_mean_ci_low.iloc[0] == 12
    assert summary.n_episodes.iloc[0] == 3
    assert len(learning_curves(ds, n_boot=10)) == 12


def test_game_length_registered_examples_and_boundary() -> None:
    def dataset(star_early=15, late=19):
        return tables_from_specs([
            dict(network="line3", knowledge="own_links", config="pilot_own_links", rounds=24,
                 points=[dict(A=0, B=[18]*12+[19]*12, C=0)] * 3),
            dict(network="star3", knowledge="own_links", config="pilot_own_links", rounds=24,
                 points=[dict(H=[star_early]*12+[late]*12, L1=0, L2=0, L3=0)] * 3)])
    result = game_length_decision(dataset())
    line, star = result["networks"]["line3"], result["networks"]["star3"]
    assert (line["w_early"], line["w_late"], line["gap"]) == pytest.approx((.5, 7/12, 1/12))
    assert (star["w_early"], star["w_late"], star["gap"]) == pytest.approx((.25, 7/12, 1/3))
    assert line["passed"] and not star["passed"] and line["n_episodes"] == 3
    assert result["decision"] == 24
    assert game_length_decision(dataset(18))["decision"] == 12
    assert game_length_decision(dataset(18, 19.2))["decision"] == 12
    wrong_length = dataset()
    wrong_length.episodes["n_rounds"] = 12
    with pytest.raises(ValueError, match="24-round"):
        game_length_decision(wrong_length)
