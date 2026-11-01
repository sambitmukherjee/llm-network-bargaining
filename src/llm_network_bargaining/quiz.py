"""A separate, seeded three-question comprehension check before play."""

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
import json
from typing import Any

from .config import ModelSpec
from .llm_agent import RetryPolicy, _complete_with_retries
from .model_client import ChatRequest, ModelClient, build_chat_kwargs
from .networks import Network
from .observation import KnowledgeSetting
from .prompts import rules_block
from .seeds import derive_seed, make_rng

QUIZ_VERSION = "q1"
QUESTIONS = ("q1", "q2", "q3")
LETTERS = "ABC"
QuizOrders = tuple[tuple[int, ...], ...]


def quiz_orders(episode_seed: int, node: str) -> QuizOrders:
    """Draw three option permutations from the quiz's own deterministic stream."""
    rng = make_rng(derive_seed(episode_seed, "quiz", node))
    return tuple(tuple(int(i) for i in rng.permutation(3)) for _ in QUESTIONS)


def _check_orders(orders: Sequence[Sequence[int]]) -> QuizOrders:
    result = tuple(tuple(order) for order in orders)
    if len(result) != 3 or any(sorted(order) != [0, 1, 2] for order in result):
        raise ValueError("orders must contain three permutations of (0, 1, 2).")
    return result


def quiz_key(orders: Sequence[Sequence[int]]) -> dict[str, str]:
    """Find the letter where correct option 0 landed in each question."""
    return {question: LETTERS[order.index(0)]
            for question, order in zip(QUESTIONS, _check_orders(orders))}


def render_quiz(network: Network, node: str, names: Mapping[str, str], *,
                knowledge: KnowledgeSetting, n_rounds: int, episode_seed: int,
                orders: Sequence[Sequence[int]] | None = None) -> str:
    """Render q1, with explicit option orders available for golden tests."""
    lines = rules_block(network, node, names, knowledge=knowledge, n_rounds=n_rounds)
    orders = quiz_orders(episode_seed, node) if orders is None else _check_orders(orders)
    neighbour = min(names[other] for other in network.neighbours(node))
    questions = [
        'Question 1. You send {"action": "offer", "to": "' + neighbour
        + '", "my_points": 15, "note": ""} and ' + neighbour
        + f" accepts. What do you and {neighbour} get?",
        f"Question 2. In phase 1 you accept an offer from {neighbour}. Can you close another deal later in the same round?",
        "Question 3. It is phase 3 of a round. What can you do?",
    ]
    options = [
        [f"You get 15 points and {neighbour} gets 9.",
         f"You get 9 points and {neighbour} gets 15.",
         f"You get 15 points and {neighbour} gets 24."],
        ["No. You are done for the rest of the round.", "Yes, in phase 2.", "Yes, in phase 3."],
        ["Accept an offer made to you, or pass.",
         "Make a new offer, accept an offer made to you, or pass.", "Only pass."],
    ]
    lines.append("Before the game starts, answer three questions about these rules.")
    for question, choices, order in zip(questions, options, orders):
        lines.append(question)
        lines.extend(f"  {letter}. {choices[index]}" for letter, index in zip(LETTERS, order))
    lines.extend(["Reply with JSON only:", '{"q1": "A|B|C", "q2": "A|B|C", "q3": "A|B|C"}'])
    return "\n".join(lines)


def quiz_response_format() -> dict[str, Any]:
    """Return a fresh strict schema for exactly three A/B/C answers."""
    return {"type": "json_schema", "json_schema": {
        "name": "rules_quiz", "strict": True, "schema": {
            "type": "object", "properties": {
                question: {"type": "string", "enum": list(LETTERS)} for question in QUESTIONS
            },
            "required": list(QUESTIONS), "additionalProperties": False,
        },
    }}


def parse_quiz(content: str | None) -> dict[str, str] | None:
    """Return the three answers, or None for invalid JSON, keys or letters."""
    if not content:
        return None
    try:
        answers = json.loads(content)
    except (ValueError, TypeError):
        return None
    if not isinstance(answers, dict) or set(answers) != set(QUESTIONS):
        return None
    if any(answers[question] not in ("A", "B", "C") for question in QUESTIONS):
        return None
    return answers


@dataclass(frozen=True)
class QuizResult:
    """Answers and correctness, with usage/cost metadata kept outside the game."""

    node: str
    quiz_version: str
    orders: QuizOrders
    key: dict[str, str]
    answers: dict[str, str]
    correct: tuple[bool, ...]
    score: int
    meta: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-ready fields; tuples become arrays when JSON is encoded."""
        return asdict(self)


async def run_rules_quiz(
    *, network: Network, node: str, names: Mapping[str, str], knowledge: KnowledgeSetting,
    n_rounds: int, episode_seed: int, model_alias: str, spec: ModelSpec, client: ModelClient,
    retry: RetryPolicy = RetryPolicy(),
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> QuizResult:
    """Ask the quiz using the same retry, failure and accounting policy as turns."""
    orders = quiz_orders(episode_seed, node)
    key = quiz_key(orders)
    text = render_quiz(network, node, names, knowledge=knowledge, n_rounds=n_rounds,
                       episode_seed=episode_seed, orders=orders)
    request = ChatRequest(
        build_chat_kwargs(spec, [{"role": "user", "content": text}], quiz_response_format()),
        spec.timeout_s, "quiz", {"node": node, "quiz_key": key},
    )
    response, meta = await _complete_with_retries(
        request, model_alias=model_alias, spec=spec, prompt_version=QUIZ_VERSION,
        client=client, retry=retry, sleep=sleep,
        parse_ok=lambda content: parse_quiz(content) is not None,
    )
    answers = parse_quiz(response.content)
    assert answers is not None  # The shared retry loop returns only parsed replies.
    meta["quiz_raw"] = response.content
    correct = tuple(answers[question] == key[question] for question in QUESTIONS)
    return QuizResult(node, QUIZ_VERSION, orders, key, answers, correct, sum(correct), meta)
