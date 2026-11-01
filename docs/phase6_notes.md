# Phase 6 implementation notes

Implemented on **1 November 2026**, before the Apart Research sprint.
This phase adds numerical analysis only. No figures, notebooks, study reports,
note coding, commits or pushes were made. Phase 7 has not started.

The Phase 6 brief defines the analysis; `Project_Proposal_Definitive_Latest.md`
provides the proposal context. All supplied numerical expectations reproduced.

## Files

| File | Purpose |
| --- | --- |
| `analysis/__init__.py` | Dataset and window imports. |
| `analysis/data.py` | Completed-log loading and the five tidy tables. |
| `analysis/windows.py` | Primary, no-last-round and all-round windows. |
| `analysis/predictions.py` | Maximum-matching equal splits, theory and centrality by node class. |
| `analysis/metrics.py` | Episode metrics, condition summaries and operational diagnostics. |
| `analysis/stats.py` | Exact/Monte Carlo tests, episode bootstraps and Holm adjustment. |
| `analysis/benchmarks.py` | H2 RMSE ranking, core distances and ordering accuracy. |
| `analysis/hypotheses.py` | H1/H3–H6, the primary Holm family and secondary H1 tests. |
| `analysis/mixed.py` | Four common-row maximum-likelihood mixed models. |
| `analysis/game_length.py` | Fixed-window 12-versus-24-round pilot decision. |
| `analysis/cli.py` | Deterministic CSV/JSON analysis outputs and text summary. |
| `analyse.py` | Entry point for `python -m llm_network_bargaining.analyse`. |
| `runlog.py`, `runner.py` | Archive interrupted attempts and preserve their costs on resume. |
| `replay.py` | Replay an interrupted prefix even when it ends partway through an engine step. |
| `tests/phase6_helpers.py` | Synthetic per-episode point-table helper. |
| `tests/test_analysis_*.py` | Reference-value, table-loading, hypothesis and end-to-end tests. |
| `tests/conftest.py`, `tests/test_runner.py` | Shared offline logs and updated interruption expectations. |
| `pyproject.toml`, `README.md`, `.gitignore` | Dependencies, usage and ignored generated dry analysis. |

The analysis module paths in this table are relative to
`src/llm_network_bargaining/`.

## Dependencies and starting checks

- Baseline: `561 passed, 1 deselected in 27.05s`.
- `preexisting/predict.py` matched SHA-256
  `71a6d6d81954ef303cdd6f0a345afe9a961b56a17e63ea20d81431ec833bf0ec`.
  Hashes of all 14 protected files (the script, prediction files and ten
  goldens) were saved before edits for final comparison.
- The only new direct requirements are `pandas>=2.2,<4` and
  `statsmodels>=0.14.4`. Neither was installed, and compatible offline wheels
  were unavailable. The user explicitly approved dependency downloads as an
  exception to the brief's network prohibition. Installed versions are
  pandas 3.1.0 and statsmodels 0.15.0, with their required transitive packages.
  NumPy 2.5.0 and SciPy 1.18.0 were already installed.
- All experiment runs use aspiration bots through `FakeChatClient` and
  `BotResponder`. Tests block sockets and real OpenAI SDK constructors, and
  scan temporary output files, including gzip files, for the dummy key.
  No API call was made.

## Dataset and loading decisions

`Dataset` is a dataclass holding `episodes`, `node_rounds`, `deals`, `turns`,
`quizzes` and `dry_run: bool`. Each table is a pandas DataFrame.

The five column lists below are exact and ordered:

```python
load_dataset(roots, *, configs=None, include_dry=False) -> Dataset
dataset_from_tables(*, episodes=None, node_rounds=None, deals=None,
                     turns=None, quizzes=None, dry_run=False) -> Dataset
outcome_rows(ds, window="second_half") -> pd.DataFrame
window_rounds(n_rounds, window="second_half") -> range
class_predictions(network_id) -> pd.DataFrame
advantaged_class(network_id) -> dict | None
```

