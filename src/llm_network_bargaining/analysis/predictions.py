"""Class-level point predictions and centrality ranks, computed from theory."""

from functools import cache
from collections.abc import Iterator, Mapping

import numpy as np
import pandas as pd

from ..networks import get_network
from ..structure import betweenness, class_label, degree, max_deals, node_classes
from ..theory import balanced_outcome, core_bounds, myerson_value, position_value

BENCHMARKS = ("equal_split", "myerson", "position_value", "balanced")
PREDICTORS = (*BENCHMARKS, "degree", "betweenness")
PREDICTION_COLUMNS = ["network_id", "node_class", "n_members", *BENCHMARKS,
                      "core_min", "core_max", "degree", "betweenness"]


def _maximum_matchings(nodes: tuple[str, ...], edges: set[frozenset[str]], target: int,
                       chosen: tuple[tuple[str, str], ...] = ()) -> Iterator[tuple[tuple[str, str], ...]]:
    """Enumerate each maximum matching once by deciding the first free node."""
    if len(chosen) == target:
        yield chosen
        return
    if len(nodes) < 2 * (target - len(chosen)):
        return
    first, rest = nodes[0], nodes[1:]
    yield from _maximum_matchings(rest, edges, target, chosen)
    for other in rest:
        if frozenset((first, other)) in edges:
            remaining = tuple(node for node in rest if node != other)
            yield from _maximum_matchings(remaining, edges, target, (*chosen, (first, other)))


@cache
def _prediction_rows(network_id: str) -> tuple[tuple, ...]:
    """Cache immutable numerical rows while callers receive fresh DataFrames."""
    net = get_network(network_id)
    if net.kind != "exchange":
        raise ValueError("Phase 6 analysis supports exchange networks only.")
    counts = dict.fromkeys(net.nodes, 0)
    n_matchings = 0
    for matching in _maximum_matchings(net.nodes, {frozenset(edge) for edge in net.edges}, max_deals(net)):
        n_matchings += 1
        for edge in matching:
            for node in edge:
                counts[node] += 1
    fair = {node: net.pie / 2 * count / n_matchings for node, count in counts.items()}
    myerson, position = myerson_value(net), position_value(net).values
    balanced, core = balanced_outcome(net), core_bounds(net)
    degrees, centrality = degree(net), betweenness(net)
    rows = []
    for members in node_classes(net):
        def mean(mapping: Mapping[str, float] | None) -> float:
            """Average the prediction over this orbit's members."""
            return float(np.mean([mapping[node] for node in members])) if mapping is not None else np.nan
        rows.append((network_id, class_label(members), len(members), mean(fair), mean(myerson),
                     mean(position), mean(balanced),
                     float(np.mean([core[node][0] for node in members])) if core else np.nan,
                     float(np.mean([core[node][1] for node in members])) if core else np.nan,
                     mean(degrees), mean(centrality)))
    return tuple(rows)


def class_predictions(network_id: str) -> pd.DataFrame:
    """Return an independent table; centrality columns are scores, not points."""
    return pd.DataFrame(_prediction_rows(network_id), columns=PREDICTION_COLUMNS)


def advantaged_class(network_id: str) -> dict | None:
    """Return the class with the highest balanced value strictly above 12."""
    table = class_predictions(network_id).dropna(subset=["balanced"])
    table = table[table.balanced > 12 + 1e-9]
    if table.empty:
        return None
    return table.sort_values(["balanced", "node_class"], ascending=[False, True]).iloc[0].to_dict()
