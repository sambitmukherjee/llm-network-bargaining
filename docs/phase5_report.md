# Phase 5 completion report

**Phase 5 is complete.** Phase 6 has not started. No real API calls, new
dependencies, commits or pushes were made during this phase. All execution
used offline clients; the real `.env` was neither read nor modified.

## What was built

| File | Purpose |
|---|---|
| `src/llm_network_bargaining/runlog.py` | Flushed JSONL attempts, atomic reproducible gzip finalization, file naming and the shared log reader. |
| `src/llm_network_bargaining/runner.py` | Jobs, estimates, quizzes, concurrent episodes, costs, restarts, resume checks and summaries rebuilt from saved logs. |
| `src/llm_network_bargaining/replay.py` | Outcome reconstruction, seeded order/name checks, exact prompt checks and tampering detection. |
| `src/llm_network_bargaining/cli.py` | Estimate, run, status and replay commands, including live-spend confirmation and exit codes. |
| `src/llm_network_bargaining/run.py` | Thin module entry point for the requested `python -m llm_network_bargaining.run` command. |
| `src/llm_network_bargaining/config.py` | Removes `budget_usd` and preserves original config-file hashes for provenance. |
| `src/llm_network_bargaining/engine.py` | Independent event snapshots, including an incremental reader for streaming logs. |
| `src/llm_network_bargaining/smoke.py` | Quiz key/score display and informational scoring; dry previews mark the unmeasured score explicitly. |
| `configs/minimum_study.yaml` | Removes its unused budget field; the other six configs already omitted it. |
| `tests/test_runner.py` | Planning, estimates, the full dry pilot, concurrency, byte-identical gzip, resume, retries, abandonment and cancellation. |
| `tests/test_replay.py` | Reconstruction and detection of altered actions, points, orders, hashes, names, messages, quizzes and totals. |
| `tests/test_run_cli.py` | CLI estimates, dry runs, status, replay, confirmation, missing keys and failure exit codes. |
| `tests/phase5_helpers.py` | Small configs, normalized comparisons and offline fault injection. |
| `tests/conftest.py` | Dummy-key session fixture and decompressed output scans, alongside existing socket and SDK-constructor guards. |
| `tests/test_config.py` | Rejects numeric and null legacy budget fields. |
| `tests/test_smoke.py` | Checks quiz key, unmeasured dry score and live-table score formatting. |
| `.gitignore` | Ignores dry runs and partial files; study gzip logs remain eligible for Git. |
| `README.md` | Experiment commands, confirmation, recovery and log usage. |
| `docs/phase1_notes.md` | Records removal of the former budget field. |
| `docs/phase5_notes.md` | Decisions, log schema and interfaces for later phases. |

## Test results

Before edits: `525 passed, 1 deselected in 22.67s`.

Default suite:

```text
561 passed, 1 deselected in 26.67s
```

Slow suite:

```text
1 passed, 561 deselected in 0.54s
```

The demonstration completed **10 episodes of 24 rounds**, with **37 quizzes**,
all scoring 3/3. Every completed log replays successfully. No partial files
remain. Recorded simulated cost is **$0.833185**, not actual expenditure.

The original script, prediction files, all nine prompt goldens and the quiz
golden remain unchanged. The script's SHA-256 is still:

```text
71a6d6d81954ef303cdd6f0a345afe9a961b56a17e63ea20d81431ec833bf0ec
```

The session fixture checked every test output file, including decompressed
logs, for the dummy key. No key leaked. The default suite remains well under
two minutes. `git diff --check` passes. No expected mathematical values or
golden stimuli were changed.

## Example log size

A completed 24-round full-map `line3` log:

```text
runs_dry/pilot_full_map/line3/full_map/terra/episode_000.jsonl.gz
compressed:   23,854 bytes
uncompressed: 620,250 bytes
```

The files remain locally in ignored `runs_dry/`, with one summary per config.
The summaries cover all configured episodes: ten are done and twenty are
still todo. The ten jobs selected by `--max-episodes 1` are all complete.

