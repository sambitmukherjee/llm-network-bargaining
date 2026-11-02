"""Versioned blind note judging, validated batches and reusable local caches."""

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, replace
import hashlib
import json
from math import ceil
from pathlib import Path
import re
from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field
import yaml

from ..analysis.data import Dataset
from ..analysis.cli import _write_csv, _write_json
from ..config import ModelSpec
from ..costs import CostTracker
from ..llm_agent import AgentTurnFailure, RetryPolicy, _complete_with_retries
from ..model_client import ChatRequest, ChatResponse, ModelClient, Usage, FatalAPIError, build_chat_kwargs
from ..networks import get_network
from ..seeds import derive_seed, make_rng
from ..structure import class_of
from . import LABELS
from .consistency import consistency_ids, consistency_summary

JUDGE_V1 = '''You will label short private notes written by agents in a bargaining game. Each round, every pair of linked agents can split 24 points, and each agent can close at most one deal per round, so some agents can be left out. Before each move, an agent wrote a private note (at most 30 words) about its reasoning.

Label each note on four questions. Judge only what the note says; do not guess what the agent might have meant. A note can be "yes" on several questions, or on none.

1. exclusion: Does the note use alternatives, or the chance of someone being left without a deal, as leverage or as a reason for its terms?
   Yes: "Vash has no one else, so ask 18." / "If Pell won't take 8, I'll deal with Talin." / "Three partners compete for me; demand more." / "I risk being left out again, so offer more."
   No: "Orsa already dealt this round." (a fact, not used as a reason) / "Accept 12; it's fair." / "Last round; take what's offered."

2. fairness: Does the note appeal to fairness, equality, an even split, reciprocity or being reasonable, as a reason?
   Yes: "A fair 12/12 keeps things friendly." / "Split evenly to build trust." / "Return the favour from last round."
   No: "Offer 12." (a number with no appeal) / "Ask 14; they accepted 12 before."

3. structure: Does the note refer to the network itself: who is linked to whom, how many partners or options an agent has, or an agent's position (such as hub, centre, end, or someone's only link)?
   Yes: "I'm the only link for Talin." / "Three partners and Talin has only me." / "As the centre I can choose."
   No: "Pell offered me 10." (offers, not links) / "Orsa dealt with Talin last round." (deals, not links)

4. recognition: Does the note name a game, a theory, a model or a textbook solution?
   Yes: "Classic ultimatum logic: take anything positive." / "Nash bargaining says split evenly." / "My BATNA is zero." / "Like an exchange network, the centre has power."
   No: "Take anything positive; 1 beats 0." (the logic without a name) / "Bargain hard."

For each question answered yes, copy the shortest exact phrase from the note that justifies it into the matching quote field. For each question answered no, set the quote to null.

Notes:
{NOTES_JSON}

Reply with JSON only: one entry per note, in the same order, with the same ids.'''


JUDGE_V2 = '''You will label short private notes written by agents in a bargaining game. Each round, every pair of linked agents can split 24 points, and each agent can close at most one deal per round, so some agents can be left out. Before each move, an agent wrote a private note (at most 30 words) about its reasoning.

Label each note on four questions. Judge only what the note says; do not guess what the agent might have meant. A note can be "yes" on several questions, or on none. Notes that say the same thing in different words get the same labels.

1. exclusion: Does the note use alternatives, or the chance of someone being left without a deal, as leverage or as a reason for its terms?
   Yes: "Vash has no one else, so ask 18." / "If Pell won't take 8, I'll deal with Talin." / "Three partners compete for me; demand more." / "I risk being left out again, so offer more." / "Offer 19 to compete with Pell." (another agent competes for the same partner, named or not) / "Keep Talin's 20 open as a fallback; ask 21." / "Both offers stay open, so seek one more point."
   No: "Orsa already dealt this round." (a fact, not used as a reason) / "Accept 12; it's fair." / "Last round; take what's offered." / "Talin accepted 21 last round." (history, not used as a reason) / "Offer 22 to secure a deal." (no alternative or rival)

2. fairness: Does the note appeal to fairness, equality, an even split, reciprocity or being reasonable toward the other side, as a reason?
   Yes: "A fair 12/12 keeps things friendly." / "Split evenly to build trust." / "Return the favour from last round."
   No: "Offer 12." (a number with no appeal) / "Ask 14; they accepted 12 before." / "Keep a reasonable share for myself." (self-interest, not fairness)

3. structure: Does the note refer to the network itself: who is linked to whom, how many partners or options an agent has, or an agent's position (such as hub, centre, end, or someone's only link)?
   Yes: "I'm the only link for Talin." / "Three partners and Talin has only me." / "As the centre I can choose."
   No: "Pell offered me 10." (offers, not links) / "Orsa dealt with Talin last round." (deals, not links)

4. recognition: Does the note name a game, a theory, a model or a textbook solution?
   Yes: "Classic ultimatum logic: take anything positive." / "Nash bargaining says split evenly." / "My BATNA is zero." / "Like an exchange network, the centre has power."
   No: "Take anything positive; 1 beats 0." (the logic without a name) / "Bargain hard."

For each question answered yes, copy the shortest exact phrase from the note that justifies it into the matching quote field. For each question answered no, set the quote to null.

Notes:
{NOTES_JSON}

Reply with JSON only: one entry per note, in the same order, with the same ids.'''

