"""Plan, play and resume experiments, with one log per episode attempt."""

import asyncio
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
import fnmatch
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import time
from typing import Any

from . import __version__
from .bots import make_bot
from .config import Condition, ExperimentConfig, ModelSpec, expand_conditions
from .costs import CostTracker
from .engine import Episode
from .fake_client import BotResponder, FakeChatClient
from .llm_agent import AgentTurnFailure, LLMAgent
from .model_client import FatalAPIError, ModelClient, OpenAIChatClient, Usage
from .names import assign_names
from .networks import get_network
from .quiz import QUIZ_VERSION, run_rules_quiz
from .runlog import LOG_SCHEMA, EpisodeLogWriter, LogRecords, episode_path, find_logs, read_log, utc_now


@dataclass(frozen=True)
class Job:
    """One episode; log_dir is relative to the chosen output root.

    config retains model specs and the original file hash for the log header.
    """

    config_name: str
    condition: Condition
    episode_index: int
    episode_seed: int
    log_dir: Path
    config: ExperimentConfig


def plan_jobs(configs: Sequence[ExperimentConfig], *, conditions: str | None = None,
              max_episodes: int | None = None) -> list[Job]:
    """Expand configs in order, optionally keeping a glob and an index prefix."""
    if max_episodes is not None and max_episodes < 1:
        raise ValueError("max_episodes must be positive.")
    if len({config.name for config in configs}) != len(configs):
        raise ValueError("Config names must be unique.")
    jobs = []
    for config in configs:
        for condition in expand_conditions(config):
            if conditions is not None and not fnmatch.fnmatchcase(condition.key, conditions):
                continue
            seeds = condition.episode_seeds[:max_episodes]
            for index, seed in enumerate(seeds):
                jobs.append(Job(config.name, condition, index, seed, Path(condition.key), config))
    return jobs


def estimate_cost(job_or_condition: Job | Condition, specs: Mapping[str, ModelSpec]) -> float:
    """Estimate one attempt using each node's own input/output prices, no cache."""
    condition = job_or_condition.condition if isinstance(job_or_condition, Job) else job_or_condition
    rounds = condition.settings.rounds
    prompt_tokens = 450 + 75 * (rounds - 1) / 2
    return sum((2 * rounds + 1) * (prompt_tokens * specs[alias].price_input_per_m
                                  + 45 * specs[alias].price_output_per_m) / 1_000_000
               for alias in condition.node_models.values())


def job_status(job: Job, out_root: str | Path, max_episode_attempts: int = 3) -> str:
    """Read status from filenames, with completed logs taking precedence."""
    folder = Path(out_root) / job.log_dir
    if episode_path(folder, job.episode_index).exists():
        return "done"
    if len(_failed_paths(job, out_root)) >= max_episode_attempts:
        return "abandoned"
    if episode_path(folder, job.episode_index, status="partial").exists():
        return "interrupted"
    return "todo"


def _failed_paths(job: Job, out_root: str | Path) -> list[Path]:
    return sorted((Path(out_root) / job.log_dir).glob(f"episode_{job.episode_index:03d}.failed*.jsonl.gz"))


def _provenance() -> dict[str, Any]:
    try:
        sdk_version = importlib.metadata.version("openai")
    except importlib.metadata.PackageNotFoundError:
        sdk_version = None
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], stderr=subprocess.DEVNULL, text=True).strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        commit = dirty = None
    return dict(package_version=__version__, python_version=platform.python_version(),
                openai_version=sdk_version, git_commit=commit, git_dirty=dirty)


def _header(job: Job, attempt: int, writer: EpisodeLogWriter, dry_run_bot: str | None) -> dict[str, Any]:
    condition = job.condition
    return dict(
        type="header", log_schema=LOG_SCHEMA, **_provenance(), config_name=job.config_name,
        config_sha256=job.config.source_sha256, condition_key=condition.key,
        network_id=condition.network_id, knowledge=condition.knowledge_setting,
        assignment=condition.assignment_name, node_models=condition.node_models,
        models={alias: spec.model_dump() for alias, spec in job.config.models.items()},
        settings=condition.settings.model_dump(), episode_index=job.episode_index,
        episode_seed=job.episode_seed, attempt=attempt,
        names=assign_names(get_network(condition.network_id), job.episode_seed),
        prompt_version=condition.settings.prompt_version, quiz_version=QUIZ_VERSION,
        dry_run_bot=dry_run_bot, started_at=writer.started.isoformat(),
    )


def _add_attempts(tracker: CostTracker, alias: str, attempts: list[dict[str, Any]]) -> None:
    for attempt in attempts:
        tracker.add(alias, Usage(**attempt["usage"]), attempt["cost_usd"])


