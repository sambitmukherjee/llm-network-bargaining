"""Step API, validation precedence, private data, and deterministic turn orders."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, asdict, fields, replace
import json
from typing import Any

import pytest

from llm_network_bargaining.actions import Action, Decision, validate
from llm_network_bargaining.bots import PassBot, make_bot
from llm_network_bargaining.engine import Episode, EpisodeResult, run_episode
from llm_network_bargaining.networks import Network, get_network, list_networks
from llm_network_bargaining import observation as observations
from llm_network_bargaining.observation import Observation
from llm_network_bargaining.seeds import derive_seed, make_rng
from phase2_helpers import RecordingAgent, scripted_episode


def _episode() -> Episode:
    return Episode(get_network("pair"), knowledge="full_map", n_rounds=1,
                   episode_seed=0, turn_order=lambda round_number, phase: ("A", "B"))


def _run(bot: str, seed: int = 0) -> EpisodeResult:
    net = get_network("sweep3")
    agents = {node: make_bot(bot, node=node, episode_seed=seed) for node in net.nodes}
    return run_episode(net, agents, knowledge="full_map", n_rounds=12, episode_seed=seed)


def test_pending_turn_and_completion() -> None:
    """The API is idempotent while waiting and rejects calls in the wrong state."""
    episode = _episode()
    assert not episode.finished
    with pytest.raises(RuntimeError, match="not finished"):
        episode.result()
    with pytest.raises(RuntimeError, match="no pending"):
        episode.submit(Decision(Action("pass")))
    pending = episode.next_turn()
    assert pending is not None and pending is episode.next_turn()
    assert (pending.turn_index, pending.round, pending.phase, pending.slot, pending.agent) == (0, 1, 1, 1, "A")
    episode.submit(Decision(Action("pass")))
    while episode.next_turn() is not None:
        episode.submit(Decision(Action("pass")))
    assert episode.finished and episode.next_turn() is None
    result = episode.result()
    assert len(result.turns) == 6
    assert [turn.auto for turn in result.turns] == [False, False, False, False, True, True]
    assert result.totals == {"A": 0, "B": 0}
    with pytest.raises(RuntimeError):
        episode.submit(Decision(None))


def test_turn_orders_are_independent_of_play() -> None:
    """All phases draw fresh permutations, including phases with no live agents."""
    passed, random = _run("pass"), _run("random")
    assert passed.turn_orders == random.turn_orders
    assert passed.turn_orders != _run("pass", seed=1).turn_orders
    rng = make_rng(derive_seed(0, "turn_order"))
    nodes = get_network("sweep3").nodes
    expected = tuple(tuple(nodes[i] for i in rng.permutation(len(nodes))) for _ in range(36))
    assert passed.turn_orders == expected
    assert all(sorted(order) == sorted(nodes) for order in passed.turn_orders)


@pytest.mark.parametrize("order", [("A",), ("A", "A"), ("A", "B", "C"), ("A", "ZZZ"), None, ("A", 1)])
def test_invalid_injected_order(order: Any) -> None:
    """An injected order must be a permutation of all canonical node labels."""
    episode = Episode(get_network("pair"), knowledge="full_map", n_rounds=1,
                       episode_seed=0, turn_order=lambda round_number, phase: order)
    with pytest.raises(ValueError, match="permutation"):
        episode.next_turn()


@pytest.mark.parametrize("kwargs,message", [
    ({"knowledge": "unknown"}, "Knowledge setting"),
    ({"n_rounds": 0}, "n_rounds"), ({"n_phases": 1}, "n_phases"),
])
def test_episode_rejects_invalid_settings(kwargs: dict[str, Any], message: str) -> None:
    """Invalid game settings fail before play begins."""
    settings = dict(knowledge="full_map", n_rounds=1, episode_seed=0)
    settings.update(kwargs)
    with pytest.raises(ValueError, match=message):
        Episode(get_network("pair"), **settings)


def test_broker_protocol_and_agent_coverage() -> None:
    """The current engine rejects brokers and incomplete or excessive agent sets."""
    with pytest.raises(ValueError, match="future work"):
        Episode(get_network("broker_parallel_1"), knowledge="full_map", n_rounds=1, episode_seed=0)
    for names in (("A",), ("A", "B", "C")):
        with pytest.raises(ValueError, match="every network node exactly"):
            run_episode(get_network("pair"), {node: PassBot() for node in names},
                        knowledge="full_map", n_rounds=1, episode_seed=0)


def test_agent_errors_are_not_swallowed() -> None:
    """Agent exceptions remain available to the future episode runner."""
    class BrokenAgent:
        """A deliberately failing agent."""

        def act(self, observation: Observation) -> Decision:
            """Raise a distinctive exception on the first actual call."""
            raise LookupError("agent failed")

    with pytest.raises(LookupError, match="agent failed"):
        run_episode(get_network("pair"), {"A": BrokenAgent(), "B": BrokenAgent()},
                    knowledge="full_map", n_rounds=1, episode_seed=0)


def test_validation_precedence() -> None:
    """The first failed rule wins even when a request violates several rules."""
    pending = _episode().next_turn()
    assert pending is not None
    obs = pending.observation
    final = replace(obs, legal=replace(obs.legal, final_phase=True, can_offer_to=()))
    done = replace(obs, legal=replace(obs.legal, can_offer_to=()))
    assert validate(Action("dance", "ZZZ", -1), final) == "unknown_action"
    assert validate(Action("pass", "ZZZ", object()), final) is None
    assert validate(Action("offer", "ZZZ", -1), final) == "offer_in_final_phase"
    assert validate(Action("offer", "ZZZ", -1), obs) == "not_a_neighbour"
    assert validate(Action("offer", "B", -1), done) == "neighbour_done"
    assert validate(Action("offer", "B", -1), obs) == "bad_points"


def test_metadata_is_copied_without_reaching_observations() -> None:
    """Metadata stays intact in records and events; notes never enter observations."""
    episode = Episode(get_network("pair"), knowledge="full_map", n_rounds=2,
                       episode_seed=0, turn_order=lambda round_number, phase: ("A", "B"))
    pending = episode.next_turn()
    assert pending is not None
    meta = {"raw": "private raw reply", "tokens": {"input": [10, 20]}, "latency_s": 0.9}
    record = episode.submit(Decision(Action("offer", "B", 14, "private note"), meta))
    assert record.meta == meta
    meta["tokens"]["input"].append(30)
    assert record.meta["tokens"]["input"] == [10, 20]
    pending = episode.next_turn()
    assert pending is not None
    episode.submit(Decision(Action("accept", "A", note="another private note"), {"refusal": None}))
    while (pending := episode.next_turn()) is not None:
        text = json.dumps(asdict(pending.observation))
        assert "private" not in text and "latency" not in text and "tokens" not in text
        episode.submit(Decision(Action("pass")))
    result = episode.result()
    event = next(event for event in result.events if event["type"] == "turn")
    assert event["meta"] == record.meta
    assert event["requested"]["note"] == "private note"


@pytest.mark.parametrize("meta", [{"bad": {1, 2}}, {"bad": object()}, {"bad": float("nan")}])
def test_invalid_metadata_does_not_consume_the_pending_turn(meta: dict[str, Any]) -> None:
    """Non-JSON metadata is a caller error and must not partly apply a move."""
    episode = _episode()
    pending = episode.next_turn()
    with pytest.raises(TypeError, match="JSON-serialisable"):
        episode.submit(Decision(Action("offer", "B", 12), meta))
    assert episode.next_turn() is pending
    record = episode.submit(Decision(Action("pass")))
    assert record.turn_index == 0


def test_non_json_request_values_are_recorded_as_repr() -> None:
    """Malformed game content cannot break the result's JSON serialisation."""
    value = object()
    result, _ = scripted_episode(get_network("pair"), {"A": {(1, 1): Action("offer", "B", value)}})
    data = result.to_dict()
    assert data["turns"][0]["requested"]["my_points"] == repr(value)
    assert data == json.loads(json.dumps(data))
    assert result.turns[0].reason == "bad_points"


