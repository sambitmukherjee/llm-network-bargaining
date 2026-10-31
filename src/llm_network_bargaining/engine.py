"""A turn-by-turn exchange game, with private observations and complete events."""

from collections.abc import Callable, Iterator, Mapping, Sequence
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
import json
from typing import Any

from .actions import Action, Agent, AppliedAction, Decision, validate
from .networks import Network
from .observation import (
    CurrentRound, KnowledgeSetting, LegalActions, MyDeal, MyTurn, NeighbourDeal,
    Observation, OfferStatus, OfferView, PastRound,
)
from .seeds import derive_seed, make_rng

TurnOrder = Callable[[int, int], Sequence[str]]


@dataclass(frozen=True)
class OfferRecord:
    """An offer and its final status; IDs are private to the engine and results."""

    offer_id: int
    round: int
    phase: int
    maker: str
    recipient: str
    maker_points: int
    recipient_points: int
    status: OfferStatus


@dataclass(frozen=True)
class DealRecord:
    """One accepted offer and the resulting payoffs."""

    round: int
    phase: int
    offer_id: int
    maker: str
    recipient: str
    maker_points: int
    recipient_points: int


@dataclass(frozen=True)
class TurnRecord:
    """A requested move, its validity, its effect, and private agent metadata."""

    turn_index: int
    round: int
    phase: int
    slot: int
    agent: str
    auto: bool
    requested: Action | None
    applied: AppliedAction
    valid: bool
    reason: str | None
    meta: Mapping[str, Any]
    offer_id: int | None
    deal: DealRecord | None


@dataclass(frozen=True)
class PendingTurn:
    """A turn awaiting a decision; only its observation is passed to agents."""

    turn_index: int
    round: int
    phase: int
    slot: int
    agent: str
    observation: Observation


def _requested_dict(action: Action | None) -> dict[str, Any] | None:
    if action is None:
        return None
    requested = {}
    for name in ("kind", "to", "my_points", "note"):
        value = getattr(action, name)
        try:
            requested[name] = json.loads(json.dumps(value, allow_nan=False))
        except (TypeError, ValueError, OverflowError):
            requested[name] = repr(value)
    return requested


def _turn_dict(turn: TurnRecord) -> dict[str, Any]:
    return dict(
        turn_index=turn.turn_index, round=turn.round, phase=turn.phase,
        slot=turn.slot, agent=turn.agent, auto=turn.auto,
        requested=_requested_dict(turn.requested), applied=turn.applied,
        valid=turn.valid, reason=turn.reason, meta=deepcopy(dict(turn.meta)),
        offer_id=turn.offer_id, deal=asdict(turn.deal) if turn.deal else None,
    )


@dataclass(frozen=True)
class EpisodeResult:
    """All outcomes and events from a finished episode, without writing files."""

    network_id: str
    knowledge: KnowledgeSetting
    n_rounds: int
    n_phases: int
    episode_seed: int
    turn_orders: tuple[tuple[str, ...], ...]
    points: dict[str, tuple[int, ...]]
    totals: dict[str, int]
    offers: tuple[OfferRecord, ...]
    deals: tuple[DealRecord, ...]
    turns: tuple[TurnRecord, ...]
    events: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        """Return independent JSON-ready data, including safe malformed requests."""
        data = dict(
            network_id=self.network_id, knowledge=self.knowledge,
            n_rounds=self.n_rounds, n_phases=self.n_phases, episode_seed=self.episode_seed,
            turn_orders=self.turn_orders, points=self.points, totals=self.totals,
            offers=[asdict(offer) for offer in self.offers],
            deals=[asdict(deal) for deal in self.deals],
            turns=[_turn_dict(turn) for turn in self.turns], events=self.events,
        )
        # JSON normalises tuples to lists, including any inside opaque metadata.
        return json.loads(json.dumps(data, allow_nan=False))