def _cost_fields(tracker: CostTracker) -> dict[str, Any]:
    totals = tracker.to_dict()
    return dict(cost_usd=tracker.total_usd,
                cost_by_alias={alias: data["cost_usd"] for alias, data in totals.items()},
                usage_by_alias={alias: {"calls": data["calls"], **data["usage"]} for alias, data in totals.items()})


def _make_dry_client(job: Job, attempt: int, bot: str) -> ModelClient:
    """Create isolated bot RNGs and fake request IDs for this attempt."""
    network = get_network(job.condition.network_id)
    bots = {node: make_bot(bot, node=node, episode_seed=job.episode_seed) for node in network.nodes}
    return FakeChatClient(BotResponder(bots))


@dataclass(frozen=True)
class AttemptOutcome:
    """A finalized attempt; interrupted/fatal attempts instead propagate errors."""

    status: str
    path: Path
    cost_usd: float
    rounds: int


async def run_episode_attempt(job: Job, attempt: int, *, client: ModelClient | None,
                              writer: EpisodeLogWriter, dry_run_bot: str | None) -> AttemptOutcome:
    """Quiz every node, then stream the real engine's events into the writer."""
    tracker = CostTracker()
    n_quiz_calls = n_turn_calls = 0
    completed_rounds = 0
    condition = job.condition
    network = get_network(condition.network_id)
    header = _header(job, attempt, writer, dry_run_bot)
    names = header["names"]
    if client is None:
        if dry_run_bot is None:
            raise ValueError("A live attempt needs a client.")
        client = _make_dry_client(job, attempt, dry_run_bot)
    agents = {node: LLMAgent(node=node, names=names, model_alias=condition.node_models[node],
                             spec=job.config.models[condition.node_models[node]], client=client,
                             version=condition.settings.prompt_version) for node in network.nodes}

    def fail(node: str, stage: str, error: AgentTurnFailure,
             round_number: int | None = None, phase: int | None = None) -> None:
        _add_attempts(tracker, condition.node_models[node], error.attempts)
        writer.write(dict(type="failure", node=node, stage=stage, round=round_number, phase=phase,
                          category=error.category, attempts=error.attempts, cost_usd=error.cost_usd))

    def finish(status: str, totals: dict[str, int] | None) -> AttemptOutcome:
        finished = writer.clock()
        writer.write(dict(type="footer", status=status, totals=totals, **_cost_fields(tracker),
                          n_turn_calls=n_turn_calls, n_quiz_calls=n_quiz_calls,
                          finished_at=finished.isoformat(),
                          duration_s=(finished - writer.started).total_seconds()))
        return AttemptOutcome(status, writer.finalize(status), tracker.total_usd, completed_rounds)

    try:
        writer.write(header)
        tasks = {node: asyncio.create_task(run_rules_quiz(
            network=network, node=node, names=names, knowledge=condition.knowledge_setting,
            n_rounds=condition.settings.rounds, episode_seed=job.episode_seed,
            model_alias=condition.node_models[node], spec=job.config.models[condition.node_models[node]],
            client=client)) for node in network.nodes}
        quiz_error: BaseException | None = None
        try:
            await asyncio.gather(*tasks.values())
        except BaseException as exc:
            quiz_error = exc
            for task in tasks.values():
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks.values(), return_exceptions=True)
        # Log successful quizzes in canonical order, even when another node failed.
        quiz_failures = []
        fatal_error = None
        for node, task in tasks.items():
            if task.cancelled():
                continue
            error = task.exception()
            if error is None:
                quiz = task.result()
                writer.write({"type": "quiz", **quiz.to_dict()})
                _add_attempts(tracker, condition.node_models[node], quiz.meta["attempts"])
                n_quiz_calls += len(quiz.meta["attempts"])
            elif isinstance(error, AgentTurnFailure):
                quiz_failures.append((node, error))
            elif isinstance(error, FatalAPIError):
                fatal_error = error
        for node, error in quiz_failures:
            fail(node, "quiz", error)
            n_quiz_calls += len(error.attempts)
        if fatal_error is not None:
            raise fatal_error
        if quiz_error is not None:
            if isinstance(quiz_error, AgentTurnFailure):
                return finish("failed", None)
            raise quiz_error

        episode = Episode(network, knowledge=condition.knowledge_setting,
                          n_rounds=condition.settings.rounds, n_phases=condition.settings.phases,
                          episode_seed=job.episode_seed)
        event_count = 0

        def log_events() -> None:
            nonlocal event_count, completed_rounds
            events = episode.events_since(event_count)
            for event in events:
                writer.write(event)
                if event["type"] == "round_end":
                    completed_rounds = event["round"]
            event_count += len(events)

        log_events()
        while True:
            pending = episode.next_turn()
            log_events()
            if pending is None:
                break
            try:
                decision = await agents[pending.agent].aact(pending.observation)
            except AgentTurnFailure as error:
                fail(pending.agent, "turn", error, pending.round, pending.phase)
                n_turn_calls += len(error.attempts)
                return finish("failed", None)
            _add_attempts(tracker, condition.node_models[pending.agent], decision.meta["attempts"])
            n_turn_calls += len(decision.meta["attempts"])
            episode.submit(decision)
            log_events()
            await asyncio.sleep(0)  # Also let other offline episodes make progress.
        return finish("completed", episode.result().totals)
    finally:
        writer.close()


