# LLM network bargaining

This project studies how network placement affects bargaining among copies of the same LLM. Agents bargain over permitted links, each agreement divides 24 points, and an agent can complete at most one deal per round. The paper is **Positional Advantage: Network Structure and Bargaining Power among LLM Agents**, by Sambit Mukherjee, Independent Researcher.

Start with the [results package](sprint_report/README.md) and its [step-by-step reproduction guide](sprint_report/REPRODUCIBILITY.md). The saved-evidence workflow regenerates the fifteen tables and six figures retained in the shortened paper and appendices. It needs no model calls or API credentials.

## Reproduce the paper's results

Use a checkout containing `sprint_report/` and the saved study records. From the repository root, with the recorded Python 3.14.3 environment available:

```sh
python3.14 -m venv sprint_report/.venv
sprint_report/.venv/bin/python -m pip install --cache-dir sprint_report/.cache/pip -r sprint_report/requirements.txt
sprint_report/.venv/bin/python -m pip check
sprint_report/.venv/bin/python -B sprint_report/reproduction/run.py all
```

The [full guide](sprint_report/REPRODUCIBILITY.md) covers obtaining the checkout, setup, stage prerequisites, expected outputs, troubleshooting and validation limits. The dependency pins record the reference scientific environment; independent installation validation has been deferred.

The command checks 194 declared repository inputs, replays all 160 study episodes, recomputes both outcome windows, regenerates the figures/tables and verifies the results. A successful recorded run has 221 scientific checks and 73 aggregate verification checks. Inspect `sprint_report/results/verification/receipt.json` after a successful command exit.

Generated numerical summaries are under `sprint_report/results/data/`, tables under `results/tables/` and figures under `results/figures/`. The generated `results/verification/output_map.json` connects all forty retained output/context routes to their artifacts. Those paths are relative to `sprint_report/`; generated files are rebuilt locally rather than included as frozen copies.

## Study scope and chronology

| Material | Role |
| --- | --- |
| Experimental harness, prompts and theory tools | Developed before the sprint |
| 2 November 2026 pilot | Thirty episodes across `pilot_full_map.yaml` and `pilot_own_links.yaml`; informed the horizon and analysis workflow |
| 6 November 2026 study | 160 episodes across `minimum_study.yaml` and `own_links_arm.yaml`; the sprint's empirical evidence |
| Retained analysis | Eight networks, two knowledge settings, ten episodes per condition, 24 rounds per episode |

The two study arms display either the full network map or only an agent's own links. Primary estimates use rounds 13–24; rounds 13–23 provide a sensitivity check on the same episodes. Pilot observations are excluded from the study estimates. H2 compares numerical benchmark fit; H1, H3, H4 and H5 retain their original test/correction procedures. The [method record](sprint_report/provenance/reproduction_spec.json) gives the exact conventions.

The study-data revision is `ff692b507bf1192d07c1e0ddd39b7e7b14382f3a`; it predates the report package. A reproduction checkout needs the report files as well as the recorded study inputs. [Study provenance](sprint_report/provenance/study_provenance.json) records dated headers, retained version fingerprints, the logged dirty-tree qualification and the limits of author-account evidence.

## Find code, inputs and outputs

| Location | Purpose |
| --- | --- |
| `src/llm_network_bargaining/` | Experimental engine, protocol/renderers, configuration, replay, theory and broader analysis tools |
| `configs/minimum_study.yaml`, `configs/own_links_arm.yaml` | The two retained study arms |
| `runs/minimum_study/`, `runs/own_links_arm/` | All 160 compressed study episode logs |
| `predictions/` | Recorded theoretical predictions and metadata |
| [Reproduction code guide](sprint_report/reproduction/README.md) | Entry point, selected producers and paper-item filenames |
| [Protocol guide](sprint_report/data/README.md) | Exact stimulus examples, schemas, hypotheses and resolved settings |
| [Comparison reference guide](sprint_report/reference/README.md) | Compact targets used after fresh computation |
| [Provenance guide](sprint_report/provenance/README.md) | Input fingerprints, methods, output map and environment record |
| [File inventory](sprint_report/files_for_reproducibility.md) | The selected report files, reused inputs and exclusions |

The results package excludes the submitted PDF, manuscript, fonts, broad raw write-ups, old draw archives, caches and preparation history. The comprehensive `paper/` archive is outside the selected reproduction route. No additional empirical observations need to be downloaded beyond the retained repository inputs.

## Broader software and development

The repository also retains a general experiment runner, simulations, theory generation, broader reports and private-note coding tools. These support extensions beyond the shortened paper. The note-coding config currently selects **`judge-v5`**; the results-only paper reproduction route does not use judge labels or ledgers. Broader analysis/report defaults are not the paper-specific reproduction command above.

For development of the full package, its existing editable installation route is:

```sh
python3.14 -m venv sprint_report/.venv-dev
sprint_report/.venv-dev/bin/python -m pip install --cache-dir sprint_report/.cache/pip -e ".[dev]"
sprint_report/.venv-dev/bin/python -m pytest
```

The package metadata requires Python 3.11 or newer; the paper's recorded scientific environment uses 3.14.3. The development installation includes broader dependencies and tests, while the results-only guide uses the narrower scientific requirements. Use the module CLIs' `--help` output when extending the harness. Collecting new remote-model episodes requires a separate decision and produces new evidence; it is not part of saved-evidence reproduction.
