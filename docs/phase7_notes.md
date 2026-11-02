# Phase 7 implementation notes

Implemented on **1 November 2026**, before the Apart Research sprint. This phase
adds the pilot gate, report figures, Markdown reports, an unexecuted notebook,
blind private-note coding and the registered H3 correction. Phase 8 has not
started. No commits, pushes or real API calls were made.

The Phase 7 brief defines the implementation. `Project_Proposal_Authoritative.md`
supplies the proposal context, including deferred hand-label validation.

## Files

| File | Purpose |
| --- | --- |
| `analysis/gate.py` | Four readiness checks, the informational game-length decision, and next steps. |
| `analysis/figures.py` | F1–F4, pilot learning curves, and deterministic PNG/SVG saving. |
| `analysis/report.py` | Pilot/study Markdown, source provenance, tables, and notebook generation. |
| `report.py` | `python -m llm_network_bargaining.report`. |
| `notes/__init__.py` | The four shared label names. |
| `notes/judge.py` | Exact blind prompt/schema, independent config, retries, caches and keyword fake. |
| `notes/consistency.py` | Seeded repeat selection, agreement and Cohen's kappa. |
| `notes/cli.py`, `notes/__main__.py` | Estimate, dry coding, and confirmed live coding entry points. |
| `configs/note_judge.yaml` | Terra/medium judge settings and token prices. |
| `notebooks/analysis.ipynb` | Rebuildable analysis notebook, with no execution counts or outputs. |
| `analysis/hypotheses.py` | H3 now includes line3 at k=2. |
| `model_client.py` | Additive `ChatRequest.purpose="judge"` annotation. |
| `tests/phase7_helpers.py` | Synthetic private notes and a report-table reader. |
| `tests/test_phase7_gate_figures.py` | Gate boundaries, figure contents/determinism, and H3 correction. |
| `tests/test_phase7_reports.py` | Source/report numerical agreement, repeated reports and executable notebook cells. |
| `tests/test_note_judge.py` | Blindness, schema, retries/splitting, costs, caches, quotes, kappa and CLI guards. |
| `tests/golden/JUDGE_V1.txt` | Independent exact judge template copied from the brief; the ten older goldens are unchanged. |
| `README.md`, `.gitignore`, `pyproject.toml` | Usage, ignored dry reports, and the one added direct dependency. |

Python module paths above are relative to `src/llm_network_bargaining/`.

## Starting checks, dependencies and earlier phases

- Baseline: `604 passed, 1 deselected in 33.35s`.
- The protected script matched SHA-256
  `71a6d6d81954ef303cdd6f0a345afe9a961b56a17e63ea20d81431ec833bf0ec`.
  All 14 protected-file hashes were saved before edits.
- `matplotlib>=3.9` is the only new direct dependency. It was missing, and the
  cached wheel supported Python 3.11 rather than this environment's 3.14.
  The user explicitly approved downloading matplotlib and required transitive
  dependencies, while keeping all runs and tests offline. Installed matplotlib
  is 3.11.2. Jupyter and nbformat were not added.
- Figures and report imports explicitly select Agg before importing pyplot.
  Tests also set `MPLBACKEND=Agg`. In this sandbox the home matplotlib cache
  is unwritable, so verification commands set
  `MPLCONFIGDIR=/private/tmp/lnb-matplotlib`; tests use a writable temp cache.
  This is an execution setting, not a new package dependency or user setting.
- Existing socket/SDK-constructor guards remain. Shared dry fixtures also
  block these explicitly during session-scoped generation. Test output files,
  including gzip, are scanned for the dummy key. Nothing copies an environment
  mapping or key into a request log, report, notebook or cache.
- Two older tests discovered experiment configs with `*.yaml`. They now
  exclude the independent `note_judge.yaml` schema, retaining every assertion
  on all seven experiment configs. The judge config has separate tests. No
  experiment-config loading behavior or existing config value was changed.
- The historical Phase 6 notes and tests now explicitly record the H3
  correction. Other statistical definitions, game behavior and prompts remain
  intact. The only model-client change is adding the judge purpose.

## Pilot gate

```python
select_configs(ds, names) -> Dataset
pilot_gate(ds, roots, *, full_map="pilot_full_map",
           own_links="pilot_own_links") -> GateResult
GateCheck(name, measure, threshold, value, passed, detail)
GateResult(checks, overall, game_length, next_steps, game_length_detail)
GateResult.to_dict() -> dict
```

`checks` is ordered G1–G5. `overall` is `PASS` or `FAIL`, depending solely on
G1–G4. All boundary comparisons are inclusive with tolerance 1e-9.

