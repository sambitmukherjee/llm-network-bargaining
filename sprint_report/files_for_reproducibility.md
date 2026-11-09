# Reproducibility files for Positional Advantage

This inventory covers the source and comparison inputs needed to reproduce the results retained in the eight-page main paper and its appendices. The [selection list](reproduction/release_files.txt) defines exactly **42 files under `sprint_report/`**. The repository-root README provides the entry point; experimental software and saved study records are reused from their existing repository locations.

## Selected report structure

| Location | Files | Contents |
| --- | ---: | --- |
| Report root | 5 | README, reproduction guide, this inventory, scientific requirements and ignore policy |
| [reproduction/](reproduction/README.md) | 17 | Fifteen Python files, code/output guide and exact selection list |
| [data/](data/README.md) | 9 | Protocol guide and eight exact protocol/comparison inputs |
| [reference/](reference/README.md) | 4 | Guide and three compact comparison specifications |
| [provenance/](provenance/README.md) | 7 | Guide and six input/method/output/environment/origin records |

```text
sprint_report/
  README.md
  REPRODUCIBILITY.md
  files_for_reproducibility.md
  requirements.txt
  .gitignore
  reproduction/
    README.md; release_files.txt
    context.py; run.py; replay_saved.py
    selected_analysis.py; tables.py; figures.py
    verification.py; provenance.py; late_prompt.py
    main_figures.py; draw_matching.py; draw_networks.py
    adapted/
      statistical_helpers.py
      draw_knowledge.py; draw_outside_options.py
  data/
    README.md
    protocol/
      hypotheses.json; verified_specification.json
      action_schema.json; quiz_schema.json
      early_full_map.txt; early_own_links.txt
      late_own_links.txt; quiz_full_map.txt
  reference/
    README.md
    claims.json; tables.json; figure_values.json
  provenance/
    README.md
    input_manifest.csv; output_map.csv
    reproduction_spec.json; environment.json
    study_provenance.json; helper_origins.json
```

## Reused repository inputs

The [194-file input manifest](provenance/input_manifest.csv) gives exact paths, sizes and SHA-256 hashes. These files remain at their original repository-relative paths:

| Input | Files | Purpose |
| --- | ---: | --- |
| Selected `src/llm_network_bargaining/` modules | 28 | Engine, replay, protocol, configuration, theory, metrics, inference and deterministic random streams |
| `pyproject.toml` | 1 | Retained dependency/version fingerprint |
| `configs/minimum_study.yaml`, `configs/own_links_arm.yaml` | 2 | The two sprint-study arms |
| Compressed logs in their two `runs/` roots | 160 | Ten completed episodes for each network/knowledge condition |
| `predictions/class_predictions.csv`, `predictions/node_predictions.csv`, `predictions/metadata.json` | 3 | Retained predictions and version evidence |

The study-data revision is `ff692b507bf1192d07c1e0ddd39b7e7b14382f3a`. It predates the report package; reproduction needs a checkout containing both this package and the recorded study inputs. No additional experimental observations are required. The runner does not read pilot episodes, run-summary JSON files, the note-judge config or judge ledgers. Existing historical repository files are retained separately from the report's runtime selection.

## Reproduction and generated outputs

Follow [REPRODUCIBILITY.md](REPRODUCIBILITY.md) to prepare the scientific environment. From the repository root:

```sh
sprint_report/.venv/bin/python -B sprint_report/reproduction/run.py all
```

The runner replays all 160 episodes, recomputes both retained outcome windows, exports fifteen tables and six figures, and checks the outputs. It uses saved replies without model calls or API credentials. The [code/output guide](reproduction/README.md) maps every paper table and figure to its generated filename; the [output map](provenance/output_map.csv) covers forty table, figure and claim/context routes.

Generated numerical CSVs, bootstrap/null arrays, protocol examples, plots and receipts go under `results/`. The aggregate receipt is `results/verification/receipt.json`, with the resolved output map beside it. Generated files and caches are excluded from the source selection and can be rebuilt.

## Comparison inputs and scientific boundaries

The compact JSON files contain reviewed comparison targets, presentation specifications and explicitly hypothetical teaching inputs. Empirical values are computed from the saved logs before comparison. Expected table cells do not supply generated empirical estimates. Historical source paths/hashes in attribution records do not create reads of the original research archive.

The selected helpers preserve the original outcome windows, class/episode weighting, undefined-share treatment, root seed 1, 2,000 bootstrap repetitions, exact/Monte Carlo assignment counts, keyed streams, tail tolerance, plus-one convention and both Holm families. The [method specification](provenance/reproduction_spec.json) records these conventions.

Existing-environment validation reproduced the 160 episodes, 221 scientific comparisons/null audits, all fifteen tables and all six figures, followed by 73 aggregate checks. The earlier migration audit also compared all 88 regenerated draw arrays and six images with preserved evidence. Public reproduction checks fresh coordinates, graph structures and numerical results without requiring the old reference images or stored arrays.

**Fresh installation and clean-copy execution remain deferred at the author's request.** The [environment record](provenance/environment.json) states that limitation. The requirements record reference pins and are installed with normal dependency resolution; a complete independently tested installation lock is not claimed.

## Exclusions

The exact-selection ignore policy keeps generated outputs, manuscript sources, the submitted PDF, font assets, broad analysis write-ups, old draw archives, historical ZIPs/manifests, local preparation records, environments and caches outside the report's tracked source set. The original `paper` archive and private proposal/prompt folders remain ignored by the repository-root rules.

The PDF and manuscript are separate submission artifacts. Result reproduction needs neither those files nor the paper's PDF toolchain. Directory-wide inclusion is inappropriate if ignore rules are bypassed: use the selection list to review additions, and update both that list and the exact ignore policy when intentionally extending the package.