JUDGE_TEMPLATES = {"judge-v1": JUDGE_V1, "judge-v2": JUDGE_V2}
JUDGE_TEMPLATE = JUDGE_TEMPLATES["judge-v2"]

OUTPUT_COLUMNS = ["episode_uid", "turn_index", "round", "phase", "node", "node_class", "network_id",
                  "knowledge", "config_name", "note", "note_id", *LABELS,
                  *(f"{label}_quote" for label in LABELS), "status", "flags", "dry_run"]


class JudgeConfig(BaseModel):
    """The note judge has its own schema, separate from experiment configs."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    judge_version: str = "judge-v2"
    seed: int = Field(default=20261106, ge=0)
    batch_size: int = Field(default=20, ge=1)
    consistency_share: float = Field(default=.10, ge=0, le=1, allow_inf_nan=False)
    model: ModelSpec


def load_judge_config(path: str | Path = "configs/note_judge.yaml") -> JudgeConfig:
    """Read the small independent Pydantic judge config."""
    return JudgeConfig.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


def note_id(note: str, judge_version: str = "judge-v2") -> str:
    """Return the specified versioned hash, without disclosing note metadata."""
    return "n" + hashlib.sha256((judge_version + "\n" + note).encode("utf-8")).hexdigest()[:10]


def judge_prompt(notes: Sequence[dict[str, str]], version: str = "judge-v2") -> str:
    """Fill the exact registered template with only the IDs and note texts."""
    if version not in JUDGE_TEMPLATES:
        raise ValueError(f"Unsupported judge prompt version: {version}.")
    blind = [{"id": note["id"], "note": note["note"]} for note in notes]
    return JUDGE_TEMPLATES[version].replace("{NOTES_JSON}", json.dumps(blind, ensure_ascii=False))


def judge_response_format() -> dict[str, Any]:
    """Strict note_labels schema: every label and nullable quote is required."""
    properties = {"id": {"type": "string"}}
    for label in LABELS:
        properties[label] = {"type": "boolean"}
        properties[f"{label}_quote"] = {"type": ["string", "null"]}
    item = dict(type="object", properties=properties, required=list(properties), additionalProperties=False)
    return {"type": "json_schema", "json_schema": {"name": "note_labels", "strict": True,
        "schema": {"type": "object", "properties": {"labels": {"type": "array", "items": item}},
                   "required": ["labels"], "additionalProperties": False}}}


def validate_labels(content: str, notes: Sequence[dict[str, str]]) -> list[dict]:
    """Check types and the complete ID set, then restore the requested order."""
    try:
        data = json.loads(content)
    except ValueError:
        raise ValueError("invalid_json") from None
    if not isinstance(data, dict) or set(data) != {"labels"} or not isinstance(data["labels"], list):
        raise ValueError("invalid_schema")
    expected = set(judge_response_format()["json_schema"]["schema"]["properties"]["labels"]["items"]["properties"])
    by_id = {}
    for row in data["labels"]:
        if not isinstance(row, dict) or set(row) != expected or not isinstance(row["id"], str):
            raise ValueError("invalid_schema")
        if any(type(row[label]) is not bool or (row[f"{label}_quote"] is not None and
               not isinstance(row[f"{label}_quote"], str)) for label in LABELS):
            raise ValueError("invalid_schema")
        if row["id"] in by_id:
            raise ValueError("duplicated_id")
        by_id[row["id"]] = row
    if set(by_id) != {note["id"] for note in notes}:
        raise ValueError("missing_or_extra_ids")
    return [by_id[note["id"]] for note in notes]


def quote_flags(row: dict, note: str) -> list[str]:
    """Flag mismatches and absent phrases without changing the model's labels."""
    normal = " ".join(note.lower().split())
    flags = []
    for label in LABELS:
        quote = row[f"{label}_quote"]
        if row[label] != (quote is not None):
            flags.append(f"quote_mismatch:{label}")
        if quote is not None and " ".join(quote.lower().split()) not in normal:
            flags.append(f"quote_not_found:{label}")
    return flags