- **G1:** completed episodes plus failed attempt files form the denominator.
  Interrupted attempts are excluded from both numerator and denominator.
  `value` records `abandoned` and `failed_share`; `detail` contains completed
  and failed counts and failure categories from Phase 6 attempt diagnostics.
- **G2:** Phase 6 invalid/asked counts are summed over aliases within each
  condition before dividing. Every condition must have asked-turn data and
  pass. `detail` names the worst condition/rate and retains all condition counts
  and reason breakdowns. The strictest rate, with a lexical tie break, is shown.
- **G3:** Phase 6 quiz summaries are weighted by their quiz-record counts.
  The perfect-share threshold is pooled over both pilot configs; details also
  give record count and the three weighted question accuracies.
- **G4:** uses `episode_pair_proposer_share` on the full-map pilot's pair,
  with the default second-half window, then averages episodes. Details retain
  all available episode values: two in the dry demonstration, three in the
  planned pilot. No-deal episodes have no defined share.
- **G5:** reuses `game_length_decision` unchanged. A valid decision (12 or 24)
  is displayed as PASS/informational even when a network's early/late gap
  recommends 24. It does not enter the overall readiness verdict.

Missing measures fail with `detail="missing data"`. If the own-links windows
are missing, G5 has `value=None` and the original error is retained in
`game_length_detail`. G1–G4 still determine `overall`, as specified; if they
pass without a length decision, next steps request the missing pilot rather
than writing a meaningless rounds setting. Complete data produce the exact
five-config rounds instruction on PASS. On FAIL there is one inspection step
per failed readiness check, followed by the required prompt-version revision.
The gate does not edit configs or run a new experiment.

## Figures

```python
fig_observed_vs_predicted(ds, config="minimum_study", window="second_half",
                          seed=1, n_boot=2000) -> Figure
fig_power_use(ds, configs=("minimum_study", "own_links_arm"),
              window="second_half", seed=1, n_boot=2000) -> Figure
fig_dose_response(ds, config="minimum_study", window="second_half",
                  seed=1, n_boot=2000) -> Figure
fig_parity_flip(ds, config="minimum_study", window="second_half",
                seed=1, n_boot=2000) -> Figure
fig_learning_curves(ds, configs=("pilot_full_map", "pilot_own_links"),
                    seed=1, n_boot=2000) -> Figure
save_figure(fig, path_stem) -> tuple[Path, Path]
```

Each function uses Phase 6 episode/class metrics and summary intervals. P1
converts the supplied per-round point means and CI bounds linearly into PUI;
it does not bootstrap rounds or introduce another analysis. F3 uses hub share,
while F2/P1 use points-based PUI. F4 obtains every length-2–7 prediction from
`class_predictions`. F1 panels follow registry order and contain no unused
padding axes. F2 always shows the six advantaged networks, with episode counts
for both knowledge settings. Human references are 0.92 at line3, 0.5 at line5,
and a 0.5–1.0 band at line4. Captions cite the proposal's human sources.

The common palette is Okabe–Ito: blue equal split, orange Myerson, purple
position value, green balanced; benchmark shapes are circle, triangle, diamond
and star. White backgrounds, light grids, units and episode counts appear
throughout. Points/markers at zero and 24 are not clipped, and the points axes
label 24 explicitly. Degenerate core intervals get a small cap.

Jitter has its own `derive_seed(seed, "figure_jitter", label)` streams.
`svg.hashsalt` is `lnb`; SVG metadata omits Date and Creator, and PNG metadata
omits Software. PNG uses 200 dpi. The same data/seed/dependency versions produce
identical bytes; tests check separately rebuilt PNG/SVG and repeated saves of
the same Figure. `save_figure` does not close figures; reports and notebook
cells close them after saving/displaying. All five generated figures were
visually reviewed for labels, markers, intervals and legends.

## Reports and notebook

```python
write_pilot_report(roots, out, *, include_dry=False, seed=1, n_boot=2000) -> Path
write_study_report(roots, out, *, include_dry=False, seed=1,
                   n_boot=2000, notes=None) -> Path
write_notebook(path="notebooks/analysis.ipynb") -> Path
gate_table(gate_result) -> str
hypothesis_table(hypothesis_report_dict) -> str
markdown_table(dataframe, columns=None, p_columns=()) -> str
label_prevalence(labels_dataframe) -> DataFrame
```

Reports call the existing Phase 6 analysis entry point, writing its complete
CSV/JSON output to `OUT/analysis/`, then read those saved results for their
tables. The pilot selects the two pilot configs; the study retains the roots'
configs for provenance/diagnostics, while the existing hypothesis/H2 functions
keep their registered named-config scope. Figures call the same Phase 6 metric
functions with matching bootstrap settings. No statistic is substituted.

