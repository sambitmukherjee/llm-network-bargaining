"""Episode-level randomisation tests and percentile bootstrap intervals.

Exact tests count assignments of the observations, including repeated values.
Monte Carlo tests add one to both the exceedance count and the sample count.
Small NumPy batches keep the larger permutation tests quick without hiding the
statistic behind a statistical testing framework.
"""

from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass
from itertools import combinations
from math import comb, factorial
from typing import Any

import numpy as np

from ..seeds import derive_seed, make_rng


@dataclass(frozen=True)
class TestResult:
    """A test statistic, its tail probability and the number of assignments."""

    statistic: float
    p_value: float
    method: str
    n_resamples: int
    alternative: str
    n: int
    n_a: int | None = None
    n_b: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return ordinary Python values, suitable for a JSON report."""
        return asdict(self)


def _values(values: Sequence[float]) -> np.ndarray:
    """Drop missing observations and reject infinite or multidimensional data."""
    result = np.asarray(values, dtype=float)
    if result.ndim != 1:
        raise ValueError("Expected a one-dimensional sequence.")
    result = result[~np.isnan(result)]
    if not np.isfinite(result).all():
        raise ValueError("Values must be finite, apart from missing NaNs.")
    return result


def _tail(samples: np.ndarray, observed: float, alternative: str) -> int:
    """Count assignments at least as extreme as the observed statistic."""
    if alternative == "greater":
        return int(np.count_nonzero(samples >= observed - 1e-12))
    if alternative == "less":
        return int(np.count_nonzero(samples <= observed + 1e-12))
    if alternative == "two-sided":
        return int(np.count_nonzero(np.abs(samples) >= abs(observed) - 1e-12))
    raise ValueError(f"Unknown alternative: {alternative!r}.")


def _check(alternative: str, n_mc: int) -> None:
    """Validate the shared test options before enumeration begins."""
    _tail(np.array([]), 0, alternative)
    if n_mc < 1:
        raise ValueError("n_mc must be positive.")


def _result(observed: float, count: int, total: int, exact: bool,
            alternative: str, n: int, n_a: int | None = None,
            n_b: int | None = None) -> TestResult:
    """Use the exact fraction or the Monte Carlo plus-one correction."""
    p = count / total if exact else (count + 1) / (total + 1)
    return TestResult(float(observed), p, "exact" if exact else "monte_carlo",
                      total, alternative, n, n_a, n_b)


def sign_flip_test(x: Sequence[float], null: float = 0.0,
                   alternative: str = "greater", exact_max_n: int = 20,
                   n_mc: int = 200_000, seed: int = 1) -> TestResult:
    """Test a mean against null by assigning signs to absolute deviations."""
    _check(alternative, n_mc)
    d = _values(x) - null
    if not len(d):
        raise ValueError("A sign-flip test needs at least one non-missing value.")
    observed = float(d.mean())
    exact = len(d) <= exact_max_n
    total = 2 ** len(d) if exact else n_mc
    rng = make_rng(derive_seed(seed, "sign_flip"))
    count = 0
    for start in range(0, total, 4096):
        size = min(4096, total - start)
        if exact:
            indices = np.arange(start, start + size, dtype=np.uint64)
            signs = 2 * ((indices[:, None] >> np.arange(len(d), dtype=np.uint64)) & 1).astype(float) - 1
        else:
            signs = 2 * rng.integers(0, 2, size=(size, len(d))) - 1
        count += _tail((signs * np.abs(d)).mean(axis=1), observed, alternative)
    return _result(observed, count, total, exact, alternative, len(d))


def _split_statistics(values: np.ndarray, n_b: int) -> np.ndarray:
    """Enumerate distinct index subsets for the second group."""
    n_a = len(values) - n_b
    return np.fromiter((values[list(indices)].sum() for indices in combinations(range(len(values)), n_b)),
                       dtype=float, count=comb(len(values), n_b)) * (1 / n_b + 1 / n_a) - values.sum() / n_a


def permutation_test_two_sample(a: Sequence[float], b: Sequence[float],
                                alternative: str = "greater", exact_max: int = 200_000,
                                n_mc: int = 200_000, seed: int = 1) -> TestResult:
    """Test mean(b) minus mean(a), preserving both group sizes."""
    _check(alternative, n_mc)
    a, b = _values(a), _values(b)
    if not len(a) or not len(b):
        raise ValueError("Both samples need at least one non-missing value.")
    observed = float(b.mean() - a.mean())
    values = np.concatenate([a, b])
    total = comb(len(values), len(b))
    exact = total <= exact_max
    if exact:
        count = _tail(_split_statistics(values, len(b)), observed, alternative)
    else:
        total = n_mc
        rng = make_rng(derive_seed(seed, "two_sample"))
        count = 0
        for start in range(0, total, 2048):
            shuffled = rng.permuted(np.tile(values, (min(2048, total - start), 1)), axis=1)
            samples = shuffled[:, len(a):].mean(axis=1) - shuffled[:, :len(a)].mean(axis=1)
            count += _tail(samples, observed, alternative)
    return _result(observed, count, total, exact, alternative, len(values), len(a), len(b))


def _assignments(indices: tuple[int, ...], sizes: list[int]) -> Iterator[list[tuple[int, ...]]]:
    """Yield all allocations to labelled groups, without within-group orders."""
    if len(sizes) == 1:
        yield [indices]
        return
    for selected in combinations(indices, sizes[0]):
        selected_set = set(selected)
        remaining = tuple(i for i in indices if i not in selected_set)
        for rest in _assignments(remaining, sizes[1:]):
            yield [selected, *rest]


def slope_permutation_test(x: Sequence[float], groups: Sequence[float],
                           alternative: str = "greater", exact_max: int = 200_000,
                           n_mc: int = 200_000, seed: int = 1) -> TestResult:
    """Permute outcomes over fixed numeric labels and test the OLS slope."""
    _check(alternative, n_mc)
    values, labels = np.asarray(x, dtype=float), np.asarray(groups, dtype=float)
    if values.ndim != 1 or values.shape != labels.shape:
        raise ValueError("Values and group labels must be equal-length vectors.")
    keep = ~np.isnan(values) & ~np.isnan(labels)
    values, labels = _values(values[keep]), _values(labels[keep])
    unique, sizes = np.unique(labels, return_counts=True)
    if len(unique) < 2:
        raise ValueError("A slope test needs at least two group labels.")
    if len(unique) == 2:
        test = permutation_test_two_sample(values[labels == unique[0]], values[labels == unique[1]],
                                           alternative, exact_max, n_mc, seed)
        return TestResult(test.statistic / float(unique[1] - unique[0]), test.p_value,
                          test.method, test.n_resamples, alternative, len(values))
    weights = (labels - labels.mean()) / np.square(labels - labels.mean()).sum()
    observed = float(values @ weights)
    total = factorial(len(values))
    for size in sizes:
        total //= factorial(int(size))
    exact = total <= exact_max
    if exact:
        group_weights = (unique - labels.mean()) / np.square(labels - labels.mean()).sum()
        samples = np.fromiter((sum(values[list(group)].sum() * weight
                                   for group, weight in zip(assignment, group_weights))
                               for assignment in _assignments(tuple(range(len(values))), list(sizes))),
                              dtype=float, count=total)
        count = _tail(samples, observed, alternative)
    else:
        total = n_mc
        rng = make_rng(derive_seed(seed, "slope"))
        count = 0
        for start in range(0, total, 2048):
            shuffled = rng.permuted(np.tile(values, (min(2048, total - start), 1)), axis=1)
            count += _tail(shuffled @ weights, observed, alternative)
    return _result(observed, count, total, exact, alternative, len(values))


def stratified_permutation_test(values: Sequence[float], labels: Sequence[str],
                                strata: Sequence[str], n_mc: int = 100_000,
                                seed: int = 1, exact_max: int = 200_000) -> TestResult:
    """Test the equally weighted mean of within-network knowledge differences."""
    _check("two-sided", n_mc)
    values = np.asarray(values, dtype=float)
    labels, strata = np.asarray(labels), np.asarray(strata)
    if values.ndim != 1 or values.shape != labels.shape or values.shape != strata.shape:
        raise ValueError("Values, labels and strata must be equal-length vectors.")
    keep = ~np.isnan(values)
    values, labels, strata = _values(values[keep]), labels[keep], strata[keep]
    if not len(values) or not set(labels).issubset({"full_map", "own_links"}):
        raise ValueError("Use non-empty data with full_map and own_links labels.")
    groups = []
    observed = []
    total = 1
    for stratum in sorted(set(strata)):
        v, lab = values[strata == stratum], labels[strata == stratum]
        n_full = int(np.count_nonzero(lab == "full_map"))
        if n_full == 0 or n_full == len(v):
            raise ValueError(f"Stratum {stratum!r} needs both knowledge settings.")
        groups.append((v, n_full))
        observed.append(v[lab == "full_map"].mean() - v[lab == "own_links"].mean())
        total *= comb(len(v), n_full)
    statistic = float(np.mean(observed))
    exact = total <= exact_max
    if exact:
        samples = np.array([0.0])
        for v, n_full in groups:
            samples = (samples[:, None] + _split_statistics(v, n_full)).ravel()
        count = _tail(samples / len(groups), statistic, "two-sided")
    else:
        total = n_mc
        rng = make_rng(derive_seed(seed, "stratified"))
        count = 0
        for start in range(0, total, 2048):
            size = min(2048, total - start)
            samples = np.zeros(size)
            for v, n_full in groups:
                shuffled = rng.permuted(np.tile(v, (size, 1)), axis=1)
                samples += shuffled[:, :n_full].mean(axis=1) - shuffled[:, n_full:].mean(axis=1)
            count += _tail(samples / len(groups), statistic, "two-sided")
    return _result(statistic, count, total, exact, "two-sided", len(values))


def bootstrap_ci(values: Sequence[float], stat: Callable = np.mean,
                 n_boot: int = 2000, seed: int = 1, level: float = 0.95) -> tuple[float, float]:
    """Return a percentile interval after resampling independent episodes."""
    if n_boot < 1 or not 0 < level < 1:
        raise ValueError("n_boot must be positive and level must be between 0 and 1.")
    values = _values(values)
    if not len(values):
        return float("nan"), float("nan")
    rng = make_rng(derive_seed(seed, "bootstrap"))
    samples = values[rng.integers(len(values), size=(n_boot, len(values)))]
    estimates = samples.mean(axis=1) if stat is np.mean else np.array([stat(row) for row in samples])
    lo, hi = np.quantile(estimates, [(1 - level) / 2, (1 + level) / 2])
    return float(lo), float(hi)


def grouped_bootstrap_means(groups: Mapping[str, np.ndarray], n_boot: int = 2000,
                             seed: int = 1) -> dict[str, np.ndarray]:
    """Resample episode rows within each condition, preserving all class columns.

    Each input matrix is episodes by classes. Each output is resamples by
    classes. Thus classes from one episode always travel together.
    """
    if n_boot < 1:
        raise ValueError("n_boot must be positive.")
    result = {}
    for key, matrix in sorted(groups.items()):
        matrix = np.asarray(matrix, dtype=float)
        if matrix.ndim != 2 or not len(matrix):
            raise ValueError("Each bootstrap group needs a non-empty episode-by-class matrix.")
        rng = make_rng(derive_seed(seed, "grouped_bootstrap", key))
        indices = rng.integers(len(matrix), size=(n_boot, len(matrix)))
        result[key] = matrix[indices].mean(axis=1)
    return result


def holm(pvalues: Mapping[str, float], alpha: float = 0.05) -> dict[str, dict[str, float | bool]]:
    """Adjust a family by Holm's step-down rule; absent tests stay absent."""
    if not 0 < alpha < 1 or any(not 0 <= p <= 1 for p in pvalues.values()):
        raise ValueError("Invalid alpha or p-value.")
    adjusted = {}
    running = 0.0
    for rank, (name, p) in enumerate(sorted(pvalues.items(), key=lambda item: (item[1], item[0]))):
        running = max(running, (len(pvalues) - rank) * p)
        value = min(1.0, running)
        adjusted[name] = {"p_adjusted": value, "reject": value <= alpha}
    return adjusted


def json_ready(value: Any) -> Any:
    """Convert tables, arrays and missing numbers to portable, strict JSON."""
    if hasattr(value, "to_dict"):
        value = value.to_dict(orient="records") if hasattr(value, "columns") else value.to_dict()
    if isinstance(value, Mapping):
        return {str(k): json_ready(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [json_ready(v) for v in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value
