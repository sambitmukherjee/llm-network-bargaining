"""Async bargaining agent with explicit retries and complete turn accounting."""

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict, dataclass
import hashlib
import math
from typing import Any

from .actions import Decision
from .config import ModelSpec
from .costs import cost_of, sum_usage
from .model_client import (
    ChatRequest, ChatResponse, ModelClient, TransientAPIError, Usage, build_chat_kwargs,
)
from .observation import Observation
from .prompts import build_messages
from .schema import parse_reply, response_format


@dataclass(frozen=True)
class RetryPolicy:
    """Independent per-turn limits for API failures and unusable model replies."""

    max_transient_attempts: int = 8
    max_model_attempts: int = 3
    base_delay_s: float = 1.0
    max_delay_s: float = 60.0

    def __post_init__(self) -> None:
        for name in ("max_transient_attempts", "max_model_attempts"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer.")
        for name in ("base_delay_s", "max_delay_s"):
            value = getattr(self, name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive.")


class AgentTurnFailure(Exception):
    """Retries ran out; attempts and cost remain available to the future runner."""

    def __init__(self, category: str, attempts: list[dict[str, Any]], cost_usd: float) -> None:
        super().__init__(f"Model call failed: {category} after {len(attempts)} attempts.")
        self.category = category
        self.attempts = attempts
        self.cost_usd = cost_usd


def _outcome(response: ChatResponse, parse_ok: Callable[[str], bool]) -> str:
    if response.finish_reason == "length":
        return "truncated"
    if response.finish_reason == "content_filter":
        return "content_filter"
    if response.refusal:
        return "refusal"
    if response.content is None or not response.content.strip():
        return "empty"
    return "ok" if parse_ok(response.content) else "parse_error"


async def _complete_with_retries(
    request: ChatRequest, *, model_alias: str, spec: ModelSpec, prompt_version: str,
    client: ModelClient, retry: RetryPolicy, sleep: Callable[[float], Awaitable[None]],
    parse_ok: Callable[[str], bool],
) -> tuple[ChatResponse, dict[str, Any]]:
    """Shared turn/quiz policy; every retry sends the very same request."""
    attempts: list[dict[str, Any]] = []
    usages: list[Usage] = []
    warnings: list[str] = []
    transient_failures = model_failures = 0

    while True:
        try:
            response = await client.complete(request)
        except TransientAPIError as exc:
            # Do not copy exception text: third-party error bodies may contain secrets.
            attempts.append({
                "n": len(attempts) + 1, "outcome": "transient_error",
                "error": type(exc).__name__,
                "request_id": getattr(exc.__cause__, "request_id", None),
                "model": None, "finish_reason": None, "usage": asdict(Usage()),
                "latency_s": 0.0, "cost_usd": 0.0,
            })
            transient_failures += 1
            if transient_failures >= retry.max_transient_attempts:
                raise AgentTurnFailure("api_error", attempts, sum(a["cost_usd"] for a in attempts)) from exc
            delay = min(retry.max_delay_s, retry.base_delay_s * 2 ** (transient_failures - 1))
            await sleep(delay)
            continue

        outcome = _outcome(response, parse_ok)
        cost = cost_of(response.usage, spec)
        usages.append(response.usage)
        attempts.append({
            "n": len(attempts) + 1, "outcome": outcome,
            "error": None if outcome == "ok" else outcome,
            "request_id": response.request_id, "model": response.model,
            "finish_reason": response.finish_reason, "usage": asdict(response.usage),
            "latency_s": response.latency_s, "cost_usd": cost,
        })
        if spec.reasoning_effort == "none" and response.usage.reasoning_tokens:
            warnings.append("reasoning_tokens_nonzero")
        if spec.prompt_cache == "off" and response.usage.cache_write_tokens:
            warnings.append("cache_writes_nonzero")
        if not (response.model or "").startswith(spec.model_id):
            warnings.append("returned_model_mismatch")
        if spec.price_cache_write_per_m is None and response.usage.cache_write_tokens:
            warnings.append("cache_write_price_assumed")

        if outcome == "ok":
            messages = request.kwargs["messages"]
            meta = {
                "agent_kind": "llm", "model_alias": model_alias, "model_id": spec.model_id,
                "prompt_version": prompt_version, "messages": messages,
                "prompt_sha256": hashlib.sha256(messages[0]["content"].encode("utf-8")).hexdigest(),
                "attempts": attempts, "content": response.content, "refusal": response.refusal,
                "finish_reason": response.finish_reason, "usage": asdict(sum_usage(usages)),
                "cost_usd": sum(a["cost_usd"] for a in attempts),
                "latency_s": sum(a["latency_s"] for a in attempts),
                "returned_model": response.model, "request_id": response.request_id,
                "system_fingerprint": response.system_fingerprint, "service_tier": response.service_tier,
                "warnings": list(dict.fromkeys(warnings)),
            }
            return response, meta
        model_failures += 1
        if model_failures >= retry.max_model_attempts:
            raise AgentTurnFailure(outcome, attempts, sum(a["cost_usd"] for a in attempts))


class LLMAgent:
    """Render each observation afresh and return a parsed action with metadata."""

    def __init__(self, *, node: str, names: Mapping[str, str], model_alias: str,
                 spec: ModelSpec, client: ModelClient, version: str = "v1",
                 retry: RetryPolicy = RetryPolicy(),
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:
        self.node = node
        self.names = dict(names)
        self.model_alias = model_alias
        self.spec = spec
        self.client = client
        self.version = version
        self.retry = retry
        self.sleep = sleep

    async def aact(self, obs: Observation) -> Decision:
        """Retry API/model failures; leave game legality to the engine."""
        if obs.agent != self.node:
            raise ValueError("The observation belongs to a different agent.")
        messages = build_messages(obs, self.names, version=self.version)
        request = ChatRequest(
            kwargs=build_chat_kwargs(self.spec, messages, response_format()),
            timeout_s=self.spec.timeout_s, purpose="turn",
            context={"observation": obs, "names": self.names, "node": self.node},
        )
        response, meta = await _complete_with_retries(
            request, model_alias=self.model_alias, spec=self.spec, prompt_version=self.version,
            client=self.client, retry=self.retry, sleep=self.sleep,
            parse_ok=lambda content: parse_reply(content, self.names).error is None,
        )
        parsed = parse_reply(response.content, self.names)
        meta["parse"] = dict(parsed.details)
        if parsed.details.get("note_over_limit"):
            meta["warnings"].append("note_over_limit")
        return Decision(parsed.action, meta)

    def act(self, obs: Observation) -> Decision:
        """Synchronous convenience method; async callers must use aact instead."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.aact(obs))
        raise RuntimeError("An event loop is already running; use aact instead of act.")