```text
episodes:
  episode_uid, config_name, condition_key, network_id, knowledge, assignment,
  episode_index, episode_seed, attempt, n_rounds, n_nodes, prompt_version,
  dry_run_bot, cost_usd, n_turn_calls, n_quiz_calls

node_rounds:
  episode_uid, config_name, network_id, knowledge, assignment, node, node_class,
  model_alias, round, points, dealt, partner, maker, share, slot1, slot1_norm

deals:
  episode_uid, round, phase, maker, recipient, maker_points, recipient_points,
  maker_class, recipient_class

turns:
  episode_uid, round, phase, slot, node, model_alias, auto, applied, valid,
  reason, n_attempts, cost_usd, note, note_words, warnings

quizzes:
  episode_uid, node, model_alias, score, q1, q2, q3
```

- `episode_uid` is `condition_key + "/" + episode_index` padded to three digits.
  Class labels use the Phase 1 automorphism orbits. Star leaves retain their
  canonical IDs, `L1`, `L2`, etc.
- Only `episode_XXX.jsonl.gz` files with completed footers create table rows.
  Failed, archived interrupted and active partial logs never become episodes.
- Config filtering applies before mode checks. Among selected configs, all
  attempt headers participate in dry/live validation, including non-completed
  attempts. Mixing modes raises. Selecting dry data without `include_dry=True`
  raises rather than silently omitting it. An empty selection has `dry_run=False`.
- Two different files claiming the same `(config_name, condition_key,
  episode_index)` raise. Repeating the very same path in roots is deduplicated
  by the shared file finder.
- Round points come from `round_end`. Deals determine partner, maker and dealt,
  including a dealt node receiving zero points. Share is missing without a
  deal. Slots come from the full phase-1 order, including already-done nodes;
  they are 1-based, and `slot1_norm = (slot1 - 1) / (n_nodes - 1)`.
- Turns include automatic engine turns; asked-call counts and costs come from
  metadata. Notes are the parsed requested action's private note, with words
  counted by whitespace splitting. Warnings remain lists in memory; the CSV
  writer stores list/dict fields as JSON strings. Quizzes' q1–q3 fields are
  correctness booleans, not answer letters.
- `dataset_from_tables` makes independent copies in the same column order and
  supplies empty frames for omitted tables. It is a convenient synthetic-data
  constructor, not a game-rule validator. Its test helper accepts a network,
  knowledge setting and a list of episode mappings from nodes to constant or
  per-round point values; optional dealt flags support zero-point deals.

## Windows, predictions and outcome tables

`second_half` is `n_rounds // 2 + 1` through the last round;
`second_half_no_last` removes only that last round; `all` starts at round 1.
The first two produce empty ranges when appropriate for a very short game.
Windowed outcome functions validate window names even with no rows.

`class_predictions(network_id)` has these columns:

```text
network_id, node_class, n_members, equal_split, myerson, position_value,
balanced, core_min, core_max, degree, betweenness
```

Every maximum matching is enumerated exactly once by either leaving the first
free node unmatched or pairing it with one free neighbour. A node's inclusion
frequency times half the pie gives its equal-split point prediction. All other
predictions use the Phase 1 functions. Centrality remains a raw score and is
used only for ordering accuracy. Undefined theory values are NaN. Prediction
calculation is cached internally, but returned DataFrames are independent.
Broker protocols are outside Phase 6 and raise explicitly.

For describing the remaining output schemas, these shorthand column lists
are expanded in the code and CSVs:

```text
CONDITION = config_name, condition_key, network_id, knowledge, assignment
EPISODE   = episode_uid, CONDITION, episode_index
METRICS   = points_mean, deal_rate, exclusion_rate, share_mean, n_deals
CI(x)     = x, x_ci_low, x_ci_high
```

| Function/table | Columns |
| --- | --- |
| `episode_node_metrics` | EPISODE, node, node_class, model_alias, METRICS |
| `episode_class_metrics` | EPISODE, node_class, METRICS |
| `power_use` | All episode-class columns, balanced, pui; only advantaged classes |
| `summarise_power_use` | CONDITION, n_episodes, CI(pui) |
| `condition_class_summary` | CONDITION, node_class, n_episodes, CI(points_mean), CI(share_mean), CI(deal_rate), all prediction columns except repeated network_id/node_class |
| `episode_efficiency` | EPISODE, efficiency |
| `summarise_efficiency` | CONDITION, n_episodes, CI(efficiency) |
| `episode_pair_proposer_share` | EPISODE, proposer_share |
| `summarise_pair_proposer_share` | CONDITION, n_episodes, CI(proposer_share), p_value, method, n_test |
| `episode_triangle_lock_in` | EPISODE, lock_in |
| `summarise_triangle_lock_in` | CONDITION, n_episodes, CI(lock_in) |
| `learning_curves` | CONDITION, node_class, round, n_episodes, CI(points_mean) |

