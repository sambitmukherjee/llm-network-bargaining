"""The registered H1/H3--H6 tests and their two separate Holm families."""

from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

from ..seeds import derive_seed
from .data import Dataset
from .metrics import episode_class_metrics, power_use
from .predictions import advantaged_class
from .stats import (bootstrap_ci, grouped_bootstrap_means, holm, json_ready,
                    permutation_test_two_sample, sign_flip_test,
                    slope_permutation_test, stratified_permutation_test)

FAMILY = ("H1", "H3", "H4", "H5", "H6")


@dataclass
class HypothesisReport:
    """Registered tests, main Holm decisions, and H1's secondary network tests."""

    results: dict
    window: str = "second_half"
    seed: int = 1
    family: dict = field(init=False)
    h1_per_network: dict = field(init=False)

    def __post_init__(self) -> None:
        """Apply the primary and secondary corrections without mixing families."""
        pvalues = {name: result["p_value"] for name, result in self.results.items()
                   if name in FAMILY and result["status"] == "run"}
        self.family = holm(pvalues)
        for name, adjustment in self.family.items():
            self.results[name].update(adjustment)
            self.results[name]["decision"] = "supported" if adjustment["reject"] else "not_supported"
        h1 = self.results.get("H1", {})
        self.h1_per_network = {}
        if h1.get("status") == "run":
            tests = h1["per_network"]
            adjusted = holm({network: row["p_value"] for network, row in tests.items()})
            self.h1_per_network = {network: {**row, **adjusted[network],
                "decision": "supported" if adjusted[network]["reject"] else "not_supported"}
                for network, row in tests.items()}

    def to_dict(self) -> dict:
        """Return strict JSON-compatible results; missing values become null."""
        return json_ready(asdict(self))


def _summary(values: pd.Series, seed: int, n_boot: int) -> dict:
    """Describe one network's independent episode inputs."""
    values = values.dropna().to_numpy(dtype=float)
    low, high = bootstrap_ci(values, n_boot=n_boot, seed=seed)
    return dict(n=len(values), mean=float(values.mean()) if len(values) else np.nan,
                ci_low=low, ci_high=high)


def _difference(b: pd.Series, a: pd.Series, seed: int, n_boot: int) -> dict:
    """Independent episode bootstraps for a descriptive difference of means."""
    a, b = a.dropna().to_numpy(dtype=float), b.dropna().to_numpy(dtype=float)
    means = grouped_bootstrap_means({"a": a[:, None], "b": b[:, None]}, n_boot, seed)
    low, high = np.quantile((means["b"] - means["a"]).ravel(), [0.025, 0.975])
    return dict(difference=float(b.mean() - a.mean()), ci_low=float(low), ci_high=float(high),
                n_a=len(a), n_b=len(b))


def _not_run(reason: str, inputs: dict | None = None) -> dict:
    """Keep a missing-data result explicit and outside the Holm family."""
    return dict(status="not_run", decision="not_run", reason=reason, per_network=inputs or {})


def _intersection(tests: dict) -> dict:
    """A joint claim succeeds only if every constituent one-sided claim does."""
    return dict(status="run", statistic=min(test["statistic"] for test in tests.values()),
                p_value=max(test["p_value"] for test in tests.values()),
                method="exact" if all(test["method"] == "exact" for test in tests.values()) else "monte_carlo",
                per_network=tests)


