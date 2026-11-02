# Phase 7.1 implementation notes

Implemented on **2 November 2026**, before the Apart Research sprint. The
Phase 7.1 brief is authoritative where it differs from the proposal. Protocol
variants are future work; no later phase was started. No commit, push, network
request, real model call or dependency installation was made in this phase.

## Starting state and protected inputs

- Baseline: `629 passed, 1 deselected in 47.50s`.
- `preexisting/predict.py` matched the required SHA-256
  `71a6d6d81954ef303cdd6f0a345afe9a961b56a17e63ea20d81431ec833bf0ec`.
- Before editing, hashes of the protected script, existing goldens, reference
  and prediction files, and every existing file under `runs_dry/` were saved.
  These inputs are checked again at completion. Existing `runs_dry/` logs were
  neither regenerated nor extended. The user's `runs_test/`, `notes_test/` and
  `.env` were not read or modified.
- The existing socket and OpenAI SDK constructor guards remain. New session
  fixtures explicitly apply guards while generating their isolated temporary
  stretch logs. All judge tests use fake clients.
- No statistical function, hypothesis, bootstrap, engine behavior, prediction,
  experiment config or runtime dependency was changed. Broker entry points only
  changed their unsupported-protocol message. The independent judge config
  changed only `judge_version`.

## Files and interfaces

Paths below are relative to `src/llm_network_bargaining/` unless otherwise noted.

| File | Change |
| --- | --- |
| `analysis/gate.py` | `STUDY_CONFIGS` supplies the five names used by the gate's unchanged PASS instruction and report selection. |
| `analysis/report.py` | Explicit columns, cell formatting, row sorting, cost totals, selected provenance, class outcomes, exploratory sections and notebook cell. |
| `analysis/figures.py` | A wider single-panel F1 and a two-column legend prevent clipping in the control figure. |
| `notes/judge.py` | Two exact templates, versioned defaults, semaphore-limited batches and ordered ledger totals. |
| `notes/cli.py` | `--concurrency`, time estimates and read-only `compare`. |
| `notes/compare.py` | Match coded turns and display the existing Cohen's kappa and changed labels. |
| `config.py`, `engine.py`, `simulate.py`, `prompts.py` | Say the broker protocol is future work. |
| `configs/note_judge.yaml` | Set the default to `judge-v2`; retain all other settings and prices. |
| `notebooks/analysis.ipynb` | Regenerated, with the optional stretch cell and no saved outputs. |
| `tests/golden/JUDGE_V2.txt` | Exact v2 text copied from the Phase 7.1 brief; v1 is unchanged. |
| `tests/test_phase7_1_reports.py` | Binding headers, numerical regressions, class cross-checks, config selection, exploratory results and notebook execution. |
| `tests/test_phase7_1_judge.py` | Both prompts, reference IDs, namespaces, parallelism, fatal recovery, timing and label comparison. |
| `README.md` | Separate pilot/study roots, sprint order, report contents, judge check and new commands. |
| `.gitignore` | Ignore only the additional generated root `runs_dry_stretch/`. |

```python
# analysis.gate, also imported by analysis.report
STUDY_CONFIGS = ("minimum_study", "own_links_arm", "stretch_2c_sweep",
                 "stretch_2d_control", "stretch_2f_h6")

# analysis.report
write_study_report(roots, out, *, include_dry=False, seed=1, n_boot=2000,
                   notes=None, configs=None) -> Path
markdown_table(table, columns=None, p_columns=()) -> str

# notes.judge
JUDGE_TEMPLATES = {"judge-v1": JUDGE_V1, "judge-v2": JUDGE_V2}
JUDGE_TEMPLATE = JUDGE_TEMPLATES["judge-v2"]
judge_prompt(notes, version="judge-v2") -> str
note_id(note, judge_version="judge-v2") -> str
collect_notes(ds, judge_version="judge-v2") -> DataFrame
estimate_notes(ds, config, out="notes_out", *, dry_run=None,
               concurrency=8) -> dict
await code_notes(ds, config, *, out, client, dry_run=False,
                 retry=RetryPolicy(), sleep=asyncio.sleep,
                 concurrency=8) -> JudgeRun

# notes.compare
compare_labels(labels_a, labels_b) -> str
```

`markdown_table` accepts a sequence of column names or the earlier rename
mapping. Explicit lists drive every report table. `_is_count` recognises count
names, including a flattened suffix such as `full_map.n`; `_format` rejects
non-integral numeric counts, formats costs to four decimals and tie credits to
one, and renders structured cells without JSON punctuation. Structured warning
cells in the Phase 6 CSV are decoded before formatting. Empty tables retain
their headers and have no invented placeholder row.