The episode metric functions take `(ds, window="second_half")`. The summary
functions add `(n_boot=2000, seed=1)` after the window. `learning_curves` has
the same arguments but defaults to `window="all"`. All functions in this
table return DataFrames, including empty frames with their documented columns.

- Node means average window rounds. Class means average members' node means,
  so a member never gains more weight by trading more often. A class's share
  mean omits members with no deals; if all lack deals it remains NaN. Class
  `n_deals` is also a member mean and can be fractional.
- The advantaged class has the highest balanced value above 12. The registered
  cases are line3 B, line4 B|C, line5 B|D, star hubs H and stem B. Pair,
  triangle and sweep0 have none. For an additional registered network with
  several distinct classes tied at the highest balanced value, lexical class
  order selects the first; no core-study network has this ambiguity.
- PUI uses class **points per round**, not share: `(points_mean - 12) /
  (balanced - 12)`. It is not clipped to [0, 1].
- Efficiency counts dealt nodes divided by two, then by maximum matching size,
  before averaging rounds. Pair proposer share averages deals within each
  episode and then episodes; a no-deal episode has a missing share. Its
  two-sided sign-flip comparison to 0.5 is descriptive, outside Holm.
- Triangle lock-in uses exclusion rates; all nodes have the same number of
  window rounds, so their common denominator cancels in `max / sum`. A zero
  sum gives NaN. Learning curves first average members within an episode and
  round, and then average episodes. Their default window is explicitly `all`.
- Condition CIs resample episodes. Missing metric values are omitted before
  resampling; `n_episodes` still counts the condition's contributing episodes.
  Empty values give NaN intervals, and one observation gives a degenerate CI.

## Statistical interfaces and conventions

```python
sign_flip_test(x, null=0.0, alternative="greater", exact_max_n=20,
               n_mc=200_000, seed=1) -> TestResult
permutation_test_two_sample(a, b, alternative="greater", exact_max=200_000,
                            n_mc=200_000, seed=1) -> TestResult
slope_permutation_test(x, groups, alternative="greater", exact_max=200_000,
                       n_mc=200_000, seed=1) -> TestResult
stratified_permutation_test(values, labels, strata, n_mc=100_000,
                            seed=1, exact_max=200_000) -> TestResult
bootstrap_ci(values, stat=np.mean, n_boot=2000, seed=1,
              level=0.95) -> tuple[float, float]
grouped_bootstrap_means(groups, n_boot=2000, seed=1) -> dict[str, np.ndarray]
holm(pvalues, alpha=0.05) -> dict[str, dict]
```

`TestResult` fields are `statistic`, `p_value`, `method`, `n_resamples`,
`alternative`, `n`, `n_a`, `n_b`; the last two are populated by the two-sample
test. `to_dict()` returns ordinary JSON-ready Python values. Empty usable
samples raise; NaNs are dropped first. All specified tail comparisons include
equality with tolerance 1e-12. Alternatives are `greater`, `less`, `two-sided`.

Exact sign flips enumerate all signs of absolute deviations, including zeros.
Permutation tests enumerate assignments of observation indices, so repeated
values do not lose multiplicity. Two-sample statistics are always mean(b)
minus mean(a). Multi-group slopes use OLS on the numeric labels. Stratified
statistics weight networks equally and shuffle labels only within networks.
Exact tests use the observed-inclusive fraction. Monte Carlo tests use
`(count + 1) / (n_mc + 1)`.

Every stochastic path uses `make_rng(derive_seed(seed, ...))`. Functions have
separate labels; grouped bootstrap streams also include the condition key.
Inputs to `grouped_bootstrap_means` are episode-by-class matrices. All class
columns from one episode are resampled together; outputs are bootstrap-by-class
means. Stable input ordering and fixed seeds give repeatable output. Percentile
intervals use NumPy's default linear quantiles.

