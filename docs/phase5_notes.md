# Phase 5 implementation notes

Implemented on **1 November 2026**, before the Apart Research sprint.
This phase adds experiment planning, execution, logs, recovery, summaries and
replay. It adds no study outcome metrics, statistics, figures or analysis
reports. No dependencies, real API calls, commits or pushes were added in this
phase. All execution and examples used offline clients.

## Starting state and earlier-phase changes

- The baseline was `525 passed, 1 deselected in 22.67s`. The protected script
  matched SHA-256
  `71a6d6d81954ef303cdd6f0a345afe9a961b56a17e63ea20d81431ec833bf0ec`.
  Baseline hashes were saved for the prediction files and all ten goldens.
- `budget_usd` was removed from the config schema and from the one example
  that contained it (`minimum_study.yaml`). The other six examples already
  omitted it. Both numeric and null values are now rejected as extra fields.
  The Phase 1 notes were updated. There is no spending cap.
- `load_config` remembers the SHA-256 of the exact file bytes in a private
  attribute; `source_sha256` exposes it without adding a YAML field. For configs
  constructed in memory, the fallback is SHA-256 of sorted UTF-8 JSON from
  `model_dump()`. CLI configs always use the original file-byte hash.
- `Episode.events` was mentioned by the brief but did not exist in Phase 2.
  It is now a property returning independent event copies. `events_since(i)`
  copies only new events, avoiding repeated copies of increasingly large turn
  metadata. Neither changes engine behavior or event fields.
- `smoke.py` displays answers, key and score together in the live table and
  prints `INFO: quiz score n/3`. A low score does not change the smoke result.
  A dry run only previews requests, so its quiz fields explicitly show
  `quiz_answers=null`, `quiz_score=null`, `quiz_score_status="not_run"`, together
  with the real key. It reports that no score was measured rather than
  inventing an answer or making a call.

## Jobs and client ownership

- `Job.log_dir` is a relative condition directory such as
  `pilot_full_map/line3/full_map/terra`. `out_root` is prepended by the runner.
  `Job` also retains its `ExperimentConfig`, which supplies model specs and
  the file hash; the five fields listed in the brief do not otherwise carry
  that information.
- Jobs follow config, condition and episode-index order. A glob filters the
  complete condition key. A positive `max_episodes` selects an index prefix
  independently for every condition. No matches produce an empty plan.
- A default dry attempt has its own `FakeChatClient`, `BotResponder` and bot
  RNGs. Names, bot RNGs, engine orders and quiz permutations use the same
  episode seed after a restart. Fake request IDs restart at `fake-1`.
- An explicitly supplied client overrides default creation, including in dry
  mode. This permits offline fault/cancellation tests at our client interface.
  It is owned by the caller. A live client created by `run_jobs` is shared
  across episodes and closed by the runner. The SDK's own retries stay off.
- Quizzes run concurrently. Successful results are written in canonical node
  order. On a quiz exception, unfinished quiz tasks are cancelled and awaited;
  results already received are still recorded. If several quizzes fail, each
  gets a failure record, so all returned usage remains accounted for. Fatal
  errors take priority over recoverable quiz failures.
- Turns within an episode are sequential. A semaphore bounds concurrent
  episodes; the existing live client separately bounds API requests at 16.
  A zero-duration yield after each turn also lets offline episodes interleave.
- The existing production handling of `None` is unchanged. The Phase 4
  None-to-dance wrapper remains test-only. Random-bot dry runs can therefore
  exercise empty-reply retries as well as ordinary invalid game actions.

## Log files and schema 1

Condition directory layout:

```text
{out_root}/{config}/{network}/{knowledge}/{assignment}/
    episode_000.partial.jsonl        current/interrupted attempt
    episode_000.failed1.jsonl.gz     failed attempt 1
    episode_000.failed2.jsonl.gz     failed attempt 2
    episode_000.jsonl.gz             completed attempt
{out_root}/{config}/summary.json
```

The attempt number is stored in the header. All attempts retain the same
episode index and episode seed. Writers use exclusive creation, flush each
JSONL record, and compress through a temporary file in the same directory.
The gzip header has `mtime=0` and an empty filename; no output path enters the
compressed bytes. The gzip destination is replaced before the partial is
deleted. Use one runner per output root; cross-process scheduling is not added.

Every line uses `json.dumps(..., sort_keys=True, ensure_ascii=False)` and strict
finite JSON. Records occur in this order:

