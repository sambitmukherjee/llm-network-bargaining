# Positional Advantage

**Positional Advantage: Network Structure and Bargaining Power among LLM Agents**  
Sambit Mukherjee · Independent Researcher

This folder contains the offline reproduction materials for the paper's results. The study uses copies of one LLM across eight exchange networks and two network-knowledge settings. The 160 study episodes were collected on 6 November 2026. The 2 November pilot informed the design; its observations do not enter these estimates.

## Reproduce the results

Follow the [step-by-step guide](REPRODUCIBILITY.md) for obtaining the checkout, setup, expected outputs and troubleshooting. The reference scientific environment uses Python 3.14.3. From a repository checkout containing this report folder:

```sh
python3.14 -m venv sprint_report/.venv
sprint_report/.venv/bin/python -m pip install --cache-dir sprint_report/.cache/pip -r sprint_report/requirements.txt
sprint_report/.venv/bin/python -m pip check
sprint_report/.venv/bin/python -B sprint_report/reproduction/run.py all
```

The pins describe the recorded environment; fresh-install validation is deferred. No editable package install or PDF toolchain is needed for this route.

## Find the materials

| Location | Contents |
| --- | --- |
| [Reproduction guide](REPRODUCIBILITY.md) | Workflow, current command, generated outputs and verification limits |
| [File inventory](files_for_reproducibility.md) | Exact publication scope, reused repository inputs and exclusions |
| [reproduction/](reproduction/README.md) | Runner, analysis, table/figure generators and verifiers |
| [data/protocol/](data/README.md) | Exact prompt examples, response schemas, hypotheses and resolved settings |
| [reference/](reference/README.md) | Compact expected results used to check fresh calculations |
| [provenance/](provenance/README.md) | Input fingerprints, method specification, output map and historical evidence |

The [selection list](reproduction/release_files.txt) defines the files for the results package. The study software, two configs, 160 saved episode logs and prediction artifacts are reused from their existing repository locations; see the [input manifest](provenance/input_manifest.csv).

Running the workflow generates fifteen tables, six figures, numerical summaries and a verification receipt under `results/`. It uses the saved records without model requests or API credentials. Generated outputs are excluded from the selection and can be rebuilt.

The PDF, manuscript, fonts, comprehensive research archive and local preparation history are outside this results package. The folder guides describe the selected files; additional local files are not automatically publication contents.
