"""Pass scripted agents through the language layer without making model calls."""

from collections.abc import Mapping

from .actions import Agent, Decision
from .observation import Observation
from .prompts import render_prompt
from .schema import action_to_reply, parse_reply


class JsonBotAdapter:
    """Render each observation and round-trip a bot's action through reply JSON."""

    def __init__(self, bot: Agent, names: Mapping[str, str]) -> None:
        self.bot = bot
        self.names = dict(names)

    def act(self, obs: Observation) -> Decision:
        """Return the parsed bot action together with language-layer diagnostics."""
        prompt = render_prompt(obs, self.names)
        decision = self.bot.act(obs)
        reply = action_to_reply(decision.action, self.names)
        parsed = parse_reply(reply, self.names)
        return Decision(parsed.action, meta={
            **decision.meta, "reply": reply, "prompt_chars": len(prompt),
            "parse_error": parsed.error,
        })