| Type | Fields available to later phases |
|---|---|
| `header` | `log_schema=1`, `package_version`, `python_version`, `openai_version`, `git_commit`, `git_dirty`, `config_name`, `config_sha256`, `condition_key`, `network_id`, `knowledge`, `assignment`, `node_models`, `models`, `settings`, `episode_index`, `episode_seed`, `attempt`, `names`, `prompt_version`, `quiz_version`, `dry_run_bot`, `started_at`. |
| `quiz` | `node`, `quiz_version`, `orders`, `key`, `answers`, `correct`, `score`, `meta`, from `QuizResult.to_dict()`. |
| Engine events | Unchanged Phase 2 `episode_start`, `phase_start`, `turn`, `offer`, `offer_status`, `deal`, `round_end`, `episode_end` dictionaries. |
| `failure` | `node`, `stage`, `round`, `phase`, `category`, `attempts`, `cost_usd`. Quiz round and phase are both null. There can be multiple concurrent quiz failures. |
| `footer` | `status`, `totals`, `cost_usd`, `cost_by_alias`, `usage_by_alias`, `n_turn_calls`, `n_quiz_calls`, `finished_at`, `duration_s`. Failed totals are null. |

Turn events contain `turn_index`, `round`, `phase`, `slot`, `agent`, `auto`,
`requested`, `applied`, `valid`, `reason` and `meta`. A requested action has
`kind`, `to`, `my_points` and `note`. Auto turns have empty metadata.

LLM `meta` retains the exact Phase 4 key set: `agent_kind`, `model_alias`,
`model_id`, `prompt_version`, `messages`, `prompt_sha256`, `attempts`, `content`,
`refusal`, `finish_reason`, `parse`, `usage`, `cost_usd`, `latency_s`,
`returned_model`, `request_id`, `system_fingerprint`, `service_tier`, `warnings`.
Quiz metadata replaces `parse` with `quiz_raw`. The raw successful reply and
messages are retained; failed-call records have the existing Phase 4 attempt
fields (outcome/error, request/model IDs, finish reason, usage, latency, cost).
No SDK object, environment mapping or key is serialized.

`cost_by_alias` maps aliases to dollar amounts. `usage_by_alias` maps each
alias to `calls` plus the five `Usage` counters: `prompt_tokens`,
`completion_tokens`, `cached_tokens`, `cache_write_tokens`, `reasoning_tokens`.
`n_turn_calls` and `n_quiz_calls` count individual client calls, including
retries and ultimately failed calls. They do not count automatic engine passes.
There is no extra charge for reasoning tokens already included in completion.

`read_log` returns a `LogRecords` dataclass with `header`, `quizzes`, `events`,
`failure` and `footer`. `failure` is the first failure; additive `failures`
contains all failures. `to_list()` restores file order. A partial may have no
footer and may end with one torn, unterminated JSON line; that line is ignored.
A malformed complete line or a gzip log missing its footer is an error.

## Recovery, costs and summaries

- Status is read from filenames: completed, abandoned after the selected
  failure limit, interrupted, or todo. The CLI uses a limit of three failed
  attempts; API callers choosing another limit should reuse it on resume.
- On resume the partial is deleted, as the brief requires, and the next
  attempt number is the failed-file count plus one. With no failed files this
  is attempt 1. A stray partial left after gzip replacement is also cleaned;
  summaries deduplicate that same finalized attempt even before cleanup.
- Config-byte hashes and prompt versions are checked before any new file is
  created. This check also covers failed and partial logs, preventing mixed
  provenance. Dry and live logs cannot share an output root, even in different
  config subdirectories.
- Fatal API errors and cancellations stop queued jobs, cancel and await active
  attempts, close writers, retain their partial files, and write summaries.
  The original exception then propagates. Caller-owned clients are not closed.
- Finalized footers include every received attempt's cost, including retries
  on failed turns and failed quizzes. An interrupted log's known costs are
  reconstructed from its recorded quiz, turn and failure metadata. Requests
  without returned usage cannot be costed. Following the specified delete-and-
  restart protocol, old interrupted records are not retained after resume;
  their historical charges cannot then be recovered from disk.
- `summary.json` is rewritten atomically from all logs in that config folder,
  including prior invocations and conditions outside the current job filter.
  It includes `config_name`, `dry_run`, `cost_kind` (`simulated` or `actual`),
  `conditions` keyed by condition key, and `totals`.
- Condition and config totals include `done`, `abandoned`, `todo`,
  `interrupted`, `failed_attempts`, `cost_usd`, `cost_by_alias`,
  `usage_by_alias`, `n_quizzes`, `mean_quiz_score` and `quiz_perfect_share`.
  Todo excludes the separately reported interrupted count. Quiz summaries use
  all logged quiz results, including failed and interrupted episode attempts;
  they are null when no quizzes are available. Later analysis can select only
  completed attempts from the underlying logs if needed.
- `RunSummary` counts only the requested jobs, while its `configs` dictionaries
  and `cost_usd` cover all saved logs for those configs. Thus the ten-episode
  pilot demonstration completes all ten requested jobs while config summaries
  still show twenty other episodes to do.
