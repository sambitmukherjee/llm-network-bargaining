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

Phase 3 adds display names, the versioned prompt renderer, the response schema
and parser, and `JsonBotAdapter` for offline checks through the language layer.
Review the nine scripted prompt examples with:

```sh
python -m llm_network_bargaining.prompts examples --out docs/prompt_examples.md
```

The review copy is committed at `docs/prompt_examples.md`, as an explicit
exception to the prompt-file ignore rules. Expected stimuli are also retained
as test fixtures in `tests/golden/`. Prompt history keeps
every offer and has no word limit. The renderer uses only the supplied
observation; it never consults the network registry to infer hidden information.

Model IDs and token prices use the API facts supplied in the Phase 4 brief,
checked against OpenAI's model pages on 1 November 2026. Implementation decisions and public interfaces
are recorded in [the Phase 1 notes](docs/phase1_notes.md) and
[the Phase 2 notes](docs/phase2_notes.md), with language-layer details in
[the Phase 3 notes](docs/phase3_notes.md).

## Model calls and the smoke test

Phase 4 adds an async Chat Completions client, `LLMAgent`, token cost tracking,
and a separate three-question rules quiz. `FakeChatClient` and `BotResponder`
exercise the same agent path entirely offline. Tests block both network access
and construction of OpenAI SDK clients. The SDK disables its own retries so
the harness can record each attempt, including costs from unusable replies.
Caching is off by default; every request explicitly sends `store=False` and
`reasoning_effort="none"` unless the config changes the reasoning setting.

Start by inspecting the four smoke requests without a key or network access:

```sh
python -m llm_network_bargaining.smoke --config configs/minimum_study.yaml --model terra --dry-run
```

For live calls, set `OPENAI_API_KEY` in your terminal environment. In bash or
zsh, these commands read it with hidden input, then export it to Python:

```sh
read -r -s OPENAI_API_KEY
export OPENAI_API_KEY
```

Never put the key in a config, source file, notebook or commit. The client reads
the environment only on its first request. After reviewing the dry run, run:

```sh
python -m llm_network_bargaining.smoke --config configs/minimum_study.yaml --model terra --live
```

The live mode sends a short turn, the same long turn twice, and a rules quiz.
It reports parsing, model identity, reasoning tokens and cache behavior, with
usage and total cost. Dry-run costs estimate input at four characters per token;
output cost is additional. Only live mode verifies actual API behavior.

Use `await agent.aact(observation)` and `await run_rules_quiz(...)` in one event
loop with a shared client; close it with `await client.aclose()`. `act()` is a
synchronous convenience and refuses to run inside an existing event loop.
API/model failures raise exceptions rather than becoming game passes. The quiz
does not enter subsequent turn messages. Phase 5 will add experiment execution
and persistent logs. See [the Phase 4 notes](docs/phase4_notes.md) for interfaces
and implementation decisions.

## Pre-existing work

`preexisting/predict.py` and this harness were written before the Apart Research
Swarm Alignment sprint (6–8 November 2026). Phase 1 of the harness was written
on **31 October 2026**. The original script is preserved unchanged; the package
ports its mathematics without importing it.
Phase 2, including the engine, observations, and scripted bots, was also written
on **31 October 2026**, before the sprint.
Phase 3, including the language layer and golden prompt fixtures, was written
on **1 November 2026**, before the sprint.
Phase 4, including the model client, LLM agent, costs, quiz and smoke CLI, was
also written on **1 November 2026**, before the sprint.
