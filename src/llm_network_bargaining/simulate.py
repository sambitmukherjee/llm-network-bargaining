"""Run scripted bots offline and print their earnings beside theory benchmarks."""

import argparse
from collections.abc import Sequence
from statistics import mean, stdev

from .bots import make_bot
from .engine import run_episode
from .networks import get_network
from .seeds import derive_seed
from .structure import class_label, max_deals, node_classes
from .theory import balanced_outcome, myerson_value, position_value


def main(argv: Sequence[str] | None = None) -> None:
    """Run the requested bot episodes and print deterministic summary rows."""
    parser = argparse.ArgumentParser(description="Simulate network bargaining with bots.")
    parser.add_argument("--network", required=True)
    parser.add_argument("--bot", choices=("pass", "equal_split", "aspiration", "random"),
                        default="aspiration")
    parser.add_argument("--episodes", type=int, default=10)
    parser.add_argument("--rounds", type=int, default=24)
    parser.add_argument("--knowledge", choices=("full_map", "own_links"), default="full_map")
    parser.add_argument("--seed", type=int, default=1)
    arguments = parser.parse_args(argv)
    if arguments.episodes < 1 or arguments.rounds < 1:
        parser.error("episodes and rounds must be at least 1")
    try:
        network = get_network(arguments.network)
    except KeyError as error:
        parser.error(str(error))
    if network.kind != "exchange":
        parser.error("Broker networks are not supported: the broker protocol is future work.")
    results = []
    for i in range(arguments.episodes):
        seed = derive_seed(arguments.seed, "simulate", network.id, i)
        agents = {node: make_bot(arguments.bot, node=node, episode_seed=seed)
                  for node in network.nodes}
        results.append(run_episode(network, agents, knowledge=arguments.knowledge,
                                   n_rounds=arguments.rounds, episode_seed=seed))
    myerson = myerson_value(network)
    position = position_value(network).values
    balanced = balanced_outcome(network)
    start = arguments.rounds // 2  # zero-based start of the second half
    print(f"network={network.id} bot={arguments.bot} knowledge={arguments.knowledge} "
          f"episodes={arguments.episodes} rounds={arguments.rounds} seed={arguments.seed}")
    print("node_class mean std equal_split myerson position_value balanced")
    for members in node_classes(network):
        episode_means = [mean(point for node in members for point in result.points[node][start:])
                         for result in results]
        deviation = stdev(episode_means) if len(episode_means) > 1 else 0.0
        node = members[0]
        balanced_text = f"{balanced[node]:.6f}" if balanced is not None else ""
        print(f"{class_label(members)} {mean(episode_means):.6f} {deviation:.6f} "
              f"{network.pie / 2:.6f} {myerson[node]:.6f} {position[node]:.6f} {balanced_text}")
    deals_per_round = mean(sum(deal.round > start for deal in result.deals)
                           / (arguments.rounds - start) for result in results)
    print(f"mean_deals_per_round {deals_per_round:.6f} / {max_deals(network)}")


if __name__ == "__main__":
    main()