## Decisions and deviations

- Jobs retain their config in addition to the listed planning fields, because
  attempt execution needs model specs and the exact source-byte hash.
- The engine lacked the brief's `events` property. The added copy-based property
  and `events_since` supply it without changing any existing event or outcome.
- Completed and failed gzip files are authoritative if a crash leaves the
  same partial file behind. Cleanup and summary deduplication avoid double
  counting its cost.
- Concurrent quizzes are cancelled on failure; already received results are
  retained in node order. Multiple failed quizzes can produce multiple failure
  records. `LogRecords.failure` is the first; `failures` preserves all of them.
- Counts named calls include actual client attempts, including retries.
  Summaries include all logs, not just the current job selection. Progress is
  emitted in completion order; per-attempt data is deterministic independently
  of concurrency, and fixed clocks produce byte-identical compressed logs.
- A dry smoke preview has no model answers, so it shows the key with null
  answers/score and `quiz_score_status="not_run"`. The live path shows the real
  key/score with a non-failing `INFO` line. No live smoke call was repeated.
- Resuming follows the requested deletion of partial files. Known partial
  costs are included while those files exist; after deletion, old interrupted
  charges cannot be reconstructed. Requests with no returned usage likewise
  cannot be costed. Finalized failed-attempt costs are always retained.

Full details are in [phase5_notes.md](phase5_notes.md).

## Interfaces and fields for Phase 6

```python
plan_jobs(configs, *, conditions=None, max_episodes=None) -> list[Job]
estimate_cost(job_or_condition, specs) -> float
run_episode_attempt(job, attempt, *, client, writer, dry_run_bot) -> Awaitable[AttemptOutcome]
run_jobs(jobs, *, out_root, dry_run_bot=None, concurrency=8,
         max_episode_attempts=3, client=None, clock=utc_now) -> Awaitable[RunSummary]
job_status(job, out_root, max_episode_attempts=3) -> str
read_log(path: str | Path) -> LogRecords
LogRecords(header, quizzes, events, failure, footer, failures=[])
LogRecords.to_list() -> list[dict[str, Any]]
replay_log(path: str | Path) -> ReplayResult
ReplayResult(path, ok, n_events, n_turns, mismatches)
```

Every record has `type`. The header identifies config hash, condition, network,
knowledge setting, assignment, model specs, game settings, episode index/seed,
attempt, display names, prompt/quiz versions, dry bot and code provenance.
Quizzes provide node, option orders, key, answers, correctness, score and full
metadata. Engine events retain Phase 2 fields. Turn records carry requested
and applied action, validity/reason, round/phase/slot and full Phase 4 metadata,
including messages, raw successful reply, prompt hash, attempts, usage and cost.
Failures carry node/stage/round/phase/category plus attempts and spent cost.
Footers carry status, totals, costs and usage by alias, turn/quiz call counts,
and timestamps/duration. Alias usage includes `calls` and all five token fields.