`_ordered` applies requested config order, registry network order, node-class
orbit order and the six-predictor order. `_select_study_configs` checks names
against all source headers, including non-completed attempts. Unknown names
raise `UnknownConfigs`; the CLI returns 2 and lists the found configs. Selected
names are passed to the Phase 6 analysis CLI, dataset loading, diagnostics,
costs and provenance. Main and robustness class sections use the two registered
main/own-links configs, in that order; exploratory classes use their own config.

`_class_tables` renders the existing saved class summaries. `_group_inputs`
flattens H5's nested groups and regroups H6's existing network/assignment
summaries. Before omitting difference sample counts it asserts `n_a` is the
second group's n and `n_b` is the first group's n: Phase 6's `_difference(b, a)`
reports first group minus second. H6's saved assignment differences supply the
existing difference and interval; the original per-assignment test columns
appear last. No test or difference is recomputed.

`_rmse_section` displays the saved shared set and ranking; `_ordering_section`
pivots existing accuracy values. Single-class networks are omitted from the
pivot and named below it. Exploratory pivots name their config-specific JSON
file, so the interval reference points to the correct saved data. The primary
pivot retains the exact `analysis/ordering_accuracy.json` reference.

For each selected 2c/2d config, the report calls the existing Phase 6 benchmark
and ordering functions, writes their results under `OUT/analysis/`, reads them
back and renders them. H6 gets class tables only. Empty shared sets and absent
stretch configs use the exact brief wording. Cost totals sum every numeric
source column and leave the three requested identifying cells blank.

G5's threshold, value and INFO status change only in `gate_table`.
`GateResult` and its readiness logic are untouched. The PASS next step is tested
character for character against its Phase 7 text.

The added notebook cell follows the figure cell and conditionally computes
and displays 2c/2d benchmark errors, ordering and F1. With neither config it
performs no work. Notebook execution tests cover both original and combined
roots using plain `exec`, without modifying the saved notebook.

## Judge versions and concurrency

The two templates have the same line count; exactly five lines differ.
`JUDGE_V1.txt`, the response schema, validation, quote checks, shuffle/batch
rules and keyword responder are unchanged. Versioned hashes retain the two
live-cache reference IDs in the brief. The new version judges every unique
note again; it neither edits nor reuses the other version's cache rows.

Concurrency is a positive CLI integer, default 8; values below 1 exit 2.
An asyncio semaphore limits batch retries in both passes. The main pass finishes
before repeat sampling. Split halves release the parent slot and use the same
semaphore. A fatal API error sets a shared stop event before releasing its
slot, so waiting batches make no request. All in-flight batches, including split
children, finish or fail before the error propagates. Cached judgments and the
cost ledger survive; the CLI returns non-zero. Reruns omit cached notes.

The append-only call ledger has an additive `batch_order` field: pass, original
shuffled first-note position and optional split path. Summing this logical
order, with IDs breaking ties, makes floating-point cost addition independent
of completion order. Earlier ledger entries without this field retain their
original relative order. The caches and ledger may differ in line order; the
three required final output files do not. Existing v1 ledger rows and cache
rows are never rewritten.

`estimate_notes` adds `concurrency` and `estimated_minutes` using the specified
nested-ceiling formula. The time is a rough estimate of primary batches only;
repeat checks remain additional. `print_estimate` adds the exact requested line.

`notes compare` reads the two files before any key or client logic. It inner
joins coded rows by episode UID and turn index, validates one-to-one matches,
and sorts changed rows by that key. It uses `cohens_kappa` without adding a
statistic. It preserves metadata/note text from file A for each changed row,
prints yes/no transitions in label order, and exits 2 on no matches. Files are
never written. Both label paths and the matched count are included in stdout.

## Decisions and small layout adjustments

- No real contradictions or open questions were found; no clarification was
  needed. The brief's expected values were retained as written.
- Main/robustness class tables retain the registered main-then-own-links order.
  Diagnostic/provenance tables follow the caller's config order. Stretch section
  headings follow the brief's fixed 2c, 2d, 2f sequence.
- H6's source shape differs from H5's, so its display groups the existing
  per-assignment summaries and saved differences rather than changing analysis.
- The new control F1 initially clipped its long legend. The single-panel layout
  now uses 7.5 by 4.5 inches and two legend columns. Multi-panel F1s keep their
  previous layout. This is a report layout fix; figure data are unchanged.
