"""The bot CLI prints deterministic class summaries and never writes outputs."""

from pathlib import Path
import subprocess
import sys


def test_simulate_cli(tmp_path: Path) -> None:
    """Two identical simulations print both line3 classes and identical text."""
    command = [sys.executable, "-m", "llm_network_bargaining.simulate",
               "--network", "line3", "--bot", "aspiration", "--episodes", "2"]
    first = subprocess.run(command, check=True, capture_output=True, text=True, cwd=tmp_path)
    second = subprocess.run(command, check=True, capture_output=True, text=True, cwd=tmp_path)
    assert first.stdout == second.stdout
    lines = first.stdout.splitlines()
    assert any(line.startswith("A|C ") for line in lines)
    assert any(line.startswith("B ") for line in lines)
    assert "mean_deals_per_round" in first.stdout
    assert list(tmp_path.iterdir()) == []


def test_simulate_empty_balanced_and_one_round() -> None:
    """A one-episode triangle simulation leaves balanced blank and reports zero SD."""
    command = [sys.executable, "-m", "llm_network_bargaining.simulate", "--network", "triangle",
               "--bot", "equal_split", "--episodes", "1", "--rounds", "1"]
    output = subprocess.check_output(command, text=True)
    row = next(line for line in output.splitlines() if line.startswith("A|B|C "))
    assert row.split()[2] == "0.000000"
    assert len(row.split()) == 6
