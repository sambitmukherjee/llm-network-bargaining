"""Verify that going through display-name JSON preserves scripted game behaviour."""

import pytest

from llm_network_bargaining.adapters import JsonBotAdapter
from llm_network_bargaining.bots import make_bot
from llm_network_bargaining.engine import run_episode
from llm_network_bargaining.names import assign_names
from llm_network_bargaining.networks import get_network
from llm_network_bargaining.observation import KnowledgeSetting


@pytest.mark.parametrize("bot", ["pass", "equal_split", "aspiration", "random"])
@pytest.mark.parametrize("identifier", ["pair", "line3", "stem", "star4", "sweep3"])
@pytest.mark.parametrize("knowledge", ["full_map", "own_links"])
def test_adapter_equivalence(bot: str, identifier: str, knowledge: KnowledgeSetting) -> None:
    """Three seeds per bot/network/setting give identical play through the adapter."""
    net = get_network(identifier)
    for seed in range(3):
        names = assign_names(net, seed)
        plain = {node: make_bot(bot, node=node, episode_seed=seed) for node in net.nodes}
        wrapped = {node: JsonBotAdapter(make_bot(bot, node=node, episode_seed=seed), names)
                   for node in net.nodes}
        before = run_episode(net, plain, knowledge=knowledge, n_rounds=12, episode_seed=seed)
        after = run_episode(net, wrapped, knowledge=knowledge, n_rounds=12, episode_seed=seed)
        assert (before.points, before.offers, before.deals) == (after.points, after.offers, after.deals)
        assert [(turn.valid, turn.reason) for turn in before.turns] == [
            (turn.valid, turn.reason) for turn in after.turns]
        for turn in after.turns:
            if not turn.auto:
                assert turn.meta["bot"] == bot
                assert turn.meta["prompt_chars"] > 0
                assert turn.meta["parse_error"] in (None, "empty")
