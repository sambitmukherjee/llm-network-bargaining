"""Hypothesis direction, intersection--union claims and the Holm families."""

import json

import pytest

from llm_network_bargaining.analysis.hypotheses import HypothesisReport, run_hypotheses
from phase6_helpers import tables_from_specs


def test_h1_intersection_union_and_missing_family_members() -> None:
    ds = tables_from_specs([
        dict(network="line3", points=[dict(A=0, B=19.2, C=0)] * 10),
        dict(network="line5", points=[dict(A=0, B=12, C=0, D=12, E=0)] * 10),
        dict(network="star3", points=[dict(H=19.2, L1=0, L2=0, L3=0)] * 10),
        dict(network="star4", points=[dict(H=19.2, L1=0, L2=0, L3=0, L4=0)] * 10)])
    report = run_hypotheses(ds, n_boot=20)
    h1 = report.results["H1"]
    assert h1["p_value"] == h1["per_network"]["line5"]["p_value"] == 1
    assert h1["per_network"]["line3"]["p_value"] == 1/1024
    assert not h1["reject"]
    assert set(report.family) == {"H1", "H3"}
    assert report.results["H4"]["status"] == report.results["H5"]["status"] == "not_run"
    assert report.results["H6"]["status"] == "not_run"
    assert report.h1_per_network["line3"]["reject"]
    assert not report.h1_per_network["line5"]["reject"]
    json.dumps(report.to_dict(), allow_nan=False)


def test_injected_h1_secondary_reporting() -> None:
    per_network = {network: dict(p_value=p, mean=.7, n=10)
                   for network, p in [("line3", .001), ("star3", .002), ("star4", .004), ("line5", .30)]}
    report = HypothesisReport({"H1": dict(status="run", p_value=.30, statistic=.1, per_network=per_network),
                               "H3": dict(status="not_run")})
    expected = dict(line3=.004, star3=.006, star4=.008, line5=.30)
    for network, p in expected.items():
        assert report.h1_per_network[network]["p_adjusted"] == pytest.approx(p)
    assert report.results["H1"]["p_value"] == .30 and not report.results["H1"]["reject"]
    assert set(report.family) == {"H1"}
    assert {net for net, row in report.h1_per_network.items() if row["reject"]} == {"line3", "star3", "star4"}
    assert report.to_dict()["h1_per_network"] == report.h1_per_network


def test_h4_direction_and_stratified_h5() -> None:
    full = dict(line3=dict(A=2, B=18, C=2), line4=dict(A=10, B=14, C=14, D=10),
                line5=dict(A=2, B=18, C=2, D=18, E=2), star3=dict(H=18, L1=2, L2=2, L3=2),
                star4=dict(H=18, L1=2, L2=2, L3=2, L4=2), stem=dict(A=2, B=15, C=12, D=12))
    specs = []
    for network, points in full.items():
        local = dict(points)
        for node in ({"line3": ["B"], "line4": ["B", "C"], "line5": ["B", "D"],
                      "star3": ["H"], "star4": ["H"], "stem": ["B"]}[network]):
            local[node] = 12 + (local[node] - 12) / 2
        specs.extend([dict(network=network, points=[points] * 2),
                      dict(network=network, knowledge="own_links", points=[local] * 2)])
    report = run_hypotheses(tables_from_specs(specs), n_boot=20)
    assert report.results["H4"]["statistic"] == 8
    assert report.results["H4"]["alternative"] == "greater"
    h5 = report.results["H5"]
    assert h5["statistic"] == pytest.approx(.25)
    assert h5["p_value"] == pytest.approx(2 / 6**6)
    assert h5["method"] == "exact" and len(h5["per_network"]) == 6
    assert all(row["difference"] == .25 for row in h5["per_network"].values())


def test_h6_requires_all_four_cells_and_reports_assignment_differences() -> None:
    specs = []
    for network, points in [("line3", dict(A=0, B=18, C=0)), ("star3", dict(H=18, L1=0, L2=0, L3=0))]:
        for assignment in ("terra_hub", "luna_hub"):
            specs.append(dict(network=network, config="stretch_2f_h6", assignment=assignment, points=[points] * 3))
    report = run_hypotheses(tables_from_specs(specs), n_boot=20)
    assert set(report.family) == {"H6"}
    assert report.results["H6"]["p_value"] == 1/8
    assert report.results["H6"]["assignment_differences"]["line3"]["difference"] == 0
    incomplete = run_hypotheses(tables_from_specs(specs[:-1]), n_boot=20)
    assert incomplete.results["H6"]["status"] == "not_run" and incomplete.family == {}
