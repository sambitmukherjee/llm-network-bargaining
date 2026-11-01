"""Registered exact results, Monte Carlo paths and episode bootstraps."""

import json

import numpy as np
import pytest

from llm_network_bargaining.analysis.stats import (
    bootstrap_ci, grouped_bootstrap_means, holm, permutation_test_two_sample,
    sign_flip_test, slope_permutation_test, stratified_permutation_test)


def test_registered_sign_flip_values() -> None:
    result = sign_flip_test([.75, .70, .83, .50, .66, .58, .92, .71, .45, .79], null=.5)
    assert result.statistic == pytest.approx(.189)
    assert result.p_value == 4 / 1024
    assert result.method == "exact" and result.n_resamples == 1024 and result.n == 10
    assert sign_flip_test([1.] * 10, null=.5).p_value == 1 / 1024
    assert sign_flip_test([.5] * 10, null=.5).p_value == 1
    assert sign_flip_test([np.nan, 1.], null=.5).n == 1
    assert sign_flip_test([-1.] * 4, alternative="less").p_value == 1 / 16
    assert sign_flip_test([1.] * 4, alternative="two-sided").p_value == 2 / 16
    json.dumps(result.to_dict(), allow_nan=False)


def test_registered_two_sample_value_and_exact_10_vs_10() -> None:
    result = permutation_test_two_sample([1, 2, 3], [4, 5, 6], "greater")
    assert result.statistic == 3 and result.p_value == 1 / 20
    assert result.method == "exact" and result.n_resamples == 20
    large = permutation_test_two_sample([0.] * 10, [1.] * 10, "greater")
    assert large.method == "exact" and large.n_resamples == 184756
    assert large.p_value == 1 / 184756


def test_slope_two_and_three_group_enumeration() -> None:
    result = slope_permutation_test([1, 2, 3, 4, 5, 6], [3, 3, 3, 4, 4, 4])
    assert result.statistic == 3 and result.p_value == .05
    # Three labelled groups: 6!/(2!2!2!) assignments, not 6! orders.
    result = slope_permutation_test([0, 0, 1, 1, 2, 2], [0, 0, 1, 1, 2, 2])
    assert result.statistic == 1 and result.n_resamples == 90
    assert result.p_value == 1 / 90


def test_registered_stratified_value() -> None:
    result = stratified_permutation_test([1., .8, .2, 0., .5, .5, .5, .5],
        ["full_map", "full_map", "own_links", "own_links"] * 2, ["g1"] * 4 + ["g2"] * 4)
    assert result.statistic == pytest.approx(.4)
    assert result.p_value == 12 / 36 and result.n_resamples == 36
    assert result.method == "exact"


@pytest.mark.parametrize("test", ["sign", "two", "slope", "stratified"])
def test_monte_carlo_determinism_and_close_to_exact(test: str) -> None:
    def run(seed):
        if test == "sign":
            return sign_flip_test([.8, .6, .3, .9], null=.5, exact_max_n=0, n_mc=4000, seed=seed)
        if test == "two":
            return permutation_test_two_sample([1, 2, 3], [3, 4, 5], exact_max=0, n_mc=4000, seed=seed)
        if test == "slope":
            return slope_permutation_test([0, 1, 1, 2, 2, 3], [0, 0, 1, 1, 2, 2], exact_max=0, n_mc=4000, seed=seed)
        return stratified_permutation_test([0, 1, 1, 2], ["own_links"] * 2 + ["full_map"] * 2,
                                           ["g"] * 4, exact_max=0, n_mc=4000, seed=seed)
    first = run(10)
    assert first == run(10) and first.method == "monte_carlo"
    assert abs(first.p_value - run(11).p_value) < .04


def test_stratified_strong_separation_and_identical_values() -> None:
    values = ([1.] * 10 + [0.] * 10) * 6
    labels = (["full_map"] * 10 + ["own_links"] * 10) * 6
    strata = [str(i) for i in range(6) for _ in range(20)]
    result = stratified_permutation_test(values, labels, strata, n_mc=4000)
    assert result.method == "monte_carlo" and result.p_value <= 2 / 4001
    assert stratified_permutation_test([.5] * 120, labels, strata, n_mc=4000).p_value == 1


def test_bootstrap_and_holm() -> None:
    assert bootstrap_ci([1, 2, 3, 6], seed=10) == bootstrap_ci([1, 2, 3, 6], seed=10)
    assert bootstrap_ci([3.]) == (3., 3.)
    assert np.isnan(bootstrap_ci([])[0])
    grouped = grouped_bootstrap_means({"a": np.array([[1, 10], [2, 20]])}, n_boot=40, seed=5)
    np.testing.assert_array_equal(grouped["a"][:, 0] * 10, grouped["a"][:, 1])
    adjustment = holm({"a": .01, "b": .04, "c": .03, "d": .005})
    assert {k: v["p_adjusted"] for k, v in adjustment.items()} == dict(a=.03, b=.06, c=.06, d=.02)
    assert {k for k, v in adjustment.items() if v["reject"]} == {"a", "d"}


@pytest.mark.parametrize("call", [lambda: sign_flip_test([]), lambda: permutation_test_two_sample([], [1]),
    lambda: slope_permutation_test([1, 2], [1, 1]),
    lambda: stratified_permutation_test([1], ["full_map"], ["a"]),
    lambda: bootstrap_ci([1], n_boot=0), lambda: holm({"a": 1.5})])
def test_bad_statistical_inputs_raise(call) -> None:
    with pytest.raises(ValueError):
        call()
