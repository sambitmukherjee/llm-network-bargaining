"""Independent retry counters, complete metadata and game-level invalid moves."""

import asyncio
from dataclasses import asdict
import hashlib
import json

import pytest

from llm_network_bargaining._prompt_examples import EX1
from llm_network_bargaining.actions import Action, Agent, Decision
from llm_network_bargaining.bots import ScriptedBot, make_bot
from llm_network_bargaining.engine import Episode, EpisodeResult, run_episode
from llm_network_bargaining.fake_client import BotResponder, FakeChatClient
from llm_network_bargaining.llm_agent import AgentTurnFailure, LLMAgent, RetryPolicy
from llm_network_bargaining.model_client import FatalAPIError, TransientAPIError, Usage, build_chat_kwargs
from llm_network_bargaining.names import assign_names
from llm_network_bargaining.networks import get_network
from llm_network_bargaining.observation import KnowledgeSetting, Observation
from llm_network_bargaining.prompts import build_messages
from llm_network_bargaining.schema import response_format
from phase4_helpers import ATTEMPT_KEYS, META_KEYS, PASS, reply, terra


def test_transient_then_success_metadata() -> None:
    client = FakeChatClient.scripted([TransientAPIError("secret-error-text"),
                                      TransientAPIError("retry"), reply()])
    sleeps: list[float] = []

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    obs = EX1.observation()
    agent = LLMAgent(node="B", names=EX1.names, model_alias="terra", spec=terra(), client=client, sleep=sleep)
    decision = asyncio.run(agent.aact(obs))
    assert decision.action == Action("pass", note="")
    meta = decision.meta
    assert set(meta) == META_KEYS
    assert json.loads(json.dumps(meta)) == meta
    assert sleeps == [1.0, 2.0]
    assert [a["outcome"] for a in meta["attempts"]] == ["transient_error", "transient_error", "ok"]
    assert all(set(a) == ATTEMPT_KEYS for a in meta["attempts"])
    assert [a["n"] for a in meta["attempts"]] == [1, 2, 3]
    assert meta["usage"] == asdict(Usage(1000, 50))
    assert meta["cost_usd"] == sum(a["cost_usd"] for a in meta["attempts"]) == pytest.approx(0.00125)
    assert meta["latency_s"] == 0.25
    assert meta["prompt_sha256"] == hashlib.sha256(meta["messages"][0]["content"].encode()).hexdigest()
    assert "secret-error-text" not in json.dumps(meta)
    assert all(request is client.requests[0] for request in client.requests)
    request = client.requests[0]
    assert request.purpose == "turn" and request.timeout_s == 60.0
    assert request.context == {"observation": obs, "names": EX1.names, "node": "B"}
    assert request.kwargs == build_chat_kwargs(terra(), build_messages(obs, EX1.names), response_format())


RETRY_CASES = [
    ([TransientAPIError("retry")] * 8, "api_error", [1, 2, 4, 8, 16, 32, 60], ["transient_error"] * 8),
    ([reply(None, refusal="no"), reply()], None, [], ["refusal", "ok"]),
    ([reply(None, refusal="no")] * 3, "refusal", [], ["refusal"] * 3),
    ([reply(finish_reason="length")] * 3, "truncated", [], ["truncated"] * 3),
    ([reply(finish_reason="content_filter"), reply("invalid JSON"), reply()], None, [],
     ["content_filter", "parse_error", "ok"]),
    ([TransientAPIError("retry"), reply(None, refusal="no"), TransientAPIError("retry"),
      reply(None, refusal="no"), reply(None, refusal="no")], "refusal", [1, 2],
     ["transient_error", "refusal", "transient_error", "refusal", "refusal"]),
    ([reply(None)] * 3, "empty", [], ["empty"] * 3),
    ([reply("  \n")] * 3, "empty", [], ["empty"] * 3),
]