- Optional note prevalence, quote checks and repeat agreement also respect the
  selected episode UIDs. A restricted repeat table reuses `consistency_summary`
  on the selected part of the saved sample and repeat cache. If a restricted
  report has only a global consistency JSON and no repeat cache, its table is
  empty rather than reporting excluded notes' agreement. A complete selection
  retains the original saved summary.
- Comparison uses file A's text and turn metadata if those fields differ between
  matched rows, because the brief matches by turn identity rather than text.
- Existing temporary test fixtures may generate their own isolated logs, as in
  Phase 7; manual verification uses the original `runs_dry/` and the requested
  separate `runs_dry_stretch/`. The original logs remain byte-identical.

## Existing tests changed

Only four existing tests changed their assertions:

1. `tests/test_config.py::test_validation_errors`, broker parameter: expect
   `future work` in the new validation message.
2. `tests/test_episode_api.py::test_broker_protocol_and_agent_coverage`: expect
   `future work` in the engine's broker message.
3. `tests/test_note_judge.py::test_exact_request_prompt_and_blindness`: compare
   the default prompt against `JUDGE_V2.txt`. All blindness, schema, request and
   output assertions remain. New tests independently preserve exact v1 text.
4. `tests/test_phase7_reports.py::test_reports_link_figures_and_reproduce_tables`:
   expect integer G1 abandoned counts and G5's rounds/INFO rendering. All source
   statistics, linked figures, determinism and numerical assertions remain.

No historical phase notes or prior golden files were edited.

## Verification results

- Default final run: `684 passed, 1 deselected in 68.02s (0:01:08)`.
- Slow run: `1 passed, 684 deselected in 1.73s`.
- All 70 protected-file hashes match, including all 57 existing dry-root files.
  The dry-root file set is also unchanged (no files added or removed).
- The 18 new stretch episodes cover 9 conditions at 12 rounds, including the
  two model aliases in H6. No runner change was needed.
- Both original and combined roots execute every notebook code cell via `exec`,
  producing five and seven figures respectively. The saved notebook remains
  output-free and byte-identical after execution.
- Repeated report Markdown and PNG/SVG outputs are byte-identical. Concurrent
  judge tests verify byte-identical CSV/consistency/cost outputs at limits 1/8,
  peak in-flight limits, both passes, split batches, fatal recovery and cached
  resumption. No real API call or network request was made.
- Every required CLI command completed with exit 0. Commands used the project
  `.venv/bin/python`; `MPLCONFIGDIR=/private/tmp/lnb-matplotlib` only selects a
  writable matplotlib font cache and changes no experiment setting.

```sh
python -m llm_network_bargaining.run run configs/stretch_2c_sweep.yaml configs/stretch_2d_control.yaml configs/stretch_2f_h6.yaml --dry-run aspiration --max-episodes 2 --out runs_dry_stretch
python -m llm_network_bargaining.report pilot runs_dry --out reports_dry/pilot --include-dry
python -m llm_network_bargaining.report study runs_dry --out reports_dry/study --include-dry
python -m llm_network_bargaining.report study runs_dry runs_dry_stretch --out reports_dry/study_stretch --include-dry
python -m llm_network_bargaining.report notebook
python -m llm_network_bargaining.notes estimate runs_dry --include-dry --concurrency 8
```

The live pre-sprint judge commands were documented but not run. The comparison
below uses the four-row synthetic example, not the user's live label files.


### Pilot gate

| Check | Measure | Threshold | Value | PASS/FAIL |
| --- | --- | --- | --- | --- |
| G1: Run health | Abandoned episodes; failed / (completed + failed) | 0 abandoned; failed share ≤ 0.10 | 0 abandoned; failed share 0.00 | PASS |
| G2: No rule-breaking | Worst condition's invalid / asked turns | ≤ 0.02 in every condition | 0.00 | PASS |
| G3: Rules understood | Share scoring 3/3 | ≥ 0.90 | 1.00 | PASS |
| G4: Pair near 12/12 | Mean episode proposer share (second half) | 0.35 to 0.65 | 0.50 | PASS |
| G5: Game length | Own-links pilot window comparison | gap ≤ 0.1 on line3 and star3 → 12 rounds, otherwise 24 | 24 rounds | INFO |


### Pilot game length

| network | n_episodes | w_early | w_late | gap | within 0.1 |
| --- | --- | --- | --- | --- | --- |
| line3 | 2 | 0.31 | 0.70 | 0.40 | no |
| star3 | 2 | 0.49 | 0.83 | 0.34 | no |


