"""Episode-first outcome metrics, summaries and operational diagnostics."""

from collections import Counter
from collections.abc import Iterable
from pathlib import Path
import re

import numpy as np
import pandas as pd

from ..networks import get_network
from ..runlog import attempt_costs, read_attempt_logs
from ..seeds import derive_seed
from ..structure import max_deals
from .data import Dataset, outcome_rows
from .predictions import PREDICTION_COLUMNS, advantaged_class, class_predictions
from .stats import bootstrap_ci, sign_flip_test

CONDITION = ["config_name", "condition_key", "network_id", "knowledge", "assignment"]
EPISODE = ["episode_uid", *CONDITION, "episode_index"]
NODE_METRICS = ["points_mean", "deal_rate", "exclusion_rate", "share_mean", "n_deals"]


def episode_node_metrics(ds: Dataset, window: str = "second_half") -> pd.DataFrame:
    """Average window rounds separately for each node in each episode."""
    rows = outcome_rows(ds, window)
    keys = [*EPISODE, "node", "node_class", "model_alias"]
    if rows.empty:
        return pd.DataFrame(columns=[*keys, *NODE_METRICS])
    result = rows.groupby(keys, sort=True, as_index=False).agg(
        points_mean=("points", "mean"), deal_rate=("dealt", "mean"),
        share_mean=("share", "mean"), n_deals=("dealt", "sum"))
    result["exclusion_rate"] = 1 - result.deal_rate
    return result[[*keys, *NODE_METRICS]]


def episode_class_metrics(ds: Dataset, window: str = "second_half") -> pd.DataFrame:
    """Average node metrics within each orbit, giving each member equal weight."""
    nodes = episode_node_metrics(ds, window)
    keys = [*EPISODE, "node_class"]
    if nodes.empty:
        return pd.DataFrame(columns=[*keys, *NODE_METRICS])
    # Pandas means skip a member's NaN share when that member never dealt.
    return nodes.groupby(keys, sort=True, as_index=False)[NODE_METRICS].mean()


def power_use(ds: Dataset, window: str = "second_half") -> pd.DataFrame:
    """Compute the registered power-use index of each episode's advantaged class."""
    classes = episode_class_metrics(ds, window)
    rows = []
    for network, group in classes.groupby("network_id", sort=True):
        prediction = advantaged_class(network)
        if prediction is None:
            continue
        for row in group[group.node_class == prediction["node_class"]].to_dict("records"):
            row["balanced"] = prediction["balanced"]
            row["pui"] = (row["points_mean"] - 12) / (prediction["balanced"] - 12)
            rows.append(row)
    return pd.DataFrame(rows, columns=[*classes.columns, "balanced", "pui"])


def _summary(table: pd.DataFrame, keys: list[str], metrics: list[str],
             n_boot: int, seed: int) -> pd.DataFrame:
    """Summarise independent episode rows with a separate stream per metric."""
    columns = [*keys, "n_episodes"]
    for metric in metrics:
        columns.extend([metric, f"{metric}_ci_low", f"{metric}_ci_high"])
    rows = []
    for key, group in table.groupby(keys, sort=True):
        key = key if isinstance(key, tuple) else (key,)
        row = dict(zip(keys, key))
        row["n_episodes"] = group.episode_uid.nunique()
        for metric in metrics:
            values = group[metric].dropna().to_numpy(dtype=float)
            row[metric] = float(values.mean()) if len(values) else np.nan
            lo, hi = bootstrap_ci(values, n_boot=n_boot, seed=derive_seed(seed, *map(str, key), metric))
            row[f"{metric}_ci_low"], row[f"{metric}_ci_high"] = lo, hi
        rows.append(row)
    return pd.DataFrame(rows, columns=columns)


def summarise_power_use(ds: Dataset, window: str = "second_half", n_boot: int = 2000,
                        seed: int = 1) -> pd.DataFrame:
    """Give condition-level mean power use and an episode-bootstrap interval."""
    return _summary(power_use(ds, window), CONDITION, ["pui"], n_boot, seed)


def condition_class_summary(ds: Dataset, window: str = "second_half", n_boot: int = 2000,
                            seed: int = 1) -> pd.DataFrame:
    """Summarise class outcomes over episodes, then attach theory predictions."""
    summary = _summary(episode_class_metrics(ds, window), [*CONDITION, "node_class"],
                        ["points_mean", "share_mean", "deal_rate"], n_boot, seed)
    networks = sorted(summary.network_id.unique())
    predictions = (pd.concat([class_predictions(net) for net in networks], ignore_index=True)
                   if networks else pd.DataFrame(columns=PREDICTION_COLUMNS))
    return summary.merge(predictions, on=["network_id", "node_class"], how="left", validate="many_to_one")