For the exact field lists and JSON shapes, see
[the log schema](phase5_notes.md#log-files-and-schema-1) and
[the public signatures](phase5_notes.md#public-interfaces).

## Required command outputs

All four commands below exited 0. They use the project's virtual environment.

### Command 1

```sh
.venv/bin/python -m llm_network_bargaining.run estimate configs/pilot_full_map.yaml configs/pilot_own_links.yaml configs/minimum_study.yaml configs/own_links_arm.yaml
```

Exit code: 0.

```text
condition | episodes | cost_per_attempt_usd | subtotal_usd
pilot_full_map/pair/full_map/terra | 3 | 0.1506750 | 0.4520250
pilot_full_map/line3/full_map/terra | 3 | 0.2260125 | 0.6780375
pilot_full_map/line4/full_map/terra | 3 | 0.3013500 | 0.9040500
pilot_full_map/line5/full_map/terra | 3 | 0.3766875 | 1.1300625
pilot_full_map/star3/full_map/terra | 3 | 0.3013500 | 0.9040500
pilot_full_map/star4/full_map/terra | 3 | 0.3766875 | 1.1300625
pilot_full_map/stem/full_map/terra | 3 | 0.3013500 | 0.9040500
pilot_full_map/triangle/full_map/terra | 3 | 0.2260125 | 0.6780375
pilot_own_links/line3/own_links/terra | 3 | 0.2260125 | 0.6780375
pilot_own_links/star3/own_links/terra | 3 | 0.3013500 | 0.9040500
minimum_study/pair/full_map/terra | 10 | 0.0543750 | 0.5437500
minimum_study/line3/full_map/terra | 10 | 0.0815625 | 0.8156250
minimum_study/line4/full_map/terra | 10 | 0.1087500 | 1.0875000
minimum_study/line5/full_map/terra | 10 | 0.1359375 | 1.3593750
minimum_study/star3/full_map/terra | 10 | 0.1087500 | 1.0875000
minimum_study/star4/full_map/terra | 10 | 0.1359375 | 1.3593750
minimum_study/stem/full_map/terra | 10 | 0.1087500 | 1.0875000
minimum_study/triangle/full_map/terra | 10 | 0.0815625 | 0.8156250
own_links_arm/pair/own_links/terra | 10 | 0.0543750 | 0.5437500
own_links_arm/line3/own_links/terra | 10 | 0.0815625 | 0.8156250
own_links_arm/line4/own_links/terra | 10 | 0.1087500 | 1.0875000
own_links_arm/line5/own_links/terra | 10 | 0.1359375 | 1.3593750
own_links_arm/star3/own_links/terra | 10 | 0.1087500 | 1.0875000
own_links_arm/star4/own_links/terra | 10 | 0.1359375 | 1.3593750
own_links_arm/stem/own_links/terra | 10 | 0.1087500 | 1.0875000
own_links_arm/triangle/own_links/terra | 10 | 0.0815625 | 0.8156250
Estimated total: $24.6749625
```

### Command 2

```sh
.venv/bin/python -m llm_network_bargaining.run run configs/pilot_full_map.yaml configs/pilot_own_links.yaml --dry-run aspiration --max-episodes 1
```

Exit code: 0.

```text
Dry run: all costs are simulated; no API key or confirmation is needed.
condition | todo | interrupted | done | abandoned | estimated_remaining_usd
pilot_full_map/pair/full_map/terra | 1 | 0 | 0 | 0 | 0.1506750
pilot_full_map/line3/full_map/terra | 1 | 0 | 0 | 0 | 0.2260125
pilot_full_map/line4/full_map/terra | 1 | 0 | 0 | 0 | 0.3013500
pilot_full_map/line5/full_map/terra | 1 | 0 | 0 | 0 | 0.3766875
pilot_full_map/star3/full_map/terra | 1 | 0 | 0 | 0 | 0.3013500
pilot_full_map/star4/full_map/terra | 1 | 0 | 0 | 0 | 0.3766875
pilot_full_map/stem/full_map/terra | 1 | 0 | 0 | 0 | 0.3013500
pilot_full_map/triangle/full_map/terra | 1 | 0 | 0 | 0 | 0.2260125
pilot_own_links/line3/own_links/terra | 1 | 0 | 0 | 0 | 0.2260125
pilot_own_links/star3/own_links/terra | 1 | 0 | 0 | 0 | 0.3013500
Estimated remaining cost: $2.7874875
pilot_full_map/pair/full_map/terra ep 000 attempt 1 completed rounds=24 cost=$0.0332 total=$0.0332 elapsed=0m0s simulated
pilot_full_map/triangle/full_map/terra ep 000 attempt 1 completed rounds=24 cost=$0.0463 total=$0.0794 elapsed=0m0s simulated
pilot_full_map/star3/full_map/terra ep 000 attempt 1 completed rounds=24 cost=$0.0552 total=$0.1347 elapsed=0m0s simulated
pilot_full_map/star4/full_map/terra ep 000 attempt 1 completed rounds=24 cost=$0.0783 total=$0.2130 elapsed=0m0s simulated
pilot_own_links/line3/own_links/terra ep 000 attempt 1 completed rounds=24 cost=$0.0457 total=$0.2587 elapsed=0m0s simulated
pilot_full_map/line5/full_map/terra ep 000 attempt 1 completed rounds=24 cost=$0.0922 total=$0.3509 elapsed=0m0s simulated
pilot_full_map/line3/full_map/terra ep 000 attempt 1 completed rounds=24 cost=$0.1143 total=$0.4651 elapsed=0m0s simulated
pilot_own_links/star3/own_links/terra ep 000 attempt 1 completed rounds=24 cost=$0.0573 total=$0.5224 elapsed=0m0s simulated
pilot_full_map/stem/full_map/terra ep 000 attempt 1 completed rounds=24 cost=$0.1478 total=$0.6702 elapsed=0m0s simulated
pilot_full_map/line4/full_map/terra ep 000 attempt 1 completed rounds=24 cost=$0.1629 total=$0.8332 elapsed=0m0s simulated
Requested jobs: done=10 abandoned=0 todo=0 interrupted=0
Simulated cost across saved logs: $0.833185
```

### Command 3

```sh
.venv/bin/python -m llm_network_bargaining.run status configs/pilot_full_map.yaml configs/pilot_own_links.yaml --out runs_dry
```

Exit code: 0.

```text
condition | todo | interrupted | done | abandoned | estimated_remaining_usd
pilot_full_map/pair/full_map/terra | 2 | 0 | 1 | 0 | 0.3013500
pilot_full_map/line3/full_map/terra | 2 | 0 | 1 | 0 | 0.4520250
pilot_full_map/line4/full_map/terra | 2 | 0 | 1 | 0 | 0.6027000
pilot_full_map/line5/full_map/terra | 2 | 0 | 1 | 0 | 0.7533750
pilot_full_map/star3/full_map/terra | 2 | 0 | 1 | 0 | 0.6027000
pilot_full_map/star4/full_map/terra | 2 | 0 | 1 | 0 | 0.7533750
pilot_full_map/stem/full_map/terra | 2 | 0 | 1 | 0 | 0.6027000
pilot_full_map/triangle/full_map/terra | 2 | 0 | 1 | 0 | 0.4520250
pilot_own_links/line3/own_links/terra | 2 | 0 | 1 | 0 | 0.4520250
pilot_own_links/star3/own_links/terra | 2 | 0 | 1 | 0 | 0.6027000
Estimated remaining cost: $5.5749750
```

### Command 4

```sh
.venv/bin/python -m llm_network_bargaining.replay runs_dry
```

Exit code: 0.

```text
PASS runs_dry/pilot_full_map/line3/full_map/terra/episode_000.jsonl.gz events=407 turns=163
PASS runs_dry/pilot_full_map/line4/full_map/terra/episode_000.jsonl.gz events=487 turns=186
PASS runs_dry/pilot_full_map/line5/full_map/terra/episode_000.jsonl.gz events=454 turns=174
PASS runs_dry/pilot_full_map/pair/full_map/terra/episode_000.jsonl.gz events=218 turns=48
PASS runs_dry/pilot_full_map/star3/full_map/terra/episode_000.jsonl.gz events=402 turns=192
PASS runs_dry/pilot_full_map/star4/full_map/terra/episode_000.jsonl.gz events=516 turns=266
PASS runs_dry/pilot_full_map/stem/full_map/terra/episode_000.jsonl.gz events=473 turns=182
PASS runs_dry/pilot_full_map/triangle/full_map/terra/episode_000.jsonl.gz events=312 turns=120
PASS runs_dry/pilot_own_links/line3/own_links/terra/episode_000.jsonl.gz events=314 turns=120
PASS runs_dry/pilot_own_links/star3/own_links/terra/episode_000.jsonl.gz events=408 turns=192
```

## Open questions

None. Phase 6 has not started; the live pilot remains for the user to run.
