"""H2 point-prediction errors and descriptive ordering accuracy."""

from itertools import combinations

import numpy as np

from .data import Dataset
from .metrics import episode_class_metrics
from .predictions import BENCHMARKS, PREDICTORS, class_predictions
from .stats import grouped_bootstrap_means, json_ready


def _class_data(ds: Dataset, config: str, window: str, n_boot: int, seed: int) -> list[dict]:
    """Align observed classes, predictions and paired episode bootstrap rows."""
    table = episode_class_metrics(ds, window)
    table = table[table.config_name == config]
    groups = []
    matrices = {}
    for network, group in table.groupby("network_id", sort=True):
        if group.condition_key.nunique() != 1:
            raise ValueError(f"Benchmark comparison needs one condition per network: {network}.")
        key = group.condition_key.iloc[0]
        pivot = group.pivot(index="episode_uid", columns="node_class", values="points_mean").sort_index(axis=1)
        if pivot.isna().any().any():
            raise ValueError("Every episode must contain every node class.")
        matrices[key] = pivot.to_numpy(dtype=float)
        prediction = class_predictions(network).set_index("node_class").loc[pivot.columns]
        groups.append(dict(network_id=network, condition_key=key, classes=list(pivot.columns),
                           observed=matrices[key].mean(axis=0), predictions=prediction, n_episodes=len(pivot)))
    boot = grouped_bootstrap_means(matrices, n_boot=n_boot, seed=seed)
    for group in groups:
        group["boot"] = boot[group["condition_key"]]
    return groups


def _interval(samples: np.ndarray) -> dict[str, float]:
    """Give a percentile interval, omitting undefined bootstrap accuracies."""
    finite = samples[np.isfinite(samples)]
    lo, hi = np.quantile(finite, [0.025, 0.975]) if len(finite) else (np.nan, np.nan)
    return dict(ci_low=float(lo), ci_high=float(hi))


def benchmark_errors(ds: Dataset, config: str = "minimum_study", window: str = "second_half",
                      n_boot: int = 2000, seed: int = 1) -> dict:
    """Compare four point benchmarks, giving each network/class pair one vote."""
    groups = _class_data(ds, config, window, n_boot, seed)
    per_network, core_distances = [], []
    eligible = []
    for group in groups:
        prediction = group["predictions"]
        if prediction[list(BENCHMARKS)].notna().all().all():
            eligible.append(group)
        for predictor in BENCHMARKS:
            predicted = prediction[predictor].to_numpy(dtype=float)
            if not np.isfinite(predicted).all():
                continue
            rmse = float(np.sqrt(np.mean((group["observed"] - predicted) ** 2)))
            samples = np.sqrt(np.mean((group["boot"] - predicted) ** 2, axis=1))
            per_network.append(dict(network_id=group["network_id"], condition_key=group["condition_key"],
                predictor=predictor, rmse=rmse, **_interval(samples), n_classes=len(predicted),
                n_episodes=group["n_episodes"]))
        for label, observed in zip(group["classes"], group["observed"]):
            low, high = prediction.loc[label, ["core_min", "core_max"]]
            distance = max(low - observed, observed - high, 0.0) if np.isfinite([low, high]).all() else np.nan
            core_distances.append(dict(network_id=group["network_id"], node_class=label,
                                       observed=float(observed), core_min=low, core_max=high, distance=distance))
    overall = []
    boot_errors = []
    if eligible:
        observed = np.concatenate([g["observed"] for g in eligible])
        boot = np.concatenate([g["boot"] for g in eligible], axis=1)
        for predictor in BENCHMARKS:
            predicted = np.concatenate([g["predictions"][predictor].to_numpy(dtype=float) for g in eligible])
            samples = np.sqrt(np.mean((boot - predicted) ** 2, axis=1))
            boot_errors.append(samples)
            overall.append(dict(predictor=predictor, rmse=float(np.sqrt(np.mean((observed - predicted) ** 2))),
                                 **_interval(samples), n_classes=len(predicted)))
        errors = np.stack(boot_errors, axis=1)
        winners = np.isclose(errors, errors.min(axis=1, keepdims=True), atol=1e-12, rtol=0)
        probabilities = (winners / winners.sum(axis=1, keepdims=True)).mean(axis=0)
        for row, probability in zip(overall, probabilities):
            row["p_best"] = float(probability)
    ranking = [row["predictor"] for row in sorted(overall, key=lambda row: row["rmse"])]
    return json_ready(dict(status="run" if groups else "not_run", config=config, window=window,
        per_network=per_network, overall=overall, ranking=ranking, best=ranking[0] if ranking else None,
        overall_networks=[g["network_id"] for g in eligible], core_distances=core_distances,
        n_boot=n_boot, seed=seed))


def _pair_counts(observed: np.ndarray, predicted: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Count correct, included and observed-tie class pairs for every resample."""
    observed = np.atleast_2d(observed)
    correct = np.zeros(len(observed))
    included = np.zeros(len(observed), dtype=int)
    tied = np.zeros(len(observed), dtype=int)
    for i, j in combinations(range(len(predicted)), 2):
        difference = observed[:, i] - observed[:, j]
        has_order = difference != 0
        included += has_order
        tied += ~has_order
        if predicted[i] == predicted[j]:
            correct += 0.5 * has_order
        else:
            correct += has_order & (np.sign(difference) == np.sign(predicted[i] - predicted[j]))
    return correct, included, tied


def ordering_accuracy(ds: Dataset, config: str = "minimum_study", window: str = "second_half",
                       n_boot: int = 2000, seed: int = 1) -> dict:
    """Compare all six predictors on within-network ordering, without ranking them."""
    groups = _class_data(ds, config, window, n_boot, seed)
    per_network, overall = [], []
    for predictor in PREDICTORS:
        total_correct = total_pairs = total_tied = 0
        boot_correct, boot_pairs = np.zeros(n_boot), np.zeros(n_boot)
        for group in groups:
            predicted = group["predictions"][predictor].to_numpy(dtype=float)
            if not np.isfinite(predicted).all():
                continue
            correct, pairs, tied = _pair_counts(group["observed"], predicted)
            bc, bp, _ = _pair_counts(group["boot"], predicted)
            boot_correct += bc
            boot_pairs += bp
            samples = np.divide(bc, bp, out=np.full(n_boot, np.nan), where=bp > 0)
            accuracy = float(correct[0] / pairs[0]) if pairs[0] else np.nan
            per_network.append(dict(network_id=group["network_id"], predictor=predictor,
                correct=float(correct[0]), n_pairs=int(pairs[0]), n_tied_observed=int(tied[0]),
                accuracy=accuracy, **_interval(samples)))
            total_correct += correct[0]
            total_pairs += int(pairs[0])
            total_tied += int(tied[0])
        samples = np.divide(boot_correct, boot_pairs, out=np.full(n_boot, np.nan), where=boot_pairs > 0)
        overall.append(dict(predictor=predictor, correct=float(total_correct), n_pairs=total_pairs,
            n_tied_observed=total_tied, accuracy=float(total_correct / total_pairs) if total_pairs else np.nan,
            **_interval(samples)))
    return json_ready(dict(status="run" if groups else "not_run", config=config, window=window,
                            per_network=per_network, overall=overall, n_boot=n_boot, seed=seed))
