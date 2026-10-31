"""Cooperative-game benchmarks, using exact enumeration or seeded sampling.

Small subsets are represented by integer masks: bit i says whether the i-th
node (or link) is present. This avoids constructing a NetworkX graph for every
coalition. All reported allocations are in points per round.
"""

from collections.abc import Callable, Hashable, Mapping, Sequence
from dataclasses import dataclass
from functools import cache, lru_cache
from math import comb, fsum, isfinite
from types import MappingProxyType
from typing import Literal, TypeVar

import numpy as np
from scipy.optimize import linprog

from .networks import Network
from .seeds import make_rng

MYERSON_EXACT_MAX_NODES = 16
POSITION_EXACT_MAX_LINKS = 16
MYERSON_SAMPLES = 20_000
POSITION_SAMPLES = 4_000
DEFAULT_SEED = 0
NUCLEOLUS_MAX_NODES = 10

Method = Literal["auto", "exact", "sample"]
Player = TypeVar("Player", bound=Hashable)


@dataclass(frozen=True)
class PositionValueResult:
    """Node allocations and the method used to estimate link contributions."""

    values: dict[str, float]
    method: Literal["exact", "sample"]
    n_samples: int | None
    seed: int | None


def _method(method: Method, size: int, exact_limit: int) -> Literal["exact", "sample"]:
    if method not in ("auto", "exact", "sample"):
        raise ValueError("Method must be 'auto', 'exact', or 'sample'.")
    if method == "auto":
        return "exact" if size <= exact_limit else "sample"
    return method


def _clean(value: float) -> float:
    return 0.0 if abs(value) < 1e-10 else float(value)


def _matching_size(adjacency: tuple[int, ...], available: int) -> int:
    """Either leave the first node unmatched, or match it to a neighbour."""
    @cache
    def solve(mask: int) -> int:
        if not mask:
            return 0
        first_bit = mask & -mask
        first = first_bit.bit_length() - 1
        rest = mask ^ first_bit
        best = solve(rest)
        neighbours = adjacency[first] & rest
        while neighbours:
            partner = neighbours & -neighbours
            best = max(best, 1 + solve(rest ^ partner))
            neighbours ^= partner
        return best

    return solve(available)


@cache
def _adjacency(net: Network) -> tuple[int, ...]:
    indices = {node: i for i, node in enumerate(net.nodes)}
    neighbours = [0] * len(net.nodes)
    for a, b in net.edges:
        i, j = indices[a], indices[b]
        neighbours[i] |= 1 << j
        neighbours[j] |= 1 << i
    return tuple(neighbours)


def _connected(adjacency: tuple[int, ...], available: int, start: int, end: int) -> bool:
    if not (available & (1 << start) and available & (1 << end)):
        return False
    reached = 0
    frontier = 1 << start
    while frontier:
        bit = frontier & -frontier
        frontier ^= bit
        reached |= bit
        frontier |= adjacency[bit.bit_length() - 1] & available & ~reached
    return bool(reached & (1 << end))


@lru_cache(maxsize=128)
def _player_game(net: Network) -> Callable[[int], float]:
    adjacency = _adjacency(net)

    @cache
    def value(mask: int) -> float:
        if net.kind == "broker":
            assert net.producers is not None
            start, end = (net.nodes.index(node) for node in net.producers)
            return float(net.pie * _connected(adjacency, mask, start, end))
        if not mask:
            return 0.0
        # Reuse values of smaller coalitions across all matching calculations.
        bit = mask & -mask
        first = bit.bit_length() - 1
        rest = mask ^ bit
        best = value(rest)
        neighbours = adjacency[first] & rest
        while neighbours:
            partner = neighbours & -neighbours
            best = max(best, net.pie + value(rest ^ partner))
            neighbours ^= partner
        return best

    return value


@lru_cache(maxsize=128)
def _link_game(net: Network) -> Callable[[int], float]:
    indices = {node: i for i, node in enumerate(net.nodes)}
    edges = tuple((indices[a], indices[b]) for a, b in net.edges)
    all_nodes = (1 << len(net.nodes)) - 1

    @lru_cache(maxsize=100_000)
    def value(mask: int) -> float:
        adjacency = [0] * len(net.nodes)
        while mask:
            bit = mask & -mask
            a, b = edges[bit.bit_length() - 1]
            adjacency[a] |= 1 << b
            adjacency[b] |= 1 << a
            mask ^= bit
        if net.kind == "broker":
            assert net.producers is not None
            start, end = (indices[node] for node in net.producers)
            return float(net.pie * _connected(tuple(adjacency), all_nodes, start, end))
        return float(net.pie * _matching_size(tuple(adjacency), all_nodes))

    return value