class Episode:
    """Run one exchange episode, pausing whenever an agent must choose a move.

    ``next_turn()`` performs automatic bookkeeping and returns a pending turn.
    ``submit()`` applies exactly one decision. Calling ``next_turn()`` again
    before submitting returns the same pending turn, without advancing play.
    """

    def __init__(self, network: Network, *, knowledge: KnowledgeSetting,
                 n_rounds: int, episode_seed: int, n_phases: int = 3,
                 turn_order: TurnOrder | None = None) -> None:
        if network.kind != "exchange":
            raise ValueError("The broker protocol arrives in Phase 8.")
        if knowledge not in ("full_map", "own_links"):
            raise ValueError("Knowledge setting must be 'full_map' or 'own_links'.")
        if n_rounds < 1:
            raise ValueError("n_rounds must be at least 1.")
        if n_phases < 2:
            raise ValueError("n_phases must be at least 2.")
        self.network = network
        self.knowledge = knowledge
        self.n_rounds = n_rounds
        self.n_phases = n_phases
        self.episode_seed = episode_seed
        self._turn_order = turn_order
        self._rng = make_rng(derive_seed(episode_seed, "turn_order"))
        self._neighbours = {node: network.neighbours(node) for node in network.nodes}
        self._points: dict[str, list[int]] = {node: [] for node in network.nodes}
        self._totals = {node: 0 for node in network.nodes}
        self._history: dict[str, list[PastRound]] = {node: [] for node in network.nodes}
        self._orders: list[tuple[str, ...]] = []
        self._offers: list[OfferRecord] = []
        self._deals: list[DealRecord] = []
        self._turns: list[TurnRecord] = []
        self._events: list[dict[str, Any]] = []
        self._pending: PendingTurn | None = None
        self._finished = False
        self._round = 0
        self._phase = 0
        self._slot = 0
        self._done: set[str] = set()
        self._open: dict[str, int] = {}  # maker -> its only open offer ID
        self._round_offers: list[int] = []
        self._round_deals: list[DealRecord] = []
        self._round_turns: list[TurnRecord] = []
        self._round_points = {node: 0 for node in network.nodes}
        self._event("episode_start", network_id=network.id, knowledge=knowledge,
                    n_rounds=n_rounds, n_phases=n_phases, episode_seed=episode_seed)
        self._steps = self._play()

    @property
    def finished(self) -> bool:
        """Whether all rounds and final bookkeeping have completed."""
        return self._finished

    def next_turn(self) -> PendingTurn | None:
        """Advance to a decision, or return the existing pending turn or None."""
        if self._pending is None and not self.finished:
            self._pending = next(self._steps, None)
        return self._pending

    def submit(self, decision: Decision) -> TurnRecord:
        """Validate and apply the pending decision; reject invalid metadata."""
        if self._pending is None:
            raise RuntimeError("There is no pending turn to submit.")
        try:
            meta = deepcopy(dict(decision.meta))
            json.dumps(meta, allow_nan=False)
        except (TypeError, ValueError, OverflowError) as error:
            raise TypeError("Decision.meta must be JSON-serialisable.") from error
        reason = validate(decision.action, self._pending.observation)
        record = self._apply(self._pending.agent, decision.action, meta,
                             auto=False, reason=reason)
        self._pending = None
        return record

    def result(self) -> EpisodeResult:
        """Return final records, or raise if play has not finished."""
        if not self.finished:
            raise RuntimeError("The episode is not finished.")
        return EpisodeResult(
            network_id=self.network.id, knowledge=self.knowledge,
            n_rounds=self.n_rounds, n_phases=self.n_phases, episode_seed=self.episode_seed,
            turn_orders=tuple(self._orders),
            points={node: tuple(values) for node, values in self._points.items()},
            totals=dict(self._totals), offers=tuple(self._offers), deals=tuple(self._deals),
            turns=tuple(self._turns), events=tuple(deepcopy(self._events)),
        )

    def _event(self, kind: str, **fields: Any) -> None:
        self._events.append({"type": kind, **fields})

    def _play(self) -> Iterator[PendingTurn]:
        for round_number in range(1, self.n_rounds + 1):
            self._round = round_number
            self._done = set()
            self._round_offers = []
            self._round_deals = []
            self._round_turns = []
            self._round_points = {node: 0 for node in self.network.nodes}
            for phase in range(1, self.n_phases + 1):
                self._phase = phase
                order = self._new_order()
                self._orders.append(order)
                self._event("phase_start", round=self._round, phase=phase, order=list(order))
                for slot, node in enumerate(order, start=1):
                    self._slot = slot
                    if node in self._done:
                        continue
                    observation = self._observation(node)
                    if not observation.legal.can_offer_to and not observation.legal.can_accept_from:
                        self._apply(node, None, {}, auto=True, reason=None)
                    else:
                        yield PendingTurn(turn_index=len(self._turns), round=self._round,
                                          phase=phase, slot=slot, agent=node,
                                          observation=observation)
            self._end_round()
        self._event("episode_end", totals=dict(self._totals))
        self._finished = True

    def _new_order(self) -> tuple[str, ...]:
        nodes = self.network.nodes
        if self._turn_order is None:
            return tuple(nodes[i] for i in self._rng.permutation(len(nodes)))
        try:
            order = tuple(self._turn_order(self._round, self._phase))
        except TypeError as error:
            raise ValueError("turn_order must return a permutation of all network nodes.") from error
        if len(order) != len(nodes) or any(order.count(node) != 1 for node in nodes):
            raise ValueError("turn_order must return a permutation of all network nodes.")
        return order

    def _apply(self, node: str, requested: Action | None, meta: Mapping[str, Any], *,
               auto: bool, reason: str | None) -> TurnRecord:
        applied: AppliedAction = "pass"
        if not auto and reason is None and requested is not None:
            applied = requested.kind  # validation has checked the action kind
        offer_id = len(self._offers) if applied == "offer" else None
        deal = None
        if applied == "accept":
            assert requested is not None and requested.to is not None
            offer = self._offers[self._open[requested.to]]
            deal = DealRecord(self._round, self._phase, offer.offer_id, offer.maker,
                              node, offer.maker_points, offer.recipient_points)
        record = TurnRecord(
            turn_index=len(self._turns), round=self._round, phase=self._phase,
            slot=self._slot, agent=node, auto=auto, requested=requested,
            applied=applied, valid=reason is None, reason=reason,
            meta=meta, offer_id=offer_id, deal=deal,
        )
        self._turns.append(record)
        self._round_turns.append(record)
        event = _turn_dict(record)
        event.pop("offer_id")
        event.pop("deal")
        self._event("turn", **event)
        if applied == "offer":
            assert requested is not None and requested.to is not None
            if node in self._open:
                self._set_status(self._open[node], "withdrawn")
            assert offer_id is not None
            offer = OfferRecord(offer_id, self._round, self._phase, node, requested.to,
                                requested.my_points, self.network.pie - requested.my_points, "open")
            self._offers.append(offer)
            self._round_offers.append(offer_id)
            self._open[node] = offer_id
            fields = asdict(offer)
            fields.pop("status")
            self._event("offer", **fields)
        elif deal is not None:
            self._close_deal(deal)
        return record

    def _set_status(self, offer_id: int, status: OfferStatus) -> None:
        offer = self._offers[offer_id]
        self._offers[offer_id] = replace(offer, status=status)
        self._open.pop(offer.maker)
        self._event("offer_status", offer_id=offer_id, status=status)

    def _close_deal(self, deal: DealRecord) -> None:
        self._deals.append(deal)
        self._round_deals.append(deal)
        partners = (deal.maker, deal.recipient)
        self._done.update(partners)
        self._round_points[deal.maker] = deal.maker_points
        self._round_points[deal.recipient] = deal.recipient_points
        self._event("deal", **asdict(deal))
        for offer_id in sorted(self._open.values()):
            offer = self._offers[offer_id]
            if offer_id == deal.offer_id:
                self._set_status(offer_id, "accepted")
            elif offer.maker in partners:
                self._set_status(offer_id, "maker_dealt")
            elif offer.recipient in partners:
                self._set_status(offer_id, "recipient_dealt")

    def _current_view(self, node: str) -> CurrentRound:
        made, received = [], []
        for offer_id in self._round_offers:
            offer = self._offers[offer_id]
            if node not in (offer.maker, offer.recipient):
                continue
            view = OfferView(offer.round, offer.phase, offer.maker, offer.recipient,
                             offer.maker_points, offer.recipient_points, offer.status)
            (made if offer.maker == node else received).append(view)
        my_turns = tuple(
            MyTurn(turn.phase, replace(turn.requested, note=None) if turn.requested else None,
                   turn.applied, turn.valid, turn.reason, turn.auto)
            for turn in self._round_turns if turn.agent == node
        )
        neighbours = self._neighbours[node]
        neighbour_deals = []
        for deal in self._round_deals:
            if node in (deal.maker, deal.recipient):
                continue  # my own partner belongs only in MyDeal
            for neighbour, partner in ((deal.maker, deal.recipient), (deal.recipient, deal.maker)):
                if neighbour in neighbours:
                    visible = self.knowledge == "full_map" or partner in neighbours
                    neighbour_deals.append(NeighbourDeal(neighbour, partner if visible else None))
        return CurrentRound(
            round=self._round, my_turns=my_turns,
            offers_made=tuple(made), offers_received=tuple(received),
            neighbour_deals=tuple(sorted(neighbour_deals, key=lambda deal: deal.neighbour)),
        )

    def _observation(self, node: str) -> Observation:
        current = self._current_view(node)
        final = self._phase == self.n_phases
        legal = LegalActions(
            can_offer_to=() if final else tuple(
                neighbour for neighbour in self._neighbours[node] if neighbour not in self._done),
            can_accept_from=tuple(sorted(
                offer.maker for offer in current.offers_received if offer.status == "open")),
            final_phase=final,
        )
        return Observation(
            agent=node, round=self._round, phase=self._phase,
            n_rounds=self.n_rounds, n_phases=self.n_phases, pie=self.network.pie,
            knowledge=self.knowledge, neighbours=self._neighbours[node],
            network_edges=self.network.edges if self.knowledge == "full_map" else None,
            total_points=self._totals[node], current=current,
            history=tuple(self._history[node]), legal=legal,
        )

    def _my_deal(self, node: str) -> MyDeal | None:
        for deal in self._round_deals:
            if node == deal.maker:
                return MyDeal(deal.recipient, deal.phase, deal.maker_points, deal.recipient_points, True)
            if node == deal.recipient:
                return MyDeal(deal.maker, deal.phase, deal.recipient_points, deal.maker_points, False)
        return None

    def _end_round(self) -> None:
        for offer_id in sorted(self._open.values()):
            self._set_status(offer_id, "lapsed")
        used = set()
        for deal in self._round_deals:
            edge = tuple(sorted((deal.maker, deal.recipient)))
            assert edge in self.network.edges, "Deal is not on a network link."
            assert not used.intersection(edge), "Agent closed two deals in one round."
            used.update((deal.maker, deal.recipient))
            assert (0 <= deal.maker_points <= self.network.pie
                    and 0 <= deal.recipient_points <= self.network.pie), "Deal points are outside the pie."
            assert deal.maker_points + deal.recipient_points == self.network.pie, (
                "Deal points do not sum to the pie.")
        expected_points = self.network.pie * len(self._round_deals)
        assert sum(self._round_points.values()) == expected_points, "Round points do not match the deals."
        for node in self.network.nodes:
            points = self._round_points[node]
            self._points[node].append(points)
            self._totals[node] += points
            current = self._current_view(node)
            self._history[node].append(PastRound(
                round=self._round, my_turns=current.my_turns,
                offers_made=current.offers_made, offers_received=current.offers_received,
                neighbour_deals=current.neighbour_deals, deal=self._my_deal(node), points=points,
            ))
        self._event("round_end", round=self._round, points=dict(self._round_points))


def run_episode(network: Network, agents: Mapping[str, Agent], *,
                knowledge: KnowledgeSetting, n_rounds: int, episode_seed: int,
                n_phases: int = 3, turn_order: TurnOrder | None = None) -> EpisodeResult:
    """Run synchronous agents to completion; let agent exceptions reach the caller."""
    if set(agents) != set(network.nodes):
        raise ValueError("agents must cover every network node exactly, with no extra nodes.")
    episode = Episode(network, knowledge=knowledge, n_rounds=n_rounds,
                      episode_seed=episode_seed, n_phases=n_phases, turn_order=turn_order)
    while (pending := episode.next_turn()) is not None:
        episode.submit(agents[pending.agent].act(pending.observation))
    return episode.result()
