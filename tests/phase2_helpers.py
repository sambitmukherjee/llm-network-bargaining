"""Small recording agents and assertions shared by the Phase 2 tests."""

from collections.abc import Mapping, Sequence

from llm_network_bargaining.actions import Action, Agent, Decision
from llm_network_bargaining.bots import ScriptedBot
from llm_network_bargaining.engine import EpisodeResult, run_episode
from llm_network_bargaining.networks import Network
from llm_network_bargaining.observation import KnowledgeSetting, Observation
from llm_network_bargaining.structure import max_deals


class RecordingAgent:
    """Keep every observation actually sent to a wrapped agent."""

    def __init__(self, agent: Agent) -> None:
        self.agent = agent
        self.observations: list[Observation] = []

    def act(self, observation: Observation) -> Decision:
        """Record a snapshot and return the wrapped agent's decision."""
        self.observations.append(observation)
        return self.agent.act(observation)

    def at(self, round_number: int, phase: int) -> Observation:
        """Look up one observed turn in a scripted test."""
        return next(obs for obs in self.observations
                    if (obs.round, obs.phase) == (round_number, phase))


def scripted_episode(net: Network, scripts: Mapping[str, Mapping[tuple[int, int], Action | None]],
                     *, rounds: int = 1, knowledge: KnowledgeSetting = "full_map",
                     order: Sequence[str] | None = None) -> tuple[EpisodeResult, dict[str, RecordingAgent]]:
    """Run fixed-order scripts, passing on every unspecified turn."""
    agents = {node: RecordingAgent(ScriptedBot(scripts.get(node, {}))) for node in net.nodes}
    result = run_episode(net, agents, knowledge=knowledge, n_rounds=rounds,
                         episode_seed=0, turn_order=lambda round_number, phase: order or net.nodes)
    return result, agents


def check_observation(obs: Observation, net: Network) -> None:
    """Check the information boundaries on a current round and all past rounds."""
    assert obs.neighbours == net.neighbours(obs.agent)
    assert obs.network_edges == (net.edges if obs.knowledge == "full_map" else None)
    assert len(obs.history) == obs.round - 1
    assert obs.total_points == sum(past.points for past in obs.history)
    assert tuple(past.round for past in obs.history) == tuple(range(1, obs.round))
    assert obs.legal.can_offer_to == tuple(sorted(obs.legal.can_offer_to))
    assert obs.legal.can_accept_from == tuple(sorted(obs.legal.can_accept_from))
    assert obs.legal.final_phase == (obs.phase == obs.n_phases)
    if obs.legal.final_phase:
        assert obs.legal.can_offer_to == ()
    assert obs.legal.can_accept_from == tuple(sorted(offer.maker for offer in obs.open_offers_to_me))
    assert sum(offer.status == "open" for offer in obs.current.offers_made) <= 1
    for past in (*obs.history, obs.current):
        for offer in (*past.offers_made, *past.offers_received):
            assert obs.agent in (offer.maker, offer.recipient)
            assert not hasattr(offer, "offer_id")
        assert tuple(deal.neighbour for deal in past.neighbour_deals) == tuple(
            sorted(deal.neighbour for deal in past.neighbour_deals))
        for deal in past.neighbour_deals:
            assert deal.neighbour in obs.neighbours
            if obs.knowledge == "own_links":
                assert deal.partner is None or deal.partner in obs.neighbours
        assert tuple(turn.phase for turn in past.my_turns) == tuple(sorted(turn.phase for turn in past.my_turns))
        for turn in past.my_turns:
            assert not hasattr(turn, "meta")
            assert turn.requested is None or turn.requested.note is None
    for past in obs.history:
        assert all(offer.status != "open" for offer in (*past.offers_made, *past.offers_received))
        if past.deal is not None:
            assert past.deal.my_points == past.points
            assert past.deal.partner not in {deal.neighbour for deal in past.neighbour_deals}


def check_result(result: EpisodeResult, net: Network) -> None:
    """Check matching, point conservation, statuses, turn indices, and done agents."""
    maximum = max_deals(net)
    for round_number in range(1, result.n_rounds + 1):
        deals = [deal for deal in result.deals if deal.round == round_number]
        used = set()
        expected = {node: 0 for node in net.nodes}
        for deal in deals:
            assert tuple(sorted((deal.maker, deal.recipient))) in net.edges
            assert not used.intersection((deal.maker, deal.recipient))
            used.update((deal.maker, deal.recipient))
            assert 0 <= deal.maker_points <= net.pie
            assert 0 <= deal.recipient_points <= net.pie
            assert deal.maker_points + deal.recipient_points == net.pie
            expected[deal.maker] = deal.maker_points
            expected[deal.recipient] = deal.recipient_points
            acceptance = next(turn for turn in result.turns if turn.deal == deal)
            assert not any(turn.round == round_number and turn.agent in (deal.maker, deal.recipient)
                           and turn.turn_index > acceptance.turn_index for turn in result.turns)
        assert len(deals) <= maximum
        assert {node: result.points[node][round_number - 1] for node in net.nodes} == expected
        assert sum(expected.values()) == net.pie * len(deals)
    assert result.totals == {node: sum(values) for node, values in result.points.items()}
    assert all(offer.status != "open" for offer in result.offers)
    assert tuple(offer.offer_id for offer in result.offers) == tuple(range(len(result.offers)))
    assert tuple(turn.turn_index for turn in result.turns) == tuple(range(len(result.turns)))
    assert len(result.turn_orders) == result.n_rounds * result.n_phases
    assert all(sorted(order) == sorted(net.nodes) for order in result.turn_orders)
    for turn in result.turns:
        if turn.auto:
            assert turn.requested is None and turn.applied == "pass"
            assert turn.valid and turn.reason is None
        if not turn.valid:
            assert turn.reason is not None and turn.applied == "pass"
