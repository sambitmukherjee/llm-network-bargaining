"""Synthetic private notes and a tiny Markdown table reader for report tests."""

import re

import pandas as pd

from llm_network_bargaining.analysis.data import TABLE_COLUMNS
from phase6_helpers import tables_from_specs


def note_dataset(texts: list[str | None], *, automatic_at: int | None = None):
    """Keep real episode/node metadata while injecting small asked-turn notes."""
    ds = tables_from_specs([dict(network="line3", points=[dict(A=0, B=18, C=6)])])
    uid = ds.episodes.episode_uid.iloc[0]
    rows = [dict(episode_uid=uid, round=1, phase=1 + i % 3, slot=1, node="B", model_alias="terra",
                 auto=i == automatic_at, applied="pass", valid=True, reason=None, n_attempts=1,
                 cost_usd=0, note=text, note_words=len((text or "").split()), warnings=[])
            for i, text in enumerate(texts)]
    ds.turns = pd.DataFrame(rows, columns=TABLE_COLUMNS["turns"])
    return ds


def read_markdown_table(text: str, header: str) -> list[dict[str, str]]:
    """Find a generated table by its first column and unescape class-label pipes."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(f"| {header} |"))
    def fields(line):
        return [part.strip().replace("\\|", "|") for part in re.split(r"(?<!\\)\|", line)[1:-1]]
    names = fields(lines[start])
    result = []
    for line in lines[start + 2:]:
        if not line.startswith("|"):
            break
        result.append(dict(zip(names, fields(line))))
    return result