- Progress reports completed rounds within that attempt. Cumulative progress
  cost includes previously finalized attempts plus attempts finished this run;
  final summaries also include known partial costs. Every dry-run cost is
  explicitly labeled as simulated.

## Replay and CLI decisions

- Replay never needs a config file, key or model client. It uses header
  settings/names and logged requested actions, compares every engine field
  except opaque metadata, and verifies seeded names and phase orders.
- It checks the rendered user message and its hash for every asked turn;
  the recorded raw reply must parse to the logged action. It also verifies
  quiz orders, keys, correctness, messages and hashes. Failed turn logs check
  the pending node/round/phase; quiz failures replay their empty game prefix.
- `estimate` uses the exact formula in the brief. The Terra `line3` estimate
  is `0.0815625` dollars per attempt. Estimates count one attempt per remaining
  episode; retries/restarts can increase actual spend.
- `status` is read-only. It returns 0 for a successful query, or 4 if an episode
  is abandoned. `run` returns 0 when requested jobs complete, 4 for abandonment,
  3 for missing confirmation and 1 for errors/interruption.
- A live run checks the exported `OPENAI_API_KEY` before loading configs or
  printing a spending plan. It does not load `.env`. It constructs no client
  before `--yes` or an exact interactive `yes`. A run with no remaining work
  does not ask for confirmation or construct a client.
- `run.py` is a small extra entry point so the requested module command works
  while its implementation lives in `cli.py`. Standalone `replay` and the
  main CLI's `replay` subcommand use the same function.
- `runs_dry/` and `*.partial.jsonl` are ignored. `runs/` remains eligible for
  version control, and the prompt-example exception remains in force.

## Public interfaces

```python
# config.py / engine.py additions
ExperimentConfig.source_sha256 -> str  # property; not a YAML field
Episode.events -> tuple[dict[str, Any], ...]  # property; independent copies
Episode.events_since(start: int) -> tuple[dict[str, Any], ...]

# runlog.py
LOG_SCHEMA = 1
EpisodeLogWriter(folder, episode_index: int, attempt: int, *, clock=utc_now)
EpisodeLogWriter.write(record: dict[str, Any]) -> None
EpisodeLogWriter.close() -> None
EpisodeLogWriter.finalize(status: str) -> Path
episode_path(folder, index: int, *, status="completed", attempt=1) -> Path
read_log(path: str | Path) -> LogRecords
LogRecords(header, quizzes, events, failure, footer, failures=[])
LogRecords.to_list() -> list[dict[str, Any]]
find_logs(paths: Iterable[str | Path]) -> list[Path]

# runner.py
Job(config_name, condition, episode_index, episode_seed, log_dir, config)
plan_jobs(configs, *, conditions=None, max_episodes=None) -> list[Job]
estimate_cost(job_or_condition: Job | Condition, specs) -> float
job_status(job, out_root, max_episode_attempts=3) -> str
run_episode_attempt(job, attempt, *, client, writer, dry_run_bot) -> Awaitable[AttemptOutcome]
AttemptOutcome(status, path, cost_usd, rounds)
run_jobs(jobs, *, out_root, dry_run_bot=None, concurrency=8,
         max_episode_attempts=3, client=None, clock=utc_now) -> Awaitable[RunSummary]
RunSummary(done, abandoned, todo, interrupted, cost_usd, dry_run, configs)
validate_logs(configs, out_root, dry_run=None) -> None
write_summaries(configs, out_root, max_episode_attempts=3) -> dict

# replay.py
replay_log(path: str | Path) -> ReplayResult
ReplayResult(path, ok, n_events, n_turns, mismatches)
main(argv: Sequence[str] | None = None) -> int

# cli.py, exposed by python -m llm_network_bargaining.run
main(argv: Sequence[str] | None = None) -> int
```

Mutable dataclass defaults in the implementation use factories. The clock is
an additive test hook returning timezone-aware datetimes; a constant clock
makes timestamps and durations fixed for byte-for-byte gzip tests.

## Validation

The final results, four requested command outputs and example compressed/raw
log sizes are recorded in `phase5_report.md`. The tests keep both SDK
constructors and sockets blocked. A session fixture installs a dummy key and
scans every test output file, decompressing gzip data, for that dummy value.

- Default suite: `561 passed, 1 deselected in 26.67s`.
- Slow suite: `1 passed, 561 deselected in 0.54s`.
- The four required commands exited 0. The ten 24-round pilot dry episodes
  completed with 37 correct quizzes and simulated cost `$0.833185`; all logs
  replayed successfully. No partial files remain.
- The sample full-map `line3` log is 23,854 bytes compressed and 620,250 bytes
  uncompressed. The protected script, predictions and ten goldens are unchanged.

No open questions remain. Phase 6 has not started.
