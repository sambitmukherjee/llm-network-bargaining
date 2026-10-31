"""Check the registry and structural references independently of game theory."""

from dataclasses import FrozenInstanceError
import hashlib
from pathlib import Path

import networkx as nx
import pytest

from llm_network_bargaining.networks import get_network, list_networks
from llm_network_bargaining.structure import (
    betweenness, class_label, class_of, degree, excludable_nodes, max_deals, node_classes,
)

EXPECTED_CLASSES = {
    "pair": "A|B", "line3": "A|C;B", "line4": "A|D;B|C",
    "line5": "A|E;B|D;C", "line6": "A|F;B|E;C|D", "line7": "A|G;B|F;C|E;D",
    "star3": "H;L1|L2|L3", "star4": "H;L1|L2|L3|L4", "star5": "H;L1|L2|L3|L4|L5",
    "stem": "A;B;C|D", "triangle": "A|B|C", "sweep0": "A|B|C|D|E|F",
    "sweep1": "A;B|F;C|E;D;L1", "sweep2": "A|D;B|C|E|F;L1|L2",
    "sweep3": "A;B;C;D;E;F;L1;L2;L3",
    "no_exclusion_control": "N01;N02;N03|N04;N05;N06|N07;N08",
    "broker_parallel_1": "A|C;B1", "broker_parallel_2": "A|C;B1|B2",
    "broker_parallel_3": "A|C;B1|B2|B3", "broker_parallel_4": "A|C;B1|B2|B3|B4",
    "broker_serial_2": "A|C;B1|B2", "broker_serial_3": "A|C;B1|B3;B2",
}
CORE_IDS = ("pair", "line3", "line4", "line5", "star3", "star4", "stem", "triangle")
EXCLUDED = {
    "pair": "", "line3": "A C", "line4": "", "line5": "A C E", "line6": "",
    "line7": "A C E G", "star3": "L1 L2 L3", "star4": "L1 L2 L3 L4",
    "star5": "L1 L2 L3 L4 L5", "stem": "", "triangle": "A B C", "sweep0": "",
    "sweep1": "B D F L1", "sweep2": "", "sweep3": "B L1 L3", "no_exclusion_control": "",
}
DEALS = {
    "pair": 1, "line3": 1, "line4": 2, "line5": 2, "line6": 3, "line7": 3,
    "star3": 1, "star4": 1, "star5": 1, "stem": 2, "triangle": 1,
    "sweep0": 3, "sweep1": 3, "sweep2": 4, "sweep3": 4, "no_exclusion_control": 4,
}


def test_registry() -> None:
    """Registry order, tags, canonical edges, and connectedness are fixed."""
    assert tuple(net.id for net in list_networks()) == tuple(EXPECTED_CLASSES)
    assert tuple(net.id for net in list_networks("core")) == CORE_IDS
    for net in list_networks():
        assert nx.is_connected(net.graph())
        assert all(a < b for a, b in net.edges)
        assert net.n_links == len(net.edges)
        if net.kind == "broker":
            assert net.producers == ("A", "C")
        else:
            assert net.producers is None
    assert list_networks("missing") == ()
    with pytest.raises(KeyError, match="Unknown network"):
        get_network("missing")


@pytest.mark.parametrize("identifier", EXPECTED_CLASSES)
def test_node_classes(identifier: str) -> None:
    """Graph automorphisms reproduce every supplied node class."""
    net = get_network(identifier)
    expected = tuple(tuple(label.split("|")) for label in EXPECTED_CLASSES[identifier].split(";"))
    assert node_classes(net) == expected
    assert class_of(net) == {node: class_label(group) for group in expected for node in group}
    assert max_deals(net) == DEALS.get(identifier, 1)


@pytest.mark.parametrize("identifier", EXCLUDED)
def test_excludable_nodes(identifier: str) -> None:
    """Maximum-matching exclusion reproduces the supplied D sets."""
    assert excludable_nodes(get_network(identifier)) == frozenset(EXCLUDED[identifier].split())


def test_broker_exclusion_is_undefined() -> None:
    """The exchange-specific exclusion API rejects brokers."""
    with pytest.raises(ValueError, match="exchange"):
        excludable_nodes(get_network("broker_parallel_1"))


def test_control_edges_and_degrees() -> None:
    """The control graph is the specified fixed graph, without regeneration."""
    net = get_network("no_exclusion_control")
    edges = "N01-N03 N01-N04 N01-N05 N01-N06 N01-N07 N01-N08 N02-N03 N02-N04 N02-N05 N03-N04 N05-N08 N06-N07"
    assert net.edges == tuple(sorted(tuple(edge.split("-")) for edge in edges.split()))
    assert degree(net) == dict(zip(net.nodes, (6, 3, 3, 3, 3, 2, 2, 2)))


def test_network_is_immutable_and_graphs_are_independent() -> None:
    """Editing a returned graph must not affect registry data or later graphs."""
    net = get_network("line3")
    with pytest.raises(FrozenInstanceError):
        net.id = "changed"  # type: ignore[misc]
    graph = net.graph()
    graph.remove_edge("A", "B")
    assert net.graph().number_of_edges() == 2
    assert net.neighbours("B") == ("A", "C")
    with pytest.raises(KeyError):
        net.neighbours("missing")
    assert betweenness(net) == {"A": 0.0, "B": 1.0, "C": 0.0}


def test_preexisting_hash() -> None:
    """The original theory script must remain byte-for-byte unchanged."""
    path = Path(__file__).resolve().parents[1] / "preexisting" / "predict.py"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == "71a6d6d81954ef303cdd6f0a345afe9a961b56a17e63ea20d81431ec833bf0ec"
