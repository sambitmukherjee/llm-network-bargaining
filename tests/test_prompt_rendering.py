"""Golden stimuli, observation coverage, and prompt privacy across all networks."""

from dataclasses import replace
from pathlib import Path
import re

import pytest

from llm_network_bargaining._prompt_examples import EX1, EX2, G6_FULL, G6_OWN, SCENARIOS
from llm_network_bargaining.actions import Agent, Decision
from llm_network_bargaining.bots import make_bot
from llm_network_bargaining.engine import Episode, run_episode
from llm_network_bargaining.names import NAME_POOL, assign_names
from llm_network_bargaining.networks import Network, get_network, list_networks
from llm_network_bargaining.observation import (
    KnowledgeSetting, MyDeal, NeighbourDeal, Observation, OfferView, PastRound,
)
from llm_network_bargaining.prompts import PROMPT_VERSION, build_messages, render_prompt

GOLDEN = Path(__file__).parent / "golden"
EXCHANGE = tuple(net for net in list_networks() if net.kind == "exchange")


@pytest.mark.parametrize("name", SCENARIOS)
def test_golden_prompts(name: str) -> None:
    """Every expected stimulus is reproduced from a real Phase 2 episode."""
    scenario = SCENARIOS[name]
    expected = (GOLDEN / f"{name}.txt").read_text(encoding="utf-8")
    obs = scenario.observation()
    assert not expected.endswith("\n")
    assert render_prompt(obs, scenario.names) == expected
    assert render_prompt(obs, scenario.names) == render_prompt(obs, scenario.names)
    assert build_messages(obs, scenario.names) == [{"role": "user", "content": expected}]
    assert PROMPT_VERSION == "v1"


def _first_observation(knowledge: KnowledgeSetting = "own_links", phases: int = 3) -> Observation:
    net = get_network("line5")
    episode = Episode(net, knowledge=knowledge, n_rounds=12, n_phases=phases,
                      episode_seed=0, turn_order=lambda round_number, phase: net.nodes)
    pending = episode.next_turn()
    assert pending is not None
    return pending.observation


def test_unsupported_version_and_phase_count() -> None:
    """V1 cannot be silently used for another prompt version or phase count."""
    with pytest.raises(ValueError, match="version"):
        render_prompt(EX1.observation(), EX1.names, version="v2")
    with pytest.raises(ValueError, match="three phases"):
        render_prompt(_first_observation(phases=4), assign_names(get_network("line5"), 0))


def test_visible_names_required_but_unseen_names_are_optional() -> None:
    """Own-links rendering permits a partial roster while requiring every neighbour."""
    obs = _first_observation()
    assert obs.agent == "A" and obs.neighbours == ("B",)
    names = assign_names(get_network("line5"), 0)
    visible = {node: names[node] for node in ("A", "B")}
    assert render_prompt(obs, visible) == render_prompt(obs, names)
    with pytest.raises(ValueError, match="Missing display names.*B"):
        render_prompt(obs, {"A": names["A"]})
    with pytest.raises(ValueError, match="Missing display names.*E"):
        render_prompt(_first_observation("full_map"), {node: name for node, name in names.items() if node != "E"})
    with pytest.raises(ValueError, match="Duplicate"):
        render_prompt(obs, {"A": "Orsa", "B": "ORSA"})


@pytest.mark.parametrize("case", ["current_offer", "past_offer", "current_neighbour", "past_neighbour", "past_partner"])
def test_every_explicit_history_reference_requires_a_name(case: str) -> None:
    """Coverage checks include explicit offer and deal references, without a network lookup."""
    obs = _first_observation()
    past = PastRound(1, (), (), (), (), None, 0)
    current = replace(obs.current, round=2)
    offer = OfferView(1, 1, "X", "A", 12, 12, "lapsed")
    if case == "current_offer":
        current = replace(current, offers_received=(replace(offer, round=2, status="open"),))
    elif case == "past_offer":
        past = replace(past, offers_received=(offer,))
    elif case == "current_neighbour":
        current = replace(current, neighbour_deals=(NeighbourDeal("B", "X"),))
    elif case == "past_neighbour":
        past = replace(past, neighbour_deals=(NeighbourDeal("X", None),))
    else:
        past = replace(past, deal=MyDeal("X", 1, 12, 12, False), points=12)
    obs = replace(obs, round=2, current=current, history=(past,))
    with pytest.raises(ValueError, match="Missing display names.*X"):
        render_prompt(obs, {"A": "Orsa", "B": "Pell"})