`pilot_report.md` has provenance, the gate/next steps, P1 and game-length table,
class outcomes/benchmark predictions, PUI and diagnostics. `study_report.md`
has provenance, main hypotheses, H1 secondary results and per-network inputs,
H2 RMSE/ranking/core distances/ordering accuracy, F1–F4, mixed models,
no-last-round hypotheses/class summaries and diagnostics. Optional notes add
prevalence, repeat consistency and the fraction of non-null quotes flagged as
not found. Coded turn rows, including repeated note texts, are the prevalence
denominator. Empty/uncoded notes are excluded. Keyword dry labels cannot be
included as live study results.

Numbers use two decimals; p-values use `.4g`. Missing numerical values are an
em dash and absent hypotheses say `not run`. Class-label pipes are escaped for
Markdown. Reports use relative PNG links; SVG companions are written beside
them. The only dates are the source headers' `started_at` range. Git commits,
prompt/quiz versions, model IDs and per-condition counts come from source logs.
Dry reports begin with the exact required bold banner. No output-folder path
or generation timestamp appears in report content.

The notebook is nbformat 4.5 JSON written with the standard library, stable
cell IDs, `execution_count=null` and empty outputs. It is eligible for the
next user-requested commit; Phase 7 itself makes no commit. Cells read
`LNB_ROOTS` (JSON list or platform-path-separated roots), `LNB_OUT`, and
`LNB_INCLUDE_DRY`, rebuild the analysis, display all four comparisons/models,
draw/save the five figures and show diagnostics/gate. A `display` fallback
allows the same cells to run through plain `exec` without Jupyter. Executing
the test cells never modifies the saved notebook.

## Judge config, prompt and interfaces

```python
JudgeConfig(judge_version="judge-v1", seed=20261106, batch_size=20,
            consistency_share=0.10, model: ModelSpec)
load_judge_config(path="configs/note_judge.yaml") -> JudgeConfig
note_id(note, judge_version="judge-v1") -> str
judge_prompt(notes, version="judge-v1") -> str
judge_response_format() -> dict
validate_labels(content, notes) -> list[dict]
quote_flags(label_row, note) -> list[str]
collect_notes(ds, judge_version="judge-v1") -> DataFrame
estimate_notes(ds, config, out="notes_out", *, dry_run=None) -> dict
KeywordResponder()  # FakeChatClient responder, never used for results
await code_notes(ds, config, *, out, client, dry_run=False,
                 retry=RetryPolicy(), sleep=asyncio.sleep) -> JudgeRun
JudgeRun(labels: DataFrame, costs: dict, consistency: dict)
```

The independent Pydantic config forbids extra fields, validates counts/shares,
and embeds the unchanged Phase 4 `ModelSpec`. The shipped model is Terra at
medium effort, with 12,000 completion tokens and the specified four prices.
Game agents remain at their experiment settings.

`JUDGE_TEMPLATE` exactly matches judge-v1, verified against the independent
fixture. The inserted JSON contains only `{id, note}`. Node IDs, network,
knowledge, model and time metadata never enter the request or fake context.
The strict `note_labels` schema requires all boolean/nullable-quote fields and
forbids additional fields at both levels. `ChatRequest` uses purpose `judge`,
and kwargs come directly from `build_chat_kwargs`.

- All engine turn positions are reconstructed with a zero-based per-episode
  count **before** removing auto turns. Phase 6 retains their source order.
  The CSV has one row per asked turn, including empty notes. Automatic turns
  are excluded because no agent was asked for a private note.
- Notes are stripped at the ends, but neither truncated nor normalised inside.
  Exact remaining text determines deduplication and the specified versioned
  SHA-256 ID. A detected truncated-hash collision raises rather than sharing
  labels. Identical texts share one primary judgment.
- Canonically sorted unique IDs are shuffled through
  `derive_seed(seed, "judge", "order")`, then cached IDs are omitted. Cache
  hits make no calls. IDs are validated as a complete set, with duplicates
  rejected and accepted replies reordered to the sent order.
- The shared Phase 4 retry helper handles response failures and API failures,
  using the same request on each retry. Once a batch exhausts model retries,
  it is split once. Each child gets one model-response attempt, retaining the
  Phase 4 transient retry policy. A failing singleton is `uncoded`, with the
  reason in its flags. Fatal errors propagate. No labels become game actions.