def collect_notes(ds: Dataset, judge_version: str = "judge-v2") -> pd.DataFrame:
    """Collect asked turns; recover the engine's zero-based index before filtering."""
    turns = ds.turns.copy()
    turns["turn_index"] = turns.groupby("episode_uid", sort=False).cumcount()
    turns = turns[~turns.auto.astype(bool)].copy()
    turns = turns.merge(ds.episodes[["episode_uid", "network_id", "knowledge", "config_name"]],
                        on="episode_uid", validate="many_to_one")
    turns["node_class"] = [class_of(get_network(net))[node] for net, node in zip(turns.network_id, turns.node)]
    turns["note"] = turns.note.fillna("").map(lambda text: str(text).strip())
    turns["note_id"] = turns.note.map(lambda text: note_id(text, judge_version) if text else "")
    return turns.sort_values(["episode_uid", "turn_index"]).reset_index(drop=True)


def _read_cache(path: Path, config: JudgeConfig, dry_run: bool) -> dict[str, dict]:
    """Read one cache namespace and reject mixing keyword labels with live ones."""
    result = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row["dry_run"] != dry_run:
                raise ValueError("Cannot mix dry-run and live judge caches in one output folder.")
            if row["judge_version"] == config.judge_version:
                result[row["note_id"]] = row
    return result