def episode_efficiency(ds: Dataset, window: str = "second_half") -> pd.DataFrame:
    """Mean matching efficiency over rounds; every deal has two dealt nodes."""
    rows = outcome_rows(ds, window)
    if rows.empty:
        return pd.DataFrame(columns=[*EPISODE, "efficiency"])
    per_round = rows.groupby([*EPISODE, "round"], as_index=False).agg(n_dealt=("dealt", "sum"))
    per_round["efficiency"] = [n / (2 * max_deals(get_network(net)))
                                for n, net in zip(per_round.n_dealt, per_round.network_id)]
    return per_round.groupby(EPISODE, as_index=False).efficiency.mean()


def summarise_efficiency(ds: Dataset, window: str = "second_half", n_boot: int = 2000,
                         seed: int = 1) -> pd.DataFrame:
    """Summarise episode efficiencies per condition."""
    return _summary(episode_efficiency(ds, window), CONDITION, ["efficiency"], n_boot, seed)


def episode_pair_proposer_share(ds: Dataset, window: str = "second_half") -> pd.DataFrame:
    """Average the maker's share over pair-network deals within each episode."""
    rows = outcome_rows(ds, window)
    selected = rows[rows.network_id == "pair"][["episode_uid", "round"]].drop_duplicates()
    deals = ds.deals.merge(selected, on=["episode_uid", "round"])
    if deals.empty:
        means = pd.DataFrame(columns=["episode_uid", "proposer_share"])
    else:
        deals["proposer_share"] = deals.maker_points / get_network("pair").pie
        means = deals.groupby("episode_uid", as_index=False).proposer_share.mean()
    # Include a no-deal episode as a missing share, not as a zero-share deal.
    episodes = ds.episodes[ds.episodes.network_id == "pair"][EPISODE]
    return episodes.merge(means, on="episode_uid", how="left")


def summarise_pair_proposer_share(ds: Dataset, window: str = "second_half", n_boot: int = 2000,
                                  seed: int = 1) -> pd.DataFrame:
    """Describe proposer advantage, including a two-sided sign-flip test."""
    episodes = episode_pair_proposer_share(ds, window)
    result = _summary(episodes, CONDITION, ["proposer_share"], n_boot, seed)
    tests = []
    for key, group in episodes.groupby(CONDITION, sort=True):
        values = group.proposer_share.dropna()
        test = sign_flip_test(values, null=0.5, alternative="two-sided",
                              seed=derive_seed(seed, "proposer", *map(str, key))) if len(values) else None
        tests.append(dict(zip(CONDITION, key)) | {
            "p_value": test.p_value if test else np.nan,
            "method": test.method if test else "not_run", "n_test": len(values)})
    return result.merge(pd.DataFrame(tests, columns=[*CONDITION, "p_value", "method", "n_test"]), on=CONDITION)


def episode_triangle_lock_in(ds: Dataset, window: str = "second_half") -> pd.DataFrame:
    """Largest node exclusion count divided by all node exclusions."""
    nodes = episode_node_metrics(ds, window)
    rows = []
    for _, group in nodes[nodes.network_id == "triangle"].groupby(EPISODE, sort=True):
        excluded = group.exclusion_rate.to_numpy(dtype=float)
        row = group.iloc[0][EPISODE].to_dict()
        row["lock_in"] = float(excluded.max() / excluded.sum()) if excluded.sum() else np.nan
        rows.append(row)
    return pd.DataFrame(rows, columns=[*EPISODE, "lock_in"])


def summarise_triangle_lock_in(ds: Dataset, window: str = "second_half", n_boot: int = 2000,
                               seed: int = 1) -> pd.DataFrame:
    """Summarise triangle lock-in across independent episodes."""
    return _summary(episode_triangle_lock_in(ds, window), CONDITION, ["lock_in"], n_boot, seed)


def learning_curves(ds: Dataset, window: str = "all", n_boot: int = 2000,
                    seed: int = 1) -> pd.DataFrame:
    """Mean class points at each round, resampling episodes rather than nodes."""
    rows = outcome_rows(ds, window)
    keys = [*EPISODE, "node_class", "round"]
    points = rows.groupby(keys, as_index=False).agg(points_mean=("points", "mean"))
    return _summary(points, [*CONDITION, "node_class", "round"], ["points_mean"], n_boot, seed)


def _turn_context(ds: Dataset, table: pd.DataFrame) -> pd.DataFrame:
    """Attach condition metadata to a turn or quiz table."""
    return table.merge(ds.episodes[["episode_uid", *CONDITION]], on="episode_uid", validate="many_to_one")


