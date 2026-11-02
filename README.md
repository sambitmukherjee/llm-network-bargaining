# LLM network bargaining

This project studies whether LLM agents earn more by occupying advantaged nodes
in a bargaining network. Each deal splits 24 points, and each agent may close
at most one deal per round. The package currently provides network definitions,
graph analysis, cooperative-game predictions, and validated experiment configs.
Phase 1 makes no model calls.

Use Python 3.11 or newer. From the project folder:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Run the default tests, or explicitly include only the slower threshold test:

```sh
pytest
pytest -m slow
```

Generate all predictions, or select networks by tag (repeated tags form a union):

```sh
python -m llm_network_bargaining.predictions --out predictions/
python -m llm_network_bargaining.predictions --out /tmp/core_predictions --tag core
```

The two CSVs are reproducible; only `metadata.json` contains a timestamp. The
eight-network main study uses the `core` tag. Every registered network uses exact
theory values; larger custom networks can use seeded permutation sampling.

A YAML **config** lists networks, knowledge settings, model aliases, assignments,
and shared game settings. A **condition** is one network × one knowledge setting
× one assignment. An **episode** is one game in a condition. All combinations
are expanded in a fixed order with distinct condition and episode seeds.
See `configs/minimum_study.yaml` and the six other examples; the pilot uses
both `pilot_full_map.yaml` and `pilot_own_links.yaml` (30 episodes together).

```python
from llm_network_bargaining.config import expand_conditions, load_config

config = load_config("configs/minimum_study.yaml")
conditions = expand_conditions(config)
print(conditions[0].key)  # minimum_study/pair/full_map/terra
```

The game engine supports `run_episode(network, agents, ...)` for synchronous
agents. For turn-by-turn control, create an `Episode`, call `next_turn()`, and
submit a `Decision` with `submit()`. Continue until `next_turn()` returns `None`,
then read `result()`. An agent implements `act(observation) -> Decision` and
receives only its permitted information. Events stay in memory in Phase 2.

Simulate without model calls using `pass`, `equal_split`, `aspiration`, or
`random` bots. This command prints second-half class earnings beside the theory
benchmarks, plus trading efficiency; it writes no result files:

```sh
python -m llm_network_bargaining.simulate --network star3 --bot aspiration
```

Phase 3 adds display names, the versioned prompt renderer, the response schema
and parser, and `JsonBotAdapter` for offline checks through the language layer.
Review the nine scripted prompt examples with:

```sh
python -m llm_network_bargaining.prompts examples --out docs/prompt_examples.md
```

The review copy is committed at `docs/prompt_examples.md`, as an explicit
exception to the prompt-file ignore rules. Expected stimuli are also retained
as test fixtures in `tests/golden/`. Prompt history keeps
every offer and has no word limit. The renderer uses only the supplied
observation; it never consults the network registry to infer hidden information.

Model IDs and token prices use the API facts supplied in the Phase 4 brief,
checked against OpenAI's model pages on 1 November 2026. Implementation decisions and public interfaces
are recorded in [the Phase 1 notes](docs/phase1_notes.md) and
[the Phase 2 notes](docs/phase2_notes.md), with language-layer details in
[the Phase 3 notes](docs/phase3_notes.md).

## Model calls and the smoke test

Phase 4 adds an async Chat Completions client, `LLMAgent`, token cost tracking,
and a separate three-question rules quiz. `FakeChatClient` and `BotResponder`
exercise the same agent path entirely offline. Tests block both network access
and construction of OpenAI SDK clients. The SDK disables its own retries so
the harness can record each attempt, including costs from unusable replies.
Caching is off by default; every request explicitly sends `store=False` and
`reasoning_effort="none"` unless the config changes the reasoning setting.

Start by inspecting the four smoke requests without a key or network access:

```sh
python -m llm_network_bargaining.smoke --config configs/minimum_study.yaml --model terra --dry-run
```

For live calls, set `OPENAI_API_KEY` in your terminal environment. In bash or
zsh, these commands read it with hidden input, then export it to Python:

```sh
read -r -s OPENAI_API_KEY
export OPENAI_API_KEY
```

Never put the key in a config, source file, notebook or commit. The client reads
the environment only on its first request. After reviewing the dry run, run:

```sh
python -m llm_network_bargaining.smoke --config configs/minimum_study.yaml --model terra --live
```