@pytest.mark.parametrize("items,category,expected_sleeps,outcomes", RETRY_CASES)
def test_retry_table(items: list, category: str | None, expected_sleeps: list, outcomes: list) -> None:
    client = FakeChatClient.scripted(items)
    sleeps: list[float] = []

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    agent = LLMAgent(node="B", names=EX1.names, model_alias="terra", spec=terra(), client=client, sleep=sleep)
    if category is not None:
        with pytest.raises(AgentTurnFailure) as caught:
            asyncio.run(agent.aact(EX1.observation()))
        failure = caught.value
        assert failure.category == category
        attempts, cost = failure.attempts, failure.cost_usd
    else:
        meta = asyncio.run(agent.aact(EX1.observation())).meta
        assert set(meta) == META_KEYS
        assert json.loads(json.dumps(meta)) == meta
        attempts, cost = meta["attempts"], meta["cost_usd"]
        assert meta["usage"]["prompt_tokens"] == 1000 * sum(not isinstance(item, Exception) for item in items)
    assert [a["outcome"] for a in attempts] == outcomes
    assert all(set(a) == ATTEMPT_KEYS for a in attempts)
    assert cost == pytest.approx(sum(a["cost_usd"] for a in attempts))
    assert cost == pytest.approx(0.00125 * sum(not isinstance(item, Exception) for item in items))
    assert sleeps == expected_sleeps
    assert all(request is client.requests[0] for request in client.requests)
    json.dumps(attempts)


def test_fatal_error_is_reraised_without_retry() -> None:
    error = FatalAPIError("configuration problem")
    client = FakeChatClient.scripted([error])

    async def no_sleep(delay: float) -> None:
        raise AssertionError("Fatal errors must not sleep.")

    agent = LLMAgent(node="B", names=EX1.names, model_alias="terra", spec=terra(), client=client, sleep=no_sleep)
    with pytest.raises(FatalAPIError) as caught:
        agent.act(EX1.observation())
    assert caught.value is error and len(client.requests) == 1


def test_outcome_priority_and_retry_costs_and_warnings() -> None:
    long_note = " ".join(["word"] * 31)
    content = json.dumps(dict(action="pass", to=None, my_points=None, note=long_note))
    bad = reply(None, refusal="no", finish_reason="length", model="gpt-6-luna",
                usage=Usage(1000, 50, cache_write_tokens=10, reasoning_tokens=5))
    client = FakeChatClient.scripted([bad, reply(content)])
    spec = terra(price_cache_write_per_m=None)
    agent = LLMAgent(node="B", names=EX1.names, model_alias="terra", spec=spec, client=client)
    with pytest.warns(UserWarning, match="cache_write_price_assumed"):
        meta = agent.act(EX1.observation()).meta
    assert [a["outcome"] for a in meta["attempts"]] == ["truncated", "ok"]
    assert set(meta["warnings"]) == {"reasoning_tokens_nonzero", "cache_writes_nonzero",
                                     "returned_model_mismatch", "cache_write_price_assumed", "note_over_limit"}
    assert meta["usage"] == asdict(Usage(2000, 100, cache_write_tokens=10, reasoning_tokens=5))
    assert meta["cost_usd"] == pytest.approx(0.0025025)
    assert meta["latency_s"] == 0.5
    assert meta["parse"]["note_words"] == 31


def test_warnings_respect_nondefault_settings() -> None:
    spec = terra(reasoning_effort="low", prompt_cache="implicit")
    response = reply(usage=Usage(1000, 50, cache_write_tokens=10, reasoning_tokens=5))
    agent = LLMAgent(node="B", names=EX1.names, model_alias="terra", spec=spec,
                     client=FakeChatClient.scripted([response]))
    assert agent.act(EX1.observation()).meta["warnings"] == []


def test_running_event_loop_and_wrong_agent() -> None:
    agent = LLMAgent(node="B", names=EX1.names, model_alias="terra", spec=terra(),
                     client=FakeChatClient.scripted([reply()]))

    async def check() -> None:
        with pytest.raises(RuntimeError, match="aact"):
            agent.act(EX1.observation())

    asyncio.run(check())
    other = LLMAgent(node="A", names=EX1.names, model_alias="terra", spec=terra(), client=agent.client)
    with pytest.raises(ValueError, match="different agent"):
        other.act(EX1.observation())


@pytest.mark.parametrize("action,recipient,points,reason", [
    ("offer", "C", 12, "not_a_neighbour"),
    ("offer", "B", 25, "bad_points"),
    ("offer", "B", True, "bad_points"),
    ("offer", "B", 12.5, "bad_points"),
    ("accept", "B", None, "no_open_offer"),
    ("dance", None, None, "unknown_action"),
])
def test_parsed_illegal_move_is_not_a_model_failure(action: str, recipient: str | None,
                                                   points: object, reason: str) -> None:
    net = get_network("line3")
    names = assign_names(net, 0)
    episode = Episode(net, knowledge="own_links", n_rounds=1, episode_seed=0,
                      turn_order=lambda r, p: net.nodes)
    pending = episode.next_turn()
    assert pending is not None and pending.agent == "A"
    content = json.dumps(dict(action=action, to=names[recipient] if recipient else None,
                             my_points=points, note=""))
    client = FakeChatClient.scripted([reply(content)])
    agent = LLMAgent(node="A", names=names, model_alias="terra", spec=terra(), client=client)
    decision = agent.act(pending.observation)
    assert decision.action.to == recipient
    turn = episode.submit(decision)
    assert not turn.valid and turn.reason == reason
    assert len(client.requests) == 1


