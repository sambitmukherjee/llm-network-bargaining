# Protocol inputs and examples

[Package index](../README.md) · [Workflow guide](../REPRODUCIBILITY.md)

The eight files in `protocol/` preserve the task definitions and comparison examples used by the reproduction code. The saved empirical episode records remain in the repository's two study `runs/` roots.

| File | Contents |
| --- | --- |
| [hypotheses.json](protocol/hypotheses.json) | The five questions/comparisons in main Table 1, including H5 and H2's no-p-value clarification |
| [action_schema.json](protocol/action_schema.json) | Structured response schema for bargaining decisions |
| [quiz_schema.json](protocol/quiz_schema.json) | Structured response schema for the rules quiz |
| [early_full_map.txt](protocol/early_full_map.txt), [early_own_links.txt](protocol/early_own_links.txt) | Early-game prompt examples on the stem under the two knowledge settings |
| [late_own_links.txt](protocol/late_own_links.txt) | Scripted late-game three-node-line prompt with accumulated own-links history |
| [quiz_full_map.txt](protocol/quiz_full_map.txt) | Example full-map rules quiz |
| [verified_specification.json](protocol/verified_specification.json) | Resolved configs, conditions/seeds, request settings and declared scripted examples |

[tables.py](../reproduction/tables.py) reconstructs the prompts and schemas using the tracked engine/renderers, resolves both study configs and checks the episode seeds against the saved headers. [late_prompt.py](../reproduction/late_prompt.py) generates the late-game example. Those examples are scripted stimuli, distinct from observations used to estimate study outcomes.

The authoritative study YAML files remain `configs/minimum_study.yaml` and `configs/own_links_arm.yaml` at the repository root. The [input manifest](../provenance/input_manifest.csv) records their hashes. Fresh protocol outputs are written to `results/protocol/`; the source data in `protocol/` are preserved for comparison.
