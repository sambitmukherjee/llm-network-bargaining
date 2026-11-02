"""Offline planning, durable logs, deterministic concurrency and recovery."""

import asyncio
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from llm_network_bargaining import runner
from llm_network_bargaining.config import load_config, load_configs, total_episodes
from llm_network_bargaining.model_client import FatalAPIError
from llm_network_bargaining.names import assign_names
from llm_network_bargaining.networks import get_network
from llm_network_bargaining.replay import replay_log
from llm_network_bargaining.runlog import EpisodeLogWriter, episode_path, find_logs, read_log
from phase5_helpers import ROOT, install_fault, normalize, small_config, write_records


def test_plans_and_estimates() -> None:
    config = load_config(ROOT / "configs/minimum_study.yaml")
    # These reference cost estimates use 12-round study episodes.
    settings = config.settings.model_copy(update={"rounds": 12})
    config = config.model_copy(update={"settings": settings})
    assert len(runner.plan_jobs([config])) == 80
    assert len(runner.plan_jobs([config], max_episodes=2)) == 16
    selected = runner.plan_jobs([config], conditions="minimum_study/line3/*")
    assert len(selected) == 10
    assert runner.estimate_cost(selected[0], config.models) == pytest.approx(0.0815625, abs=1e-9)
    assert runner.estimate_cost(selected[0].condition, config.models) == pytest.approx(0.0815625, abs=1e-9)
    assert selected[0].log_dir == Path("minimum_study/line3/full_map/terra")
    assert [job.episode_index for job in selected] == list(range(10))
    assert [job.episode_seed for job in selected] == selected[0].condition.episode_seeds
    assert config.source_sha256 == hashlib.sha256((ROOT / "configs/minimum_study.yaml").read_bytes()).hexdigest()
    configs = load_configs(sorted(path for path in (ROOT / "configs").glob("*.yaml")
                                  if path.name != "note_judge.yaml"))
    assert len(runner.plan_jobs(configs)) == sum(total_episodes(config) for config in configs)
    h6 = load_config(ROOT / "configs/stretch_2f_h6.yaml")
    settings = h6.settings.model_copy(update={"rounds": 12})
    h6 = h6.model_copy(update={"settings": settings})
    job = runner.plan_jobs([h6])[0]
    per_node = sum((25 * (862.5 * h6.models[alias].price_input_per_m + 45 * h6.models[alias].price_output_per_m))
                   / 1e6 for alias in job.condition.node_models.values())
    assert runner.estimate_cost(job, h6.models) == pytest.approx(per_node)
    with pytest.raises(ValueError, match="positive"):
        runner.plan_jobs([config], max_episodes=0)