def test_knowledge_setting_changes_only_map_and_partner_visibility() -> None:
    """The two G6 stimuli differ only where the knowledge setting permits it."""
    full = render_prompt(G6_FULL.observation(), G6_FULL.names)
    own = render_prompt(G6_OWN.observation(), G6_OWN.names)
    full_lines, own_lines = full.splitlines(), own.splitlines()
    full_lines[2] = own_lines[2]
    normalised = "\n".join(full_lines)
    for visible, hidden in (("Jaro dealt with Isko", "Jaro closed a deal"),
                            ("Mardo dealt with Nesh", "Mardo closed another deal"),
                            ("Mardo (with Nesh)", "Mardo")):
        normalised = normalised.replace(visible, hidden)
    # An independent neighbour-deal sentence uses 'a deal', not 'another deal'.
    normalised = normalised.replace("Mardo closed another deal.\n  Round 2:",
                                    "Mardo closed a deal.\n  Round 2:")
    assert normalised == own


def _check_fixed_lines(text: str, obs: Observation, names: dict[str, str]) -> None:
    golden = (GOLDEN / "EX1.txt").read_text(encoding="utf-8").splitlines()
    lines = text.splitlines()
    expected = golden[:9]
    expected[0] = f"You are agent {names[obs.agent]}. You earn points by making deals with your neighbours."
    neighbours = ", ".join(sorted(names[node] for node in obs.neighbours))
    if obs.knowledge == "own_links":
        sentence = "Each agent knows only its own neighbours."
    else:
        edges = sorted(tuple(sorted((names[a], names[b]))) for a, b in obs.network_edges)
        sentence = "The whole network: " + ", ".join(f"{a}–{b}" for a, b in edges)
        sentence += ". Every agent is shown this same map."
    expected[2] = f"Your neighbours: {neighbours}. {sentence}"
    expected[6] = golden[6].replace("Round 1 of 12, phase 1", f"Round {obs.round} of 12, phase {obs.phase}")
    assert lines[:9] == expected
    assert lines[-4:] == golden[-4:]
    assert not text.endswith("\n")


class CheckingAgent:
    """Render and audit every observation before letting a random bot choose."""

    def __init__(self, bot: Agent, names: dict[str, str], net: Network) -> None:
        self.bot, self.names, self.net = bot, names, net
        self.calls = 0

    def act(self, obs: Observation) -> Decision:
        """Check the exact fixed text and dynamic-region name boundaries."""
        text = render_prompt(obs, self.names)
        _check_fixed_lines(text, obs, self.names)
        region = text.splitlines()[9:-4]
        tokens = set(re.findall(r"[A-Za-z0-9]+", "\n".join(region)))
        assert not tokens.intersection(self.net.nodes)
        assert tokens.intersection(NAME_POOL).issubset(self.names.values())
        assert "ZZZ" not in tokens
        self.calls += 1
        return self.bot.act(obs)


@pytest.mark.parametrize("net", EXCHANGE, ids=lambda net: net.id)
@pytest.mark.parametrize("knowledge", ["full_map", "own_links"])
def test_rendering_fuzz_and_privacy(net: Network, knowledge: KnowledgeSetting) -> None:
    """Render every asked turn for five seeds on all exchange graphs and both settings."""
    for seed in range(5):
        names = assign_names(net, seed)
        agents = {node: CheckingAgent(make_bot("random", node=node, episode_seed=seed), names, net)
                  for node in net.nodes}
        run_episode(net, agents, knowledge=knowledge, n_rounds=12, episode_seed=seed)
        assert all(agent.calls > 0 for agent in agents.values())
