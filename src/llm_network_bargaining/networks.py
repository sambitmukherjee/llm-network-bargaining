"""Canonical networks, in the order used by the study's prediction tables."""

from dataclasses import dataclass
from typing import Literal

import networkx as nx


@dataclass(frozen=True)
class Network:
    """An immutable, connected, undirected network with canonical node labels.

    Node order is preserved. Edges are sorted, including their endpoints, so
    equivalent input edge orders give the same representation. ``graph()``
    returns a fresh graph that callers may safely change.
    """

    id: str
    kind: Literal["exchange", "broker"]
    nodes: tuple[str, ...]
    edges: tuple[tuple[str, str], ...]
    pie: int = 24
    tags: frozenset[str] = frozenset()
    description: str = ""
    producers: tuple[str, str] | None = None

    def __post_init__(self) -> None:
        if not self.nodes or len(set(self.nodes)) != len(self.nodes):
            raise ValueError("Network nodes must be non-empty and unique.")
        if self.kind not in ("exchange", "broker"):
            raise ValueError("Network kind must be 'exchange' or 'broker'.")
        if self.pie < 1:
            raise ValueError("The pie must be positive.")
        edges = tuple(sorted(tuple(sorted(edge)) for edge in self.edges))
        if len(set(edges)) != len(edges):
            raise ValueError("Network edges must be unique.")
        for a, b in edges:
            if a == b or a not in self.nodes or b not in self.nodes:
                raise ValueError("Every edge must join two distinct network nodes.")
        object.__setattr__(self, "edges", edges)
        if self.kind == "broker":
            if (self.producers is None or len(set(self.producers)) != 2
                    or not set(self.producers).issubset(self.nodes)):
                raise ValueError("Broker networks need two distinct producers.")
        elif self.producers is not None:
            raise ValueError("Only broker networks have producers.")
        if not nx.is_connected(self.graph()):
            raise ValueError("Every network must be connected.")

    def graph(self) -> nx.Graph:
        """Return a fresh NetworkX graph with pie-sized edge weights."""
        graph = nx.Graph()
        graph.add_nodes_from(self.nodes)
        graph.add_weighted_edges_from((a, b, self.pie) for a, b in self.edges)
        return graph

    def neighbours(self, node: str) -> tuple[str, ...]:
        """Return sorted neighbours; raise KeyError for an unknown node."""
        if node not in self.nodes:
            raise KeyError(f"Unknown node {node!r} in network {self.id!r}.")
        return tuple(sorted(self.graph().neighbors(node)))

    @property
    def n_links(self) -> int:
        """Return the number of undirected links."""
        return len(self.edges)


def _path(size: int) -> Network:
    nodes = tuple("ABCDEFG"[:size])
    identifier = "pair" if size == 2 else f"line{size}"
    tags = {"parity"}
    if size <= 5:
        tags.add("core")
    if size == 3:
        tags.add("dose")
    return Network(identifier, "exchange", nodes, tuple(zip(nodes, nodes[1:])),
                   tags=frozenset(tags), description=f"Path with {size} nodes.")


def _star(leaves: int) -> Network:
    nodes = ("H",) + tuple(f"L{i}" for i in range(1, leaves + 1))
    tags = {"dose", "core"} if leaves <= 4 else {"dose"}
    return Network(f"star{leaves}", "exchange", nodes,
                   tuple(("H", leaf) for leaf in nodes[1:]),
                   tags=frozenset(tags), description=f"Hub with {leaves} leaves.")


def _sweep(step: int) -> Network:
    nodes = tuple("ABCDEF") + tuple(f"L{i}" for i in range(1, step + 1))
    ring = (("A", "B"), ("B", "C"), ("C", "D"), ("D", "E"),
            ("E", "F"), ("F", "A"))
    leaves = (("A", "L1"), ("D", "L2"), ("C", "L3"))
    return Network(f"sweep{step}", "exchange", nodes, ring + leaves[:step],
                   tags=frozenset({"sweep"}),
                   description=f"Six-node ring with {step} added leaves.")


def _broker(size: int, parallel: bool) -> Network:
    middle = tuple(f"B{i}" for i in range(1, size + 1))
    nodes = ("A",) + middle + ("C",)
    if parallel:
        edges = tuple(edge for broker in middle
                      for edge in (("A", broker), (broker, "C")))
        layout = "parallel"
    else:
        edges = tuple(zip(nodes, nodes[1:]))
        layout = "serial"
    return Network(f"broker_{layout}_{size}", "broker", nodes, edges,
                   tags=frozenset({"broker"}), producers=("A", "C"),
                   description=f"Two producers with {size} {layout} brokers.")


_NETWORKS = (
    *(_path(size) for size in range(2, 8)),
    *(_star(leaves) for leaves in range(3, 6)),
    Network("stem", "exchange", tuple("ABCD"),
            (("A", "B"), ("B", "C"), ("B", "D"), ("C", "D")),
            tags=frozenset({"core"}), description="A leaf attached to a triangle."),
    Network("triangle", "exchange", tuple("ABC"),
            (("A", "B"), ("B", "C"), ("C", "A")),
            tags=frozenset({"core"}), description="Three mutually linked agents."),
    *(_sweep(step) for step in range(4)),
    Network("no_exclusion_control", "exchange",
            tuple(f"N{i:02d}" for i in range(1, 9)),
            (("N01", "N03"), ("N01", "N04"), ("N01", "N05"),
             ("N01", "N06"), ("N01", "N07"), ("N01", "N08"),
             ("N02", "N03"), ("N02", "N04"), ("N02", "N05"),
             ("N03", "N04"), ("N05", "N08"), ("N06", "N07")),
            tags=frozenset({"control"}),
            description="Varying degree, with a unique core allocation of 12 each."),
    *(_broker(size, parallel=True) for size in range(1, 5)),
    *(_broker(size, parallel=False) for size in range(2, 4)),
)
_BY_ID = {network.id: network for network in _NETWORKS}


def get_network(id: str) -> Network:
    """Look up a network by its canonical ID; raise KeyError if unknown."""
    try:
        return _BY_ID[id]
    except KeyError:
        raise KeyError(f"Unknown network ID: {id!r}.") from None


def list_networks(tag: str | None = None) -> tuple[Network, ...]:
    """Return networks in registry order, optionally keeping one tag."""
    return tuple(net for net in _NETWORKS if tag is None or tag in net.tags)
