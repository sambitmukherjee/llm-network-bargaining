"""Offline smoke previews and CLI guards; live calls are never run here."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from llm_network_bargaining import smoke
from phase4_helpers import terra

ROOT = Path(__file__).resolve().parents[1]
ARGS = ["--config", str(ROOT / "configs" / "minimum_study.yaml"), "--model", "terra"]


def test_smoke_inputs_and_repeated_long_request() -> None:
    requests = smoke.build_smoke_requests(terra())
    assert [label for label, request in requests] == ["short_turn", "long_turn_1", "long_turn_2", "quiz"]
    assert requests[1][1] is requests[2][1]
    assert len(requests[1][1].kwargs["messages"][0]["content"]) > 4096
    assert requests[1][1].context["observation"].round == 24


def test_dry_run_prints_bodies_counts_and_costs_without_key(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    sentinel = "dummy-environment-secret"
    monkeypatch.setenv("OPENAI_API_KEY", sentinel)
    assert smoke.main([*ARGS, "--dry-run"]) == 0
    output = capsys.readouterr().out
    assert sentinel not in output
    lines = output.splitlines()
    for line, (label, request) in zip(lines[:4], smoke.build_smoke_requests(terra())):
        prefix, text = line.split(": ", 1)
        assert prefix == label
        data = json.loads(text)
        content = request.kwargs["messages"][0]["content"]
        assert data["kwargs"]["messages"][0]["content"] == content[:80] + " ... " + content[-80:]
        assert data["message_characters"] == [len(content)]
        assert data["estimated_input_usd"] > 0
        assert data["kwargs"]["store"] is False
        assert data["kwargs"]["extra_body"] == {"prompt_cache_options": {"mode": "explicit"}}
        if label == "quiz":
            assert data["quiz_key"] == {"q1": "A", "q2": "B", "q3": "A"}
            assert data["quiz_answers"] is None and data["quiz_score"] is None
            assert data["quiz_score_status"] == "not_run"
    assert "Estimated input total" in output
    assert "INFO: quiz score not run" in output


def test_quiz_display_keeps_answers_key_and_nonperfect_score_together() -> None:
    answers = {"q1": "A", "q2": "B", "q3": "A"}
    assert smoke._quiz_display(answers, {"q1": "A", "q2": "C", "q3": "B"}, 1) == (
        '{"q1": "A", "q2": "B", "q3": "A"} key A/C/B score 1/3')


@pytest.mark.parametrize("mode,code", [(["--dry-run"], 0), ([], 2), (["--live"], 1),
                                      (["--dry-run", "--live"], 2)])
def test_cli_offline_modes_and_errors(mode: list[str], code: int) -> None:
    env = os.environ.copy()
    env.pop("OPENAI_API_KEY", None)
    result = subprocess.run([sys.executable, "-m", "llm_network_bargaining.smoke", *ARGS, *mode],
                            cwd=ROOT, env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode == code
    if code == 1:
        assert "OPENAI_API_KEY" in result.stdout
    elif code == 2:
        assert "usage:" in result.stderr
    else:
        assert sum(line.startswith(("short_turn:", "long_turn_1:", "long_turn_2:", "quiz:"))
                   for line in result.stdout.splitlines()) == 4


def test_missing_key_precedes_any_client(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def refuse(*args, **kwargs):
        raise AssertionError("Even the wrapper must not be built before checking the key.")

    monkeypatch.setattr(smoke, "OpenAIChatClient", refuse)
    assert smoke.main([*ARGS, "--live"]) == 1
    assert "OPENAI_API_KEY" in capsys.readouterr().out