### Study hypotheses

| Hypothesis | Data | Statistic | p | Holm-adjusted p | Decision |
| --- | --- | --- | --- | --- | --- |
| H1 | line3 (n = 2); line5 (n = 2); star3 (n = 2); star4 (n = 2) | 0.10 | 0.25 | 0.4335 | not supported |
| H3 | line3 (n = 2); star3 (n = 2); star4 (n = 2) | 0.05 | 0.02222 | 0.08889 | not supported |
| H4 | line4 (n = 2); line5 (n = 2) | 4.88 | 0.1667 | 0.4335 | not supported |
| H5 | line3 (n = 2); line4 (n = 2); line5 (n = 2); star3 (n = 2); star4 (n = 2); stem (n = 2) | -0.03 | 0.1445 | 0.4335 | not supported |
| H6 | not run | — | — | — | not run |


### Study robustness hypotheses

| Hypothesis | Data | Statistic | p | Holm-adjusted p | Decision |
| --- | --- | --- | --- | --- | --- |
| H1 | line3 (n = 2); line5 (n = 2); star3 (n = 2); star4 (n = 2) | 0.09 | 0.25 | 0.3333 | not supported |
| H3 | line3 (n = 2); star3 (n = 2); star4 (n = 2) | 0.05 | 0.01111 | 0.04444 | supported |
| H4 | line4 (n = 2); line5 (n = 2) | 4.95 | 0.1667 | 0.3333 | not supported |
| H5 | line3 (n = 2); line4 (n = 2); line5 (n = 2); star3 (n = 2); star4 (n = 2); stem (n = 2) | -0.05 | 0.02426 | 0.07279 | not supported |
| H6 | not run | — | — | — | not run |


### Study line3 class outcomes

| condition_key | node_class | n_episodes | points_mean | points_mean_ci_low | points_mean_ci_high | share_mean | share_mean_ci_low | share_mean_ci_high | equal_split | myerson | position_value | balanced |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| minimum_study/line3/full_map/terra | A\|C | 2 | 4.08 | 4.00 | 4.17 | 0.34 | 0.33 | 0.34 | 6.00 | 4.00 | 6.00 | 0.00 |
| minimum_study/line3/full_map/terra | B | 2 | 15.83 | 15.67 | 16.00 | 0.66 | 0.65 | 0.67 | 12.00 | 16.00 | 12.00 | 24.00 |
| own_links_arm/line3/own_links/terra | A\|C | 2 | 3.54 | 3.42 | 3.67 | 0.30 | 0.29 | 0.31 | 6.00 | 4.00 | 6.00 | 0.00 |
| own_links_arm/line3/own_links/terra | B | 2 | 16.92 | 16.67 | 17.17 | 0.70 | 0.69 | 0.72 | 12.00 | 16.00 | 12.00 | 24.00 |


### Study per-network ordering

| network_id | n_pairs | equal_split | myerson | position_value | balanced | degree | betweenness |
| --- | --- | --- | --- | --- | --- | --- | --- |
| line3 | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| line4 | 1 | 0.50 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| line5 | 3 | 0.83 | 0.67 | 0.67 | 0.83 | 0.50 | 0.33 |
| star3 | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| star4 | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| stem | 3 | 0.50 | 0.67 | 0.67 | 0.67 | 0.67 | 0.83 |


### Study costs

| config_name | model_alias | status | dry_run | calls | prompt_tokens | cached_tokens | cache_write_tokens | completion_tokens | reasoning_tokens | cost_usd |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| minimum_study | terra | completed | yes | 867 | 493326 | 0 | 0 | 11240 | 0 | 0.5495 |
| own_links_arm | terra | completed | yes | 963 | 550789 | 0 | 0 | 12498 | 0 | 0.6133 |
| total |  |  |  | 1830 | 1044115 | 0 | 0 | 23738 | 0 | 1.1628 |


### Combined-root hypotheses

| Hypothesis | Data | Statistic | p | Holm-adjusted p | Decision |
| --- | --- | --- | --- | --- | --- |
| H1 | line3 (n = 2); line5 (n = 2); star3 (n = 2); star4 (n = 2) | 0.10 | 0.25 | 0.578 | not supported |
| H3 | line3 (n = 2); star3 (n = 2); star4 (n = 2) | 0.05 | 0.02222 | 0.1111 | not supported |
| H4 | line4 (n = 2); line5 (n = 2) | 4.88 | 0.1667 | 0.578 | not supported |
| H5 | line3 (n = 2); line4 (n = 2); line5 (n = 2); star3 (n = 2); star4 (n = 2); stem (n = 2) | -0.03 | 0.1445 | 0.578 | not supported |
| H6 | line3/luna_hub (n = 2); line3/terra_hub (n = 2); star3/luna_hub (n = 2); star3/terra_hub (n = 2) | 0.27 | 0.25 | 0.578 | not supported |