def test_pilot_dry_run_end_to_end(tmp_path: Path) -> None:
    configs = load_configs([ROOT / "configs/pilot_full_map.yaml", ROOT / "configs/pilot_own_links.yaml"])
    jobs = runner.plan_jobs(configs, max_episodes=1)
    summary = asyncio.run(runner.run_jobs(jobs, out_root=tmp_path, dry_run_bot="aspiration"))
    assert len(jobs) == summary.done == 10
    assert summary.abandoned == summary.todo == summary.interrupted == 0
    assert summary.dry_run
    assert not list(tmp_path.rglob("*.partial.jsonl"))
    total_cost = 0.0
    required = {"type", "log_schema", "package_version", "python_version", "openai_version",
                "git_commit", "git_dirty", "config_name", "config_sha256", "condition_key", "network_id",
                "knowledge", "assignment", "node_models", "models", "settings", "episode_index",
                "episode_seed", "attempt", "names", "prompt_version", "quiz_version", "dry_run_bot", "started_at"}
    for job in jobs:
        path = episode_path(tmp_path / job.log_dir, 0)
        assert list(path.parent.glob("episode_*")) == [path]
        records = read_log(path)
        assert set(records.header) == required
        assert records.header["names"] == assign_names(get_network(job.condition.network_id), job.episode_seed)
        assert records.header["episode_seed"] == job.condition.episode_seeds[0]
        assert records.header["settings"]["rounds"] == 24
        assert len(records.quizzes) == len(job.condition.node_models)
        assert all(quiz["score"] == 3 for quiz in records.quizzes)
        footer = records.footer
        assert footer["status"] == "completed"
        costs = sum(quiz["meta"]["cost_usd"] for quiz in records.quizzes)
        costs += sum(event["meta"]["cost_usd"] for event in records.events if event["type"] == "turn" and not event["auto"])
        assert footer["cost_usd"] == pytest.approx(costs)
        assert footer["n_turn_calls"] == sum(event["type"] == "turn" and not event["auto"] for event in records.events)
        assert sum(entry["calls"] for entry in footer["usage_by_alias"].values()) == footer["n_turn_calls"] + footer["n_quiz_calls"]
        total_cost += footer["cost_usd"]
        assert replay_log(path).ok
        for line in gzip.decompress(path.read_bytes()).decode().splitlines():
            assert line == json.dumps(json.loads(line), sort_keys=True, ensure_ascii=False)
    assert sum(value["totals"]["done"] for value in summary.configs.values()) == 10
    assert sum(value["totals"]["abandoned"] for value in summary.configs.values()) == 0
    assert all(value["dry_run"] and value["cost_kind"] == "simulated" for value in summary.configs.values())
    assert summary.cost_usd == pytest.approx(total_cost)
    assert sum(value["totals"]["cost_usd"] for value in summary.configs.values()) == pytest.approx(total_cost)
    for value in summary.configs.values():
        assert all(condition["mean_quiz_score"] == 3 for condition in value["conditions"].values())
        assert all(condition["quiz_perfect_share"] == 1 for condition in value["conditions"].values())


def test_determinism_concurrency_and_reproducible_gzip(tmp_path: Path) -> None:
    config = small_config(tmp_path, networks=("line3", "stem"), episodes=2)
    jobs = runner.plan_jobs([config])
    fixed = lambda: datetime(2026, 11, 1, tzinfo=timezone.utc)
    for folder, concurrency in (("one", 1), ("four", 4), ("again", 4)):
        asyncio.run(runner.run_jobs(jobs, out_root=tmp_path / folder, dry_run_bot="aspiration",
                                    concurrency=concurrency, clock=fixed if folder != "again" else runner.utc_now))
    for job in jobs:
        first = episode_path(tmp_path / "one" / job.log_dir, job.episode_index)
        concurrent = episode_path(tmp_path / "four" / job.log_dir, job.episode_index)
        again = episode_path(tmp_path / "again" / job.log_dir, job.episode_index)
        assert first.read_bytes() == concurrent.read_bytes()
        assert normalize(read_log(first).to_list()) == normalize(read_log(again).to_list())


def test_resume_only_new_episodes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = small_config(tmp_path, episodes=2)
    clients = install_fault(monkeypatch, lambda job, attempt, request: False)
    first_jobs = runner.plan_jobs([config], max_episodes=1)
    asyncio.run(runner.run_jobs(first_jobs, out_root=tmp_path / "out", dry_run_bot="aspiration"))
    first_requests = len(clients[0].requests)
    result = asyncio.run(runner.run_jobs(runner.plan_jobs([config], max_episodes=2), out_root=tmp_path / "out", dry_run_bot="aspiration"))
    assert result.done == 2 and len(clients) == 2
    assert len(clients[0].requests) == first_requests
    assert clients[1].requests


@pytest.mark.parametrize("prior_failed", [False, True])
def test_resume_partial_counts_failed_and_interrupted(tmp_path: Path, prior_failed: bool) -> None:
    config = small_config(tmp_path)
    jobs = runner.plan_jobs([config])
    root = tmp_path / "out"
    asyncio.run(runner.run_jobs(jobs, out_root=root, dry_run_bot="aspiration"))
    path = episode_path(root / jobs[0].log_dir, 0)
    records = read_log(path)
    path.unlink()
    if prior_failed:
        footer = {**records.footer, "status": "failed", "totals": None,
                  "cost_usd": 0.0, "cost_by_alias": {}, "usage_by_alias": {}}
        write_records(episode_path(path.parent, 0, status="failed", attempt=1), [records.header, footer])
    partial = episode_path(path.parent, 0, status="partial")
    header = {**records.header, "attempt": 2 if prior_failed else 1}
    partial.write_text(json.dumps(header) + '\n{"torn":')
    assert runner.job_status(jobs[0], root) == "interrupted"
    asyncio.run(runner.run_jobs(jobs, out_root=root, dry_run_bot="aspiration"))
    assert read_log(path).header["attempt"] == (3 if prior_failed else 2)
    archived = episode_path(path.parent, 0, status="interrupted", attempt=1)
    assert read_log(archived).header == header
    assert not partial.exists()


