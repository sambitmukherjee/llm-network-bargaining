# Reproducing the paper's results

This guide rebuilds the retained results for **Positional Advantage: Network Structure and Bargaining Power among LLM Agents**. It uses the 160 saved study episodes, replays their recorded decisions and regenerates fifteen tables and six figures. Reproduction makes no model requests and needs no API credentials. The 2 November pilot is excluded from these estimates.

Use a repository checkout containing this report package and the recorded study inputs. If you already have that checkout, start at Step 2. Fresh-install validation is deferred; the current checks used the recorded scientific environment.

## 1. Obtain the code and saved study records

For a published checkout containing this report folder:

```sh
git clone https://github.com/sambitmukherjee/llm-network-bargaining.git
cd llm-network-bargaining
```

Run all subsequent commands from that repository root. The checkout needs `sprint_report/reproduction/run.py`, `src/`, the two study configs, the 160 compressed logs under `runs/minimum_study/` and `runs/own_links_arm/`, and the retained prediction artifacts. The [input manifest](provenance/input_manifest.csv) lists all 194 reused repository files and their hashes; the runner checks them before each stage. No additional dataset download is required when those tracked files are present.

The study-data revision is `ff692b507bf1192d07c1e0ddd39b7e7b14382f3a`. That revision predates the new report package: checking it out alone does not supply `sprint_report`. Use a revision containing both the report package and the recorded study inputs. The default workflow uses file fingerprints and saved headers; it does not require Git history.

## 2. Create a scientific Python environment

The recorded environment uses **Python 3.14.3**. The examples use a macOS/Linux shell and a `python3.14` executable:

```sh
python3.14 --version
python3.14 -m venv sprint_report/.venv
sprint_report/.venv/bin/python -m pip install --cache-dir sprint_report/.cache/pip -r sprint_report/requirements.txt
sprint_report/.venv/bin/python -m pip check
```

Use the environment's Python explicitly; shell activation is optional. [requirements.txt](requirements.txt) records the scientific package pins. Install normally with dependencies: the recorded pins are not a fully resolved lock file, and packages such as the SDK and Matplotlib need their transitive dependencies. Do not use `--no-deps` for this setup. Installation needs package-index access; the result calculations then run locally.

The runner adds the repository's `src/` directory to its import path. An editable install of the entire project, its development extras and its broader analysis dependencies is unnecessary for this results-only route. The submitted PDF, Pandoc, Node/MathJax, Poppler and vendored paper fonts are also outside this workflow. [environment.json](provenance/environment.json) records the current installation-validation status. Other Python/platform combinations have not yet been independently validated for this package.

## 3. Reproduce all retained outputs

```sh
sprint_report/.venv/bin/python -B sprint_report/reproduction/run.py all
```

The command checks the declared inputs, replays the 160 episodes, recomputes both outcome windows, generates the figures and tables, and verifies the completed outputs. It prints progress, including replay counts and the analysis window being processed. The exact and Monte Carlo calculations perform substantial resampling; let the command finish and check that it exits successfully.

The recorded successful run reports:

| Product | Expected result |
| --- | --- |
| Saved episode replay | 160/160 match |
| Scientific comparisons and independent null audits | 221 checks pass |
| Table outputs | All fifteen match their reviewed cells |
| Figures | All six pass coordinate/graph checks and export checks |
| Aggregate verification | 73 checks pass, covering forty output routes |

The script generates all bootstrap/null arrays afresh. Old stored draw arrays, reference plot images, original manuscript files, judge ledgers and the comprehensive `paper` archive are unnecessary. Re-running `all` replaces generated outputs under `sprint_report/results/`; the saved study logs and comparison inputs are read only.

## 4. Inspect the results

| Location under `sprint_report/` | What to inspect |
| --- | --- |
| `results/verification/receipt.json` | Aggregate pass/total counts, stage hashes, fifteen tables, six figures and `new_model_calls: false` |
| `results/verification/output_map.json` | All forty table, figure and narrative/context routes with generated artifacts |
| `results/data/section_6/` | Earnings, participation, received shares, H2 fits, hypothesis results and effect intervals |
| `results/data/appendices/` | H5 summaries, inference audits, histories, efficiency failures and theoretical allocations |
| `results/data/completed_links/` | Link frequencies and uniform-maximum-matching references |
| `results/tables/` | Main Tables 1–2, Tables C1–C8 and the five specification/teaching tables |
| `results/figures/` | Six regenerated PNG/SVG figures and numerical plotting coordinates |
| `results/protocol/` | Exact prompt/schema/request examples and condition/header seed checks |

The [code and output guide](reproduction/README.md) maps every paper table and figure to its filename. The [source output map](provenance/output_map.csv) is available before running the workflow. The historical `data/section_6/` name supplies the shortened paper's Results Section 5 and Appendix C.

