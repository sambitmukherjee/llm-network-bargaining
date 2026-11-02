"""The pilot's four readiness checks and informational game-length decision."""

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .data import Dataset, dataset_from_tables
from .game_length import game_length_decision
from .metrics import (attempt_diagnostics, episode_pair_proposer_share,
                      invalid_action_rates, quiz_summary)
from .stats import json_ready


def select_configs(ds: Dataset, names: Sequence[str]) -> Dataset:
    """Copy a Dataset restricted to config names, preserving table schemas."""
    episodes = ds.episodes[ds.episodes.config_name.isin(names)]
    ids = set(episodes.episode_uid)
    return dataset_from_tables(episodes=episodes, dry_run=ds.dry_run, **{
        name: getattr(ds, name)[getattr(ds, name).episode_uid.isin(ids)]
        for name in ("node_rounds", "deals", "turns", "quizzes")})


@dataclass(frozen=True)
class GateCheck:
    """One check's displayed value and the evidence behind its decision."""

    name: str
    measure: str
    threshold: str
    value: Any
    passed: bool
    detail: Any


@dataclass(frozen=True)
class GateResult:
    """Readiness depends on G1--G4; G5 supplies a study length when available."""

    checks: dict[str, GateCheck]
    overall: str
    game_length: int | None
    next_steps: list[str]
    game_length_detail: dict

    def to_dict(self) -> dict:
        """Return strict JSON-compatible gate evidence."""
        return json_ready(asdict(self))


def pilot_gate(ds: Dataset, roots: Iterable[str | Path], *, full_map: str = "pilot_full_map",
                own_links: str = "pilot_own_links") -> GateResult:
    """Evaluate inclusive thresholds with tolerance 1e-9, using Phase 6 metrics."""
    pilot = select_configs(ds, [full_map, own_links])
    attempts = attempt_diagnostics(roots, configs=[full_map, own_links])
    failed = int(attempts.failed_attempts.sum())
    abandoned = int(attempts.abandoned_episodes.sum())
    completed = len(pilot.episodes)
    denominator = completed + failed
    failure_share = failed / denominator if denominator else None
    categories = Counter()
    for values in attempts.failed_by_category:
        categories.update(values)
    checks = {"G1": GateCheck("Run health", "Abandoned episodes; failed / (completed + failed)",
        "0 abandoned; failed share ≤ 0.10", dict(abandoned=abandoned, failed_share=failure_share),
        bool(denominator and abandoned == 0 and failure_share <= .10 + 1e-9),
        dict(completed=completed, failed=failed, failure_categories=dict(sorted(categories.items())))
        if denominator else "missing data")}

    rates = invalid_action_rates(pilot)
    per_condition = rates.groupby("condition_key", as_index=False)[["n_asked", "n_invalid"]].sum()
    present = set(per_condition.condition_key)
    missing = not len(per_condition) or not set(pilot.episodes.condition_key).issubset(present)
    missing |= bool(len(per_condition) and (per_condition.n_asked == 0).any())
    if missing:
        worst, detail = None, "missing data"
    else:
        per_condition["rate"] = per_condition.n_invalid / per_condition.n_asked
        row = per_condition.sort_values(["rate", "condition_key"], ascending=[False, True]).iloc[0]
        worst = float(row.rate)
        detail = dict(worst_condition=row.condition_key, rate=worst,
                       conditions=per_condition.to_dict("records"),
                       reasons=[dict(condition_key=row.condition_key, model_alias=row.model_alias, by_reason=row.by_reason)
                                for row in rates.itertuples()])
    checks["G2"] = GateCheck("No rule-breaking", "Worst condition's invalid / asked turns", "≤ 0.02 in every condition",
                              worst, worst is not None and worst <= .02 + 1e-9, detail)

    quizzes = quiz_summary(pilot)
    n = int(quizzes.n.sum())
    perfect = float((quizzes.n * quizzes.perfect_share).sum() / n) if n else None
    quiz_detail = (dict(n=n, **{q: float((quizzes.n * quizzes[f"{q}_accuracy"]).sum() / n)
                                for q in ("q1", "q2", "q3")}) if n else "missing data")
    checks["G3"] = GateCheck("Rules understood", "Share scoring 3/3", "≥ 0.90", perfect,
                              perfect is not None and perfect >= .90 - 1e-9, quiz_detail)

    pair = episode_pair_proposer_share(select_configs(pilot, [full_map])).proposer_share.dropna()
    proposer = float(pair.mean()) if len(pair) else None
    checks["G4"] = GateCheck("Pair near 12/12", "Mean episode proposer share (second half)", "0.35 to 0.65",
        proposer, proposer is not None and .35 - 1e-9 <= proposer <= .65 + 1e-9,
        dict(episode_values=pair.tolist()) if len(pair) else "missing data")

    try:
        length_detail = game_length_decision(pilot, config=own_links)
        length = length_detail["decision"]
    except ValueError as exc:
        length, length_detail = None, dict(reason=str(exc))
    checks["G5"] = GateCheck("Game length", "Own-links pilot window comparison", "12 or 24 (informational)",
                              length, length is not None, length_detail if length else "missing data")
    overall = "PASS" if all(checks[key].passed for key in ("G1", "G2", "G3", "G4")) else "FAIL"
    if overall == "PASS" and length is not None:
        steps = [f"Set `settings.rounds: {length}` in the five study configs (minimum_study, own_links_arm, "
                 "stretch_2c_sweep, stretch_2d_control, stretch_2f_h6), keep the pilot configs at 24, "
                 "then run the minimum study."]
    elif overall == "PASS":
        steps = ["Complete the 24-round own-links pilot to obtain the game-length decision before starting the study."]
    else:
        inspections = {
            "G1": f"G1: inspect the failure categories ({dict(sorted(categories.items()))}) and abandoned episodes.",
            "G2": "G2: inspect the reasons for invalid moves in each condition.",
            "G3": f"G3: inspect the per-question quiz accuracy ({quiz_detail}).",
            "G4": "G4: inspect quiz question 1 and the pair's notes for a my_points misreading.",
        }
        steps = [inspections[key] for key in inspections if not checks[key].passed]
        steps.append("Revise the prompt as a new prompt version and re-run the pilot.")
    return GateResult(checks, overall, length, steps, length_detail)
