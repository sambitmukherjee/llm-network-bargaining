"""Quiz golden text, deterministic scoring and knowledge-setting privacy."""

import asyncio
import json
from pathlib import Path
import re

import pytest

from llm_network_bargaining._prompt_examples import EX1
from llm_network_bargaining.bots import make_bot
from llm_network_bargaining.engine import Episode
from llm_network_bargaining.fake_client import BotResponder, FakeChatClient
from llm_network_bargaining.llm_agent import AgentTurnFailure, LLMAgent
from llm_network_bargaining.model_client import TransientAPIError
from llm_network_bargaining.names import assign_names
from llm_network_bargaining.networks import get_network, list_networks
from llm_network_bargaining.observation import KnowledgeSetting
from llm_network_bargaining.prompts import build_messages, render_prompt, rules_block
from llm_network_bargaining.quiz import (
    QUIZ_VERSION, parse_quiz, quiz_key, quiz_orders, quiz_response_format, render_quiz, run_rules_quiz,
)
from phase4_helpers import META_KEYS, reply, terra


def test_quiz_golden() -> None:
    text = render_quiz(get_network("stem"), "B", EX1.names, knowledge="full_map",
                       n_rounds=12, episode_seed=1, orders=[(0, 1, 2)] * 3)
    assert text == (Path(__file__).parent / "golden" / "QUIZ_EX1.txt").read_text()
    assert QUIZ_VERSION == "q1"


@pytest.mark.parametrize("identifier", ["stem", "line5", "star4"])
@pytest.mark.parametrize("knowledge", ["full_map", "own_links"])
def test_rules_match_game_for_every_node(identifier: str, knowledge: KnowledgeSetting) -> None:
    net = get_network(identifier)
    names = assign_names(net, 0)
    for node in net.nodes:
        order = (node,) + tuple(other for other in net.nodes if other != node)
        episode = Episode(net, knowledge=knowledge, n_rounds=12, episode_seed=0,
                          turn_order=lambda r, p: order)
        pending = episode.next_turn()
        assert pending is not None and pending.agent == node
        quiz = render_quiz(net, node, names, knowledge=knowledge, n_rounds=12, episode_seed=0)
        rules = rules_block(net, node, names, knowledge=knowledge, n_rounds=12)
        assert quiz.splitlines()[:9] == render_prompt(pending.observation, names).splitlines()[:9] == rules


def test_quiz_privacy_and_full_map_links_all_exchange_networks() -> None:
    networks = [net for net in list_networks() if net.kind == "exchange"]
    assert len(networks) == 16
    for net in networks:
        names = assign_names(net, 0)
        for node in net.nodes:
            visible = {node, *net.neighbours(node)}
            local_names = {other: name for other, name in names.items() if other in visible}
            own = render_quiz(net, node, names, knowledge="own_links", n_rounds=12, episode_seed=0)
            assert "The whole network:" not in own
            assert "Each agent knows only its own neighbours." in own
            mentioned = {other for other, name in names.items() if re.search(rf"\b{name}\b", own)}
            assert mentioned == visible
            assert render_quiz(net, node, local_names, knowledge="own_links", n_rounds=12, episode_seed=0) == own
            full = render_quiz(net, node, names, knowledge="full_map", n_rounds=12, episode_seed=0)
            assert "The whole network:" in full
            for a, b in net.edges:
                assert "–".join(sorted((names[a], names[b]))) in full


def test_seeded_orders_and_keys() -> None:
    letters = set()
    for seed in range(50):
        orders = quiz_orders(seed, "B")
        assert orders == quiz_orders(seed, "B")
        assert all(sorted(order) == [0, 1, 2] for order in orders)
        letters.add(quiz_key(orders)["q1"])
    assert letters == {"A", "B", "C"}
    assert quiz_key([(0, 1, 2)] * 3) == dict(q1="A", q2="A", q3="A")
    assert quiz_key([(1, 0, 2), (2, 1, 0), (0, 2, 1)]) == dict(q1="B", q2="C", q3="A")
    with pytest.raises(ValueError, match="permutations"):
        render_quiz(get_network("stem"), "B", EX1.names, knowledge="full_map",
                    n_rounds=12, episode_seed=0, orders=[(0, 0, 2)] * 3)


