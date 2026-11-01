# Phase 1 notes — 31 October 2026

Phase 1 implements the scaffold, network registry, graph analysis, theory,
prediction files, seed derivation, and experiment configs. The Phase 1 brief
defines the implementation requirements; `Project_Proposal_Latest.md` supplies
the project context and terminology. No later-phase components were built.

## Decisions

- Registry order follows the table in the brief, rather than alphabetical
  network IDs. Nodes keep their specified order. Edges, their endpoints, and
  node-class members are sorted. Classes are sorted by their first member.
- `Network` is a frozen dataclass; `graph()` always returns a fresh graph.
  Unknown IDs and neighbours raise `KeyError`. Graphs are connected, with
  distinct nodes, no loops, and no duplicate edges. Pie size defaults to 24.
- GraphMatcher automorphisms preserve a Boolean producer attribute. A producer
  may swap with the other producer, but never with a broker.
- Coalitions use integer masks: bit i corresponds to node i. Maximum matching
  uses a short recurrence: leave the first node unmatched, or match it with
  one available neighbour. Memoisation reuses smaller coalition results.
  Link games use the same matching recurrence on their selected links.
- `characteristic_function()` returns a cached, read-only mapping. Core and
  nucleolus calculations cache internal results but return fresh dictionaries.
  Public Shapley calculations return fresh dictionaries too.
- Exact Shapley sums use coalition-size weights and `math.fsum`. Sampling
  uses `numpy.random.default_rng(seed)` without symmetry averaging. Sample
  results retain the differences actually produced by sampled arrival orders.
  Reproducibility assumes the same dependency versions; the SHA-256 seed
  encoding itself is independent of Python, platform, and process hash seed.
- Auto thresholds are 16 nodes for Myerson and 16 links for position value.
  Default sample counts are 20,000 and 4,000, respectively, both with seed 0.
  `PositionValueResult` reports the chosen method; its sample count and seed
  are `None` for exact calculations.
- The nucleolus uses sequential LPs over all proper non-empty coalitions.
  A coalition is fixed only after an additional LP shows it is tight at
  every optimum of the current stage. Coalitions slack at the first optimum
  need no such check. Only independent equality rows are retained. This
  preserves the original algorithm's logic while reducing LP count.
- LPs use SciPy HiGHS. Infeasible core constraints return `None`; other solver
  failures raise an error. Small numerical zeros become positive `0.0`.
  Internal results are not rounded to the CSV's display precision.
- `nucleolus()` supports exchange games through 10 nodes by default, even if
  the core is empty. `balanced_outcome()` also requires a non-empty core.
  Both raise `ValueError` for broker networks. Broker balanced CSV fields are
  left empty without calling those exchange-specific functions.
- Repeated CLI tags select their union. Unknown tags raise `ValueError`.
  CSV numbers, including counts, use exactly six decimals as requested;
  integer formatting avoids losing integer precision. Booleans are lowercase
  `true`/`false`, and undefined entries are empty. The class `members` field
  uses the same `|` separator as the class label.
- Class rows first check each member's values, then average numerical values
  across the class. Exact comparisons use 1e-9; sampled comparisons use 0.05.
  A mismatch raises `ValueError`, even when Python assertions are disabled.
- Only metadata has a generation timestamp, in UTC. It records all thresholds,
  sample counts, seeds, covered networks, and package version. Git provenance
  describes the source checkout: a clean tree with HEAD gets its commit hash;
  a dirty tree or a folder without Git gets `null`. No Git repository was
  initialised for this phase, and no commits or pushes were made.
- Seeds hash UTF-8 canonical JSON containing a format marker, the parent
  integer, and an ordered list of string/integer labels. SHA-256 is reduced
  modulo 2**63. Types, order, and label boundaries are retained. As with any
  finite hash, collisions are theoretically possible; tests check all seeds
  actually used by the supplied configs.
- Configs use Pydantic v2 with unknown fields forbidden at every schema level.
  Empty model/network/knowledge/assignment collections are rejected. Prices
  must be finite and non-negative; token limits are positive;
  config seeds are non-negative, as required by NumPy generators.
- Phase 5 removed the unused `budget_usd` field. Configs containing it are
  now rejected; experiment costs are recorded without a spending cap.
