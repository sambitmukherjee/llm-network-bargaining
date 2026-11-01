"""Compare every loaded analysis field against the runner's actual log events."""

import asyncio
import gzip
import json
from pathlib import Path
import shutil

import numpy as np
import pytest

from llm_network_bargaining.analysis.data import TABLE_COLUMNS, load_dataset
from llm_network_bargaining.analysis.metrics import attempt_diagnostics, cost_summary, invalid_action_rates, quiz_summary
from llm_network_bargaining.runner import plan_jobs, run_jobs
from llm_network_bargaining.replay import replay_log
from llm_network_bargaining.runlog import attempt_costs, episode_path, find_logs, read_log
from phase5_helpers import small_config, write_records, install_fault


def test_all_tables_against_dry_logs(analysis_logs: Path) -> None:
    ds = load_dataset([analysis_logs], include_dry=True)
    assert len(ds.episodes) == 36 and ds.dry_run
    for table, columns in TABLE_COLUMNS.items():
        assert list(getattr(ds, table).columns) == columns
    for path in find_logs([analysis_logs]):
        records = read_log(path)
        header = records.header
        uid = f"{header['condition_key']}/{header['episode_index']:03d}"
        episode = ds.episodes[ds.episodes.episode_uid == uid].iloc[0]
        rows = ds.node_rounds[ds.node_rounds.episode_uid == uid]
        assert len(rows) == episode.n_nodes * episode.n_rounds
        assert rows.groupby("node").points.sum().to_dict() == records.footer["totals"]
        events = records.events
        assert len(ds.deals[ds.deals.episode_uid == uid]) == sum(e["type"] == "deal" for e in events)
        assert len(ds.turns[ds.turns.episode_uid == uid]) == sum(e["type"] == "turn" for e in events)
        for event in events:
            if event["type"] == "phase_start" and event["phase"] == 1:
                round_rows = rows[rows["round"] == event["round"]].set_index("node")
                assert [round_rows.loc[node, "slot1"] for node in event["order"]] == list(range(1, episode.n_nodes + 1))
            if event["type"] == "deal":
                for node, other, maker in [(event["maker"], event["recipient"], True),
                                            (event["recipient"], event["maker"], False)]:
                    row = rows[(rows.node == node) & (rows["round"] == event["round"])].iloc[0]
                    assert row.dealt and row.partner == other and bool(row.maker) == maker
                    assert row.share == row.points/24
        assert rows.loc[~rows.dealt, "share"].isna().all()
        assert rows.slot1_norm.to_numpy() == pytest.approx((rows.slot1 - 1) / (episode.n_nodes - 1))
    assert len(ds.quizzes) == ds.episodes.n_nodes.sum()
    assert (ds.quizzes.score == 3).all() and ds.quizzes[["q1", "q2", "q3"]].all().all()
    invalid = invalid_action_rates(ds)
    assert invalid.n_asked.sum() == (~ds.turns.auto).sum()
    assert invalid.n_invalid.sum() == ((~ds.turns.valid) & (~ds.turns.auto)).sum()
    assert (quiz_summary(ds).mean_score == 3).all()


def test_dataset_mode_filter_and_duplicate_checks(analysis_logs: Path, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="include_dry"):
        load_dataset([analysis_logs])
    filtered = load_dataset([analysis_logs], configs=["pilot_own_links"], include_dry=True)
    assert len(filtered.episodes) == 4
    source = next(analysis_logs.rglob("episode_000.jsonl.gz"))
    duplicate = tmp_path / "duplicate"
    duplicate.mkdir()
    shutil.copyfile(source, duplicate / source.name)
    with pytest.raises(ValueError, match="Duplicate"):
        load_dataset([analysis_logs, duplicate], include_dry=True)
    data = read_log(source).to_list()
    data[0]["dry_run_bot"] = None
    write_records(duplicate / source.name, data)
    with pytest.raises(ValueError, match="mix"):
        load_dataset([analysis_logs, duplicate], include_dry=True)


def test_interrupted_costs_survive_resume(tmp_path: Path) -> None:
    config = small_config(tmp_path)
    job = plan_jobs([config])[0]
    root = tmp_path / "out"
    asyncio.run(run_jobs([job], out_root=root, dry_run_bot="aspiration"))
    completed = episode_path(root / job.log_dir, 0)
    records = read_log(completed)
    prefix = [records.header, *records.quizzes]
    for event in records.events:
        prefix.append(event)
        if event["type"] == "round_end" and event["round"] == 2:
            break
    partial = episode_path(completed.parent, 0, status="partial")
    write_records(partial, prefix)
    completed.unlink()
    known_cost = attempt_costs(read_log(partial))["cost_usd"]
    assert known_cost > 0
    assert load_dataset([root], include_dry=True).episodes.empty
    asyncio.run(run_jobs([job], out_root=root, dry_run_bot="aspiration", max_episode_attempts=1))
    interrupted = episode_path(completed.parent, 0, status="interrupted", attempt=1)
    assert interrupted.exists() and not partial.exists()
    done = read_log(completed)
    assert done.header["attempt"] == 2
    assert attempt_costs(read_log(interrupted))["cost_usd"] == known_cost
    assert replay_log(interrupted).ok
    summary = json.loads((root / "tiny/summary.json").read_text())["totals"]
    assert summary["interrupted_attempts"] == 1 and summary["failed_attempts"] == 0
    assert summary["cost_usd"] == pytest.approx(known_cost + done.footer["cost_usd"])
    ds = load_dataset([root], include_dry=True)
    assert len(ds.episodes) == 1
    costs = cost_summary(ds, [root]).set_index("status")
    assert costs.loc["non_completed", "cost_usd"] == known_cost
    assert costs.loc["completed", "cost_usd"] == done.footer["cost_usd"]
    diagnostic = attempt_diagnostics([root]).iloc[0]
    assert diagnostic.interrupted_attempts == 1 and diagnostic.non_completed_cost_usd == known_cost


def test_interruptions_do_not_use_up_failure_limit(tmp_path: Path, monkeypatch) -> None:
    config = small_config(tmp_path)
    job = plan_jobs([config])[0]
    root = tmp_path / "out"
    asyncio.run(run_jobs([job], out_root=root, dry_run_bot="aspiration"))
    completed = episode_path(root / job.log_dir, 0)
    records = read_log(completed)
    write_records(episode_path(completed.parent, 0, status="partial"), [records.header, *records.quizzes])
    completed.unlink()
    install_fault(monkeypatch, lambda job, attempt, request: True)
    result = asyncio.run(run_jobs([job], out_root=root, dry_run_bot="aspiration", max_episode_attempts=2))
    assert result.abandoned == 1
    assert read_log(episode_path(completed.parent, 0, status="failed", attempt=2)).header["attempt"] == 2
    assert read_log(episode_path(completed.parent, 0, status="failed", attempt=3)).header["attempt"] == 3
    diagnostic = attempt_diagnostics([root], max_failed=2).iloc[0]
    assert diagnostic.failed_attempts == 2 and diagnostic.interrupted_attempts == 1
    assert diagnostic.abandoned_episodes == 1 and diagnostic.failed_by_category == {"refusal": 2}
    empty = load_dataset([root], include_dry=True)
    assert empty.episodes.empty
    assert cost_summary(empty, [root]).cost_usd.sum() == pytest.approx(result.cost_usd)
