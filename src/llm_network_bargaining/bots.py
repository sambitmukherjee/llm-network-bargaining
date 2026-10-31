"""Small observation-only agents for offline checks and dry runs."""

from collections.abc import Mapping
from typing import Any

import numpy as np

from .actions import Action, Agent, Decision
from .observation import Observation, OfferView
from .seeds import derive_seed, make_rng


def _best_offer(observation: Observation) -> OfferView | None:
    return min(observation.open_offers_to_me,
               key=lambda offer: (-offer.recipient_points, offer.phase, offer.maker),
               default=None)


class PassBot:
    """Always pass, regardless of the available moves."""

    def act(self, observation: Observation) -> Decision:
        """Return a pass with the bot's name as private metadata."""
        return Decision(Action("pass"), meta={"bot": "pass"})


class EqualSplitBot:
    """Propose half the pie and accept offers worth at least half."""

    def act(self, observation: Observation) -> Decision:
        """Accept a fair offer, propose once to the first legal neighbour, or pass."""
        half = observation.pie // 2
        offer = _best_offer(observation)
        action = Action("pass")
        if offer is not None and offer.recipient_points >= half:
            action = Action("accept", to=offer.maker)
        elif (not observation.legal.final_phase and observation.my_open_offer is None
              and observation.legal.can_offer_to):
            action = Action("offer", to=observation.legal.can_offer_to[0], my_points=half)
        return Decision(action, meta={"bot": "equal_split"})


class AspirationBot:
    """Learn a desired payoff from local history, without consulting the map."""

    def __init__(self, rng: np.random.Generator, *, start: int = 12, step: int = 1,
                 floor: int = 1, ceiling: int = 23, slack: int = 3) -> None:
        self.rng = rng
        self.start = start
        self.step = step
        self.floor = floor
        self.ceiling = ceiling
        self.slack = slack

    def act(self, observation: Observation) -> Decision:
        """Recompute aspiration from every past round and choose one local move."""
        aspiration = self.start
        for past in observation.history:
            if past.deal is None:
                aspiration = max(self.floor, aspiration - self.step)
            elif past.points >= aspiration and len({offer.maker for offer in past.offers_received}) >= 2:
                aspiration = min(self.ceiling, aspiration + self.step)
        threshold = aspiration
        if observation.legal.final_phase:
            threshold = max(self.floor, aspiration - self.slack)
        offer = _best_offer(observation)
        action = Action("pass")
        if offer is not None and offer.recipient_points >= threshold:
            action = Action("accept", to=offer.maker)
        elif (not observation.legal.final_phase and observation.my_open_offer is None
              and observation.legal.can_offer_to):
            targets = observation.legal.can_offer_to
            target = targets[int(self.rng.integers(len(targets)))]
            action = Action("offer", to=target, my_points=aspiration)
        return Decision(action, meta={"bot": "aspiration"})


class RandomBot:
    """Choose random legal moves, occasionally injecting a malformed request."""

    def __init__(self, rng: np.random.Generator, *, p_invalid: float = 0.1) -> None:
        if not 0 <= p_invalid <= 1:
            raise ValueError("p_invalid must be between 0 and 1.")
        self.rng = rng
        self.p_invalid = p_invalid

    def act(self, observation: Observation) -> Decision:
        """Draw one request from the specified legal or invalid choices."""
        if self.rng.random() < self.p_invalid:
            neighbour = observation.neighbours[0]
            requests = (
                Action("offer", "ZZZ", 12), Action("offer", neighbour, 25),
                Action("offer", neighbour, 12.5), Action("accept", "ZZZ"),
                Action("dance"), None,
            )
            action = requests[int(self.rng.integers(len(requests)))]
            return Decision(action, meta={"bot": "random"})
        kinds = ["pass"]
        if observation.legal.can_offer_to:
            kinds.append("offer")
        if observation.legal.can_accept_from:
            kinds.append("accept")
        kind = kinds[int(self.rng.integers(len(kinds)))]
        action = Action(kind)
        if kind == "offer":
            targets = observation.legal.can_offer_to
            action = Action(kind, targets[int(self.rng.integers(len(targets)))],
                            int(self.rng.integers(observation.pie + 1)))
        elif kind == "accept":
            makers = observation.legal.can_accept_from
            action = Action(kind, makers[int(self.rng.integers(len(makers)))])
        return Decision(action, meta={"bot": "random"})


class ScriptedBot:
    """Return test requests keyed by (round, phase), passing when absent."""

    def __init__(self, script: Mapping[tuple[int, int], Action | None]) -> None:
        self.script = dict(script)

    def act(self, observation: Observation) -> Decision:
        """Look up this turn's request without retaining game state."""
        action = self.script.get((observation.round, observation.phase), Action("pass"))
        return Decision(action, meta={"bot": "scripted"})


def make_bot(name: str, *, node: str, episode_seed: int, **params: Any) -> Agent:
    """Build a named bot, deriving an independent RNG for each node if needed."""
    if name == "pass":
        if params:
            raise TypeError("PassBot does not accept parameters.")
        return PassBot()
    if name == "equal_split":
        if params:
            raise TypeError("EqualSplitBot does not accept parameters.")
        return EqualSplitBot()
    rng = make_rng(derive_seed(episode_seed, "bot", node))
    if name == "aspiration":
        return AspirationBot(rng, **params)
    if name == "random":
        return RandomBot(rng, **params)
    raise ValueError(f"Unknown bot {name!r}; choose pass, equal_split, aspiration, or random.")
