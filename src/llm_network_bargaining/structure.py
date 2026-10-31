"""Graph structure used by both theory tables and experiment conditions."""

from functools import cache

import networkx as nx
from networkx.algorithms.isomorphism import GraphMatcher

from .networks import Network


@cache
def node_classes(net: Network) -> tuple[tuple[str, ...], ...]:
    """Return sorted automorphism orbits, preserving the broker producer set."""
    graph = net.graph()
    producers = set(net.producers or ())
    nx.set_node_attributes(graph, {node: node in producers for node in net.nodes},
                           "producer")
    matcher = GraphMatcher(graph, graph,
                           node_match=lambda a, b: a["producer"] == b["producer"])
    # Union the nodes related by any graph-preserving relabelling.
    groups = {node: {node} for node in net.nodes}
    for mapping in matcher.isomorphisms_iter():
        for node, image in mapping.items():
            merged = groups[node] | groups[image]
            for member in merged:
                groups[member] = merged
    classes = {tuple(sorted(group)) for group in groups.values()}
    return tuple(sorted(classes, key=lambda members: members[0]))


def class_label(members: tuple[str, ...]) -> str:
    """Join the members of a node class with vertical bars."""
    return "|".join(members)


def class_of(net: Network) -> dict[str, str]:
    """Map every node to its deterministic node-class label."""
    labels = {node: class_label(members)
              for members in node_classes(net) for node in members}
    return {node: labels[node] for node in net.nodes}


def max_deals(net: Network) -> int:
    """Return maximum matching size for exchange, or one deal for brokers."""
    if net.kind == "broker":
        return 1
    return len(nx.max_weight_matching(net.graph(), maxcardinality=True))


def excludable_nodes(net: Network) -> frozenset[str]:
    """Return nodes omitted by some maximum matching (exchange networks only)."""
    if net.kind != "exchange":
        raise ValueError("Excludable nodes are defined only for exchange networks.")
    graph = net.graph()
    maximum = max_deals(net)
    excluded = set()
    for node in net.nodes:
        remaining = graph.subgraph([other for other in net.nodes if other != node])
        if len(nx.max_weight_matching(remaining, maxcardinality=True)) == maximum:
            excluded.add(node)
    return frozenset(excluded)


def degree(net: Network) -> dict[str, int]:
    """Return each node's number of links, in node order."""
    return dict(net.graph().degree())


def betweenness(net: Network) -> dict[str, float]:
    """Return NetworkX's normalised, unweighted betweenness centrality."""
    return nx.betweenness_centrality(net.graph(), normalized=True, weight=None)
