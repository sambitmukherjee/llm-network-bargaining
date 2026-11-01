"""Scripted review scenarios shared by the prompt CLI and golden tests.

These are inputs to the real engine, not expected prompt strings. Keeping
them here lets the CLI work without importing test code or reading the brief.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from .actions import Action
from .bots import ScriptedBot
from .engine import Episode
from .networks import get_network
from .observation import KnowledgeSetting, Observation


def offer(to: str, my_points: int) -> Action:
    """Make a scripted offer; my_points always means the maker's share."""
    return Action("offer", to, my_points)


def accept(to: str) -> Action:
    """Make a scripted acceptance of the named node's offer."""
    return Action("accept", to)


@dataclass(frozen=True)
class Scenario:
    """One fixed-order episode and the turn whose prompt should be captured."""

    network: str
    knowledge: KnowledgeSetting
    n_rounds: int
    names: Mapping[str, str]
    capture: tuple[str, int, int]
    rounds: list[tuple[list[str], list[tuple[int, str, Action]]]]

    def observation(self) -> Observation:
        """Replay scripts through Phase 2 and capture an actual pending turn."""
        network = get_network(self.network)
        scripts: dict[str, dict[tuple[int, int], Action]] = {node: {} for node in network.nodes}
        for number, (_, actions) in enumerate(self.rounds, start=1):
            for phase, node, action in actions:
                scripts[node][number, phase] = action
        bots = {node: ScriptedBot(script) for node, script in scripts.items()}

        def turn_order(round_number: int, phase: int) -> list[str] | tuple[str, ...]:
            if round_number <= len(self.rounds):
                return self.rounds[round_number - 1][0]
            return network.nodes

        episode = Episode(network, knowledge=self.knowledge, n_rounds=self.n_rounds,
                          episode_seed=0, turn_order=turn_order)
        while (pending := episode.next_turn()) is not None:
            if (pending.agent, pending.round, pending.phase) == self.capture:
                return pending.observation
            episode.submit(bots[pending.agent].act(pending.observation))
        raise ValueError(f"Scenario capture {self.capture!r} was not asked to act.")


# Scenario inputs copied from section 5.1 of the Phase 3 brief.
EX1 = Scenario(
    network="stem", knowledge="full_map", n_rounds=12,
    names={"A": "Talin", "B": "Orsa", "C": "Pell", "D": "Vash"},
    capture=('B', 1, 1),   # (node, round, phase) whose observation is rendered
    rounds=[  # one entry per round: (turn order used in all three phases, scripted actions)
        (["B", "A", "C", "D"], []),  # round 1
    ],
)

EX2 = Scenario(
    network="stem", knowledge="own_links", n_rounds=12,
    names={"A": "Talin", "B": "Orsa", "C": "Pell", "D": "Vash"},
    capture=('A', 5, 2),   # (node, round, phase) whose observation is rendered
    rounds=[  # one entry per round: (turn order used in all three phases, scripted actions)
        (["A", "B", "C", "D"], [(1, "A", offer("B", 12)), (1, "B", accept("A")), (1, "C", offer("D", 12)), (1, "D", accept("C"))]),  # round 1
        (["B", "A", "C", "D"], [(1, "B", offer("A", 12)), (1, "A", accept("B"))]),  # round 2
        (["B", "A", "C", "D"], [(1, "B", offer("A", 15)), (1, "A", accept("B"))]),  # round 3
        (["A", "C", "B", "D"], [(1, "A", offer("B", 10)), (1, "C", offer("B", 12)), (1, "B", accept("C"))]),  # round 4
        (["A", "B", "C", "D"], [(1, "A", offer("B", 10))]),  # round 5
    ],
)