The live mode sends a short turn, the same long turn twice, and a rules quiz.
It reports parsing, model identity, reasoning tokens and cache behavior, with
usage and total cost. Dry-run costs estimate input at four characters per token;
output cost is additional. Only live mode verifies actual API behavior.

Use `await agent.aact(observation)` and `await run_rules_quiz(...)` in one event
loop with a shared client; close it with `await client.aclose()`. `act()` is a
synchronous convenience and refuses to run inside an existing event loop.
API/model failures raise exceptions rather than becoming game passes. The quiz
does not enter subsequent turn messages. The experiment runner below adds
persistent logs and recovery. See [the Phase 4 notes](docs/phase4_notes.md) for interfaces
and implementation decisions.

## Running experiments

Try the pilot offline through the complete LLM path, with simulated costs:

```sh
python -m llm_network_bargaining.run run configs/pilot_full_map.yaml configs/pilot_own_links.yaml --dry-run aspiration --max-episodes 1
```

This plays ten 24-round episodes and writes to `runs_dry/`, which stays ignored
by Git. Every agent answers the rules quiz before play. No key is needed.

For a live experiment, export `OPENAI_API_KEY` as described above (the runner
does not load `.env` automatically), inspect the estimate, then start the run:

```sh
python -m llm_network_bargaining.run estimate configs/pilot_full_map.yaml configs/pilot_own_links.yaml
python -m llm_network_bargaining.run run configs/pilot_full_map.yaml configs/pilot_own_links.yaml --concurrency 8
```

The live command prints a plan and asks you to type `yes` before spending.
Use `--yes` for an explicitly approved noninteractive run. There is no spending
cap; actual usage and costs are recorded. Old configs containing `budget_usd`
are rejected. Live output defaults to `runs/`, which remains eligible for Git.

Inspect progress and verify saved logs without making API calls:

```sh
python -m llm_network_bargaining.run status configs/pilot_full_map.yaml configs/pilot_own_links.yaml --out runs_dry
python -m llm_network_bargaining.replay runs_dry
```

Re-run the same command and output folder to resume: completed episodes are
skipped; interrupted partial logs are archived as `interrupted1`, `interrupted2`,
and so on, and their episodes start again with a new attempt number.
A recoverable failure produces `failed1`, `failed2`, or `failed3` logs and
restarts with the same seed. After three failed attempts, an episode is
`abandoned`; other jobs continue. A bad key or another fatal API error stops
the run and preserves partial logs. Summaries include failed and interrupted
attempt costs. Interruptions do not count towards the three-failure limit.
Keep one runner per output root. Dry and live logs cannot share a root, and a
config or prompt-version mismatch requires a separate output folder.

Each completed attempt is a `.jsonl.gz` file. Each record is a JSON object:
header, quizzes, engine events, any failures, then a footer. `summary.json`
covers all logs for the config, including earlier invocations and conditions
outside the current filter. Replay rebuilds game outcomes and verifies prompt
hashes. See [the Phase 5 notes](docs/phase5_notes.md) for the schema and Python
interfaces.

## Analysing saved episodes

Phase 6 turns completed logs into tidy tables, episode metrics, benchmark
comparisons and the pre-registered statistical tests. It makes no model calls.
Install the updated dependencies with `pip install -e ".[dev]"` if needed.

```sh
python -m llm_network_bargaining.analyse runs --out analysis
```

To exercise the analysis offline, first generate two episodes per condition:

```sh
python -m llm_network_bargaining.run run configs/minimum_study.yaml configs/own_links_arm.yaml configs/pilot_own_links.yaml --dry-run aspiration --max-episodes 2
python -m llm_network_bargaining.analyse runs_dry --out analysis_dry --include-dry
```

`analysis_dry/` stays ignored by Git. Dry and live logs cannot be analysed
together; dry logs require `--include-dry`. Select configs with
`--configs minimum_study own_links_arm`; set `--boot` and `--seed` to control
the episode bootstrap. Repeating an analysis with the same data, seed and
dependency versions produces identical files, including the compressed CSVs.