def invalid_action_rates(ds: Dataset) -> pd.DataFrame:
    """Count asked turns and illegal game actions, keeping automatic turns out."""
    turns = _turn_context(ds, ds.turns)
    rows = []
    for key, group in turns.groupby([*CONDITION, "model_alias"], sort=True):
        asked = group[~group.auto.astype(bool)]
        invalid = asked[~asked.valid.astype(bool)]
        rows.append(dict(zip([*CONDITION, "model_alias"], key)) | {
            "n_asked": len(asked), "n_invalid": len(invalid),
            "invalid_rate": len(invalid) / len(asked) if len(asked) else np.nan,
            "by_reason": dict(sorted(Counter(invalid.reason).items()))})
    return pd.DataFrame(rows, columns=[*CONDITION, "model_alias", "n_asked", "n_invalid", "invalid_rate", "by_reason"])


def quiz_summary(ds: Dataset) -> pd.DataFrame:
    """Summarise only completed episodes' quizzes, per condition and model alias."""
    quizzes = _turn_context(ds, ds.quizzes)
    rows = []
    for key, group in quizzes.groupby([*CONDITION, "model_alias"], sort=True):
        rows.append(dict(zip([*CONDITION, "model_alias"], key)) | {
            "n": len(group), "mean_score": float(group.score.mean()),
            "perfect_share": float((group.score == 3).mean()),
            **{f"{q}_accuracy": float(group[q].mean()) for q in ("q1", "q2", "q3")}})
    return pd.DataFrame(rows, columns=[*CONDITION, "model_alias", "n", "mean_score", "perfect_share",
                                       "q1_accuracy", "q2_accuracy", "q3_accuracy"])


def attempt_diagnostics(roots: Iterable[str | Path], *, configs: Iterable[str] | None = None,
                         max_failed: int = 3) -> pd.DataFrame:
    """Count failed/interrupted attempts and abandonment, including known costs."""
    conditions = {}
    episodes = {}
    for path, records in read_attempt_logs(roots):
        header = records.header
        if configs is not None and header["config_name"] not in configs:
            continue
        key = header["condition_key"]
        condition = conditions.setdefault(key, dict(config_name=header["config_name"], condition_key=key,
            failed_attempts=0, failed_by_category=Counter(), interrupted_attempts=0,
            abandoned_episodes=0, non_completed_cost_usd=0.0))
        identity = (key, header["episode_index"])
        episode = episodes.setdefault(identity, dict(failed=0, completed=False))
        completed = bool(re.fullmatch(r"episode_\d+\.jsonl\.gz", path.name))
        if completed:
            episode["completed"] = True
            continue
        condition["non_completed_cost_usd"] += attempt_costs(records)["cost_usd"]
        if ".failed" in path.name:
            condition["failed_attempts"] += 1
            episode["failed"] += 1
            # Concurrent quiz failures can carry several categories in one attempt.
            categories = {failure["category"] for failure in records.failures} or {"unknown"}
            condition["failed_by_category"].update(categories)
        else:
            condition["interrupted_attempts"] += 1
    for (key, _), episode in episodes.items():
        conditions[key]["abandoned_episodes"] += not episode["completed"] and episode["failed"] >= max_failed
    for condition in conditions.values():
        condition["failed_by_category"] = dict(sorted(condition["failed_by_category"].items()))
    return pd.DataFrame([conditions[key] for key in sorted(conditions)], columns=["config_name", "condition_key",
        "failed_attempts", "failed_by_category", "interrupted_attempts", "abandoned_episodes", "non_completed_cost_usd"])


def cost_summary(ds: Dataset, roots: Iterable[str | Path], *, configs: Iterable[str] | None = None) -> pd.DataFrame:
    """Separate completed and non-completed cost/usage by config and model alias.

    All configs under roots are included by default, including failed-only
    configs. An explicit filter lets the CLI keep the selected analysis scope.
    """
    selected = set(configs) if configs is not None else None
    totals = {}
    for path, records in read_attempt_logs(roots):
        config = records.header["config_name"]
        if selected is not None and config not in selected:
            continue
        status = "completed" if re.fullmatch(r"episode_\d+\.jsonl\.gz", path.name) else "non_completed"
        fields = attempt_costs(records)
        for alias in sorted(set(fields["cost_by_alias"]) | set(fields["usage_by_alias"])):
            key = (config, alias, status)
            row = totals.setdefault(key, dict(config_name=config, model_alias=alias, status=status,
                dry_run=records.header.get("dry_run_bot") is not None, cost_usd=0.0, calls=0,
                prompt_tokens=0, completion_tokens=0, cached_tokens=0, cache_write_tokens=0, reasoning_tokens=0))
            row["cost_usd"] += fields["cost_by_alias"].get(alias, 0.0)
            for name, value in fields["usage_by_alias"].get(alias, {}).items():
                row[name] += value
    return pd.DataFrame([totals[key] for key in sorted(totals)], columns=["config_name", "model_alias", "status",
        "dry_run", "cost_usd", "calls", "prompt_tokens", "completion_tokens", "cached_tokens", "cache_write_tokens", "reasoning_tokens"])