EX3 = Scenario(
    network="stem", knowledge="full_map", n_rounds=12,
    names={"A": "Talin", "B": "Orsa", "C": "Pell", "D": "Vash"},
    capture=('C', 9, 3),   # (node, round, phase) whose observation is rendered
    rounds=[  # one entry per round: (turn order used in all three phases, scripted actions)
        (["D", "C", "A", "B"], [(1, "D", offer("C", 12)), (1, "C", accept("D")), (1, "A", offer("B", 12)), (1, "B", accept("A"))]),  # round 1
        (["C", "B", "A", "D"], [(1, "C", offer("B", 13)), (1, "B", accept("C"))]),  # round 2
        (["C", "A", "B", "D"], [(1, "C", offer("B", 14)), (1, "A", offer("B", 12)), (1, "B", accept("A")), (1, "D", offer("C", 12)), (2, "C", accept("D"))]),  # round 3
        (["C", "D", "A", "B"], [(1, "C", offer("D", 14)), (1, "D", accept("C")), (1, "A", offer("B", 12)), (1, "B", accept("A"))]),  # round 4
        (["B", "C", "A", "D"], [(1, "B", offer("C", 13)), (1, "C", accept("B"))]),  # round 5
        (["C", "D", "A", "B"], [(1, "C", offer("D", 12)), (1, "D", accept("C")), (1, "A", offer("B", 12)), (1, "B", accept("A"))]),  # round 6
        (["D", "C", "A", "B"], [(1, "D", offer("C", 12)), (1, "C", accept("D")), (1, "A", offer("B", 12)), (1, "B", accept("A"))]),  # round 7
        (["C", "B", "D", "A"], [(1, "C", offer("D", 12)), (1, "B", offer("D", 12)), (1, "D", accept("B"))]),  # round 8
        (["C", "A", "B", "D"], [(1, "C", offer("B", 13)), (2, "A", offer("B", 12)), (2, "B", accept("A")), (2, "D", offer("C", 14))]),  # round 9
    ],
)

EX4 = Scenario(
    network="stem", knowledge="own_links", n_rounds=12,
    names={"A": "Talin", "B": "Orsa", "C": "Pell", "D": "Vash"},
    capture=('B', 12, 1),   # (node, round, phase) whose observation is rendered
    rounds=[  # one entry per round: (turn order used in all three phases, scripted actions)
        (["B", "A", "C", "D"], [(1, "B", offer("A", 12)), (1, "A", accept("B")), (1, "C", offer("D", 12)), (1, "D", accept("C"))]),  # round 1
        (["C", "B", "A", "D"], [(1, "C", offer("B", 12)), (1, "B", accept("C"))]),  # round 2
        (["B", "C", "D", "A"], [(1, "B", offer("C", 14)), (1, "C", offer("D", 12)), (1, "D", accept("C")), (1, "A", offer("B", 10)), (2, "B", accept("A"))]),  # round 3
        (["B", "A", "C", "D"], [(1, "B", offer("A", 15)), (1, "A", accept("B")), (1, "C", offer("D", 12)), (1, "D", accept("C"))]),  # round 4
        (["C", "B", "A", "D"], [(1, "C", offer("B", 8)), (1, "B", accept("C"))]),  # round 5
        (["A", "B", "C", "D"], [(1, "A", offer("B", 6)), (1, "B", accept("A")), (1, "C", offer("D", 12)), (1, "D", accept("C"))]),  # round 6
        (["B", "D", "A", "C"], [(1, "B", offer("D", 18)), (1, "D", accept("B"))]),  # round 7
        (["A", "B", "C", "D"], [(1, "A", offer("B", 6)), (1, "B", accept("A")), (1, "C", offer("D", 12)), (1, "D", accept("C"))]),  # round 8
        (["B", "A", "C", "D"], [(1, "B", offer("A", 16)), (1, "A", accept("B")), (1, "C", offer("D", 12)), (1, "D", accept("C"))]),  # round 9
        (["C", "B", "A", "D"], [(1, "C", offer("B", 9)), (1, "B", accept("C"))]),  # round 10
        (["B", "A", "C", "D"], [(1, "B", offer("A", 17)), (1, "A", accept("B")), (1, "C", offer("D", 12)), (1, "D", accept("C"))]),  # round 11
        (["A", "D", "B", "C"], [(1, "A", offer("B", 6)), (1, "D", offer("B", 9))]),  # round 12
    ],
)

G5 = Scenario(
    network="star3", knowledge="own_links", n_rounds=12,
    names={"H": "Bexa", "L1": "Calo", "L2": "Deni", "L3": "Fira"},
    capture=('H', 2, 1),   # (node, round, phase) whose observation is rendered
    rounds=[  # one entry per round: (turn order used in all three phases, scripted actions)
        (["H", "L1", "L2", "L3"], [(1, "H", offer("L1", 16)), (1, "L1", offer("H", 10)), (1, "L2", offer("H", 9)), (1, "L3", offer("H", 11)), (2, "H", accept("L2"))]),  # round 1
        (["H", "L1", "L2", "L3"], []),  # round 2
    ],
)

