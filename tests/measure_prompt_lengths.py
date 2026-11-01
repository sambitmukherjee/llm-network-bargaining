"""Repeat the Phase 3 stimulus-length audit: python tests/measure_prompt_lengths.py."""

from collections.abc import Mapping
from dataclasses import dataclass, field
import json
import re
from statistics import median, quantiles

from llm_network_bargaining.actions import Agent, Decision
from llm_network_bargaining.bots import make_bot
from llm_network_bargaining.engine import run_episode
from llm_network_bargaining.names import assign_names
from llm_network_bargaining.networks import list_networks
from llm_network_bargaining.observation import Observation
from llm_network_bargaining.prompts import render_prompt
from llm_network_bargaining.seeds import derive_seed


@dataclass
class Measurement:
    """Counts of displayed history-line occurrences and maximum prompt size."""

    words: list[int] = field(default_factory=list)
    max_chars: int = 0
    prompts: int = 0

    def record(self, prompt: str) -> None:
        """Count each displayed history line, excluding its 'Round k:' prefix."""
        self.prompts += 1
        self.max_chars = max(self.max_chars, len(prompt))
        for line in prompt.splitlines():
            match = re.fullmatch(r"  Round \d+: (.*)", line)
            if match is not None:
                self.words.append(len(match.group(1).split()))


class MeasuringAgent:
    """Audit each rendered prompt before delegating to an aspiration bot."""

    def __init__(self, bot: Agent, names: Mapping[str, str], measurement: Measurement) -> None:
        self.bot, self.names, self.measurement = bot, names, measurement

    def act(self, obs: Observation) -> Decision:
        """Measure the exact prompt presented at this turn."""
        self.measurement.record(render_prompt(obs, self.names))
        return self.bot.act(obs)


def measure_lengths() -> dict[str, int | float]:
    """Audit 10 seeds on each core network and setting, at 12 and 24 rounds."""
    measurements = {12: Measurement(), 24: Measurement()}
    for rounds, measurement in measurements.items():
        for network in list_networks("core"):
            for i in range(10):
                seed = derive_seed(2026, network.id, i)
                names = assign_names(network, seed)
                for knowledge in ("full_map", "own_links"):
                    agents = {
                        node: MeasuringAgent(make_bot("aspiration", node=node, episode_seed=seed),
                                             names, measurement)
                        for node in network.nodes
                    }
                    run_episode(network, agents, knowledge=knowledge,
                                n_rounds=rounds, episode_seed=seed)
    words = measurements[12].words
    return {
        "history_words_p50": median(words),
        "history_words_p95": quantiles(words, n=100, method="inclusive")[94],
        "history_words_max": max(words),
        "history_line_occurrences": len(words),
        "prompts_12_rounds": measurements[12].prompts,
        "max_prompt_chars_12_rounds": measurements[12].max_chars,
        "prompts_24_rounds": measurements[24].prompts,
        "max_prompt_chars_24_rounds": measurements[24].max_chars,
    }


if __name__ == "__main__":
    print(json.dumps(measure_lengths(), indent=2, sort_keys=True))