Use a successful command exit together with the current receipt. If a run fails, a receipt left by an earlier run does not establish that the failed run completed. Stage receipts bind their outputs to the producing code and comparison inputs, and `verify` checks those hashes.

Generated plots, CSVs, draw archives, caches and receipts do not need to be committed. [files_for_reproducibility.md](files_for_reproducibility.md) and the [selection list](reproduction/release_files.txt) identify the source/input material retained for reproduction.

## Running a stage separately

Use the same environment and repository-root working directory:

```sh
sprint_report/.venv/bin/python -B sprint_report/reproduction/run.py replay
sprint_report/.venv/bin/python -B sprint_report/reproduction/run.py analyse
sprint_report/.venv/bin/python -B sprint_report/reproduction/run.py figures
sprint_report/.venv/bin/python -B sprint_report/reproduction/run.py tables
sprint_report/.venv/bin/python -B sprint_report/reproduction/run.py verify
```

`replay` and `analyse` can start from the declared repository inputs. `figures` needs analysis outputs. `tables` needs replay and analysis outputs. `verify` needs all preceding outputs. Use `all` for the first complete reproduction; running `verify` alone does not recompute estimates or replay episodes.

In a complete clone containing the historical objects, the optional additional check is:

```sh
sprint_report/.venv/bin/python -B sprint_report/reproduction/run.py verify --verify-git
```

It compares the retained file fingerprints with the historical pre-sprint commit and checks the recorded source/config/dependency diff. It uses local Git objects, makes no model calls and does not fetch history automatically. A missing historical object affects this optional check, not the default file/header verification.

## What the numerical comparisons preserve

- The primary outcome window is rounds **13–24**; rounds **13–23** are a sensitivity check on the same episodes.
- Earnings and participation include no-deal rounds. Conditional received shares use only deal rounds; undefined shares remain missing. Averages proceed from rounds within a node to equally weighted class members and then equally weighted episodes within a condition.
- The root analysis seed is **1**, with **2,000** bootstrap repetitions. Episode rows travel together within conditions. Original keyed streams, ordering and permutation batching are retained.
- H1 uses 1,024 exact sign patterns per constituent network; H4 uses 184,756 exact assignments. H3 and H5 use 200,000 and 100,000 Monte Carlo assignments. Ties use the original numerical tolerance and Monte Carlo p-values use the plus-one convention.
- The main Holm family is joint H1, H3, H4 and H5. The four H1 constituent tests have their separate secondary correction. H2 ranks prediction errors and produces no hypothesis-test p-value. Bootstrap intervals are marginal intervals.
- H2's four-reference overall comparison uses the same fifteen classes in seven networks: the pair is included and the triangle excluded. H5 instead weights each of its six eligible networks equally.

The [method specification](provenance/reproduction_spec.json) records these conventions. The [reference guide](reference/README.md) explains expected targets and declared teaching inputs. Empirical values are computed before comparison. The continuous-core and balance examples are theoretical calculations; matching a theoretical reference does not show that an agent calculated it.

Figure verification compares numerical coordinates and graph structure. Font rendering and vector-file metadata can vary across machines, so public reproduction does not require pixel-identical PNGs. The earlier migration audit compared the six images and all 88 draw arrays in the existing environment; those comparisons are historical implementation evidence.

## If something fails

| Symptom | Next step |
| --- | --- |
| `sprint_report/reproduction/run.py` is absent | Obtain a checkout containing the report package; the earlier study-data commit alone lacks it |
| `python3.14` is absent or has a different version | Set up the recorded Python environment before installing the pinned scientific packages |
| Import error or `pip check` reports missing dependencies | Confirm you used `sprint_report/.venv/bin/python`; install the requirements normally with dependency resolution |
| Input file/hash assertion fails | Compare the named path with `provenance/input_manifest.csv`; use the recorded study inputs and matching software/configs |
| A component stage cannot find generated files | Run `all`, or run its prerequisites in the order above |
| Producer/reference/artifact hash is stale | Regenerate the affected stage and downstream verification; `all` rebuilds the complete result set |
| Optional Git check cannot find a commit | Use a full clone with the historical objects, or use the default verification route |
| A fresh numerical comparison fails | Retain the traceback, Python/package versions and generated receipt files; compare them with the environment/method records |

The study's participant identifier and recorded replies are historical inputs. Re-running the experiment harness against a remote model would collect new evidence and need not reproduce those replies. The commands in this guide operate only on saved evidence. [study_provenance.json](provenance/study_provenance.json) records the pilot/study chronology and the limits of the historical version evidence; author recollections and literature priority are outside machine-verification claims.