G6_OWN = Scenario(
    network="line5", knowledge="own_links", n_rounds=12,
    names={"A": "Isko", "B": "Jaro", "C": "Lusa", "D": "Mardo", "E": "Nesh"},
    capture=('C', 4, 3),   # (node, round, phase) whose observation is rendered
    rounds=[  # one entry per round: (turn order used in all three phases, scripted actions)
        (["A", "B", "D", "E", "C"], [(1, "A", offer("B", 12)), (1, "B", accept("A")), (1, "D", offer("E", 12)), (1, "E", accept("D"))]),  # round 1
        (["C", "B", "A", "D", "E"], [(1, "C", offer("B", 13)), (1, "B", offer("C", 23)), (1, "A", offer("B", 12)), (2, "C", accept("B"))]),  # round 2
        (["D", "B", "C", "A", "E"], [(1, "D", offer("C", 14)), (1, "B", offer("C", 15)), (1, "C", offer("D", 16)), (2, "D", offer("E", 12))]),  # round 3
        (["D", "C", "B", "A", "E"], [(1, "D", offer("C", 12)), (1, "C", offer("B", 14)), (2, "C", offer("D", 13)), (2, "B", offer("C", 15)), (2, "E", offer("D", 12)), (3, "D", accept("E"))]),  # round 4
    ],
)

G6_FULL = Scenario(
    network="line5", knowledge="full_map", n_rounds=12,
    names={"A": "Isko", "B": "Jaro", "C": "Lusa", "D": "Mardo", "E": "Nesh"},
    capture=('C', 4, 3),   # (node, round, phase) whose observation is rendered
    rounds=[  # one entry per round: (turn order used in all three phases, scripted actions)
        (["A", "B", "D", "E", "C"], [(1, "A", offer("B", 12)), (1, "B", accept("A")), (1, "D", offer("E", 12)), (1, "E", accept("D"))]),  # round 1
        (["C", "B", "A", "D", "E"], [(1, "C", offer("B", 13)), (1, "B", offer("C", 23)), (1, "A", offer("B", 12)), (2, "C", accept("B"))]),  # round 2
        (["D", "B", "C", "A", "E"], [(1, "D", offer("C", 14)), (1, "B", offer("C", 15)), (1, "C", offer("D", 16)), (2, "D", offer("E", 12))]),  # round 3
        (["D", "C", "B", "A", "E"], [(1, "D", offer("C", 12)), (1, "C", offer("B", 14)), (2, "C", offer("D", 13)), (2, "B", offer("C", 15)), (2, "E", offer("D", 12)), (3, "D", accept("E"))]),  # round 4
    ],
)

G7 = Scenario(
    network="pair", knowledge="full_map", n_rounds=12,
    names={"A": "Rulo", "B": "Sefi"},
    capture=('A', 1, 2),   # (node, round, phase) whose observation is rendered
    rounds=[  # one entry per round: (turn order used in all three phases, scripted actions)
        (["A", "B"], [(1, "A", offer("Z", 12)), (1, "B", offer("A", 12))]),  # round 1
    ],
)

G8 = Scenario(
    network="line5", knowledge="own_links", n_rounds=12,
    names={"A": "Isko", "B": "Jaro", "C": "Lusa", "D": "Mardo", "E": "Nesh"},
    capture=('C', 6, 2),   # (node, round, phase) whose observation is rendered
    rounds=[  # one entry per round: (turn order used in all three phases, scripted actions)
        (["A", "B", "D", "E", "C"], [(1, "A", offer("B", 12)), (1, "B", accept("A")), (1, "D", offer("E", 12)), (1, "E", accept("D"))]),  # round 1
        (["C", "B", "A", "D", "E"], [(1, "C", offer("B", 13)), (1, "B", offer("C", 23)), (1, "A", offer("B", 12)), (2, "C", accept("B"))]),  # round 2
        (["D", "B", "C", "A", "E"], [(1, "D", offer("C", 14)), (1, "B", offer("C", 15)), (1, "C", offer("D", 16)), (2, "D", offer("E", 12))]),  # round 3
        (["D", "C", "B", "A", "E"], [(1, "D", offer("C", 12)), (1, "C", offer("B", 14)), (2, "C", offer("D", 13)), (2, "B", offer("C", 15)), (2, "E", offer("D", 12)), (3, "D", accept("E"))]),  # round 4
        (["C", "B", "A", "D", "E"], [(1, "C", offer("B", 12)), (1, "B", offer("C", 14)), (2, "B", accept("C"))]),  # round 5
        (["D", "C", "B", "A", "E"], [(1, "D", offer("C", 13)), (2, "D", offer("E", 12))]),  # round 6
    ],
)

SCENARIOS = {
    "EX1": EX1,
    "EX2": EX2,
    "EX3": EX3,
    "EX4": EX4,
    "G5": G5,
    "G6_OWN": G6_OWN,
    "G6_FULL": G6_FULL,
    "G7": G7,
    "G8": G8,
}
