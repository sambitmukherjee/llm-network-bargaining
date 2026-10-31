"""Game requests, private decision metadata, and shared legality checks."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol

if TYPE_CHECKING:
    from .observation import Observation

AppliedAction = Literal["offer", "accept", "pass"]
ReasonCode = Literal[
    "no_action", "unknown_action", "offer_in_final_phase", "not_a_neighbour",
    "neighbour_done", "bad_points", "no_open_offer",
]


@dataclass(frozen=True)
class Action:
    """A requested move; loose point types let validation handle mistakes."""

    kind: str
    to: str | None = None
    my_points: Any = None
    note: str | None = None


@dataclass(frozen=True)
class Decision:
    """A move plus JSON-serialisable metadata kept out of observations."""

    action: Action | None
    meta: Mapping[str, Any] = field(default_factory=dict)


class Agent(Protocol):
    """The common interface for scripted bots and, later, model agents."""

    def act(self, observation: Observation) -> Decision:
        """Choose a move using only the agent's observation."""
        ...


def validate(action: Action | None, observation: Observation) -> ReasonCode | None:
    """Return the first failed rule, or None for a legal request.

    The check order is part of the protocol. Pass ignores its arguments, and
    accept ignores points because the standing offer fixes the split.
    """
    if action is None:
        return "no_action"
    if action.kind not in ("offer", "accept", "pass"):
        return "unknown_action"
    if action.kind == "pass":
        return None
    if action.kind == "offer":
        if observation.legal.final_phase:
            return "offer_in_final_phase"
        if action.to not in observation.neighbours:
            return "not_a_neighbour"
        if action.to not in observation.legal.can_offer_to:
            return "neighbour_done"
        if (not isinstance(action.my_points, int) or isinstance(action.my_points, bool)
                or not 0 <= action.my_points <= observation.pie):
            return "bad_points"
    elif action.to not in observation.legal.can_accept_from:
        return "no_open_offer"
    return None
