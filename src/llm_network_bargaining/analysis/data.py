"""Read completed episode logs into the five analysis tables."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
import re

import numpy as np
import pandas as pd

from ..networks import get_network
from ..runlog import LogRecords, find_logs, read_log
from ..structure import class_of
from .windows import window_rounds

TABLE_COLUMNS = {
    "episodes": "episode_uid config_name condition_key network_id knowledge assignment episode_index episode_seed attempt n_rounds n_nodes prompt_version dry_run_bot cost_usd n_turn_calls n_quiz_calls".split(),
    "node_rounds": "episode_uid config_name network_id knowledge assignment node node_class model_alias round points dealt partner maker share slot1 slot1_norm".split(),
    "deals": "episode_uid round phase maker recipient maker_points recipient_points maker_class recipient_class".split(),
    "turns": "episode_uid round phase slot node model_alias auto applied valid reason n_attempts cost_usd note note_words warnings".split(),
    "quizzes": "episode_uid node model_alias score q1 q2 q3".split(),
}


@dataclass
class Dataset:
    """Five tidy tables of completed episodes, plus their shared dry/live mode."""

    episodes: pd.DataFrame
    node_rounds: pd.DataFrame
    deals: pd.DataFrame
    turns: pd.DataFrame
    quizzes: pd.DataFrame
    dry_run: bool


def dataset_from_tables(*, episodes: pd.DataFrame | None = None,
                        node_rounds: pd.DataFrame | None = None,
                        deals: pd.DataFrame | None = None,
                        turns: pd.DataFrame | None = None,
                        quizzes: pd.DataFrame | None = None,
                        dry_run: bool = False) -> Dataset:
    """Copy supplied test tables and supply the documented columns on empty ones."""
    supplied = dict(episodes=episodes, node_rounds=node_rounds, deals=deals,
                    turns=turns, quizzes=quizzes)
    tables = {name: (pd.DataFrame(columns=columns) if supplied[name] is None
                     else supplied[name].reindex(columns=columns).copy())
              for name, columns in TABLE_COLUMNS.items()}
    return Dataset(**tables, dry_run=dry_run)


def _episode_tables(records: LogRecords, rows: dict[str, list[dict]]) -> None:
    """Append one episode's event-derived rows to the five table builders."""
    header, footer = records.header, records.footer
    net = get_network(header["network_id"])
    classes = class_of(net)
    uid = f"{header['condition_key']}/{header['episode_index']:03d}"
    context = {key: header[key] for key in ("config_name", "network_id", "knowledge", "assignment")}
    rows["episodes"].append(dict(
        episode_uid=uid, **context, condition_key=header["condition_key"],
        episode_index=header["episode_index"], episode_seed=header["episode_seed"],
        attempt=header["attempt"], n_rounds=header["settings"]["rounds"], n_nodes=len(net.nodes),
        prompt_version=header["prompt_version"], dry_run_bot=header.get("dry_run_bot"),
        cost_usd=footer["cost_usd"], n_turn_calls=footer["n_turn_calls"], n_quiz_calls=footer["n_quiz_calls"]))
    phase1 = {}
    deals = {}
    for event in records.events:
        kind = event["type"]
        if kind == "phase_start" and event["phase"] == 1:
            phase1[event["round"]] = {node: slot for slot, node in enumerate(event["order"], 1)}
        elif kind == "deal":
            row = {key: event[key] for key in ("round", "phase", "maker", "recipient", "maker_points", "recipient_points")}
            rows["deals"].append(dict(episode_uid=uid, **row,
                                      maker_class=classes[event["maker"]], recipient_class=classes[event["recipient"]]))
            for node, partner, maker in [(event["maker"], event["recipient"], True),
                                         (event["recipient"], event["maker"], False)]:
                deals[(event["round"], node)] = (partner, maker)
        elif kind == "turn":
            meta = event.get("meta", {})
            requested = event.get("requested") or {}
            note = requested.get("note") or ""
            rows["turns"].append(dict(
                episode_uid=uid, round=event["round"], phase=event["phase"], slot=event["slot"],
                node=event["agent"], model_alias=header["node_models"][event["agent"]],
                auto=event["auto"], applied=event["applied"], valid=event["valid"], reason=event["reason"],
                n_attempts=len(meta.get("attempts", [])), cost_usd=meta.get("cost_usd", 0.0),
                note=note, note_words=len(note.split()), warnings=meta.get("warnings", [])))
        elif kind == "round_end":
            r = event["round"]
            for node in net.nodes:
                partner, maker = deals.get((r, node), (None, False))
                points, slot = event["points"][node], phase1[r][node]
                rows["node_rounds"].append(dict(
                    episode_uid=uid, **context, node=node, node_class=classes[node],
                    model_alias=header["node_models"][node], round=r, points=points,
                    dealt=partner is not None, partner=partner, maker=maker,
                    share=points / net.pie if partner is not None else np.nan,
                    slot1=slot, slot1_norm=(slot - 1) / (len(net.nodes) - 1)))
    for quiz in records.quizzes:
        rows["quizzes"].append(dict(episode_uid=uid, node=quiz["node"],
                                    model_alias=header["node_models"][quiz["node"]], score=quiz["score"],
                                    **dict(zip(("q1", "q2", "q3"), quiz["correct"]))))


def load_dataset(roots: Iterable[str | Path], *, configs: Sequence[str] | None = None,
                 include_dry: bool = False) -> Dataset:
    """Load completed logs; reject duplicate episodes and mixed dry/live sources.

    Mode validation includes non-completed attempts in the selected configs.
    They contribute no rows to these tables. Use diagnostics for their costs.
    """
    rows = {name: [] for name in TABLE_COLUMNS}
    modes = set()
    identities = set()
    for path in find_logs(roots):
        records = read_log(path)
        header = records.header
        if not header or (configs is not None and header["config_name"] not in configs):
            continue
        modes.add(header.get("dry_run_bot") is not None)
        if len(modes) > 1:
            raise ValueError("Cannot mix live and dry-run logs.")
        if True in modes and not include_dry:
            raise ValueError("Dry-run logs require include_dry=True.")
        if not re.fullmatch(r"episode_\d+\.jsonl\.gz", path.name):
            continue
        if records.footer is None or records.footer["status"] != "completed":
            raise ValueError(f"Completed filename has no completed footer: {path}")
        identity = (header["config_name"], header["condition_key"], header["episode_index"])
        if identity in identities:
            raise ValueError(f"Duplicate episode: {identity}")
        identities.add(identity)
        _episode_tables(records, rows)
    return dataset_from_tables(**{name: pd.DataFrame(data, columns=TABLE_COLUMNS[name])
                                   for name, data in rows.items()}, dry_run=True in modes)


def outcome_rows(ds: Dataset, window: str = "second_half") -> pd.DataFrame:
    """Select window rounds, adding episode metadata needed by grouped metrics."""
    # Validate the name even for an empty dataset.
    window_rounds(12, window)
    rows = ds.node_rounds.merge(ds.episodes[["episode_uid", "condition_key", "episode_index", "n_rounds"]],
                                 on="episode_uid", validate="many_to_one")
    if rows.empty:
        return rows
    keep = pd.Series(False, index=rows.index)
    for length in sorted(rows.n_rounds.unique()):
        keep |= (rows.n_rounds == length) & rows["round"].isin(window_rounds(int(length), window))
    return rows.loc[keep].copy()
