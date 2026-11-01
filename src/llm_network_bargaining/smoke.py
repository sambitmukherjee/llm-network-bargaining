"""Preview four requests offline, or let the user check the live API explicitly."""

import argparse
import asyncio
from collections.abc import Sequence
from copy import deepcopy
from dataclasses import asdict
import json
import os
from typing import Any

from ._prompt_examples import EX1
from .bots import make_bot
from .config import ModelSpec, load_config
from .costs import cost_of
from .engine import Episode
from .llm_agent import AgentTurnFailure, LLMAgent, RetryPolicy
from .model_client import ChatRequest, FatalAPIError, OpenAIChatClient, Usage, build_chat_kwargs
from .names import assign_names
from .networks import get_network
from .prompts import build_messages
from .quiz import quiz_key, quiz_orders, quiz_response_format, render_quiz, run_rules_quiz
from .schema import response_format


def build_smoke_requests(spec: ModelSpec) -> list[tuple[str, ChatRequest]]:
    """Build the short turn, repeated long turn and quiz without any API client."""
    short_obs = EX1.observation()
    short = ChatRequest(
        build_chat_kwargs(spec, build_messages(short_obs, EX1.names), response_format()),
        spec.timeout_s, "turn", {"observation": short_obs, "names": EX1.names, "node": "B"},
    )
    network = get_network("star4")
    names = assign_names(network, 1)
    bots = {node: make_bot("aspiration", node=node, episode_seed=1) for node in network.nodes}
    episode = Episode(network, knowledge="full_map", n_rounds=24, episode_seed=1)
    last_hub_obs = None
    while (pending := episode.next_turn()) is not None:
        if pending.agent == "H":
            last_hub_obs = pending.observation
        episode.submit(bots[pending.agent].act(pending.observation))
    assert last_hub_obs is not None
    long_messages = build_messages(last_hub_obs, names)
    if len(long_messages[0]["content"]) <= 4096:
        raise ValueError("The long smoke prompt must exceed 4,096 characters.")
    long = ChatRequest(
        build_chat_kwargs(spec, long_messages, response_format()), spec.timeout_s, "turn",
        {"observation": last_hub_obs, "names": names, "node": "H"},
    )
    text = render_quiz(get_network("stem"), "B", EX1.names, knowledge="full_map",
                       n_rounds=12, episode_seed=1)
    quiz = ChatRequest(
        build_chat_kwargs(spec, [{"role": "user", "content": text}], quiz_response_format()),
        spec.timeout_s, "quiz", {"node": "B", "quiz_key": quiz_key(quiz_orders(1, "B"))},
    )
    return [("short_turn", short), ("long_turn_1", long), ("long_turn_2", long), ("quiz", quiz)]