@pytest.mark.parametrize("field,value", [("config_sha256", "changed"), ("prompt_version", "v2")])
def test_resume_rejects_changed_provenance(tmp_path: Path, field: str, value: str) -> None:
    config = small_config(tmp_path)
    jobs = runner.plan_jobs([config])
    root = tmp_path / "out"
    asyncio.run(runner.run_jobs(jobs, out_root=root, dry_run_bot="aspiration"))
    path = episode_path(root / jobs[0].log_dir, 0)
    records = read_log(path).to_list()
    records[0][field] = value
    write_records(path, records)
    with pytest.raises(ValueError, match=str(path)):
        asyncio.run(runner.run_jobs(jobs, out_root=root, dry_run_bot="aspiration"))


@pytest.mark.parametrize("stage", ["turn", "quiz"])
def test_failure_then_same_seed_restart(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str) -> None:
    config = small_config(tmp_path)
    jobs = runner.plan_jobs([config])

    def refuse(job, attempt, request):
        if attempt != 1 or request.context["node"] != "B" or request.purpose != stage:
            return False
        if stage == "quiz":
            return True
        obs = request.context["observation"]
        return (obs.round, obs.phase) == (2, 1)

    install_fault(monkeypatch, refuse)
    root = tmp_path / "out"
    summary = asyncio.run(runner.run_jobs(jobs, out_root=root, dry_run_bot="aspiration"))
    failed_path = episode_path(root / jobs[0].log_dir, 0, status="failed", attempt=1)
    done_path = episode_path(root / jobs[0].log_dir, 0)
    failed, done = read_log(failed_path), read_log(done_path)
    assert failed.failure["stage"] == stage and failed.failure["category"] == "refusal"
    assert len(failed.failure["attempts"]) == 3 and failed.failure["cost_usd"] > 0
    assert failed.footer["status"] == "failed" and failed.footer["totals"] is None
    if stage == "turn":
        assert (failed.failure["round"], failed.failure["phase"]) == (2, 1)
    else:
        assert failed.failure["round"] is None and failed.failure["phase"] is None
    assert done.header["attempt"] == 2
    assert failed.header["episode_seed"] == done.header["episode_seed"]
    assert failed.header["names"] == done.header["names"]
    assert summary.configs["tiny"]["totals"]["failed_attempts"] == 1
    assert summary.cost_usd == pytest.approx(failed.footer["cost_usd"] + done.footer["cost_usd"])
    for path in (failed_path, done_path):
        result = replay_log(path)
        assert result.ok, result.mismatches


def test_abandonment_skips_and_other_jobs_complete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = small_config(tmp_path, networks=("line3", "stem"))
    jobs = runner.plan_jobs([config])
    clients = install_fault(monkeypatch, lambda job, attempt, req: job.condition.network_id == "line3")
    root = tmp_path / "out"
    result = asyncio.run(runner.run_jobs(jobs, out_root=root, dry_run_bot="aspiration"))
    assert result.abandoned == result.done == 1
    assert len(list((root / jobs[0].log_dir).glob("*.failed*.jsonl.gz"))) == 3
    count = len(clients)
    again = asyncio.run(runner.run_jobs(jobs, out_root=root, dry_run_bot="aspiration"))
    assert again.abandoned == again.done == 1 and len(clients) == count


