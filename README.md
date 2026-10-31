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

Model IDs and token prices in the examples are placeholders supplied in the
brief. Check them before Phase 4. Implementation decisions and public interfaces
are recorded in [the Phase 1 notes](docs/phase1_notes.md) and
[the Phase 2 notes](docs/phase2_notes.md).

## Pre-existing work

`preexisting/predict.py` and this harness were written before the Apart Research
Swarm Alignment sprint (6–8 November 2026). Phase 1 of the harness was written
on **31 October 2026**. The original script is preserved unchanged; the package
ports its mathematics without importing it.
Phase 2, including the engine, observations, and scripted bots, was also written
on **31 October 2026**, before the sprint.