def _log_costs(records: LogRecords) -> dict[str, Any]:
    if records.footer:
        return {name: records.footer[name] for name in ("cost_usd", "cost_by_alias", "usage_by_alias")}
    tracker = CostTracker()
    for record in [*records.quizzes, *records.events, *records.failures]:
        node = record.get("node", record.get("agent"))
        meta = record if record["type"] == "failure" else record.get("meta", {})
        if node is not None and meta.get("attempts"):
            _add_attempts(tracker, records.header["node_models"][node], meta["attempts"])
    return _cost_fields(tracker)


def validate_logs(configs: Sequence[ExperimentConfig], out_root: str | Path,
                  dry_run: bool | None = None) -> None:
    """Refuse mixed modes or changed configs before creating any new log."""
    root = Path(out_root)
    if not root.exists():
        return
    by_name = {config.name: config for config in configs}
    modes = set()
    for path in find_logs([root]):
        header = read_log(path).header
        if not header:
            continue
        modes.add(header.get("dry_run_bot") is not None)
        config = by_name.get(header["config_name"])
        if config is not None:
            if header["config_sha256"] != config.source_sha256:
                raise ValueError(f"Config hash differs from the current config: {path}")
            if header["prompt_version"] != config.settings.prompt_version:
                raise ValueError(f"Prompt version differs from the current config: {path}")
    if len(modes) > 1 or (dry_run is not None and modes and dry_run not in modes):
        raise ValueError(f"Refusing to mix dry-run and live logs in {root}.")


def _empty_counts() -> dict[str, int]:
    return dict(done=0, abandoned=0, todo=0, interrupted=0)


def _add_usage(target: dict[str, dict[str, int]], source: dict[str, dict[str, int]]) -> None:
    for alias, values in source.items():
        entry = target.setdefault(alias, {name: 0 for name in ("calls", *asdict(Usage()))})
        for name, value in values.items():
            entry[name] += value