Holm returns `p_adjusted` and `reject` per supplied hypothesis, using the
running maximum of `(m - rank) * p`, capped at 1. Missing hypotheses are not
passed into it.

## H2 and ordering result interfaces

```python
benchmark_errors(ds, config="minimum_study", window="second_half",
                  n_boot=2000, seed=1) -> dict
ordering_accuracy(ds, config="minimum_study", window="second_half",
                   n_boot=2000, seed=1) -> dict
```

Both use one condition per network within the named config. Multiple
assignments/settings for the same network raise instead of silently pooling
distinct conditions. Observed values are episode means of class means. Every
class gets equal RMSE weight, regardless of its number of members. Bootstrap
episodes stay within conditions. Every predictor uses the same resamples.

`benchmark_errors` returns `status`, `config`, `window`, `per_network`,
`overall`, `ranking`, `best`, `overall_networks`, `core_distances`, `n_boot`,
`seed`. Its record schemas are:

```text
per_network: network_id, condition_key, predictor, rmse, ci_low, ci_high,
             n_classes, n_episodes
overall: predictor, rmse, ci_low, ci_high, n_classes, p_best
core_distances: network_id, node_class, observed, core_min, core_max, distance
```

Only four point benchmarks enter RMSE. A network missing any one is excluded
from every overall RMSE, making comparisons use identical network/class pairs.
The triangle still has separate errors for its three defined predictions.
Core distances are zero inside an interval and undefined for an empty core.
`ranking` sorts point-estimate overall RMSEs. A point-estimate tie keeps benchmark
order; `best` is its first entry. Bootstrap P(best) splits ties equally, using
1e-12 tolerance. No ranking exists if there are no eligible networks.

`ordering_accuracy` returns `status`, `config`, `window`, `per_network`,
`overall`, `n_boot`, `seed`. Both record lists have `predictor`, `correct`,
`n_pairs`, `n_tied_observed`, `accuracy`, `ci_low`, `ci_high`; per-network
records additionally have `network_id`. All six predictors participate.
Each unordered class pair counts once. Exactly equal observed means remove
the pair; predicted ties count half. Undefined predictors skip that network.
Zero included pairs give undefined accuracy. Bootstrap resamples can alter
observed ties, so counts are recalculated in every resample; undefined
replicate accuracies are omitted from the CI. These scores are not ranked.

## HypothesisReport

```python
run_hypotheses(ds, *, main="minimum_study", own_links="own_links_arm",
               h6="stretch_2f_h6", window="second_half", seed=1,
               n_boot=2000) -> HypothesisReport
```

The additive `n_boot` argument lets the CLI's `--boot` control descriptive CIs
throughout. Test sample counts are unchanged. `HypothesisReport` exposes
`results`, `family`, `h1_per_network`, `window`, `seed`, and JSON-serialisable
`to_dict()`. H2 remains in its separate ranking result, outside this object.

- `results` is keyed by H1/H3/H4/H5/H6. Available results have `status="run"`,
  `statistic`, `p_value`, `method`, `per_network`, `p_adjusted`, `reject`,
  `decision` and test details as applicable. Missing required inputs give
  `status="not_run"`, `decision="not_run"` and a reason. Available per-network
  inputs are retained even for an incomplete joint claim.
- Network inputs record `n`, `mean`, `ci_low`, `ci_high`, plus component test
  fields when there is a component test. All counts are usable episode values.
- H1 needs all four networks. Component tests use advantaged-class share minus
  0.5. Its joint p-value is the largest component p-value. The aggregate
  `statistic` is the smallest component mean deviation, a descriptive effect;
  the p-value always comes from the intersection–union rule. H6 follows the
  same rule for four network/assignment cells, using PUI minus zero.
- H1's `h1_per_network` copies the four component results and adds a **separate**
  Holm adjustment, reject flag and decision across those four only. It never
  expands the primary family. Constructing `HypothesisReport` from injected
  test dictionaries also exercises this reporting path in the specified test.
- H3 permutes hub shares over numeric leaf counts, requiring two star sizes.
  H4 supplies line5 ends as sample a and line4 ends as b, so a positive
  statistic is the registered direction.
