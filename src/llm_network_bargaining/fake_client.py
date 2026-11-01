"""Offline replies at our client interface, without constructing SDK clients."""

from collections.abc import Callable, Iterable, Mapping
import json
from typing import Literal

from .actions import Agent
from .model_client import ChatRequest, ChatResponse, Usage
from .schema import action_to_reply


class FakeChatClient:
    """Record each request and return (or raise) its responder's next result."""

    def __init__(self, responder: Callable[[ChatRequest], ChatResponse | Exception]) -> None:
        self.responder = responder
        self.requests: list[ChatRequest] = []

    async def complete(self, request: ChatRequest) -> ChatResponse:
        """Keep the full private request available to offline assertions."""
        self.requests.append(request)
        response = self.responder(request)
        if isinstance(response, Exception):
            raise response
        return response

    @classmethod
    def scripted(cls, items: Iterable[ChatResponse | Exception]) -> "FakeChatClient":
        """Consume a fixed response/error sequence; fail loudly if it runs out."""
        iterator = iter(items)

        def respond(request: ChatRequest) -> ChatResponse | Exception:
            try:
                return next(iterator)
            except StopIteration:
                raise AssertionError("The fake response script is exhausted.") from None

        return cls(respond)


class BotResponder:
    """Serialize bot decisions and answer quizzes from their private fake key."""

    def __init__(self, bots: Mapping[str, Agent], *,
                 quiz_answers: Literal["correct", "wrong"] = "correct") -> None:
        if quiz_answers not in ("correct", "wrong"):
            raise ValueError("quiz_answers must be 'correct' or 'wrong'.")
        self.bots = bots
        self.quiz_answers = quiz_answers
        self.calls = 0

    def __call__(self, request: ChatRequest) -> ChatResponse:
        """Answer one turn or quiz using only its fake-client context."""
        self.calls += 1
        if request.purpose == "turn":
            decision = self.bots[request.context["node"]].act(request.context["observation"])
            content = action_to_reply(decision.action, request.context["names"])
        elif request.purpose == "quiz":
            answers = dict(request.context["quiz_key"])
            if self.quiz_answers == "wrong":
                wrong = {"A": "B", "B": "C", "C": "A"}
                answers = {question: wrong[letter] for question, letter in answers.items()}
            content = json.dumps(answers)
        else:
            raise ValueError("BotResponder handles turn and quiz requests.")
        return ChatResponse(
            content=content, refusal=None, finish_reason="stop", model=request.kwargs["model"],
            request_id=f"fake-{self.calls}", system_fingerprint=None, service_tier=None,
            usage=Usage(len(request.kwargs["messages"][0]["content"]) // 4, len(content) // 4),
            latency_s=0.0,
        )