def _append(path: Path, row: dict) -> None:
    """Flush each cache/cost record so returned judgments survive later failures."""
    with path.open("a", encoding="utf-8") as output:
        output.write(json.dumps(row, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n")
        output.flush()


def estimate_notes(ds: Dataset, config: JudgeConfig, out: str | Path = "notes_out", *,
                    dry_run: bool | None = None, concurrency: int = 8) -> dict:
    """Count primary notes and apply the brief's batch-token cost estimate."""
    if concurrency < 1:
        raise ValueError("concurrency must be at least 1.")
    turns = collect_notes(ds, config.judge_version)
    unique = set(turns.loc[turns.note != "", "note_id"])
    path = Path(out) / "judge_cache.jsonl"
    cached = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if dry_run is not None and row["dry_run"] != dry_run:
                raise ValueError("Cannot mix dry-run and live judge caches in one output folder.")
            if row["judge_version"] == config.judge_version:
                cached.add(row["note_id"])
    new = len(unique - cached)
    calls = ceil(new / config.batch_size)
    cost = calls * ((1200 + 40 * config.batch_size) * config.model.price_input_per_m
                    + 3000 * config.model.price_output_per_m) / 1e6
    return dict(non_empty=int((turns.note != "").sum()), empty=int((turns.note == "").sum()), unique=len(unique),
                already_cached=len(unique & cached), new=new, estimated_calls=calls, estimated_cost_usd=cost,
                concurrency=concurrency, estimated_minutes=ceil(ceil(calls / concurrency) * 20 / 60))


class KeywordResponder:
    """An offline test double. Its keyword labels must never be study results."""

    keywords = {
        "exclusion": ("no one else", "only me", "deal with", "left out", "compete", "other option"),
        "fairness": ("fair", "even", "equal", "12/12", "reciprocate", "favour", "favor"),
        "structure": ("link", "partners", "neighbours", "neighbors", "hub", "centre", "center", "only link"),
        "recognition": ("nash", "ultimatum", "shapley", "batna", "game theory", "exchange network"),
    }

    def __init__(self) -> None:
        """Keep fake request IDs local to this responder instance."""
        self.calls = 0

    def __call__(self, request: ChatRequest) -> ChatResponse:
        """Match the earliest keyword in the note, retaining its exact spelling."""
        self.calls += 1
        rows = []
        for note in request.context["notes"]:
            row = {"id": note["id"]}
            for label, keywords in self.keywords.items():
                matches = [match for keyword in keywords if (match := re.search(re.escape(keyword), note["note"], re.I))]
                match = min(matches, key=lambda found: found.start()) if matches else None
                row[label] = match is not None
                row[f"{label}_quote"] = match.group() if match else None
            rows.append(row)
        content = json.dumps({"labels": rows}, ensure_ascii=False)
        return ChatResponse(content, None, "stop", request.kwargs["model"], f"judge-fake-{self.calls}", None, None,
                            Usage(ceil(len(request.kwargs["messages"][0]["content"]) / 4), ceil(len(content) / 4)), 0.0)


@dataclass
class JudgeRun:
    """Saved per-turn labels, cumulative costs and the separate repeat check."""

    labels: pd.DataFrame
    costs: dict
    consistency: dict


async def code_notes(ds: Dataset, config: JudgeConfig, *, out: str | Path, client: ModelClient,
                      dry_run: bool = False, retry: RetryPolicy = RetryPolicy(),
                      sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
                      concurrency: int = 8) -> JudgeRun:
    """Judge unique notes, cache successes/failures, and code a separate repeat sample."""
    if concurrency < 1:
        raise ValueError("concurrency must be at least 1.")
    semaphore = asyncio.Semaphore(concurrency)
    stopped = asyncio.Event()
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    costs_path = out / "judge_costs.json"
    if costs_path.exists() and json.loads(costs_path.read_text())["dry_run"] != dry_run:
        raise ValueError("Cannot mix dry-run and live judge outputs.")
    primary_path, repeat_path = out / "judge_cache.jsonl", out / "consistency_cache.jsonl"
    main, repeat = _read_cache(primary_path, config, dry_run), _read_cache(repeat_path, config, dry_run)
    turns = collect_notes(ds, config.judge_version)
    unique = {row.note_id: row.note for row in turns[turns.note != ""].itertuples()}
    if turns[turns.note != ""].groupby("note_id").note.nunique().gt(1).any():
        raise ValueError("A truncated note-ID hash collision occurred.")
    for key, note in unique.items():
        if key in main and main[key]["note"] != note:
            raise ValueError("A cached note ID belongs to different text.")
    ledger = out / "judge_calls.jsonl"

    def save_costs() -> dict:
        """Rebuild cumulative usage from the append-only logical-call ledger."""
        tracker = CostTracker()
        if ledger.exists():
            entries = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
            # Completion order can vary. Sum floating-point costs in logical batch order.
            for index, entry in enumerate(entries):
                entry.setdefault("batch_order", f"legacy/{index:010d}")
            entries.sort(key=lambda entry: (entry["batch_order"], tuple(entry["ids"])))
            for entry in entries:
                if entry["judge_version"] == config.judge_version:
                    for attempt in entry["attempts"]:
                        tracker.add("judge", Usage(**attempt["usage"]), attempt["cost_usd"])
        totals = tracker.to_dict().get("judge", dict(calls=0, usage=Usage().__dict__, cost_usd=0.0))
        costs = dict(dry_run=dry_run, judge_version=config.judge_version, model_id=config.model.model_id,
                     total_cost_usd=totals["cost_usd"], n_calls=totals["calls"], usage=totals["usage"])
        _write_json(costs_path, costs)
        return costs

    async def batch(notes: list[dict[str, str]], cache: dict, path: Path,
                    kind: str, batch_order: str, allow_split: bool = True) -> None:
        """Apply Phase 4 retries, then split once on exhausted model failures."""
        last_reason = "parse_error"

        def valid(content: str) -> bool:
            """Remember a precise validation reason while exposing a bool to retries."""
            nonlocal last_reason
            try:
                validate_labels(content, notes)
                return True
            except ValueError as exc:
                last_reason = str(exc)
                return False

        messages = [{"role": "user", "content": judge_prompt(notes, config.judge_version)}]
        request = ChatRequest(build_chat_kwargs(config.model, messages, judge_response_format()),
                              config.model.timeout_s, "judge", {"notes": notes})
        policy = retry if allow_split else replace(retry, max_model_attempts=1)
        rows, failure = [], None
        try:
            async with semaphore:
                if stopped.is_set():
                    return
                try:
                    response, meta = await _complete_with_retries(request, model_alias="judge", spec=config.model,
                        prompt_version=config.judge_version, client=client, retry=policy, sleep=sleep, parse_ok=valid)
                except FatalAPIError:
                    # Set this before releasing the slot so no waiting batch starts.
                    stopped.set()
                    raise
            rows = validate_labels(response.content, notes)
            attempts = meta["attempts"]
        except AgentTurnFailure as exc:
            attempts = exc.attempts
            failure = f"{exc.category}:{last_reason}" if exc.category == "parse_error" else exc.category
        _append(ledger, dict(judge_version=config.judge_version, kind=kind, batch_order=batch_order, ids=[n["id"] for n in notes], attempts=attempts))
        if failure and allow_split and len(notes) > 1:
            middle = len(notes) // 2
            children = await asyncio.gather(batch(notes[:middle], cache, path, kind, batch_order + "/0", False),
                                            batch(notes[middle:], cache, path, kind, batch_order + "/1", False),
                                            return_exceptions=True)
            for child in children:
                if isinstance(child, BaseException):
                    raise child
            return
        for index, note in enumerate(notes):
            row = dict(note_id=note["id"], note=note["note"], judge_version=config.judge_version,
                       dry_run=dry_run, status="uncoded" if failure else "coded")
            if failure:
                row.update({label: None for label in LABELS})
                row.update({f"{label}_quote": None for label in LABELS})
                row["flags"] = [f"uncoded:{failure}"]
            else:
                row.update({key: value for key, value in rows[index].items() if key != "id"})
                row["flags"] = quote_flags(rows[index], note["note"])
            cache[note["id"]] = row
            _append(path, row)

    async def judge_pending(ids: list[str], cache: dict, path: Path, kind: str, batch_size: int) -> None:
        """Shuffle the canonical IDs, omit cached judgments and send batches."""
        ordered = sorted(ids)
        rng = make_rng(derive_seed(config.seed, "judge", "order" if kind == "main" else "consistency-order"))
        ordered = [ordered[int(i)] for i in rng.permutation(len(ordered))]
        positions = {key: index for index, key in enumerate(ordered)}
        ordered = [key for key in ordered if key not in cache]
        tasks = [batch([dict(id=key, note=unique[key]) for key in ordered[start:start + batch_size]],
                       cache, path, kind, f"{0 if kind == 'main' else 1}/{positions[ordered[start]]:010d}")
                 for start in range(0, len(ordered), batch_size)]
        # Fatal errors stop waiting batches; finish the in-flight requests before returning.
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException):
                raise result

    try:
        await judge_pending(list(unique), main, primary_path, "main", config.batch_size)
        coded = [key for key in unique if main[key]["status"] == "coded"]
        sample = consistency_ids(coded, config.consistency_share, config.seed)
        await judge_pending(sample, repeat, repeat_path, "consistency", max(1, config.batch_size // 2))
    finally:
        costs = save_costs()
    consistency = consistency_summary(main, repeat, sample, dry_run=dry_run)
    consistency["judge_version"] = config.judge_version
    rows = []
    for turn in turns.to_dict("records"):
        row = {key: turn[key] for key in OUTPUT_COLUMNS if key in turn}
        if turn["note_id"]:
            record = main[turn["note_id"]]
            row.update({key: record[key] for key in (*LABELS, *(f"{label}_quote" for label in LABELS), "status", "flags")})
        else:
            row.update(status="empty", flags=[])
        row["dry_run"] = dry_run
        rows.append(row)
    labels = pd.DataFrame(rows).reindex(columns=OUTPUT_COLUMNS)
    _write_csv(out / "note_labels.csv", labels)
    _write_json(out / "consistency.json", consistency)
    return JudgeRun(labels, costs, consistency)
