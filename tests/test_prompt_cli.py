"""Review CLI output is generated from replayed observations and exact stimuli."""

from pathlib import Path
import re
import subprocess
import sys

from llm_network_bargaining._prompt_examples import SCENARIOS


def test_examples_cli(tmp_path: Path) -> None:
    """The CLI prints all nine goldens and writes the identical Markdown review copy."""
    command = [sys.executable, "-m", "llm_network_bargaining.prompts", "examples"]
    printed = subprocess.check_output(command, text=True)
    sections = dict(re.findall(r"## (\w+)\n\n```text\n(.*?)\n```", printed, re.DOTALL))
    assert tuple(sections) == tuple(SCENARIOS)
    for name, actual in sections.items():
        assert actual == (Path(__file__).parent / "golden" / f"{name}.txt").read_text(encoding="utf-8")
    path = tmp_path / "prompt_examples.md"
    subprocess.run([*command, "--out", str(path)], check=True, capture_output=True, text=True)
    assert path.read_text(encoding="utf-8") == printed


def test_sample_cli() -> None:
    """The requested stem turn prints a prompt, and identical seeds repeat it."""
    command = [sys.executable, "-m", "llm_network_bargaining.prompts", "sample",
               "--network", "stem", "--bot", "aspiration", "--knowledge", "own_links",
               "--seed", "1", "--agent", "B", "--round", "3", "--phase", "1"]
    output = subprocess.check_output(command, text=True)
    assert output.startswith("You are agent ")
    assert "Round 3 of 12, phase 1 of 3." in output
    assert subprocess.check_output(command, text=True) == output


def test_sample_turn_not_asked() -> None:
    """A pass bot's forced final-phase turn exits one with a clear explanation."""
    command = [sys.executable, "-m", "llm_network_bargaining.prompts", "sample",
               "--network", "pair", "--bot", "pass", "--knowledge", "own_links",
               "--agent", "A", "--round", "1", "--phase", "3"]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 1
    assert "was not asked" in result.stderr