def test_quiz_schema() -> None:
    expected = {"type": "json_schema", "json_schema": {"name": "rules_quiz", "strict": True,
        "schema": {"type": "object", "properties": {
            "q1": {"type": "string", "enum": ["A", "B", "C"]},
            "q2": {"type": "string", "enum": ["A", "B", "C"]},
            "q3": {"type": "string", "enum": ["A", "B", "C"]}},
            "required": ["q1", "q2", "q3"], "additionalProperties": False}}}
    assert quiz_response_format() == expected


def _run(client: FakeChatClient, **kwargs):
    return run_rules_quiz(network=get_network("stem"), node="B", names=EX1.names,
                          knowledge="full_map", n_rounds=12, episode_seed=1,
                          model_alias="terra", spec=terra(), client=client, **kwargs)


@pytest.mark.parametrize("mode,score", [("correct", 3), ("wrong", 0)])
def test_fake_quiz_scoring_and_metadata(mode: str, score: int) -> None:
    client = FakeChatClient(BotResponder({}, quiz_answers=mode))
    result = asyncio.run(_run(client))
    assert result.score == score and sum(result.correct) == score
    assert len(result.correct) == 3
    assert result.quiz_version == "q1" and result.node == "B"
    assert set(result.meta) == META_KEYS - {"parse"} | {"quiz_raw"}
    assert result.meta["prompt_version"] == "q1"
    assert result.meta["quiz_raw"] == result.meta["content"]
    data = json.loads(json.dumps(result.to_dict()))
    assert data["score"] == score and data["correct"] == list(result.correct)
    request = client.requests[0]
    assert request.purpose == "quiz"
    assert request.context == {"node": "B", "quiz_key": result.key}
    assert "quiz_key" not in json.dumps(request.kwargs)
    assert request.kwargs["response_format"] == quiz_response_format()
    assert result.meta["usage"]["prompt_tokens"] == len(request.kwargs["messages"][0]["content"]) // 4


@pytest.mark.parametrize("content", [None, "", "bad JSON", "[]", '{"q1":"D","q2":"A","q3":"B"}',
                                    '{"q1":"A","q2":"B"}', '{"q1":"a","q2":"A","q3":"B"}',
                                    '{"q1":[],"q2":"A","q3":"B"}',
                                    '{"q1":"A","q2":"B","q3":"C","extra":1}'])
def test_invalid_quiz_replies(content: str | None) -> None:
    assert parse_quiz(content) is None


@pytest.mark.parametrize("content", ['{"q1":"D","q2":"A","q3":"B"}', '{"q1":"A","q2":"B"}'])
def test_quiz_parse_errors_retry_then_fail(content: str) -> None:
    client = FakeChatClient.scripted([reply(content)] * 3)
    with pytest.raises(AgentTurnFailure) as caught:
        asyncio.run(_run(client))
    assert caught.value.category == "parse_error"
    assert len(caught.value.attempts) == 3
    assert caught.value.cost_usd == pytest.approx(0.00375)
    assert all(request is client.requests[0] for request in client.requests)


def test_quiz_shares_retry_policy_and_never_enters_turn_messages() -> None:
    sleeps: list[float] = []

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    client = FakeChatClient.scripted([TransientAPIError("retry"), reply(None, refusal="no"),
                                      reply('{"q1":"A","q2":"B","q3":"C"}'), reply()])

    async def play() -> None:
        quiz = await _run(client, sleep=sleep)
        assert quiz.meta["cost_usd"] == pytest.approx(0.0025)
        agent = LLMAgent(node="B", names=EX1.names, model_alias="terra", spec=terra(), client=client)
        decision = await agent.aact(EX1.observation())
        assert decision.meta["messages"] == build_messages(EX1.observation(), EX1.names)
        assert decision.meta["usage"]["prompt_tokens"] == 1000

    asyncio.run(play())
    assert sleeps == [1.0]
    assert [request.purpose for request in client.requests] == ["quiz", "quiz", "quiz", "turn"]
