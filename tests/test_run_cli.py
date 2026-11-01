"""CLI planning, dry runs, resume status and live-mode safety without network."""

import io
from pathlib import Path

import pytest

from llm_network_bargaining import cli
from llm_network_bargaining.model_client import FatalAPIError
from phase5_helpers import ROOT, install_fault, small_config


def test_estimate_total_matches_rows(capsys) -> None:
    assert cli.main(["estimate", str(ROOT / "configs/minimum_study.yaml")]) == 0
    lines = capsys.readouterr().out.splitlines()
    subtotals = [float(line.rsplit(" | ", 1)[1]) for line in lines[1:-1]]
    total = float(lines[-1].split("$")[1])
    assert total == pytest.approx(sum(subtotals), abs=1e-7)


def test_dry_cli_status_replay_and_resume(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    small_config(tmp_path, episodes=2)
    config = str(tmp_path / "tiny.yaml")
    output = str(tmp_path / "out")
    assert cli.main(["run", config, "--dry-run", "aspiration", "--max-episodes", "1", "--out", output]) == 0
    assert "simulated" in capsys.readouterr().out.lower()
    assert cli.main(["status", config, "--out", output]) == 0
    assert "tiny/line3/full_map/terra | 1 | 0 | 1 | 0" in capsys.readouterr().out
    assert cli.main(["run", config, "--dry-run", "aspiration", "--max-episodes", "2", "--out", output]) == 0
    assert "ep 000 attempt" not in capsys.readouterr().out
    assert cli.main(["replay", output]) == 0
    assert "PASS" in capsys.readouterr().out


def test_live_without_key_precedes_planning(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def refuse(*args, **kwargs):
        raise AssertionError("No planning or client construction is permitted without a key.")

    monkeypatch.setattr(cli, "load_configs", refuse)
    assert cli.main(["run", "missing.yaml"]) == 1
    assert "OPENAI_API_KEY" in capsys.readouterr().out


def test_non_tty_without_yes_stops_before_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    small_config(tmp_path)
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO())

    def refuse(*args, **kwargs):
        raise AssertionError("The run must not start without confirmation.")

    monkeypatch.setattr(cli, "run_jobs", refuse)
    assert cli.main(["run", str(tmp_path / "tiny.yaml"), "--out", str(tmp_path / "out")]) == 3
    output = capsys.readouterr().out
    assert "condition | todo" in output and "not confirmed" in output
    assert not (tmp_path / "out").exists()


def test_cli_abandoned_and_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    small_config(tmp_path, networks=("line3", "stem"))
    clients = install_fault(monkeypatch, lambda job, attempt, request: job.condition.network_id == "line3")
    args = ["run", str(tmp_path / "tiny.yaml"), "--dry-run", "aspiration", "--out", str(tmp_path / "out")]
    assert cli.main(args) == 4
    count = len(clients)
    assert cli.main(args) == 4 and len(clients) == count
    assert cli.main(["status", str(tmp_path / "tiny.yaml"), "--out", str(tmp_path / "out")]) == 4
    output = capsys.readouterr().out
    assert "tiny/line3/full_map/terra | 0 | 0 | 0 | 1" in output
    assert "tiny/stem/full_map/terra | 0 | 0 | 1 | 0" in output


def test_cli_fatal_error_returns_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    small_config(tmp_path)
    install_fault(monkeypatch, lambda job, attempt, request: True, fatal=True)
    assert cli.main(["run", str(tmp_path / "tiny.yaml"), "--dry-run", "aspiration", "--out", str(tmp_path / "out")]) == 1


def test_modes_cannot_mix(tmp_path: Path) -> None:
    small_config(tmp_path)
    args = [str(tmp_path / "tiny.yaml"), "--out", str(tmp_path / "out")]
    assert cli.main(["run", *args, "--dry-run", "aspiration"]) == 0
    # It must refuse before confirmation or constructing any real client.
    assert cli.main(["run", *args]) == 1
