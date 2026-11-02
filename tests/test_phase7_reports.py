"""Reports reproduce the source numbers, and notebook cells run without Jupyter."""

import asyncio
import json
from pathlib import Path
import re

import pytest

from llm_network_bargaining.analysis.data import load_dataset
from llm_network_bargaining.analysis.gate import pilot_gate
from llm_network_bargaining.analysis.hypotheses import run_hypotheses
from llm_network_bargaining.analysis.report import (DRY_BANNER, main, write_notebook, write_pilot_report, write_study_report)
from llm_network_bargaining.fake_client import FakeChatClient
from llm_network_bargaining.notes.judge import KeywordResponder, code_notes, load_judge_config
from phase7_helpers import note_dataset, read_markdown_table


def test_reports_link_figures_and_reproduce_tables(report_logs: Path, tmp_path: Path) -> None:
    roots = [report_logs]
    ds = load_dataset(roots, include_dry=True)
    gate = pilot_gate(ds, roots)
    hypotheses = run_hypotheses(ds, seed=4, n_boot=30).to_dict()
    paths = []
    for name, function in [("pilot", write_pilot_report), ("study", write_study_report)]:
        for repeat in range(2):
            path = function(roots, tmp_path / f"{name}{repeat}", include_dry=True, seed=4, n_boot=30)
            paths.append(path)
            text = path.read_text()
            assert text.startswith(DRY_BANNER)
            links = re.findall(r"!\[[^\]]*\]\((figures/[^)]+\.png)\)", text)
            assert len(links) == (1 if name == "pilot" else 4)
            for link in links:
                assert (path.parent / link).is_file()
                assert (path.parent / link).with_suffix(".svg").is_file()
    assert paths[0].read_bytes() == paths[1].read_bytes()
    assert paths[2].read_bytes() == paths[3].read_bytes()
    for first, second in [(paths[0], paths[1]), (paths[2], paths[3])]:
        for svg in (first.parent / "figures").glob("*.svg"):
            assert svg.read_bytes() == (second.parent / "figures" / svg.name).read_bytes()
    gate_rows = read_markdown_table(paths[0].read_text(), "Check")
    assert len(gate_rows) == 5
    for row, (key, value) in zip(gate_rows, gate.checks.items()):
        assert row["Check"].startswith(key)
        assert row["PASS/FAIL"] == ("INFO" if key == "G5" else "PASS" if value.passed else "FAIL")
        if key == "G1":
            assert row["Value"] == f"{value.value['abandoned']} abandoned; failed share {value.value['failed_share']:.2f}"
        elif key == "G5":
            assert row["Value"] == f"{value.value} rounds"
        else:
            assert row["Value"] == f"{value.value:.2f}"
    test_rows = read_markdown_table(paths[2].read_text(), "Hypothesis")
    assert [row["Hypothesis"] for row in test_rows] == ["H1", "H3", "H4", "H5", "H6"]
    for row in test_rows:
        expected = hypotheses["results"][row["Hypothesis"]]
        if expected["status"] == "not_run":
            assert row["Decision"] == "not run"
        else:
            assert row["Statistic"] == f"{expected['statistic']:.2f}"
            assert row["p"] == f"{expected['p_value']:.4g}"
            assert row["Holm-adjusted p"] == f"{expected['p_adjusted']:.4g}"


def test_notebook_json_and_executable_cells(report_logs: Path, tmp_path: Path, monkeypatch, capsys) -> None:
    notebook_path = write_notebook(tmp_path / "analysis.ipynb")
    original = notebook_path.read_bytes()
    assert write_notebook(notebook_path).read_bytes() == original
    notebook = json.loads(original)
    assert notebook["nbformat"] == 4
    monkeypatch.setenv("LNB_ROOTS", str(report_logs))
    monkeypatch.setenv("LNB_INCLUDE_DRY", "1")
    monkeypatch.setenv("LNB_OUT", str(tmp_path / "executed"))
    namespace = {"display": lambda value: None}
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            assert cell["outputs"] == [] and cell["execution_count"] is None
            exec(compile("".join(cell["source"]), str(notebook_path), "exec"), namespace)
    assert len(list((tmp_path / "executed/figures").glob("*.png"))) == 5
    assert notebook_path.read_bytes() == original


def test_notes_prevalence_in_report_and_cli(report_logs: Path, tmp_path: Path) -> None:
    config = load_judge_config()
    result = asyncio.run(code_notes(note_dataset(["A fair split.", "Classic ultimatum logic."]), config,
        out=tmp_path / "notes", client=FakeChatClient(KeywordResponder()), dry_run=True))
    from llm_network_bargaining.analysis.report import _notes_section
    text = _notes_section(tmp_path / "notes/note_labels.csv", load_dataset([report_logs], include_dry=True))
    assert "Repeat consistency measures consistency, not correctness" in text
    assert "validation against hand labels is future work" in text.lower()
    assert "Quotes not found in their notes: 0.00" in text
    assert "fairness" in text and "recognition" in text
    assert main(["notebook", "--out", str(tmp_path / "cli.ipynb")]) == 0