- Model overrides may repeat a node with the same alias, but conflicting
  aliases are rejected. Defaults are replaced by explicit overrides. The
  `Condition.node_models` dictionary follows canonical node order and contains
  an alias for every node. Settings are Pydantic models; conditions are frozen
  dataclasses. Episode indices start at zero.
- The pilot is two configs: 24 full-map episodes plus 6 own-links episodes,
  for **30 total**, as specified by the Phase 1 brief's config table.
- Only the requested runtime dependencies and pytest were added. Setuptools
  is the packaging build dependency. `.gitignore` excludes the local virtual
  environment, caches, and generated packaging files, while retaining
  generated predictions for review and eventual version control.

## Main interfaces for later phases

All networks use canonical node IDs. Prompt-facing agent names are deliberately
outside this phase. Function annotations and docstrings in the source give the
complete types; the main interfaces are:

```python
# networks.py
Network(id, kind, nodes, edges, pie=24, tags=frozenset(),
        description="", producers=None)
get_network(id: str) -> Network
list_networks(tag: str | None = None) -> tuple[Network, ...]
# Network.graph(), Network.neighbours(node), Network.n_links

# structure.py
node_classes(net: Network) -> tuple[tuple[str, ...], ...]
class_label(members: tuple[str, ...]) -> str
class_of(net: Network) -> dict[str, str]
max_deals(net: Network) -> int
excludable_nodes(net: Network) -> frozenset[str]
degree(net: Network) -> dict[str, int]
betweenness(net: Network) -> dict[str, float]

# theory.py; Method is Literal["auto", "exact", "sample"]
characteristic_function(net: Network) -> Mapping[frozenset[str], float]
shapley_value(players, value: Callable[[int], float], method="exact",
              n_samples=20000, seed=0) -> dict
myerson_value(net: Network, method="auto", n_samples=20000, seed=0) -> dict[str, float]
position_value(net: Network, method="auto", n_samples=4000, seed=0) -> PositionValueResult
core_bounds(net: Network) -> dict[str, tuple[float, float]] | None
in_core(net: Network, allocation: Mapping[str, float], tol=1e-9) -> bool
nucleolus(net: Network, max_nodes=10) -> dict[str, float] | None
balanced_outcome(net: Network) -> dict[str, float] | None

# seeds.py
derive_seed(parent: int, *labels: str | int) -> int
make_rng(seed: int) -> numpy.random.Generator

# config.py
load_config(path: str | Path) -> ExperimentConfig
load_configs(paths: list[str | Path]) -> list[ExperimentConfig]
expand_conditions(config: ExperimentConfig) -> list[Condition]
total_episodes(config: ExperimentConfig) -> int

# predictions.py
write_predictions(out: str | Path, tags: Sequence[str] | None = None) -> None
```

`PositionValueResult` fields: `values`, `method`, `n_samples`, `seed`.

`Condition` fields: `key`, `config_name`, `network_id`, `knowledge_setting`,
`assignment_name`, `settings`, `node_models`, `condition_seed`, `episode_seeds`.

## Validation and deviations

- Editable installation in a fresh Python 3.14.3 virtual environment succeeded
  using **only locally cached wheels**. Pip used `PIP_NO_INDEX=1` and an offline
  wheel directory, including for isolated build dependencies. No network or
  model calls were made. This offline installation setting changes no package
  dependencies or normal installation instructions.
- The environment uses NetworkX 3.6.1, NumPy 2.5.0, SciPy 1.18.0, Pydantic
  2.13.4, PyYAML 6.0.3, and pytest 9.1.1.
- Default suite: `134 passed, 1 deselected in 7.67s`.
- Slow suite: `1 passed, 134 deselected in 0.46s`.
- All supplied numerical references reproduced, including every sweep and
  broker network and the no-exclusion control's unique core allocation.
- Two separate CLI processes produced byte-identical CSVs. The CLI tests also
  checked columns, row order, counts, formatting, undefined fields, tag
  selection, and rejection of inconsistent class values.
- The original script's SHA-256 is still
  `71a6d6d81954ef303cdd6f0a345afe9a961b56a17e63ea20d81431ec833bf0ec`.

No changes to the specified mathematical references or dependencies were needed.
No unresolved questions remain for Phase 1.