- Quote checks lower-case and collapse whitespace. Flags preserve the label:
  `quote_not_found:LABEL` and `quote_mismatch:LABEL`. Uncoded flags start with
  `uncoded:` and include the failure/validation category.
- The keyword responder matches case-insensitively using the specified lists.
  When several keywords match, it quotes the earliest occurrence in the note,
  preserving its original spelling. It is explicitly a test double.

## Cache, costs, consistency and output schemas

`note_labels.csv` columns are:

```text
episode_uid, turn_index, round, phase, node, node_class, network_id,
knowledge, config_name, note, note_id, exclusion, fairness, structure,
recognition, exclusion_quote, fairness_quote, structure_quote,
recognition_quote, status, flags, dry_run
```

`status` is `coded`, `empty` or `uncoded`; missing labels/quotes are blank CSV
fields. `flags` is a JSON-array string. **The additive `dry_run` column** marks
keyword outputs while retaining every required column. An all-empty output
still has rows marked dry; a completely absent asked-turn table gives a
header-only CSV with its mode stated in both companion JSON files.

The append-only `judge_cache.jsonl` and `consistency_cache.jsonl` store
`note_id`, `note`, `judge_version`, `dry_run`, `status`, `flags`, and the four
labels/quotes. The logical key is `(judge_version, note_id)`. Uncoded notes
are also cached, so a restart does not spend indefinitely on a persistent
failure. Use a new judge version/implementation when revising instructions or
judging settings. Dry and live outputs cannot share a cache directory.

`judge_calls.jsonl` is an append-only cost ledger: `judge_version`, `kind`
(`main` or `consistency`), sent `ids` and Phase 4 `attempts`. Costs/usage include
all successful and failed returned attempts, retries and split calls. The
shared retry helper uses `cost_of`; no second reasoning-token charge is added.
No timestamps or secret-bearing exception bodies are stored.

`judge_costs.json` fields are `dry_run`, `judge_version`, `model_id`,
`total_cost_usd`, `n_calls`, `usage`. Usage has the five Phase 4 counters.
Totals are cumulative over the version's ledger, including repeat checks;
a no-call second run leaves them unchanged rather than replacing them with
zero. Already recorded labels, CSVs and consistency output are byte-identical
on a cached rerun. Fresh live model replies remain provider-dependent; fixed
cached replies give deterministic files.

```python
consistency_ids(coded_ids, share, seed) -> list[str]
cohens_kappa(a, b) -> dict
consistency_summary(main_cache, repeat_cache, sample, *, dry_run) -> dict
```

The sample is `ceil(consistency_share * coded_unique)` using the specified
`judge/consistency` seed. Repeat order uses `judge/consistency-order`; repeat
batch capacity is half the primary batch size, at least one. With a singleton,
another ordering is impossible, but the request is still independent. Repeat
results never overwrite primary labels and have their own reusable cache.

`consistency.json` fields are `dry_run`, `judge_version`, `sample_ids`,
`n_selected`, `n_paired`, `labels`, `interpretation`. Every label's row has
`n`, `agreement`, `yes_rate_a`, `yes_rate_b`, `expected_agreement`, `kappa`,
`reason`. Undefined kappa is JSON null with a reason (same constant label in
both runs, or no paired coded notes). No unrequested confidence interval or
hand-label validation is added. This measures consistency, not correctness.

Report note-prevalence tables have `condition_key`, `config_name`, `network_id`,
`knowledge`, `node_class`, `n_notes`, and the four label proportions. The
repeat table adds `label` to each kappa row. Quote-miss share uses non-null
quotes across coded turn rows, including quote/label mismatches.

## Commands and confirmation

```sh
python -m llm_network_bargaining.report pilot ROOT --out DIR [--include-dry]
python -m llm_network_bargaining.report study ROOT --out DIR [--include-dry] [--notes LABELS_CSV]
python -m llm_network_bargaining.report notebook [--out notebooks/analysis.ipynb]
python -m llm_network_bargaining.notes estimate ROOT [--include-dry] [--out notes_out]
python -m llm_network_bargaining.notes code ROOT --out DIR [--include-dry] --dry-run
python -m llm_network_bargaining.notes code ROOT --out DIR --live [--yes]
```

Reports accept multiple roots, `--seed` and `--boot`. Notes commands also accept
`--configs` and an additive `--judge-config` path. `estimate`'s additive `--out`
selects the cache to inspect; without it the cache directory is `notes_out/`.
This resolves the brief's unspecified estimate cache location.

Live coding checks for the exported key, prints the primary-call estimate,
and requires `--yes` or interactive `yes` before constructing a client.
Non-TTY/no-yes returns 3; missing key returns 1. Dry coding/estimates need no
key. Reasoning costs are explicitly uncertain and repeat calls are additional
to the required primary estimate formula. No `.env` loading was added.

