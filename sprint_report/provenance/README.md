# Inputs, methods and provenance

[Package index](../README.md) · [Workflow guide](../REPRODUCIBILITY.md)

The results package selects the six records below. Other historical phase folders present in a local working copy are excluded from that selection.

| File | Use |
| --- | --- |
| [input_manifest.csv](input_manifest.csv) | Exact paths, sizes and SHA-256 hashes for 194 reused repository inputs: 28 source modules, one dependency specification, two study configs, 160 logs and three prediction/provenance artifacts |
| [output_map.csv](output_map.csv) | All fifteen tables, six figures and nineteen retained narrative/context groups, with their inputs, producers and output locations |
| [reproduction_spec.json](reproduction_spec.json) | Outcome windows, weights, seed conventions, bootstrap/permutation counts, tail rules and the two Holm families |
| [environment.json](environment.json) | Recorded scientific environment and fresh-installation validation status |
| [study_provenance.json](study_provenance.json) | Retained study chronology, six historical file fingerprints and qualifications about the recorded dirty-tree state |
| [helper_origins.json](helper_origins.json) | Origins of copied/adapted statistical, drawing and prompt helpers |

[provenance.py](../reproduction/provenance.py) checks retained fingerprints and dates/config hashes from the study headers; a full clone can additionally check the historical Git objects. Author recollections and literature priority remain outside machine-verification claims.

[verification.py](../reproduction/verification.py) writes the current receipt and resolved output map under `results/verification/`. Generated receipts are evidence from a particular local run and are excluded from the publication selection. Historical verification counts and manifests from the earlier paper-building workflow do not describe the current results-only route.
