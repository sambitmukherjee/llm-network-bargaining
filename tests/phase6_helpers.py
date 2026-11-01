"""Small synthetic outcome tables and a shared offline log fixture builder."""

from collections.abc import Sequence

import numpy as np
import pandas as pd

from llm_network_bargaining.analysis.data import dataset_from_tables
from llm_network_bargaining.networks import get_network
from llm_network_bargaining.structure import class_of


def tables_from_specs(specs: Sequence[dict]):
    """Build node rounds from network/knowledge/episode point specifications.

    A spec's points is a list of episodes. Each episode maps every node to a
    constant or a list of per-round points. These are synthetic metric inputs,
    not necessarily legal deals. Optional dealt flags override points > 0.
    Integration tests instead check physically valid data from real logs.
    """
    episodes, rows = [], []
    for spec in specs:
        net = get_network(spec["network"])
        knowledge = spec.get("knowledge", "full_map")
        config = spec.get("config", "minimum_study" if knowledge == "full_map" else "own_links_arm")
        assignment = spec.get("assignment", "terra")
        rounds = spec.get("rounds", 12)
        key = f"{config}/{net.id}/{knowledge}/{assignment}"
        classes = class_of(net)
        for i, points in enumerate(spec["points"]):
            uid = f"{key}/{i:03d}"
            episodes.append(dict(episode_uid=uid, config_name=config, condition_key=key, network_id=net.id,
                knowledge=knowledge, assignment=assignment, episode_index=i, episode_seed=i, attempt=1,
                n_rounds=rounds, n_nodes=len(net.nodes), prompt_version="v1", dry_run_bot=None,
                cost_usd=0.0, n_turn_calls=0, n_quiz_calls=0))
            for node_index, node in enumerate(net.nodes):
                values = points[node] if isinstance(points[node], list) else [points[node]] * rounds
                assert len(values) == rounds
                for r, value in enumerate(values, 1):
                    dealt = spec.get("dealt", {}).get(node, value > 0)
                    dealt = dealt[r - 1] if isinstance(dealt, list) else dealt
                    slot = (node_index + r) % len(net.nodes) + 1
                    rows.append(dict(episode_uid=uid, config_name=config, network_id=net.id,
                        knowledge=knowledge, assignment=assignment, node=node, node_class=classes[node],
                        model_alias=spec.get("models", {}).get(node, "terra"), round=r,
                        points=value, dealt=bool(dealt), partner=None, maker=False,
                        share=value / net.pie if dealt else np.nan, slot1=slot,
                        slot1_norm=(slot - 1) / (len(net.nodes) - 1)))
    return dataset_from_tables(episodes=pd.DataFrame(episodes), node_rounds=pd.DataFrame(rows))