## Validation and dry-run outputs

The required 36 Phase 6 dry episodes were preserved; pilot_full_map was extended
from one to two episodes per condition, adding eight episodes. `runs_dry/` now
contains **52 completed episodes**, including 20 pilot episodes. `reports_dry/`
is ignored; the notebook stays eligible for version control with no outputs.
The user's existing `runs_test/` data were not read or changed.

All four requested commands succeeded:

```sh
python -m llm_network_bargaining.report pilot runs_dry --out reports_dry/pilot --include-dry
python -m llm_network_bargaining.report study runs_dry --out reports_dry/study --include-dry
python -m llm_network_bargaining.notes estimate runs_dry --include-dry
python -m llm_network_bargaining.report notebook
```

From `pilot_report.md`:

| Check | Measure | Threshold | Value | PASS/FAIL |
| --- | --- | --- | --- | --- |
| G1: Run health | Abandoned episodes; failed / (completed + failed) | 0 abandoned; failed share ≤ 0.10 | 0.00 abandoned; failed share 0.00 | PASS |
| G2: No rule-breaking | Worst condition's invalid / asked turns | ≤ 0.02 in every condition | 0.00 | PASS |
| G3: Rules understood | Share scoring 3/3 | ≥ 0.90 | 1.00 | PASS |
| G4: Pair near 12/12 | Mean episode proposer share (second half) | 0.35 to 0.65 | 0.50 | PASS |
| G5: Game length | Own-links pilot window comparison | 12 or 24 (informational) | 24.00 | PASS |

Overall is PASS; G5 recommends 24 for these **scripted-bot** inputs.

From `study_report.md`:

| Hypothesis | Data | Statistic | p | Holm-adjusted p | Decision |
| --- | --- | --- | --- | --- | --- |
| H1 | line3 (n = 2); line5 (n = 2); star3 (n = 2); star4 (n = 2) | 0.10 | 0.25 | 0.4335 | not supported |
| H3 | line3 (n = 2); star3 (n = 2); star4 (n = 2) | 0.05 | 0.02222 | 0.08889 | not supported |
| H4 | line4 (n = 2); line5 (n = 2) | 4.88 | 0.1667 | 0.4335 | not supported |
| H5 | line3 (n = 2); line4 (n = 2); line5 (n = 2); star3 (n = 2); star4 (n = 2); stem (n = 2) | -0.03 | 0.1445 | 0.4335 | not supported |
| H6 | not run | — | — | — | not run |

Notes estimate output:

```text
Non-empty notes: 0; empty: 3710
Unique notes: 0; already cached: 0; new: 0
Estimated primary calls: 0; cost: $0.000000
Reasoning makes actual cost uncertain; repeat-consistency calls are additional.
```

The bots' empty notes are expected. Separate tests inject non-empty notes to
exercise the judge. These dry outcomes are pipeline checks, not study findings.

### H3 correction

| Dry-run H3 | Inputs | Slope | Raw p | Holm p | Method |
| --- | --- | --- | --- | --- | --- |
| Historical Phase 6 | star3, star4 (two episodes each) | 0.0208333333 | 0.3333333333 | 0.5780178326 | exact, 6 assignments |
| Corrected Phase 7 | line3, star3, star4 (two each) | 0.0503472222 | 0.0222222222 | 0.0888888889 | exact, 90 assignments |

The corrected report records per-network k, n, mean and CI. At least two k
values are required. Three groups of ten use the existing slope permutation
function with exactly 200,000 Monte Carlo draws. Both small expected slopes
and p-values (0.1 with p=1/6 and p=1/90) pass. The correction also changes other
Holm-adjusted p-values through the existing family adjustment; their raw tests
are unchanged. All hypotheses remain unsupported on this tiny dry dataset.

- Final default suite: `629 passed, 1 deselected in 46.48s`.
- Slow suite: `1 passed, 629 deselected in 1.50s`.
- All 14 protected files retain their starting hashes: the original script,
  prediction files and ten earlier golden fixtures are unchanged.
- Report table tests compare every gate/hypothesis number to its source result.
  Repeated reports, rebuilt figures, repeated figure saves, cached labels and
  the notebook generator produce identical bytes as specified.
- The notebook's code cells executed in order with `exec`, using the dry logs,
  without Jupyter, network access or model calls. The saved notebook remains
  unexecuted and output-free.
- No real API calls, key copies, commits or pushes were made. No open questions
  remain for Phase 7; Phase 8 has not started.