def test_fatal_stops_queued_jobs_and_summarizes_partial(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = small_config(tmp_path, networks=("line3", "stem"))
    jobs = runner.plan_jobs([config])
    clients = install_fault(monkeypatch, lambda job, attempt, req: True, fatal=True)
    root = tmp_path / "out"
    with pytest.raises(FatalAPIError):
        asyncio.run(runner.run_jobs(jobs, out_root=root, dry_run_bot="aspiration", concurrency=1))
    assert len(clients) == 1
    assert not list(root.rglob("*.jsonl.gz"))
    assert len(list(root.rglob("*.partial.jsonl"))) == 1
    assert json.loads((root / "tiny/summary.json").read_text())["totals"]["interrupted"] == 1


def test_cancellation_leaves_partial_and_summary(tmp_path: Path) -> None:
    config = small_config(tmp_path)
    jobs = runner.plan_jobs([config])

    class WaitingClient:
        async def complete(self, request):
            entered.set()
            await asyncio.Event().wait()

    async def cancel():
        nonlocal entered
        entered = asyncio.Event()
        task = asyncio.create_task(runner.run_jobs(jobs, out_root=tmp_path / "out",
                                                  dry_run_bot="aspiration", client=WaitingClient()))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    entered = None
    asyncio.run(cancel())
    assert len(list((tmp_path / "out").rglob("*.partial.jsonl"))) == 1
    assert (tmp_path / "out/tiny/summary.json").exists()


def test_writer_flush_and_plain_read(tmp_path: Path) -> None:
    writer = EpisodeLogWriter(tmp_path, 0, 1)
    writer.write({"type": "header", "log_schema": 1})
    assert read_log(writer.path).header["log_schema"] == 1
    writer.close()


def test_partial_with_torn_utf8_keeps_complete_records(tmp_path: Path) -> None:
    path = episode_path(tmp_path, 0, status="partial")
    path.write_bytes(b'{"type":"header","log_schema":1}\n{"note":"\xe2\x80')
    records = read_log(path)
    assert records.header == {"type": "header", "log_schema": 1}
    assert records.events == [] and records.footer is None


def test_completed_gzip_cleans_leftover_partial_without_double_cost(tmp_path: Path) -> None:
    config = small_config(tmp_path)
    jobs = runner.plan_jobs([config])
    root = tmp_path / "out"
    first = asyncio.run(runner.run_jobs(jobs, out_root=root, dry_run_bot="aspiration"))
    completed = episode_path(root / jobs[0].log_dir, 0)
    partial = episode_path(completed.parent, 0, status="partial")
    partial.write_bytes(gzip.decompress(completed.read_bytes()))
    again = asyncio.run(runner.run_jobs(jobs, out_root=root, dry_run_bot="aspiration"))
    assert again.done == 1 and again.cost_usd == first.cost_usd
    assert not partial.exists()


def test_fatal_cancels_running_attempts_and_never_starts_queued_job(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = small_config(tmp_path, networks=("line3", "stem", "star3"))
    jobs = runner.plan_jobs([config])
    created = []

    class ControlledClient:
        def __init__(self, identifier):
            self.identifier = identifier

        async def complete(self, request):
            if self.identifier == "line3":
                await other_started.wait()
                raise FatalAPIError("Injected configuration error")
            other_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                other_cancelled.set()
                raise

    def factory(job, attempt, bot):
        created.append(job.condition.network_id)
        return ControlledClient(job.condition.network_id)

    monkeypatch.setattr(runner, "_make_dry_client", factory)

    async def check():
        nonlocal other_started, other_cancelled
        other_started, other_cancelled = asyncio.Event(), asyncio.Event()
        with pytest.raises(FatalAPIError):
            await asyncio.wait_for(runner.run_jobs(jobs, out_root=tmp_path / "out",
                                                  dry_run_bot="aspiration", concurrency=2), timeout=3)
        assert other_cancelled.is_set()

    other_started = other_cancelled = None
    asyncio.run(check())
    assert created == ["line3", "stem"]
    assert len(list((tmp_path / "out").rglob("*.partial.jsonl"))) == 2
    totals = json.loads((tmp_path / "out/tiny/summary.json").read_text())["totals"]
    assert totals["interrupted"] == 2 and totals["todo"] == 1