def _print_dry_run(requests: list[tuple[str, ChatRequest]], spec: ModelSpec) -> None:
    total = 0.0
    for label, request in requests:
        preview = deepcopy(dict(request.kwargs))
        counts = [len(message["content"]) for message in preview["messages"]]
        for message in preview["messages"]:
            text = message["content"]
            message["content"] = text[:80] + " ... " + text[-80:]
        prompt_tokens = sum((count + 3) // 4 for count in counts)
        estimate = cost_of(Usage(prompt_tokens=prompt_tokens), spec)
        total += estimate
        print(f"{label}: " + json.dumps({
            "kwargs": preview, "message_characters": counts,
            "estimated_prompt_tokens": prompt_tokens, "estimated_input_usd": estimate,
        }, ensure_ascii=False))
    print(f"Estimated input total (4 characters/token): ${total:.6f}")
    print(f"Output adds up to ${4 * spec.max_completion_tokens * spec.price_output_per_m / 1_000_000:.6f} "
          f"at the configured limit of {spec.max_completion_tokens} completion tokens per request.")


async def _run_live(requests: list[tuple[str, ChatRequest]], alias: str, spec: ModelSpec) -> int:
    client = OpenAIChatClient()
    retry = RetryPolicy(max_model_attempts=1)
    rows: list[dict[str, Any]] = []
    try:
        for label, request in requests:
            try:
                if request.purpose == "quiz":
                    result = await run_rules_quiz(
                        network=get_network("stem"), node="B", names=EX1.names,
                        knowledge="full_map", n_rounds=12, episode_seed=1, model_alias=alias,
                        spec=spec, client=client, retry=retry,
                    )
                    meta, parsed = result.meta, json.dumps(result.answers)
                else:
                    agent = LLMAgent(
                        node=request.context["node"], names=request.context["names"],
                        model_alias=alias, spec=spec, client=client, retry=retry,
                    )
                    decision = await agent.aact(request.context["observation"])
                    meta, parsed = dict(decision.meta), json.dumps(asdict(decision.action))
                rows.append({"label": label, "meta": meta, "parsed": parsed, "ok": True})
            except AgentTurnFailure as exc:
                last = exc.attempts[-1]
                usage = {name: sum(a["usage"][name] for a in exc.attempts) for name in asdict(Usage())}
                rows.append({"label": label, "parsed": exc.category, "ok": False, "meta": {
                    "returned_model": last["model"], "finish_reason": last["finish_reason"],
                    "usage": usage, "cost_usd": exc.cost_usd,
                    "latency_s": sum(a["latency_s"] for a in exc.attempts),
                    "attempts": exc.attempts,
                }})
            except FatalAPIError as exc:
                print(f"FAIL {label}: {exc}")
                print(f"Total cost so far: ${sum(row['meta']['cost_usd'] for row in rows):.6f}")
                return 1
    finally:
        await client.aclose()

    print("request | returned model | finish_reason | action/answers | prompt | cached | cache-write | completion | reasoning | latency_s | cost_usd")
    for row in rows:
        meta = row["meta"]
        usage = meta["usage"]
        fields = [row["label"], meta["returned_model"], meta["finish_reason"], row["parsed"],
                  usage["prompt_tokens"], usage["cached_tokens"], usage["cache_write_tokens"],
                  usage["completion_tokens"], usage["reasoning_tokens"],
                  f"{meta['latency_s']:.3f}", f"{meta['cost_usd']:.6f}"]
        print(" | ".join(str(value) for value in fields))
    attempts = [attempt for row in rows for attempt in row["meta"]["attempts"]
                if attempt["outcome"] != "transient_error"]
    long_attempts = [attempt for row in rows if row["label"].startswith("long_turn")
                     for attempt in row["meta"]["attempts"] if attempt["outcome"] != "transient_error"]
    checks = {
        "every reply parses": all(row["ok"] for row in rows),
        "reasoning tokens are zero": all(a["usage"]["reasoning_tokens"] == 0 for a in attempts),
        "both long requests have zero cache writes": all(a["usage"]["cache_write_tokens"] == 0 for a in long_attempts),
        "both long requests have zero cached tokens": all(a["usage"]["cached_tokens"] == 0 for a in long_attempts),
        "returned models match": all((a["model"] or "").startswith(spec.model_id) for a in attempts),
    }
    for label, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'}: {label}")
    print(f"Total cost: ${sum(row['meta']['cost_usd'] for row in rows):.6f}")
    return 0 if all(checks.values()) else 1


def main(argv: Sequence[str] | None = None) -> int:
    """Require an explicit dry/live choice; the dry path never reads the key."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--model", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--live", action="store_true")
    args = parser.parse_args(argv)
    if args.live and not os.environ.get("OPENAI_API_KEY"):
        print("Set OPENAI_API_KEY before using --live.")
        return 1
    try:
        config = load_config(args.config)
        spec = config.models[args.model]
    except (ValueError, KeyError, OSError) as exc:
        parser.error(str(exc))
    requests = build_smoke_requests(spec)
    if args.dry_run:
        _print_dry_run(requests, spec)
        return 0
    return asyncio.run(_run_live(requests, args.model, spec))


if __name__ == "__main__":
    raise SystemExit(main())
