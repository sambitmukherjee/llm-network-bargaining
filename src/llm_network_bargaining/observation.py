"""Immutable agent-visible data, with no global IDs, orders, notes, or metadata."""

from dataclasses import dataclass
from typing import Literal

from .actions import Action, AppliedAction

KnowledgeSetting = Literal["full_map", "own_links"]
OfferStatus = Literal[
    "open", "accepted", "withdrawn", "maker_dealt", "recipient_dealt", "lapsed",
]


@dataclass(frozen=True)
class OfferView:
    """An offer involving the viewer; it deliberately has no offer ID."""

    round: int
    phase: int
    maker: str
    recipient: str
    maker_points: int
    recipient_points: int
    status: OfferStatus


@dataclass(frozen=True)
class NeighbourDeal:
    """A neighbour who dealt, with its partner shown only when permitted."""

    neighbour: str
    partner: str | None


@dataclass(frozen=True)
class MyTurn:
    """One of the viewer's turns, excluding notes and decision metadata."""

    phase: int
    requested: Action | None
    applied: AppliedAction
    valid: bool
    reason: str | None
    auto: bool


@dataclass(frozen=True)
class MyDeal:
    """The viewer's own deal, including both payoffs and who proposed it."""

    partner: str
    phase: int
    my_points: int
    partner_points: int
    i_offered: bool


@dataclass(frozen=True)
class CurrentRound:
    """The viewer's turns, offers, and visible neighbour deals so far."""

    round: int
    my_turns: tuple[MyTurn, ...]
    offers_made: tuple[OfferView, ...]
    offers_received: tuple[OfferView, ...]
    neighbour_deals: tuple[NeighbourDeal, ...]


@dataclass(frozen=True)
class PastRound:
    """A complete permitted history of one finished round."""

    round: int
    my_turns: tuple[MyTurn, ...]
    offers_made: tuple[OfferView, ...]
    offers_received: tuple[OfferView, ...]
    neighbour_deals: tuple[NeighbourDeal, ...]
    deal: MyDeal | None
    points: int


@dataclass(frozen=True)
class LegalActions:
    """Sorted legal partners and whether only accept or pass is allowed."""

    can_offer_to: tuple[str, ...]
    can_accept_from: tuple[str, ...]
    final_phase: bool


@dataclass(frozen=True)
class Observation:
    """Everything an agent may know when asked for its next decision."""

    agent: str
    round: int
    phase: int
    n_rounds: int
    n_phases: int
    pie: int
    knowledge: KnowledgeSetting
    neighbours: tuple[str, ...]
    network_edges: tuple[tuple[str, str], ...] | None
    total_points: int
    current: CurrentRound
    history: tuple[PastRound, ...]
    legal: LegalActions

    @property
    def open_offers_to_me(self) -> tuple[OfferView, ...]:
        """Return the current open offers addressed to this agent."""
        return tuple(offer for offer in self.current.offers_received if offer.status == "open")

    @property
    def my_open_offer(self) -> OfferView | None:
        """Return this agent's standing offer, if it has one."""
        return next((offer for offer in self.current.offers_made if offer.status == "open"), None)