- H5 uses every common eligible network from the named full-map and own-links
  configs. It uses the shared stratified test's exact threshold when small;
  otherwise it uses exactly 100,000 Monte Carlo draws. Thus the two-episode
  dry data use exact enumeration; the planned ten-episode six-network study
  uses Monte Carlo. Network differences have independent episode-bootstrap
  CIs, not seed-paired bootstraps.
- H6 additionally reports `assignment_differences`, keyed by network, for
  terra_hub minus luna_hub, with CIs. These differences are descriptive.
- `family` contains only run H1/H3/H4/H5/H6 results, adjusted together at 0.05.
  Decisions are `supported` or `not_supported`; incomplete tests stay outside.

## Diagnostics, mixed models and game length

Diagnostics' table columns are:

```text
invalid_action_rates:
  CONDITION, model_alias, n_asked, n_invalid, invalid_rate, by_reason
quiz_summary:
  CONDITION, model_alias, n, mean_score, perfect_share,
  q1_accuracy, q2_accuracy, q3_accuracy
attempt_diagnostics:
  config_name, condition_key, failed_attempts, failed_by_category,
  interrupted_attempts, abandoned_episodes, non_completed_cost_usd
cost_summary:
  config_name, model_alias, status, dry_run, cost_usd, calls, prompt_tokens,
  completion_tokens, cached_tokens, cache_write_tokens, reasoning_tokens
```

Invalid actions exclude auto turns. Quiz summaries use only completed episodes.
Attempt diagnostics use every retained attempt; concurrent failure categories
are counted once each per failed attempt. The default abandonment threshold
is three failed files (`max_failed` can be supplied explicitly).
`cost_summary(ds, roots, configs=None)` reads all configs under roots by
default, including failed-only configs; `status` is `completed` or
`non_completed`. An explicit config filter keeps CLI diagnostics scoped to
the selection. `attempt_diagnostics(roots, configs=None, max_failed=3)` accepts
the same optional filter. Costs and all five token counters include retries.

`fit_mixed_models(ds, config="minimum_study", window="second_half")` returns:

```text
predictor, intercept, intercept_se, pred, pred_se, slot1_norm, slot1_norm_se,
log_likelihood, aic, n_obs, n_groups, converged, error, warnings
```

It calls the specified `MixedLM.from_formula("points ~ pred + slot1_norm",
groups="episode_uid", data=...).fit(reml=False)` for the four point benchmarks.
All use identical rows from networks with all four benchmarks defined.
Warnings are recorded; failed fits record an error and do not stop the other
fits. No centrality score enters a mixed model, and no successful fit is
silently replaced by another model. An empty config returns a header-only table.

`game_length_decision(ds, config="pilot_own_links", networks=("line3",
"star3"), tolerance=0.1)` uses precisely rounds 7–12 and 13–24, averaging
episode PUIs in each. It returns `config`, `networks`, `tolerance`, `rule` and
`decision` (12 or 24). Each network records `w_early`, `w_late`, `gap`,
`n_episodes`, `passed`. The comparison uses tolerance + 1e-9. Empty, incomplete
or non-24-round input raises. The CLI reports an incomplete optional pilot
decision as `not_run`, rather than choosing a length with missing networks.

## Interrupted-attempt follow-up and earlier-phase changes

- On resume an unarchived partial becomes
  `episode_XXX.interruptedK.jsonl.gz`; K counts that episode's interruptions.
  Gzip headers have mtime zero and an empty filename. A torn final JSON/UTF-8
  line remains recoverable after compression. No footer is invented.
- `read_log` accepts such archived prefixes without a footer, just as it does
  active partials. Failed and completed gzip logs still require footers.
- Header attempt numbers count **both** failed and interrupted files plus one.
  Failed filenames retain the original Phase 5 convention of using the actual
  attempt number: after interrupted attempt 1, a failed attempt 2 is `failed2`.
  Abandonment counts failed files, not their numeric suffixes or interruptions.
- `summary.json` includes known costs of all retained attempts and gains
  `interrupted_attempts`, counting archived and active interruptions separately
  from its existing episode-status count `interrupted`.
- A leftover partial for an already compressed attempt is deduplicated before
  cost accounting and removed on resume. A genuinely different attempt is
  archived even if the episode is already completed or abandoned.
