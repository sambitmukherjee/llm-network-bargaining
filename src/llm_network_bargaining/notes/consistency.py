"""Repeat agreement measures consistency, not correctness against hand labels."""

from collections.abc import Sequence
from math import ceil

import numpy as np

from ..seeds import derive_seed, make_rng
from . import LABELS


def consistency_ids(ids: Sequence[str], share: float, seed: int) -> list[str]:
    """Select ceil(share * coded unique notes) from a stable list of IDs."""
    if not 0 <= share <= 1:
        raise ValueError("consistency_share must be between zero and one.")
    ids = sorted(set(ids))
    rng = make_rng(derive_seed(seed, "judge", "consistency"))
    return [ids[int(i)] for i in rng.choice(len(ids), size=ceil(share * len(ids)), replace=False)] if ids else []


def cohens_kappa(a: Sequence[bool], b: Sequence[bool]) -> dict:
    """Return raw agreement, marginal yes rates and kappa with its denominator."""
    a, b = np.asarray(a, dtype=bool), np.asarray(b, dtype=bool)
    if a.ndim != 1 or a.shape != b.shape:
        raise ValueError("The two label arrays must have equal length.")
    if not len(a):
        return dict(n=0, agreement=None, yes_rate_a=None, yes_rate_b=None, expected_agreement=None,
                    kappa=None, reason="no paired coded notes")
    agreement = float((a == b).mean())
    yes_a, yes_b = float(a.mean()), float(b.mean())
    expected = yes_a * yes_b + (1 - yes_a) * (1 - yes_b)
    return dict(n=len(a), agreement=agreement, yes_rate_a=yes_a, yes_rate_b=yes_b, expected_agreement=expected,
                kappa=(agreement - expected) / (1 - expected) if expected < 1 else None,
                reason=None if expected < 1 else "both runs give the same constant label")


def consistency_summary(main: dict[str, dict], repeat: dict[str, dict], sample: Sequence[str],
                         *, dry_run: bool) -> dict:
    """Describe paired coded results; retain missing repeat counts separately."""
    paired = [key for key in sample if key in repeat and repeat[key]["status"] == "coded"]
    return dict(dry_run=dry_run, sample_ids=list(sample), n_selected=len(sample), n_paired=len(paired),
                labels={label: cohens_kappa([main[key][label] for key in paired],
                                             [repeat[key][label] for key in paired]) for label in LABELS},
                interpretation="Repeat consistency is not correctness. Validation against hand labels is future work.")