The output includes the five source tables, class summaries, power use,
learning-curve numbers, H2 benchmark RMSEs and ordering accuracy, H1/H3–H6
tests with Holm decisions, four mixed models, operational diagnostics and the
pilot game-length decision when available. Missing hypothesis inputs are
reported as `not_run`. Separate `_no_last` class summaries and hypotheses
check whether the last round changes the findings. The primary outcome is
the second half; `--window all` is available for exploratory summaries.
These files contain numbers only; figures and note coding come in Phase 7.

```python
from llm_network_bargaining.analysis import load_dataset
from llm_network_bargaining.analysis.metrics import condition_class_summary
from llm_network_bargaining.analysis.hypotheses import run_hypotheses

data = load_dataset(["runs"])
classes = condition_class_summary(data)
tests = run_hypotheses(data).to_dict()
```

Every class has equal weight in the RMSE comparison. Degree and betweenness
enter only ordering accuracy, since they have no points scale. All hypothesis
tests use episodes as observations. See [the Phase 6 notes](docs/phase6_notes.md)
for the exact output columns, interfaces and analysis decisions.

## Pilot gate and report

After the live pilot finishes, generate its report without making model calls:

```sh
python -m llm_network_bargaining.report pilot runs_pilot --out reports/pilot
```

`pilot_report.md` contains provenance, five gate rows, learning curves, outcomes
and diagnostics. The first four checks must pass: no abandoned episodes and at
most 10% failed attempts; at most 2% invalid asked turns in every condition;
at least 90% perfect quizzes; and pair proposer share between 35% and 65%.
The fifth check reports the 12- or 24-round game-length decision as INFO. Interrupted
attempts are excluded from the failed-attempt fraction.

Follow the report's next steps. On PASS, set `settings.rounds` to the recommended
length in the five study configs, leaving both pilots at 24 rounds. On FAIL,
inspect the named diagnostic, revise the prompt under a new version, and rerun
the pilot. The report does not edit configs or start another experiment.

Exercise the same path with scripted bots:

```sh
python -m llm_network_bargaining.run run configs/pilot_full_map.yaml configs/pilot_own_links.yaml --dry-run aspiration --max-episodes 2
python -m llm_network_bargaining.report pilot runs_dry --out reports_dry/pilot --include-dry
```

## Study report and figures

```sh
python -m llm_network_bargaining.report study runs --out reports/study
```

`study_report.md` brings together the registered hypothesis tests, H1's secondary
network tests, second-half class outcomes beside the benchmarks, H2 RMSEs and
ordering accuracy, four headline figures, mixed models, exploratory stretch
results, the no-last-round check and diagnostics. Exploratory tables and figures
cover the sweep and no-exclusion control; H6 has class tables and its registered
test. It reads the same Phase 6
analysis results; it introduces no alternative statistical tests. H3 includes
the 3-line centre at k=2, star3 at k=3 and star4 at k=4 (plus star5 if present).

Figures in `figures/` have PNG and SVG copies, episode dots, bootstrap intervals,
colour-safe colours and distinct benchmark markers. Dry reports begin with a
banner stating that scripted-bot data are not study results. Set `--seed` and
`--boot` to control reproducible jitter and bootstraps. Generated dry reports
under `reports_dry/` stay ignored by Git.

By default the study report selects the five study configs present in its roots,
leaving out the pilots. Use `--configs minimum_study own_links_arm` to choose an
exact selection; unknown names report the available configs. All analysis files,
diagnostics and costs use that selection. Provenance lists excluded configs.

Keep pilot and study runs in separate folders so the notebook's default root
`runs` holds the study:

```sh
python -m llm_network_bargaining.run run configs/pilot_full_map.yaml configs/pilot_own_links.yaml --out runs_pilot
python -m llm_network_bargaining.report pilot runs_pilot --out reports/pilot
# Set settings.rounds in the study configs from the pilot decision, then:
python -m llm_network_bargaining.run run configs/minimum_study.yaml configs/own_links_arm.yaml configs/stretch_2c_sweep.yaml configs/stretch_2d_control.yaml configs/stretch_2f_h6.yaml --out runs
python -m llm_network_bargaining.notes code runs --out notes_results --live
python -m llm_network_bargaining.report study runs --out reports/study --notes notes_results/note_labels.csv
```

The sprint order is pilot, pilot report, set rounds, study runs, live note coding,
then the study report with notes. Note coding defaults to concurrency 8.

## Coding private notes

