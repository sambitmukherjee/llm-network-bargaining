"""Exercise actual CLI output, deterministic CSVs, and class consistency checks."""

import csv
import json
from pathlib import Path
import re
import subprocess
import sys

import pytest

from llm_network_bargaining import predictions
from llm_network_bargaining.networks import Network, list_networks
from llm_network_bargaining.structure import node_classes
from llm_network_bargaining.theory import myerson_value

NODE_COLUMNS = "network_id,kind,node,node_class,degree,betweenness,excludable,max_deals,total_value,myerson,myerson_method,position_value,position_value_method,position_value_samples,position_value_seed,core_min,core_max,core_empty,balanced".split(",")
CLASS_COLUMNS = "network_id,node_class,n_members,members,myerson,position_value,core_min,core_max,balanced,excludable".split(",")


def _run_cli(out: Path, *tags: str) -> None:
    command = [sys.executable, "-m", "llm_network_bargaining.predictions", "--out", str(out)]
    for tag in tags:
        command.extend(["--tag", tag])
    subprocess.run(command, check=True, capture_output=True, text=True)


def test_cli_tables_are_complete_and_repeatable(tmp_path: Path) -> None:
    """Separate processes produce complete tables with byte-identical CSVs."""
    first, second = tmp_path / "first", tmp_path / "second"
    _run_cli(first)
    _run_cli(second)
    assert {path.name for path in first.iterdir()} == {
        "node_predictions.csv", "class_predictions.csv", "metadata.json"}
    for name, columns in (("node_predictions.csv", NODE_COLUMNS),
                          ("class_predictions.csv", CLASS_COLUMNS)):
        assert (first / name).read_bytes() == (second / name).read_bytes()
        with (first / name).open(newline="", encoding="utf-8") as source:
            reader = csv.DictReader(source)
            assert reader.fieldnames == columns
            rows = list(reader)
        if name == "node_predictions.csv":
            assert len(rows) == sum(len(net.nodes) for net in list_networks())
            assert [(row["network_id"], row["node"]) for row in rows] == [
                (net.id, node) for net in list_networks() for node in net.nodes]
            for row in rows:
                for column in ("degree", "betweenness", "max_deals", "total_value", "myerson",
                               "position_value", "position_value_samples", "position_value_seed",
                               "core_min", "core_max", "balanced"):
                    assert row[column] == "" or re.fullmatch(r"-?\d+\.\d{6}", row[column])
                if row["kind"] == "broker":
                    assert row["excludable"] == "" and row["balanced"] == ""
                if row["network_id"] == "triangle":
                    assert row["core_empty"] == "true"
                    assert row["core_min"] == row["core_max"] == row["balanced"] == ""
            assert "-0.000000" not in (first / name).read_text()
        else:
            assert len(rows) == sum(len(node_classes(net)) for net in list_networks())
    metadata = json.loads((first / "metadata.json").read_text())
    assert metadata["package_version"] == "0.1.0"
    assert metadata["networks"] == [net.id for net in list_networks()]
    assert metadata["generated_at"]
    assert metadata["theory_settings"]["myerson_exact_max_nodes"] == 16
    assert metadata["theory_settings"]["position_exact_max_links"] == 16
    assert metadata["git_commit"] is None or re.fullmatch(r"[0-9a-f]{40,64}", metadata["git_commit"])


def test_cli_tag_selection(tmp_path: Path) -> None:
    """A single tag selects the core, and repeated tags form a registry-ordered union."""
    _run_cli(tmp_path / "core", "core")
    metadata = json.loads((tmp_path / "core" / "metadata.json").read_text())
    assert metadata["networks"] == [net.id for net in list_networks("core")]
    _run_cli(tmp_path / "union", "core", "control")
    metadata = json.loads((tmp_path / "union" / "metadata.json").read_text())
    assert metadata["networks"] == [net.id for net in list_networks()
                                     if "core" in net.tags or "control" in net.tags]


def test_class_values_are_checked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Class aggregation fails if the source allocations violate exact symmetry."""
    def inconsistent(net: Network) -> dict[str, float]:
        values = myerson_value(net)
        if net.id == "line3":
            values["C"] += 0.01
        return values

    monkeypatch.setattr(predictions, "myerson_value", inconsistent)
    with pytest.raises(ValueError, match="Class members differ"):
        predictions.write_predictions(tmp_path, ["core"])
