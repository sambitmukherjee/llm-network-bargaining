"""Recompute outcomes and prompts from recorded requests, without any client."""

import argparse
from collections.abc import Sequence
from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path

from .actions import Action, Decision
from .engine import Episode
from .names import assign_names
from .networks import get_network
from .prompts import build_messages, render_prompt
from .quiz import quiz_key, quiz_orders, render_quiz
from .runlog import LOG_SCHEMA, find_logs, read_log
from .schema import parse_reply
from .seeds import derive_seed, make_rng


@dataclass(frozen=True)
class ReplayResult:
    """What was checked, and short descriptions of any discrepancies."""

    path: Path
    ok: bool
    n_events: int
    n_turns: int
    mismatches: list[str]


def replay_log(path: str | Path) -> ReplayResult:
    """Replay completed logs or a failed/interrupted prefix from the log alone."""
    path = Path(path)
    mismatches: list[str] = []
    event_count = turn_count = 0
    try:
        records = read_log(path)
        header = records.header
        if header.get("log_schema") != LOG_SCHEMA:
            raise ValueError("header log_schema is missing or unsupported")
        network = get_network(header["network_id"])
        seed, names = header["episode_seed"], header["names"]
        if names != assign_names(network, seed):
            mismatches.append("header names differ from assign_names for the episode seed")
        settings = header["settings"]
        for quiz in records.quizzes:
            node = quiz["node"]
            orders = quiz_orders(seed, node)
            if quiz["orders"] != [list(order) for order in orders]:
                mismatches.append(f"quiz orders differ for node {node}")
            key = quiz_key(orders)
            if quiz["key"] != key:
                mismatches.append(f"quiz key differs for node {node}")
            correct = [quiz["answers"][question] == key[question] for question in ("q1", "q2", "q3")]
            if quiz["correct"] != correct or quiz["score"] != sum(correct):
                mismatches.append(f"quiz score differs for node {node}")
            text = render_quiz(network, node, names, knowledge=header["knowledge"],
                               n_rounds=settings["rounds"], episode_seed=seed)
            if quiz["meta"]["messages"] != [{"role": "user", "content": text}]:
                mismatches.append(f"quiz prompt differs for node {node}")
            if quiz["meta"]["prompt_sha256"] != hashlib.sha256(text.encode("utf-8")).hexdigest():
                mismatches.append(f"quiz prompt_sha256 differs for node {node}")

        orders = {}
        rng = make_rng(derive_seed(seed, "turn_order"))
        seeded_orders = {(r, p): [network.nodes[int(i)] for i in rng.permutation(len(network.nodes))]
                         for r in range(1, settings["rounds"] + 1)
                         for p in range(1, settings["phases"] + 1)}
        for event in records.events:
            if event["type"] == "phase_start":
                position = (event["round"], event["phase"])
                orders[position] = event["order"]
                expected = seeded_orders[position]
                if event["order"] != expected:
                    mismatches.append(f"phase_start order differs from seed at round {position[0]} phase {position[1]}")

        if records.events:
            episode = Episode(network, knowledge=header["knowledge"], n_rounds=settings["rounds"],
                              n_phases=settings["phases"], episode_seed=seed,
                              turn_order=lambda r, p: orders.get((r, p), seeded_orders[r, p]))

            def compare_events() -> None:
                nonlocal event_count, turn_count
                for actual in episode.events_since(event_count):
                    # One engine step can emit several events. An interrupted
                    # writer may have flushed only the beginning of that step.
                    if event_count >= len(records.events) and records.footer is None:
                        return
                    if actual["type"] == "turn":
                        turn_count += 1
                    if event_count >= len(records.events):
                        mismatches.append(f"extra replayed event {actual['type']} at index {event_count}")
                    else:
                        logged = records.events[event_count]
                        left = {k: v for k, v in actual.items() if k != "meta"}
                        right = {k: v for k, v in logged.items() if k != "meta"}
                        if left != right:
                            fields = sorted(k for k in left.keys() | right.keys() if left.get(k) != right.get(k))
                            mismatches.append(f"{logged['type']} event {event_count} differs in {', '.join(fields)}")
                    event_count += 1

            compare_events()
            while event_count < len(records.events):
                pending = episode.next_turn()
                compare_events()
                if event_count >= len(records.events):
                    break
                if pending is None:
                    mismatches.append("logged events remain after the replay finished")
                    break
                turn = records.events[event_count]
                if turn["type"] != "turn" or turn["auto"]:
                    mismatches.append(f"expected a requested turn at event {event_count}")
                    break
                meta = turn.get("meta", {})
                text = render_prompt(pending.observation, names, version=header["prompt_version"])
                digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
                if meta.get("prompt_sha256") != digest:
                    mismatches.append(f"turn {turn['turn_index']} prompt_sha256 differs")
                if meta.get("messages") != build_messages(pending.observation, names, version=header["prompt_version"]):
                    mismatches.append(f"turn {turn['turn_index']} prompt messages differ")
                requested = turn["requested"]
                parsed = parse_reply(meta.get("content"), names, refusal=meta.get("refusal"))
                if parsed.error is not None or parsed.action is None or asdict(parsed.action) != requested:
                    mismatches.append(f"turn {turn['turn_index']} requested action differs from its raw reply")
                episode.submit(Decision(Action(**requested) if requested is not None else None))
                compare_events()
            if records.footer and records.footer["status"] == "completed":
                if not episode.finished:
                    mismatches.append("completed footer but replayed episode is unfinished")
                elif records.footer["totals"] != episode.result().totals:
                    mismatches.append("footer totals differ from replayed totals")
            elif records.failure and records.failure["stage"] == "turn":
                pending = episode.next_turn()
                compare_events()
                failure = records.failure
                if pending is None or (pending.agent, pending.round, pending.phase) != (
                        failure["node"], failure["round"], failure["phase"]):
                    mismatches.append("failure turn does not match the replay's pending turn")
        elif records.footer and records.footer["status"] == "completed":
            mismatches.append("completed log has no engine events")
    except (OSError, ValueError, KeyError, TypeError, AssertionError, RuntimeError) as exc:
        mismatches.append(f"replay stopped: {type(exc).__name__}: {exc}")
    return ReplayResult(path, not mismatches, event_count, turn_count, mismatches)


def main(argv: Sequence[str] | None = None) -> int:
    """Check all supplied log files/directories and return a shell exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args(argv)
    try:
        paths = find_logs(args.paths)
    except OSError as exc:
        print(f"FAIL: {exc}")
        return 1
    if not paths:
        print("No episode logs found.")
        return 1
    ok = True
    for path in paths:
        result = replay_log(path)
        print(f"{'PASS' if result.ok else 'FAIL'} {path} events={result.n_events} turns={result.n_turns}"
              + (" " + "; ".join(result.mismatches) if result.mismatches else ""))
        ok &= result.ok
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
