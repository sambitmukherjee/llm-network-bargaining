"""Read-only comparison of two sets of labels on the same asked turns."""

from pathlib import Path

import pandas as pd

from . import LABELS
from .consistency import cohens_kappa


def compare_labels(labels_a: str | Path, labels_b: str | Path) -> str:
    """Match coded turns and show agreement and every changed label as Markdown."""
    from ..analysis.report import markdown_table

    tables = []
    for path in (labels_a, labels_b):
        table = pd.read_csv(path)
        table = table[table.status == "coded"].copy()
        for label in LABELS:
            table[label] = table[label].astype(str).str.lower().map({"true": True, "false": False})
            if table[label].isna().any():
                raise ValueError(f"Invalid coded label in {path}: {label}.")
        tables.append(table)
    paired = tables[0].merge(tables[1], on=["episode_uid", "turn_index"], suffixes=("_a", "_b"), validate="one_to_one")
    paired = paired.sort_values(["episode_uid", "turn_index"])
    if paired.empty:
        raise ValueError("No matching rows coded in both files.")
    agreement = [dict(label=label, **cohens_kappa(paired[f"{label}_a"], paired[f"{label}_b"])) for label in LABELS]
    changes = []
    for row in paired.to_dict("records"):
        changed = [f"{label}: {'yes' if row[f'{label}_a'] else 'no'} → {'yes' if row[f'{label}_b'] else 'no'}"
                   for label in LABELS if row[f"{label}_a"] != row[f"{label}_b"]]
        if changed:
            changes.append({key: row[f"{key}_a"] for key in ("round", "phase", "node", "note")} | {"changes": "; ".join(changed)})
    return "\n\n".join([f"Labels A: {labels_a}\n\nLabels B: {labels_b}\n\nMatched rows: {len(paired)}",
        markdown_table(pd.DataFrame(agreement), "label n agreement yes_rate_a yes_rate_b kappa".split()),
        markdown_table(pd.DataFrame(changes), "round phase node note changes".split())])