### Exploratory headings

```text
### stretch_2c_sweep
#### sweep0
#### sweep1
#### sweep2
#### sweep3
#### Benchmark errors
#### Ordering accuracy
### stretch_2d_control
#### no_exclusion_control
#### Benchmark errors
#### Ordering accuracy
### stretch_2f_h6
#### line3
#### star3
```


### Control RMSE

| predictor | n_classes | rmse | ci_low | ci_high | p_best |
| --- | --- | --- | --- | --- | --- |
| equal_split | 6 | 2.49 | 2.49 | 2.73 | 0.00 |
| myerson | 6 | 2.57 | 2.38 | 3.04 | 0.00 |
| position_value | 6 | 2.04 | 1.88 | 2.54 | 1.00 |
| balanced | 6 | 2.49 | 2.49 | 2.73 | 0.00 |


### Control ranking

Ranking: position_value, balanced, equal_split, myerson. Best benchmark: **position_value**.


### Five-line judge change

```diff
--- judge-v1
+++ judge-v2
@@ -3 +3 @@
-Label each note on four questions. Judge only what the note says; do not guess what the agent might have meant. A note can be "yes" on several questions, or on none.
+Label each note on four questions. Judge only what the note says; do not guess what the agent might have meant. A note can be "yes" on several questions, or on none. Notes that say the same thing in different words get the same labels.
@@ -6,2 +6,2 @@
-   Yes: "Vash has no one else, so ask 18." / "If Pell won't take 8, I'll deal with Talin." / "Three partners compete for me; demand more." / "I risk being left out again, so offer more."
-   No: "Orsa already dealt this round." (a fact, not used as a reason) / "Accept 12; it's fair." / "Last round; take what's offered."
+   Yes: "Vash has no one else, so ask 18." / "If Pell won't take 8, I'll deal with Talin." / "Three partners compete for me; demand more." / "I risk being left out again, so offer more." / "Offer 19 to compete with Pell." (another agent competes for the same partner, named or not) / "Keep Talin's 20 open as a fallback; ask 21." / "Both offers stay open, so seek one more point."
+   No: "Orsa already dealt this round." (a fact, not used as a reason) / "Accept 12; it's fair." / "Last round; take what's offered." / "Talin accepted 21 last round." (history, not used as a reason) / "Offer 22 to secure a deal." (no alternative or rival)
@@ -9 +9 @@
-2. fairness: Does the note appeal to fairness, equality, an even split, reciprocity or being reasonable, as a reason?
+2. fairness: Does the note appeal to fairness, equality, an even split, reciprocity or being reasonable toward the other side, as a reason?
@@ -11 +11 @@
-   No: "Offer 12." (a number with no appeal) / "Ask 14; they accepted 12 before."
+   No: "Offer 12." (a number with no appeal) / "Ask 14; they accepted 12 before." / "Keep a reasonable share for myself." (self-interest, not fairness)
```


### Estimate output

```text
Non-empty notes: 0; empty: 3710
Unique notes: 0; already cached: 0; new: 0
Estimated primary calls: 0; cost: $0.000000
Estimated time: about 0 minutes at concurrency 8 (about 20 s per batch).
Reasoning makes actual cost uncertain; repeat-consistency calls are additional.
```


### Synthetic comparison output

Labels A: reports_dry/compare/labels_a.csv

Labels B: reports_dry/compare/labels_b.csv

Matched rows: 4

| label | n | agreement | yes_rate_a | yes_rate_b | kappa |
| --- | --- | --- | --- | --- | --- |
| exclusion | 4 | 0.75 | 0.50 | 0.25 | 0.50 |
| fairness | 4 | 1.00 | 0.00 | 0.00 | — |
| structure | 4 | 1.00 | 0.00 | 0.00 | — |
| recognition | 4 | 1.00 | 0.00 | 0.00 | — |

| round | phase | node | note | changes |
| --- | --- | --- | --- | --- |
| 1.00 | 1.00 | B | Note 1 | exclusion: yes → no |

## Open questions and status

None. Phase 7.1 is complete. Work stopped without a commit or push.