EXPECTED_FIELDS = {
    "OfferView": "round phase maker recipient maker_points recipient_points status",
    "NeighbourDeal": "neighbour partner",
    "MyTurn": "phase requested applied valid reason auto",
    "MyDeal": "partner phase my_points partner_points i_offered",
    "CurrentRound": "round my_turns offers_made offers_received neighbour_deals",
    "PastRound": "round my_turns offers_made offers_received neighbour_deals deal points",
    "LegalActions": "can_offer_to can_accept_from final_phase",
    "Observation": "agent round phase n_rounds n_phases pie knowledge neighbours network_edges total_points current history legal",
}


@pytest.mark.parametrize("name,expected", EXPECTED_FIELDS.items())
def test_observation_dataclass_fields(name: str, expected: str) -> None:
    """Observation schemas are exact contracts for Phase 3."""
    cls = getattr(observations, name)
    assert [field.name for field in fields(cls)] == expected.split()
    assert cls.__dataclass_params__.frozen


def test_observation_snapshots_are_frozen_and_do_not_change_later() -> None:
    """An earlier snapshot retains open status after the same offer is accepted."""
    result, agents = scripted_episode(get_network("pair"), {
        "A": {(1, 1): Action("offer", "B", 12)}, "B": {(1, 1): Action("accept", "A")},
    })
    obs = agents["B"].at(1, 1)
    assert obs.open_offers_to_me[0].status == "open"
    assert result.offers[0].status == "accepted"
    assert isinstance(obs.history, tuple) and isinstance(obs.current.offers_received, tuple)
    with pytest.raises(FrozenInstanceError):
        obs.round = 99  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        obs.current.round = 99  # type: ignore[misc]


@pytest.mark.parametrize("net", [net for net in list_networks() if net.kind == "exchange"], ids=lambda net: net.id)
def test_pass_bots_are_called_only_in_offering_phases(net: Network) -> None:
    """Pass bots receive exactly two calls per round, with forced final passes."""
    agents = {node: RecordingAgent(PassBot()) for node in net.nodes}
    result = run_episode(net, agents, knowledge="full_map", n_rounds=12, episode_seed=42)
    assert result.deals == ()
    for agent in agents.values():
        assert len(agent.observations) == 24
        assert {obs.phase for obs in agent.observations} == {1, 2}


def test_two_phase_games_and_pie_boundaries() -> None:
    """The engine also supports a two-phase game and 0/pie offer endpoints."""
    for points in (0, 24):
        episode = Episode(get_network("pair"), knowledge="full_map", n_rounds=1,
                           episode_seed=0, n_phases=2, turn_order=lambda round_number, phase: ("A", "B"))
        episode.next_turn()
        episode.submit(Decision(Action("offer", "B", points)))
        episode.next_turn()
        episode.submit(Decision(Action("accept", "A")))
        assert episode.next_turn() is None
        assert episode.result().totals == {"A": points, "B": 24 - points}


def test_episodes_have_no_shared_random_state() -> None:
    """Running independent episodes in threads matches their sequential results."""
    expected = [_run("random", seed).to_dict() for seed in range(3)]
    with ThreadPoolExecutor(max_workers=3) as pool:
        actual = list(pool.map(lambda seed: _run("random", seed).to_dict(), range(3)))
    assert actual == expected