def test_bot_none_reply_is_retried_and_never_becomes_a_pass() -> None:
    client = FakeChatClient(BotResponder({"B": ScriptedBot({(1, 1): None})}))
    agent = LLMAgent(node="B", names=EX1.names, model_alias="terra", spec=terra(), client=client)
    with pytest.raises(AgentTurnFailure) as caught:
        agent.act(EX1.observation())
    assert caught.value.category == "empty"
    assert [a["outcome"] for a in caught.value.attempts] == ["empty"] * 3
    assert len(client.requests) == 3
    assert caught.value.cost_usd > 0  # Input tokens still cost money for empty replies.


@pytest.mark.parametrize("changes", [{"max_transient_attempts": 0}, {"max_model_attempts": 0},
                                     {"max_model_attempts": True}, {"base_delay_s": 0},
                                     {"max_delay_s": float("inf")}])
def test_invalid_retry_policy(changes: dict) -> None:
    with pytest.raises(ValueError):
        RetryPolicy(**changes)


class _NoneAsDance:
    """Test-only adapter: keep invalid moves, but give None a JSON action."""

    def __init__(self, bot: Agent) -> None:
        self.bot = bot

    def act(self, observation: Observation) -> Decision:
        """Call the bot once, preserving its RNG stream and private metadata."""
        decision = self.bot.act(observation)
        if decision.action is None:
            return Decision(Action("dance"), meta=decision.meta)
        return decision


@pytest.mark.parametrize("action", [
    None, Action("offer", "ZZZ", 12), Action("offer", "A", 25),
    Action("offer", "A", 12.5), Action("accept", "ZZZ"), Action("dance"),
])
def test_none_wrapper_preserves_other_invalid_requests(action: Action | None) -> None:
    obs = EX1.observation()
    bot = ScriptedBot({(1, 1): action})
    decision = _NoneAsDance(bot).act(obs)
    assert decision.action == (Action("dance") if action is None else action)
    assert decision.meta == {"bot": "scripted"}


@pytest.mark.parametrize("bot", ["aspiration", "random"])
@pytest.mark.parametrize("identifier", ["line3", "stem", "star4"])
@pytest.mark.parametrize("knowledge", ["full_map", "own_links"])
@pytest.mark.parametrize("seed", [0, 1])
def test_bot_equivalence(bot: str, identifier: str, knowledge: KnowledgeSetting, seed: int) -> None:
    """Compare complete games, including the random bot's invalid requests."""
    net = get_network(identifier)
    names = assign_names(net, seed)
    plain = {node: make_bot(bot, node=node, episode_seed=seed) for node in net.nodes}
    wrapped = {node: make_bot(bot, node=node, episode_seed=seed) for node in net.nodes}
    if bot == "random":
        plain = {node: _NoneAsDance(agent) for node, agent in plain.items()}
        wrapped = {node: _NoneAsDance(agent) for node, agent in wrapped.items()}
    before = run_episode(net, plain, knowledge=knowledge, n_rounds=12, episode_seed=seed)
    client = FakeChatClient(BotResponder(wrapped))
    agents = {node: LLMAgent(node=node, names=names, model_alias="terra", spec=terra(), client=client)
              for node in net.nodes}

    async def play() -> EpisodeResult:
        episode = Episode(net, knowledge=knowledge, n_rounds=12, episode_seed=seed)
        while (pending := episode.next_turn()) is not None:
            episode.submit(await agents[pending.agent].aact(pending.observation))
        return episode.result()

    after = asyncio.run(play())
    assert (before.points, before.deals, before.offers) == (after.points, after.deals, after.offers)
    assert [(turn.valid, turn.reason) for turn in before.turns] == [(turn.valid, turn.reason) for turn in after.turns]
    for request in client.requests:
        assert request.purpose == "turn"
        assert request.kwargs == build_chat_kwargs(
            terra(), build_messages(request.context["observation"], names), response_format())
        assert "quiz" not in json.dumps(request.kwargs)