def write_summaries(configs: Sequence[ExperimentConfig], out_root: str | Path,
                    max_episode_attempts: int = 3) -> dict[str, dict[str, Any]]:
    """Rebuild each config summary from every available attempt on disk."""
    root = Path(out_root)
    summaries = {}
    for config in configs:
        conditions: dict[str, dict[str, Any]] = {}
        for condition in expand_conditions(config):
            conditions[condition.key] = {**_empty_counts(), "failed_attempts": 0, "cost_usd": 0.0,
                                         "cost_by_alias": {}, "usage_by_alias": {}, "quiz_scores": []}
        for job in plan_jobs([config]):
            conditions[job.condition.key][job_status(job, root, max_episode_attempts)] += 1
        folder = root / config.name
        dry_run = False
        logs = [(path, read_log(path)) for path in find_logs([folder])] if folder.exists() else []
        finalized = {(path.parent, records.header["episode_index"], records.header["attempt"])
                     for path, records in logs if records.footer and path.suffix == ".gz"}
        for path, records in logs:
            if not records.header:
                continue
            identity = (path.parent, records.header["episode_index"], records.header["attempt"])
            if path.name.endswith(".partial.jsonl") and identity in finalized:
                continue  # A crash after gzip replacement must not bill the same data twice.
            condition = conditions[records.header["condition_key"]]
            dry_run |= records.header.get("dry_run_bot") is not None
            condition["failed_attempts"] += bool(records.footer and records.footer["status"] == "failed")
            fields = _log_costs(records)
            condition["cost_usd"] += fields["cost_usd"]
            for alias, cost in fields["cost_by_alias"].items():
                condition["cost_by_alias"][alias] = condition["cost_by_alias"].get(alias, 0.0) + cost
            _add_usage(condition["usage_by_alias"], fields["usage_by_alias"])
            condition["quiz_scores"].extend(quiz["score"] for quiz in records.quizzes)
        totals = {**_empty_counts(), "failed_attempts": 0, "cost_usd": 0.0,
                  "cost_by_alias": {}, "usage_by_alias": {}}
        all_scores = []
        for condition in conditions.values():
            scores = condition.pop("quiz_scores")
            all_scores.extend(scores)
            condition["n_quizzes"] = len(scores)
            condition["mean_quiz_score"] = sum(scores) / len(scores) if scores else None
            condition["quiz_perfect_share"] = scores.count(3) / len(scores) if scores else None
            for name in (*_empty_counts(), "failed_attempts", "cost_usd"):
                totals[name] += condition[name]
            for alias, cost in condition["cost_by_alias"].items():
                totals["cost_by_alias"][alias] = totals["cost_by_alias"].get(alias, 0.0) + cost
            _add_usage(totals["usage_by_alias"], condition["usage_by_alias"])
        totals.update(n_quizzes=len(all_scores),
                      mean_quiz_score=sum(all_scores) / len(all_scores) if all_scores else None,
                      quiz_perfect_share=all_scores.count(3) / len(all_scores) if all_scores else None)
        summary = dict(config_name=config.name, dry_run=dry_run,
                       cost_kind="simulated" if dry_run else "actual", conditions=conditions, totals=totals)
        folder.mkdir(parents=True, exist_ok=True)
        temporary = folder / "summary.json.tmp"
        temporary.write_text(json.dumps(summary, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(folder / "summary.json")
        summaries[config.name] = summary
    return summaries


@dataclass(frozen=True)
class RunSummary:
    """Requested-job status, plus summaries covering all logs in those configs."""

    done: int
    abandoned: int
    todo: int
    interrupted: int
    cost_usd: float
    dry_run: bool
    configs: dict[str, dict[str, Any]]


async def run_jobs(jobs: Sequence[Job], *, out_root: str | Path, dry_run_bot: str | None = None,
                   concurrency: int = 8, max_episode_attempts: int = 3,
                   client: ModelClient | None = None,
                   clock: Callable[[], datetime] = utc_now) -> RunSummary:
    """Run bounded episode tasks; preserve partial logs on cancellation or fatal errors."""
    if concurrency < 1 or max_episode_attempts < 1:
        raise ValueError("concurrency and max_episode_attempts must be positive.")
    identities = [(job.condition.key, job.episode_index) for job in jobs]
    if len(set(identities)) != len(identities):
        raise ValueError("Jobs must be unique.")
    configs = list({job.config_name: job.config for job in jobs}.values())
    validate_logs(configs, out_root, dry_run_bot is not None)
    semaphore = asyncio.Semaphore(concurrency)
    stopping = asyncio.Event()
    owned_client = None
    if dry_run_bot is None and client is None and any(job_status(job, out_root, max_episode_attempts)
                                                    in ("todo", "interrupted") for job in jobs):
        owned_client = OpenAIChatClient(max_concurrency=16)
        client = owned_client
    running_cost = 0.0
    root = Path(out_root)
    if root.exists():
        for path in find_logs([root]):
            records = read_log(path)
            if records.footer and path.suffix == ".gz":
                running_cost += records.footer["cost_usd"]
    started = time.monotonic()

    async def run_one(job: Job) -> None:
        nonlocal running_cost
        async with semaphore:
            if stopping.is_set():
                return
            partial = episode_path(root / job.log_dir, job.episode_index, status="partial")
            if job_status(job, root, max_episode_attempts) in ("done", "abandoned"):
                # A crash can happen after gzip replacement but before partial cleanup.
                partial.unlink(missing_ok=True)
                return
            partial.unlink(missing_ok=True)
            attempt = len(_failed_paths(job, root)) + 1
            while attempt <= max_episode_attempts and not stopping.is_set():
                writer = EpisodeLogWriter(root / job.log_dir, job.episode_index, attempt, clock=clock)
                try:
                    outcome = await run_episode_attempt(job, attempt, client=client, writer=writer, dry_run_bot=dry_run_bot)
                except BaseException:
                    stopping.set()
                    raise
                finally:
                    writer.close()
                running_cost += outcome.cost_usd
                elapsed = int(time.monotonic() - started)
                label = " simulated" if dry_run_bot is not None else ""
                print(f"{job.condition.key} ep {job.episode_index:03d} attempt {attempt} {outcome.status} "
                      f"rounds={outcome.rounds} cost=${outcome.cost_usd:.4f} "
                      f"total=${running_cost:.4f} elapsed={elapsed // 60}m{elapsed % 60}s{label}", flush=True)
                if outcome.status == "completed":
                    return
                attempt += 1

    tasks = [asyncio.create_task(run_one(job)) for job in jobs]
    try:
        await asyncio.gather(*tasks)
    except BaseException:
        stopping.set()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    finally:
        try:
            if owned_client is not None:
                await owned_client.aclose()
        finally:
            summaries = write_summaries(configs, root, max_episode_attempts)
    counts = _empty_counts()
    for job in jobs:
        counts[job_status(job, root, max_episode_attempts)] += 1
    return RunSummary(**counts, cost_usd=sum(summary["totals"]["cost_usd"] for summary in summaries.values()),
                      dry_run=dry_run_bot is not None, configs=summaries)