The separate `configs/note_judge.yaml` config uses Terra at medium reasoning
effort. Its `judge-v2` blind prompt sees only note text and a hash ID. It clarifies
competitive offers and fallbacks as exclusion reasoning, and distinguishes
self-interest from fairness toward the other side. Four labels cover
exclusion, fairness, structure and recognition. Repeated identical notes share
one primary judgment; a separate sample is judged again for consistency.
Consistency is not correctness: validation against hand labels is future work.

```sh
python -m llm_network_bargaining.notes estimate runs --out notes_results
python -m llm_network_bargaining.notes code runs_dry --out reports_dry/notes --include-dry --dry-run
python -m llm_network_bargaining.notes code runs --out notes_results --live
python -m llm_network_bargaining.notes compare notes_test/note_labels.csv notes_test_v2/note_labels.csv
```

Before the sprint, check the revised judge on the test episode:

```sh
python -m llm_network_bargaining.notes code runs_test --out notes_test_v2 --live
python -m llm_network_bargaining.notes compare notes_test/note_labels.csv notes_test_v2/note_labels.csv
```

`notes compare` is read-only: it matches coded turns and prints agreement,
Cohen's kappa and every changed label. It needs no key. Versioned IDs keep v1
caches valid for `judge-v1` and make v2 judge the notes again.

`--concurrency N` controls simultaneous batches in both coding passes (default
8; use 1 for sequential requests). Estimates include an approximate duration
at 20 seconds per batch. Fatal API errors stop new batches, let in-flight calls
finish, and retain cached results so a rerun sends only uncached notes.

The live mode requires an exported `OPENAI_API_KEY` and an interactive `yes`
(or an explicitly chosen `--yes`). Reasoning tokens make costs uncertain;
the estimate covers primary batches, with repeat checks additional. No key is
needed for estimates or dry runs. Keyword labels from `--dry-run` are test
outputs and must never be used as study results.

Outputs include per-turn `note_labels.csv`, `consistency.json`, cumulative
`judge_costs.json`, and reusable JSONL caches. Use the same output directory
to resume; cached notes make no new calls. Use `--out` on `estimate` to inspect
that cache; its default is `notes_out/`. Dry and live caches cannot share a
directory. Include labels in the study report with:

```sh
python -m llm_network_bargaining.report study runs --out reports/study --notes notes_results/note_labels.csv
```

## Rebuilding the notebook

```sh
python -m llm_network_bargaining.report notebook
```

This regenerates `notebooks/analysis.ipynb` as notebook JSON with no outputs.
Its cells rebuild the analysis tables, five figures and diagnostics without
model calls. Edit its first cell, or set `LNB_ROOTS`, `LNB_OUT` and
`LNB_INCLUDE_DRY=1`. Multiple roots can be a JSON list or separated with the
platform's path separator. It uses matplotlib's non-interactive Agg backend.
Jupyter and nbformat are not package dependencies. See
[the Phase 7 notes](docs/phase7_notes.md) for schemas and Python interfaces.
See [the Phase 7.1 notes](docs/phase7_1_notes.md) for the revised report layout,
judge versions, concurrency and label comparison.

## Pre-existing work

`preexisting/predict.py` and this harness were written before the Apart Research
Swarm Alignment sprint (6–8 November 2026). Phase 1 of the harness was written
on **31 October 2026**. The original script is preserved unchanged; the package
ports its mathematics without importing it.
Phase 2, including the engine, observations, and scripted bots, was also written
on **31 October 2026**, before the sprint.
Phase 3, including the language layer and golden prompt fixtures, was written
on **1 November 2026**, before the sprint.
Phase 4, including the model client, LLM agent, costs, quiz and smoke CLI, was
also written on **1 November 2026**, before the sprint.
Phase 5, including experiment execution, logs, recovery, replay and the CLI,
was written on **1 November 2026**, before the sprint.
Phase 6, including the offline analysis library and preservation of interrupted
attempts, was written on **1 November 2026**, before the sprint.
Phase 7, including reports, figures, the notebook, note coding and the H3
correction, was written on **1 November 2026**, before the sprint.
Phase 7.1, including report fixes, judge-v2, concurrent note coding and label
comparison, was written on **2 November 2026**, before the sprint. Protocol
variants such as brokers, attached messages, leaf unions and framing are future
work.
