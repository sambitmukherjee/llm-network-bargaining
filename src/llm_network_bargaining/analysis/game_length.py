"""The pilot's pre-registered 12-versus-24-round decision."""

import pandas as pd

from .data import Dataset
from .predictions import advantaged_class

RULE = ("Keep 12 rounds only if the episode-averaged power-use indices over rounds 7–12 "
        "and 13–24 differ by at most the tolerance on every listed network; otherwise use "
        "24 rounds for both knowledge settings.")


def game_length_decision(ds: Dataset, *, config: str = "pilot_own_links",
                         networks: tuple[str, ...] = ("line3", "star3"), tolerance: float = 0.1) -> dict:
    """Compare the two fixed pilot windows; incomplete pilot data raises."""
    episodes = ds.episodes[ds.episodes.config_name == config]
    if episodes.empty or not (episodes.n_rounds == 24).all():
        raise ValueError("Game-length decision requires a non-empty 24-round pilot config.")
    if not networks or tolerance < 0:
        raise ValueError("Supply networks and a non-negative tolerance.")
    rows = ds.node_rounds.merge(episodes[["episode_uid"]], on="episode_uid")
    results = {}
    for network in networks:
        prediction = advantaged_class(network)
        if prediction is None:
            raise ValueError(f"No advantaged class for {network}.")
        group = rows[(rows.network_id == network) & (rows.node_class == prediction["node_class"])]
        if group.empty:
            raise ValueError(f"Missing pilot network: {network}.")
        means = []
        for window in (range(7, 13), range(13, 25)):
            selected = group[group["round"].isin(window)]
            # Every episode must contribute all rounds of both fixed windows.
            counts = selected.groupby("episode_uid")["round"].nunique()
            if len(counts) != group.episode_uid.nunique() or not (counts == len(window)).all():
                raise ValueError(f"Incomplete pilot windows for {network}.")
            per_episode = selected.groupby("episode_uid").points.mean()
            means.append(float(((per_episode - 12) / (prediction["balanced"] - 12)).mean()))
        gap = abs(means[0] - means[1])
        results[network] = dict(w_early=means[0], w_late=means[1], gap=gap,
                                n_episodes=group.episode_uid.nunique(), passed=gap <= tolerance + 1e-9)
    return dict(config=config, networks=results, tolerance=tolerance, rule=RULE,
                decision=12 if all(row["passed"] for row in results.values()) else 24)
