"""A log alone reproduces play; altered actions, points, orders and prompts fail."""

import asyncio
from pathlib import Path

import pytest

from llm_network_bargaining.replay import main, replay_log
from llm_network_bargaining.runlog import episode_path, read_log
from llm_network_bargaining.runner import plan_jobs, run_jobs
from phase5_helpers import small_config, write_records


@pytest.fixture
def completed_log(tmp_path: Path) -> Path:
    config = small_config(tmp_path)
    jobs = plan_jobs([config])
    asyncio.run(run_jobs(jobs, out_root=tmp_path / "out", dry_run_bot="aspiration"))
    return episode_path(tmp_path / "out" / jobs[0].log_dir, 0)


@pytest.mark.parametrize("change,description", [
    ("action", "requested"), ("points", "round_end"), ("order", "phase_start"),
    ("hash", "prompt_sha256"), ("name", "names"), ("message", "prompt messages"),
    ("quiz_order", "quiz orders"), ("totals", "footer totals"),
])
def test_tampering_is_detected(completed_log: Path, tmp_path: Path, change: str, description: str) -> None:
    assert replay_log(completed_log).ok
    records = read_log(completed_log).to_list()
    if change == "action":
        record = next(record for record in records if record["type"] == "turn" and not record["auto"]
                      and record["requested"]["kind"] == "offer")
        record["requested"]["my_points"] += 1
    elif change == "points":
        record = next(record for record in records if record["type"] == "round_end")
        record["points"]["A"] += 1
    elif change == "order":
        record = next(record for record in records if record["type"] == "phase_start")
        record["order"].reverse()
    elif change in ("hash", "message"):
        record = next(record for record in records if record["type"] == "turn" and not record["auto"])
        if change == "hash":
            record["meta"]["prompt_sha256"] = "changed"
        else:
            record["meta"]["messages"][0]["content"] += " changed"
    elif change == "name":
        records[0]["names"]["A"] = "Changed"
    elif change == "quiz_order":
        record = next(record for record in records if record["type"] == "quiz")
        record["orders"][0].reverse()
    elif change == "totals":
        records[-1]["totals"]["A"] += 1
    path = tmp_path / "tampered.jsonl.gz"
    write_records(path, records)
    replay = replay_log(path)
    assert not replay.ok
    assert any(description in message for message in replay.mismatches), replay.mismatches
    assert main([str(path)]) == 1


def test_standalone_cli_and_plain_log(completed_log: Path, tmp_path: Path) -> None:
    plain = tmp_path / "plain.jsonl"
    write_records(plain, read_log(completed_log).to_list())
    result = replay_log(plain)
    assert result.ok and result.n_events > result.n_turns > 0
    assert main([str(plain), str(completed_log.parent)]) == 0
