"""Write deterministic prediction tables: python -m llm_network_bargaining.predictions."""

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from typing import Sequence

from . import __version__
from .networks import Network, list_networks
from .structure import (betweenness, class_label, class_of, degree,
                        excludable_nodes, max_deals, node_classes)
from .theory import (DEFAULT_SEED, MYERSON_EXACT_MAX_NODES, MYERSON_SAMPLES,
                     NUCLEOLUS_MAX_NODES, POSITION_EXACT_MAX_LINKS, POSITION_SAMPLES,
                     balanced_outcome, core_bounds, myerson_value, position_value)

NODE_COLUMNS = (
    "network_id", "kind", "node", "node_class", "degree", "betweenness",
    "excludable", "max_deals", "total_value", "myerson", "myerson_method",
    "position_value", "position_value_method", "position_value_samples",
    "position_value_seed", "core_min", "core_max", "core_empty", "balanced",
)
CLASS_COLUMNS = (
    "network_id", "node_class", "n_members", "members", "myerson",
    "position_value", "core_min", "core_max", "balanced", "excludable",
)

Cell = str | int | float | bool | None
Row = dict[str, Cell]


def _network_rows(net: Network) -> tuple[list[Row], list[Row]]:
    classes = class_of(net)
    degrees, centrality = degree(net), betweenness(net)
    excluded = excludable_nodes(net) if net.kind == "exchange" else None
    deals = max_deals(net)
    myerson = myerson_value(net)
    myerson_method = "exact" if len(net.nodes) <= MYERSON_EXACT_MAX_NODES else "sample"
    position = position_value(net)
    core = core_bounds(net)
    balanced = balanced_outcome(net) if net.kind == "exchange" else None
    nodes: list[Row] = []
    for node in net.nodes:
        nodes.append(dict(
            network_id=net.id, kind=net.kind, node=node, node_class=classes[node],
            degree=degrees[node], betweenness=centrality[node],
            excludable=node in excluded if excluded is not None else None,
            max_deals=deals, total_value=net.pie * deals,
            myerson=myerson[node], myerson_method=myerson_method,
            position_value=position.values[node], position_value_method=position.method,
            position_value_samples=position.n_samples, position_value_seed=position.seed,
            core_min=core[node][0] if core is not None else None,
            core_max=core[node][1] if core is not None else None,
            core_empty=core is None,
            balanced=balanced[node] if balanced is not None else None,
        ))
    by_node = {row["node"]: row for row in nodes}
    class_rows: list[Row] = []
    compared = ("myerson", "position_value", "core_min", "core_max", "balanced", "excludable")
    for members in node_classes(net):
        first = by_node[members[0]]
        for field in compared:
            sampled = ((field == "myerson" and myerson_method == "sample")
                       or (field == "position_value" and position.method == "sample"))
            tolerance = 0.05 if sampled else 1e-9
            for member in members[1:]:
                expected, actual = first[field], by_node[member][field]
                if expected is None or actual is None or isinstance(expected, bool):
                    same = expected == actual
                else:
                    same = abs(float(expected) - float(actual)) <= tolerance
                if not same:
                    raise ValueError(f"Class members differ in {field}: "
                                     f"{net.id}/{class_label(members)}.")
        row: Row = dict(network_id=net.id, node_class=class_label(members),
                        n_members=len(members), members=class_label(members))
        for field in compared:
            # Average numerical class values; this also handles future sampled tables.
            if first[field] is None or isinstance(first[field], bool):
                row[field] = first[field]
            else:
                row[field] = sum(float(by_node[node][field]) for node in members) / len(members)
        class_rows.append(row)
    return nodes, class_rows


def _format(value: Cell) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return f"{value}.000000"
    if isinstance(value, float):
        return f"{0.0 if abs(value) < 0.5e-6 else value:.6f}"
    return value


def _write_csv(path: Path, columns: tuple[str, ...], rows: list[Row]) -> None:
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: _format(row[column]) for column in columns})


def _clean_git_commit() -> str | None:
    root = Path(__file__).resolve().parents[2]
    try:
        status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"],
                                cwd=root, capture_output=True, text=True, check=True)
        if status.stdout:
            return None
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                                capture_output=True, text=True, check=True)
        return commit.stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None


def write_predictions(out: str | Path, tags: Sequence[str] | None = None) -> None:
    """Write node/class CSVs and metadata, keeping the union of any supplied tags.

    Networks follow registry order, nodes follow canonical node order, and node
    classes follow their sorted labels. Only metadata contains a timestamp.
    """
    networks = list_networks()
    if tags:
        known_tags = {tag for net in networks for tag in net.tags}
        unknown = set(tags) - known_tags
        if unknown:
            raise ValueError(f"Unknown network tags: {', '.join(sorted(unknown))}.")
        networks = tuple(net for net in networks if net.tags.intersection(tags))
    node_rows: list[Row] = []
    class_rows: list[Row] = []
    for net in networks:
        nodes, classes = _network_rows(net)
        node_rows.extend(nodes)
        class_rows.extend(classes)
    metadata = dict(
        package_version=__version__,
        theory_settings=dict(
            myerson_exact_max_nodes=MYERSON_EXACT_MAX_NODES,
            position_exact_max_links=POSITION_EXACT_MAX_LINKS,
            myerson_samples=MYERSON_SAMPLES, myerson_seed=DEFAULT_SEED,
            position_value_samples=POSITION_SAMPLES, position_value_seed=DEFAULT_SEED,
            nucleolus_max_nodes=NUCLEOLUS_MAX_NODES,
        ),
        networks=[net.id for net in networks], git_commit=_clean_git_commit(),
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    directory = Path(out)
    directory.mkdir(parents=True, exist_ok=True)
    _write_csv(directory / "node_predictions.csv", NODE_COLUMNS, node_rows)
    _write_csv(directory / "class_predictions.csv", CLASS_COLUMNS, class_rows)
    (directory / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> None:
    """Parse the prediction-table CLI arguments and write its three outputs."""
    parser = argparse.ArgumentParser(description="Generate network bargaining predictions.")
    parser.add_argument("--out", type=Path, default=Path("predictions"))
    parser.add_argument("--tag", action="append", help="Keep networks with any supplied tag.")
    arguments = parser.parse_args(argv)
    write_predictions(arguments.out, arguments.tag)


if __name__ == "__main__":
    main()