- Shared helpers are `archive_interrupted(folder, index) -> Path`,
  `attempt_costs(records) -> dict` and `read_attempt_logs(roots) -> list` of
  `(Path, LogRecords)` pairs. The latter drops only duplicate partials, not
  different completed files, which the Dataset loader must reject.
- Replay now derives unlogged phase orders from the seed and checks only the
  recorded event prefix when there is no footer. This covers a crash between
  two events emitted by one engine step. Completed/failed log comparisons
  retain their full-event checks. This additive repair was exposed by an
  archived-interruption integration test.
- These changes supersede the delete-on-resume behavior described in the
  historical Phase 5 notes. Engine actions, prompts, schemas, goldens and
  mathematical prediction files are unchanged.

## CLI outputs and reproducibility

```sh
python -m llm_network_bargaining.analyse ROOT [ROOT ...] --out DIR \
  [--configs NAME ...] [--include-dry] [--window second_half] \
  [--boot 2000] [--seed 1]
```

Writes `episodes.csv`, `node_rounds.csv.gz`, `deals.csv.gz`, `turns.csv.gz`,
`quizzes.csv`, `class_summary.csv`, `power_use.csv`, `learning_curves.csv`,
`benchmark_errors.json`, `ordering_accuracy.json`, `hypotheses.json`,
`mixed_models.csv`, `diagnostics.json`, `class_summary_no_last.csv`, and
`hypotheses_no_last.json`. `game_length.json` is included when a selected
24-round pilot_own_links config is present. A stale game-length file is removed
when that optional input is absent. A non-default `--window` affects the main
outcome outputs; learning curves still use all rounds and the `_no_last`
outputs always use `second_half_no_last`.

`power_use.csv` contains per-episode values. Its condition summary is also
in `diagnostics.json` under `power_use`. Other diagnostics keys are `dry_run`,
`invalid_actions`, `quizzes`, `attempts`, `costs`, `efficiency`,
`proposer_share`, `triangle_lock_in`. DataFrame values become record lists.
JSON uses sorted keys and strict finite numbers, with missing/undefined values
represented as null. Compressed CSV headers have no path or timestamp. No
analysis output includes timestamps. `analysis_dry/` is ignored; live analysis
outputs are not automatically ignored.

## Validation and requested dry-run summary

The 36 required test episodes were generated with two episodes per condition
for minimum_study, own_links_arm and the 24-round pilot_own_links. They cover
all table/log comparisons, exact references, Monte Carlo paths, missing
hypotheses, H1's two Holm families, finite mixed-model AICs, and repeated
byte-identical CLI files. Interrupted-cost tests check both summary.json and
analysis costs, plus preservation of the failure limit.

The same data were generated in the project's `runs_dry/` folder. It already
held eight pilot_full_map episodes and the first two pilot_own_links episodes
from Phase 5; these were preserved, bringing the analysis input to 44 completed
episodes. The requested command exited 0:

```sh
python -m llm_network_bargaining.analyse runs_dry --out analysis_dry --include-dry
```

```text
Dry-run analysis (simulated costs).
minimum_study: 16 completed episodes
own_links_arm: 16 completed episodes
pilot_full_map: 8 completed episodes
pilot_own_links: 4 completed episodes
H1: not_supported (p=0.25, Holm=0.578018)
H3: not_supported (p=0.333333, Holm=0.578018)
H4: not_supported (p=0.166667, Holm=0.578018)
H5: not_supported (p=0.144504, Holm=0.578018)
H6: not_run
H2 best benchmark: myerson
Game length: 24 rounds
```

These outputs verify analysis on synthetic bot behavior; they are not evidence
for or against the study hypotheses and do not choose the live study's length.

- Final default suite: `604 passed, 1 deselected in 33.10s`.
- Slow suite: `1 passed, 604 deselected in 1.15s`.
- All 14 protected files retain their original hashes, including the ten goldens.
- All 16 specified analysis files were written. Repeated CLI tests produce
  byte-identical files, including gzip CSVs, with the same data and seed.
- No model calls, commits or pushes were made. The user's existing `runs_test/`
  directory was left untouched. No open questions remain for Phase 6.
