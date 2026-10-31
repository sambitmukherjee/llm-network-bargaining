"""Independent numerical references from the Phase 1 brief (not generated)."""

from math import fsum

import pytest

from llm_network_bargaining.networks import Network, get_network, list_networks
from llm_network_bargaining.structure import max_deals, node_classes
from llm_network_bargaining.theory import (
    balanced_outcome, characteristic_function, core_bounds, in_core,
    myerson_value, nucleolus, position_value, shapley_value,
)

# Each row is: nodes sharing a reference, Myerson, position, core interval, balanced.
# Fractions stay as fractions in the source so the reference precision is explicit.
REFERENCES = {
    "pair": [("A B", 12, 12, (0, 24), 12)],
    "line3": [("A C", 4, 6, (0, 0), 0), ("B", 16, 12, (24, 24), 24)],
    "line4": [("A D", 10, 10, (0, 24), 8), ("B C", 14, 14, (0, 24), 16)],
    "line5": [("A E", 26/5, 7, (0, 0), 0), ("B D", 76/5, 12, (24, 24), 24),
              ("C", 36/5, 10, (0, 0), 0)],
    "line6": [("A F", 46/5, 47/5, (0, 24), 6), ("B E", 72/5, 69/5, (0, 24), 18),
              ("C D", 62/5, 64/5, (0, 24), 12)],
    "line7": [("A G", 202/35, 37/5, (0, 0), 0), ("B F", 524/35, 61/5, (24, 24), 24),
              ("C E", 286/35, 53/5, (0, 0), 0), ("D", 496/35, 58/5, (24, 24), 24)],
    "star3": [("H", 18, 12, (24, 24), 24), ("L1 L2 L3", 2, 4, (0, 0), 0)],
    "star4": [("H", 96/5, 12, (24, 24), 24), ("L1 L2 L3 L4", 6/5, 3, (0, 0), 0)],
    "star5": [("H", 20, 12, (24, 24), 24), ("L1 L2 L3 L4 L5", 4/5, 12/5, (0, 0), 0)],
    "stem": [("A", 8, 9, (0, 12), 6), ("B", 16, 15, (12, 24), 18),
             ("C D", 12, 12, (0, 24), 12)],
    "triangle": [("A B C", 8, 8, None, None)],
    "sweep0": [("A B C D E F", 12, 12, (0, 24), 12)],
    "sweep1": [("A", 578/35, 442/35, (24, 24), 24), ("B F", 256/35, 353/35, (0, 0), 0),
               ("C E", 494/35, 409/35, (24, 24), 24), ("D", 284/35, 374/35, (0, 0), 0),
               ("L1", 158/35, 36/7, (0, 0), 0)],
    "sweep2": [("A D", 557/35, 1039/70, (0, 24), 18),
               ("B C E F", 85/7, 89/7, (0, 24), 12), ("L1 L2", 39/5, 541/70, (0, 24), 6)],
    "sweep3": [("A", 84/5, 13, (24, 24), 24), ("B", 41/7, 306/35, (0, 0), 0),
               ("C", 82/5, 459/35, (24, 24), 24), ("D", 76/5, 536/35, (0, 24), 16),
               ("E", 451/35, 456/35, (0, 24), 16), ("F", 409/35, 442/35, (0, 24), 8),
               ("L1", 27/7, 191/35, (0, 0), 0), ("L2", 317/35, 62/7, (0, 24), 8),
               ("L3", 149/35, 41/7, (0, 0), 0)],
    "no_exclusion_control": [
        ("N01", 120/7, 2422/165, (12, 12), 12),
        ("N02", 412/35, 13672/1155, (12, 12), 12),
        ("N03 N04", 384/35, 12659/1155, (12, 12), 12),
        ("N05", 466/35, 29677/2310, (12, 12), 12),
        ("N06 N07", 56/5, 412/33, (12, 12), 12),
        ("N08", 66/7, 1501/154, (12, 12), 12),
    ],
    "broker_parallel_1": [("A C", 8, 6, (0, 24), None), ("B1", 8, 12, (0, 24), None)],
    "broker_parallel_2": [("A C", 10, 6, (0, 24), None), ("B1 B2", 2, 6, (0, 0), None)],
    "broker_parallel_3": [("A C", 54/5, 6, (0, 24), None), ("B1 B2 B3", 4/5, 4, (0, 0), None)],
    "broker_parallel_4": [("A C", 56/5, 6, (0, 24), None), ("B1 B2 B3 B4", 2/5, 3, (0, 0), None)],
    "broker_serial_2": [("A C", 6, 4, (0, 24), None), ("B1 B2", 6, 8, (0, 24), None)],
    "broker_serial_3": [("A C", 24/5, 3, (0, 24), None), ("B1 B2 B3", 24/5, 6, (0, 24), None)],
}


@pytest.mark.parametrize("identifier", REFERENCES)
def test_reference_values(identifier: str) -> None:
    """All registered network allocations match the supplied reference numbers."""
    net = get_network(identifier)
    myerson = myerson_value(net)
    position = position_value(net)
    core = core_bounds(net)
    balanced = balanced_outcome(net) if net.kind == "exchange" else None
    assert position.method == "exact"
    assert position.n_samples is None and position.seed is None
    covered = set()
    for nodes, expected_myerson, expected_position, expected_core, expected_balanced in REFERENCES[identifier]:
        for node in nodes.split():
            covered.add(node)
            assert myerson[node] == pytest.approx(expected_myerson, abs=1e-6)
            assert position.values[node] == pytest.approx(expected_position, abs=1e-6)
            if expected_core is None:
                assert core is None
            else:
                assert core is not None
                assert core[node] == pytest.approx(expected_core, abs=1e-6)
            if expected_balanced is None:
                assert balanced is None
            else:
                assert balanced is not None
                assert balanced[node] == pytest.approx(expected_balanced, abs=1e-6)
    assert covered == set(net.nodes)


