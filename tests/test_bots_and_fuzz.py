"""End-to-end bot behaviour, privacy checks, fuzzing, and reproducibility."""

from dataclasses import replace
import json
from statistics import mean
from time import perf_counter

import pytest

from llm_network_bargaining.actions import Action, Decision
from llm_network_bargaining.bots import EqualSplitBot, make_bot
from llm_network_bargaining.engine import EpisodeResult, run_episode
from llm_network_bargaining.networks import Network, get_network, list_networks
from llm_network_bargaining.observation import KnowledgeSetting, OfferView
from llm_network_bargaining.seeds import derive_seed
from phase2_helpers import RecordingAgent, check_observation, check_result, scripted_episode

EXCHANGE = tuple(net for net in list_networks() if net.kind == "exchange")


def _play(net: Network, bot: str, seed: int, rounds: int = 24,
          knowledge: KnowledgeSetting = "full_map") -> EpisodeResult:
    agents = {node: make_bot(bot, node=node, episode_seed=seed) for node in net.nodes}
    return run_episode(net, agents, knowledge=knowledge, n_rounds=rounds, episode_seed=seed)


@pytest.mark.parametrize("net", EXCHANGE, ids=lambda net: net.id)
@pytest.mark.parametrize("knowledge", ["full_map", "own_links"])
def test_random_fuzz(net: Network, knowledge: KnowledgeSetting) -> None:
    """Twenty seeds per graph and setting preserve all game and privacy invariants."""
    invalid_count = 0
    for seed in range(20):
        agents = {node: RecordingAgent(make_bot("random", node=node, episode_seed=seed))
                  for node in net.nodes}
        result = run_episode(net, agents, knowledge=knowledge, n_rounds=12, episode_seed=seed)
        check_result(result, net)
        for agent in agents.values():
            for observation in agent.observations:
                check_observation(observation, net)
        invalid_count += sum(not turn.valid for turn in result.turns)
    assert invalid_count > 0


@pytest.mark.parametrize("identifier", ["pair", "line3", "star3", "line4"])
def test_aspiration_behaviour(identifier: str) -> None:
    """The local learner meets the brief's fixed, independently supplied thresholds."""
    net = get_network(identifier)
    results = [_play(net, "aspiration", derive_seed(2026, identifier, i)) for i in range(10)]
    means = {node: mean(point for result in results for point in result.points[node][12:])
             for node in net.nodes}
    if identifier == "pair":
        assert all(result.points[node] == (12,) * 24 for result in results for node in net.nodes)
    elif identifier == "line3":
        assert means["B"] >= 16
        assert means["A"] <= 6 and means["C"] <= 6
    elif identifier == "star3":
        assert means["H"] >= 18
        assert all(means[leaf] <= 4 for leaf in ("L1", "L2", "L3"))
    else:
        assert mean((means["B"], means["C"])) - mean((means["A"], means["D"])) >= 0.5


@pytest.mark.parametrize("identifier", ["line5", "stem"])
def test_aspiration_does_not_use_the_map(identifier: str) -> None:
    """Removing the map leaves local-learner points identical at every seed."""
    net = get_network(identifier)
    for i in range(10):
        seed = derive_seed(2026, identifier, i)
        assert _play(net, "aspiration", seed).points == _play(net, "aspiration", seed, knowledge="own_links").points


@pytest.mark.parametrize("net", EXCHANGE, ids=lambda net: net.id)
def test_equal_split_deals(net: Network) -> None:
    """Equal-split bots always close 12/12 deals, and simple networks trade every round."""
    every_round = {"pair", "line3", "star3", "star4", "star5", "triangle"}
    for i in range(5):
        result = _play(net, "equal_split", derive_seed(2026, net.id, i), rounds=12)
        assert all(deal.maker_points == deal.recipient_points == 12 for deal in result.deals)
        if net.id in every_round:
            assert all(any(deal.round == round_number for deal in result.deals)
                       for round_number in range(1, 13))


@pytest.mark.parametrize("bot", ["random", "aspiration"])
def test_full_result_determinism_and_json(bot: str) -> None:
    """Re-created bots and episodes yield byte-identical serialised results."""
    net = get_network("sweep3")
    first, second = _play(net, bot, 17), _play(net, bot, 17)
    data = first.to_dict()
    assert data == json.loads(json.dumps(data))
    assert json.dumps(data, sort_keys=True) == json.dumps(second.to_dict(), sort_keys=True)


def test_twenty_four_round_episode_performance() -> None:
    """A nine-node random-bot episode completes within the specified two seconds."""
    start = perf_counter()
    _play(get_network("sweep3"), "random", 123)
    assert perf_counter() - start < 2


def test_best_offer_ties_and_bot_metadata() -> None:
    """Best offers prioritise payoff, then earlier phase, then maker label."""
    _, agents = scripted_episode(get_network("star3"), {}, order=("H", "L1", "L2", "L3"))
    obs = agents["H"].at(1, 1)
    offers = (
        OfferView(1, 2, "L1", "H", 10, 14, "open"),
        OfferView(1, 1, "L3", "H", 10, 14, "open"),
        OfferView(1, 1, "L2", "H", 10, 14, "open"),
    )
    obs = replace(obs, current=replace(obs.current, offers_received=offers))
    for name in ("equal_split", "aspiration"):
        decision = make_bot(name, node="H", episode_seed=0).act(obs)
        assert decision == Decision(Action("accept", "L2"), {"bot": name})
    better = replace(offers[0], recipient_points=15, maker_points=9)
    obs = replace(obs, current=replace(obs.current, offers_received=(better, *offers[1:])))
    assert EqualSplitBot().act(obs).action == Action("accept", "L1")
    assert make_bot("pass", node="H", episode_seed=0).act(obs).meta == {"bot": "pass"}
    with pytest.raises(ValueError, match="Unknown bot"):
        make_bot("unknown", node="H", episode_seed=0)


def test_offer_status_events_reproduce_final_statuses() -> None:
    """Append-only status events reconstruct the final offer records exactly."""
    result = _play(get_network("sweep3"), "random", 3)
    statuses = {}
    for event in result.events:
        if event["type"] == "offer":
            statuses[event["offer_id"]] = "open"
        elif event["type"] == "offer_status":
            assert statuses[event["offer_id"]] == "open"
            statuses[event["offer_id"]] = event["status"]
    assert statuses == {offer.offer_id: offer.status for offer in result.offers}