@lru_cache(maxsize=128)
def characteristic_function(net: Network) -> Mapping[frozenset[str], float]:
    """Return a memoised, read-only table of all coalitional values, including ∅."""
    value = _player_game(net)
    return MappingProxyType({
        frozenset(node for i, node in enumerate(net.nodes) if mask & (1 << i)): value(mask)
        for mask in range(1 << len(net.nodes))
    })


def shapley_value(
    players: Sequence[Player],
    value: Callable[[int], float],
    method: Literal["exact", "sample"] = "exact",
    n_samples: int = MYERSON_SAMPLES,
    seed: int = DEFAULT_SEED,
) -> dict[Player, float]:
    """Compute Shapley values for nodes, links, or any ordered, unique players.

    ``value(mask)`` evaluates a subset whose bit i refers to ``players[i]``.
    Exact computation weights every marginal contribution by coalition size;
    sampling averages contributions over seeded random arrival orders.
    """
    size = len(players)
    if not size or len(set(players)) != size:
        raise ValueError("Shapley players must be non-empty and unique.")
    if method not in ("exact", "sample"):
        raise ValueError("Shapley method must be 'exact' or 'sample'.")
    if method == "sample":
        if n_samples < 1:
            raise ValueError("n_samples must be at least 1.")
        totals = [0.0] * size
        rng = make_rng(seed)
        for _ in range(n_samples):
            mask = 0
            previous = value(mask)
            for index in rng.permutation(size):
                index = int(index)
                mask |= 1 << index
                current = value(mask)
                totals[index] += current - previous
                previous = current
        return {player: _clean(totals[i] / n_samples)
                for i, player in enumerate(players)}
    weights = [1 / (size * comb(size - 1, count)) for count in range(size)]
    full = (1 << size) - 1
    result = {}
    for i, player in enumerate(players):
        bit = 1 << i
        result[player] = _clean(fsum(
            weights[mask.bit_count()] * (value(mask | bit) - value(mask))
            for mask in range(full + 1) if not mask & bit
        ))
    return result


def myerson_value(net: Network, method: Method = "auto",
                  n_samples: int = MYERSON_SAMPLES,
                  seed: int = DEFAULT_SEED) -> dict[str, float]:
    """Return node Shapley values; auto is exact through 16 nodes."""
    selected = _method(method, len(net.nodes), MYERSON_EXACT_MAX_NODES)
    return shapley_value(net.nodes, _player_game(net), selected, n_samples, seed)


def position_value(net: Network, method: Method = "auto",
                   n_samples: int = POSITION_SAMPLES,
                   seed: int = DEFAULT_SEED) -> PositionValueResult:
    """Split each link's Shapley value between its endpoints; exact through 16 links."""
    selected = _method(method, net.n_links, POSITION_EXACT_MAX_LINKS)
    links = shapley_value(net.edges, _link_game(net), selected, n_samples, seed)
    values = {node: 0.0 for node in net.nodes}
    for (a, b), contribution in links.items():
        values[a] += contribution / 2
        values[b] += contribution / 2
    return PositionValueResult(values, selected,
                               n_samples if selected == "sample" else None,
                               seed if selected == "sample" else None)


def _coalition_rows(net: Network) -> tuple[np.ndarray, np.ndarray, float]:
    size = len(net.nodes)
    full = (1 << size) - 1
    value = _player_game(net)
    rows = np.array([[float(bool(mask & (1 << i))) for i in range(size)]
                     for mask in range(1, full)]).reshape((-1, size))
    worth = np.array([value(mask) for mask in range(1, full)])
    return rows, worth, value(full)


@lru_cache(maxsize=128)
def _core_intervals(net: Network) -> tuple[tuple[float, float], ...] | None:
    rows, worth, total = _coalition_rows(net)
    size = len(net.nodes)
    intervals = []
    for i in range(size):
        objective = np.zeros(size)
        objective[i] = 1
        arguments = dict(A_ub=-rows, b_ub=-worth,
                         A_eq=np.ones((1, size)), b_eq=[total],
                         bounds=[(None, None)] * size, method="highs")
        lower = linprog(objective, **arguments)
        if lower.status == 2:
            return None
        if not lower.success:
            raise RuntimeError(f"Core minimisation failed: {lower.message}")
        upper = linprog(-objective, **arguments)
        if not upper.success:
            raise RuntimeError(f"Core maximisation failed: {upper.message}")
        intervals.append((_clean(lower.fun), _clean(-upper.fun)))
    return tuple(intervals)