@pytest.mark.parametrize("net", list_networks(), ids=lambda net: net.id)
def test_efficiency_symmetry_and_core(net: Network) -> None:
    """Allocations conserve value, respect symmetry, and satisfy core constraints."""
    worth = characteristic_function(net)
    total = 24 * max_deals(net)
    assert worth[frozenset()] == 0
    assert worth[frozenset(net.nodes)] == total
    assert characteristic_function(net) is worth
    for values in (myerson_value(net), position_value(net).values):
        assert fsum(values.values()) == pytest.approx(total, abs=1e-6)
        for members in node_classes(net):
            assert all(abs(values[node] - values[members[0]]) < 1e-9 for node in members)
    if net.kind == "exchange":
        balanced = balanced_outcome(net)
        if balanced is not None:
            assert in_core(net, balanced)


def test_characteristic_functions_and_generic_shapley() -> None:
    """Coalitions use induced graphs, and the shared Shapley helper is reusable."""
    line = characteristic_function(get_network("line3"))
    assert line[frozenset({"A", "C"})] == 0
    assert line[frozenset({"A", "B"})] == 24
    broker = characteristic_function(get_network("broker_parallel_2"))
    assert broker[frozenset({"A", "C"})] == 0
    assert broker[frozenset({"A", "B2", "C"})] == 24
    assert broker[frozenset({"A", "B1", "B2"})] == 0
    assert shapley_value(("x", "y"), lambda mask: 10.0 if mask == 3 else 0.0) == {"x": 5, "y": 5}
    with pytest.raises(TypeError):
        line[frozenset()] = 1  # type: ignore[index]


def test_empty_core_and_broker_restrictions() -> None:
    """A nucleolus can exist when a balanced outcome is undefined."""
    triangle = get_network("triangle")
    assert nucleolus(triangle) == {"A": 8, "B": 8, "C": 8}
    assert core_bounds(triangle) is None
    assert balanced_outcome(triangle) is None
    assert not in_core(triangle, {"A": 8, "B": 8, "C": 8})
    broker = get_network("broker_parallel_1")
    for function in (nucleolus, balanced_outcome):
        with pytest.raises(ValueError, match="exchange"):
            function(broker)


def test_control_membership_and_invalid_allocations() -> None:
    """The control's equal allocation is in its core; its Myerson value is not."""
    net = get_network("no_exclusion_control")
    assert in_core(net, {node: 12 for node in net.nodes})
    assert not in_core(net, myerson_value(net))
    assert not in_core(net, {})
    assert not in_core(net, {node: float("nan") for node in net.nodes})
    assert not in_core(net, {node: float("inf") for node in net.nodes})


def test_sampling_agrees_with_exact() -> None:
    """Both sampling paths approximate exact allocations and repeat identically."""
    line = get_network("line5")
    sampled = myerson_value(line, method="sample", n_samples=20_000, seed=1)
    assert sampled == myerson_value(line, method="sample", n_samples=20_000, seed=1)
    assert sampled == pytest.approx(myerson_value(line), abs=0.25)
    stem = get_network("stem")
    sampled_position = position_value(stem, method="sample", n_samples=20_000, seed=0)
    assert sampled_position.values == pytest.approx(position_value(stem, method="exact").values, abs=0.25)
    assert sampled_position.method == "sample"
    assert sampled_position.n_samples == 20_000
    assert sampled_position.seed == 0


def test_complete_seven_uses_link_sampling() -> None:
    """Seven nodes fit exact player enumeration, but their 21 links use sampling."""
    nodes = tuple(str(i) for i in range(7))
    net = Network("complete7", "exchange", nodes,
                  tuple((a, b) for i, a in enumerate(nodes) for b in nodes[i + 1:]))
    sampled = position_value(net, n_samples=4_000, seed=0)
    assert sampled.method == "sample"
    assert fsum(sampled.values.values()) == pytest.approx(72, abs=1e-6)
    assert all(abs(value - 72/7) <= 1 for value in sampled.values.values())
    assert sampled == position_value(net, n_samples=4_000, seed=0)
    assert myerson_value(net) == pytest.approx({node: 72/7 for node in nodes}, abs=1e-6)


def _ring(size: int) -> Network:
    nodes = tuple(f"N{i:02d}" for i in range(size))
    return Network(f"ring{size}", "exchange", nodes,
                   tuple((nodes[i], nodes[(i + 1) % size]) for i in range(size)))


def test_nucleolus_size_limit() -> None:
    """Large exchange networks skip nucleolus computation before building LPs."""
    assert nucleolus(_ring(12)) is None


@pytest.mark.slow
def test_exact_sixteen_node_ring() -> None:
    """The exact threshold handles all 65,536 coalitions and gives 12 each."""
    net = _ring(16)
    assert myerson_value(net, method="exact") == pytest.approx(
        {node: 12 for node in net.nodes}, abs=1e-6)


def test_player_auto_sampling_above_threshold() -> None:
    """Auto player sampling is deterministic on a 17-node graph."""
    net = _ring(17)
    sampled = myerson_value(net, n_samples=100, seed=7)
    assert sampled == myerson_value(net, method="sample", n_samples=100, seed=7)
    assert fsum(sampled.values()) == pytest.approx(192, abs=1e-6)