def run_hypotheses(ds: Dataset, *, main: str = "minimum_study", own_links: str = "own_links_arm",
                    h6: str = "stretch_2f_h6", window: str = "second_half", seed: int = 1,
                    n_boot: int = 2000) -> HypothesisReport:
    """Run only tests whose required inputs exist; H2 is a separate ranking."""
    classes = episode_class_metrics(ds, window)
    main_rows = classes[(classes.config_name == main) & (classes.knowledge == "full_map")]
    advantaged = []
    for network, group in main_rows.groupby("network_id", sort=True):
        prediction = advantaged_class(network)
        if prediction is not None:
            advantaged.append(group[group.node_class == prediction["node_class"]])
    advantages = pd.concat(advantaged, ignore_index=True) if advantaged else main_rows.iloc[:0]
    results = {}

    h1_tests = {}
    for network in ("line3", "line5", "star3", "star4"):
        values = advantages.loc[advantages.network_id == network, "share_mean"].dropna()
        if len(values):
            stream = derive_seed(seed, "H1", network)
            h1_tests[network] = {**_summary(values, stream, n_boot),
                                 **sign_flip_test(values, null=0.5, seed=stream).to_dict()}
    results["H1"] = (_intersection(h1_tests) if len(h1_tests) == 4 else
                     _not_run("H1 requires line3, line5, star3 and star4 with observed deals.", h1_tests))

    stars = advantages[advantages.network_id.isin(["star3", "star4", "star5"])].dropna(subset=["share_mean"])
    inputs = {network: _summary(group.share_mean, derive_seed(seed, "H3", network), n_boot)
              for network, group in stars.groupby("network_id", sort=True)}
    if stars.network_id.nunique() >= 2:
        test = slope_permutation_test(stars.share_mean, [int(name[4:]) for name in stars.network_id],
                                      alternative="greater", seed=derive_seed(seed, "H3"))
        results["H3"] = dict(status="run", **test.to_dict(), per_network=inputs)
    else:
        results["H3"] = _not_run("H3 requires at least two star sizes.", inputs)

    ends4 = main_rows[(main_rows.network_id == "line4") & (main_rows.node_class == "A|D")].points_mean.dropna()
    ends5 = main_rows[(main_rows.network_id == "line5") & (main_rows.node_class == "A|E")].points_mean.dropna()
    inputs = {network: _summary(values, derive_seed(seed, "H4", network), n_boot)
              for network, values in [("line4", ends4), ("line5", ends5)]}
    if len(ends4) and len(ends5):
        test = permutation_test_two_sample(ends5, ends4, "greater", seed=derive_seed(seed, "H4"))
        results["H4"] = dict(status="run", **test.to_dict(), per_network=inputs)
    else:
        results["H4"] = _not_run("H4 requires both line4 and line5 end classes.", inputs)

    pui = power_use(ds, window)
    full = pui[(pui.config_name == main) & (pui.knowledge == "full_map")]
    local = pui[(pui.config_name == own_links) & (pui.knowledge == "own_links")]
    common = sorted(set(full.network_id) & set(local.network_id))
    common = [net for net in common if net in {"line3", "line4", "line5", "star3", "star4", "stem"}]
    inputs = {}
    for network in common:
        b, a = full[full.network_id == network].pui, local[local.network_id == network].pui
        stream = derive_seed(seed, "H5", network)
        inputs[network] = {"full_map": _summary(b, derive_seed(stream, "full"), n_boot),
                           "own_links": _summary(a, derive_seed(stream, "own"), n_boot),
                           **_difference(b, a, stream, n_boot)}
    if common:
        combined = pd.concat([full[full.network_id.isin(common)], local[local.network_id.isin(common)]])
        test = stratified_permutation_test(combined.pui, combined.knowledge, combined.network_id,
                                           n_mc=100_000, seed=derive_seed(seed, "H5"))
        results["H5"] = dict(status="run", **test.to_dict(), per_network=inputs)
    else:
        results["H5"] = _not_run("H5 requires networks in both named knowledge configs.")

    stretch = pui[pui.config_name == h6]
    h6_tests, differences = {}, {}
    for network in ("line3", "star3"):
        assignments = {}
        for assignment in ("terra_hub", "luna_hub"):
            values = stretch[(stretch.network_id == network) & (stretch.assignment == assignment)].pui.dropna()
            assignments[assignment] = values
            if len(values):
                stream = derive_seed(seed, "H6", network, assignment)
                h6_tests[f"{network}/{assignment}"] = {**_summary(values, stream, n_boot),
                                                       **sign_flip_test(values, seed=stream).to_dict()}
        if all(len(values) for values in assignments.values()):
            differences[network] = _difference(assignments["terra_hub"], assignments["luna_hub"],
                                                derive_seed(seed, "H6", network, "difference"), n_boot)
    results["H6"] = (_intersection(h6_tests) if len(h6_tests) == 4 else
                     _not_run("H6 requires both hub assignments on line3 and star3.", h6_tests))
    results["H6"]["assignment_differences"] = differences
    return HypothesisReport(results, window, seed)