def core_bounds(net: Network) -> dict[str, tuple[float, float]] | None:
    """Find each node's minimum and maximum core payoff; return None if empty."""
    intervals = _core_intervals(net)
    return None if intervals is None else dict(zip(net.nodes, intervals))


def in_core(net: Network, allocation: Mapping[str, float], tol: float = 1e-9) -> bool:
    """Check efficiency and every coalitional constraint of an allocation."""
    if tol < 0:
        raise ValueError("The tolerance must be non-negative.")
    if set(allocation) != set(net.nodes):
        return False
    points = np.array([allocation[node] for node in net.nodes], dtype=float)
    if not all(isfinite(point) for point in points):
        return False
    rows, worth, total = _coalition_rows(net)
    return bool(abs(fsum(points) - total) <= tol
                and np.all(rows @ points >= worth - tol))


@lru_cache(maxsize=128)
def _nucleolus_values(net: Network) -> tuple[float, ...]:
    rows, worth, total = _coalition_rows(net)
    size = len(net.nodes)
    if size == 1:
        return (total,)
    active = list(range(len(rows)))
    fixed_rows = [np.ones(size)]
    fixed_values = [total]
    # At each stage maximise the smallest remaining coalitional surplus.
    # Then fix only coalitions tight in EVERY optimum of that stage.
    for _ in range(len(rows)):
        current_rows = rows[active]
        current_worth = worth[active]
        equality_rows = np.array(fixed_rows)
        equality_values = np.array(fixed_values)
        objective = np.zeros(size + 1)
        objective[-1] = -1
        result = linprog(
            objective,
            A_ub=np.column_stack((-current_rows, np.ones(len(active)))),
            b_ub=-current_worth,
            A_eq=np.column_stack((equality_rows, np.zeros(len(fixed_rows)))),
            b_eq=equality_values, bounds=[(None, None)] * (size + 1), method="highs",
        )
        if not result.success:
            raise RuntimeError(f"Nucleolus optimisation failed: {result.message}")
        points, level = result.x[:size], result.x[-1]
        newly_fixed = []
        for index in active:
            # A coalition slack at this optimum cannot be tight at every optimum.
            if rows[index] @ points - worth[index] > level + 1e-7:
                continue
            check = linprog(-rows[index], A_ub=-current_rows,
                            b_ub=-(current_worth + level),
                            A_eq=equality_rows, b_eq=equality_values,
                            bounds=[(None, None)] * size, method="highs")
            if not check.success:
                raise RuntimeError(f"Nucleolus tightness check failed: {check.message}")
            if -check.fun - worth[index] <= level + 1e-7:
                newly_fixed.append(index)
        if not newly_fixed:
            raise RuntimeError("Nucleolus optimisation made no progress.")
        for index in newly_fixed:
            # Keep an independent set of equalities to make the LPs smaller.
            candidate = np.vstack((fixed_rows, rows[index]))
            if np.linalg.matrix_rank(candidate) > len(fixed_rows):
                fixed_rows.append(rows[index])
                fixed_values.append(float(worth[index] + level))
        if len(fixed_rows) == size:
            points = np.linalg.solve(np.array(fixed_rows), np.array(fixed_values))
            return tuple(_clean(point) for point in points)
        newly_fixed_set = set(newly_fixed)
        active = [index for index in active if index not in newly_fixed_set]
    raise RuntimeError("Nucleolus optimisation did not determine a unique allocation.")


def nucleolus(net: Network, max_nodes: int = NUCLEOLUS_MAX_NODES) -> dict[str, float] | None:
    """Return the exchange-game nucleolus, or None above the node limit.

    This allocation also exists when the core is empty. Broker games are
    deliberately excluded from this interface.
    """
    if net.kind != "exchange":
        raise ValueError("The nucleolus interface supports exchange networks only.")
    if len(net.nodes) > max_nodes:
        return None
    return dict(zip(net.nodes, _nucleolus_values(net)))


def balanced_outcome(net: Network) -> dict[str, float] | None:
    """Return the exchange-game nucleolus when the core exists and size permits."""
    if net.kind != "exchange":
        raise ValueError("Balanced outcomes are defined for exchange networks only.")
    if core_bounds(net) is None:
        return None
    return nucleolus(net)
