# Phase 2 notes — 31 October 2026

Phase 2 adds the exchange-game engine, agent observations, scripted bots, and
the small simulation CLI. No prompt builder, parser, model client, file logger,
or later-phase runner was added. No dependencies were added.

## Starting checks

- `preexisting/predict.py` matched the required SHA-256 before any edits.
- The Phase 1 baseline passed: `134 passed, 1 deselected in 7.57s`.
- The implementation uses the actual Phase 1 `Network`, registry, structural
  helpers, `derive_seed`, and `make_rng` interfaces.

## Decisions and implementation

- `Action` contains game content only. `Decision` adds private metadata, and
  `Agent.act(observation)` is the common bot/model interface. Shared `validate`
  checks requests in exactly the brief's order. Integers are accepted for
  offers, but booleans and all floats are rejected. Pass and accept ignore
  the arguments specified as unused in the brief.
- `Episode` is a small state machine implemented with a private generator.
  Each `next_turn()` advances bookkeeping until a decision is needed. It
  returns the same pending object until `submit()` consumes that decision.
  Finish bookkeeping is also driven by `next_turn()`, including phases where
  everyone is done, forced passes, round ends, and the episode end.
- The turn-order generator is local to each episode. It draws once per phase,
  regardless of the agents' play. Bot generators are independently derived by
  node. There is no shared mutable engine or bot state between episodes.
- A maker's open offer is indexed by its node. Offers have frozen records;
  the engine replaces a record when its status changes rather than changing
  the record itself. An offer's position in the internal list is its ID.
- A closing deal gives maker-related voiding priority over recipient-related
  voiding, including crossing offers. Status events are emitted in offer-ID
  order after the deal event, even when that puts a voided offer before the
  accepted offer. Every requested turn event precedes its consequences.
- Forced passes are valid, automatic records with no request, reason, or
  agent metadata. Done agents produce no further records that round.
- Observations are assembled from allowed fields, without exposing internal
  records wholesale. Earlier observations retain the offer statuses they had
  when created. Finished-round histories are cached as immutable snapshots;
  all past rounds are included in every later observation.
- Own notes are removed from `MyTurn.requested` with a fresh `Action` whose
  `note` is `None`. Decision metadata is never added to an observation. Offers
  have no visible IDs. Neighbour deals have no payoff fields, and a viewer's
  own partner appears only in `MyDeal`, as specified.
- Dataclasses for observations, requests, pending turns, and records are
  frozen, and ordered collections inside observations are tuples. Result
  points, totals, opaque metadata, and event dictionaries retain the mapping
  forms required by the brief. Frozen dataclasses do not recursively freeze
  arbitrary values inside malformed `Action.my_points` or private metadata.
- Metadata is deep-copied before recording, without filtering its contents.
  It must encode as strict JSON, so non-finite numbers and unsupported objects
  raise `TypeError`. A rejected metadata value leaves the pending turn intact
  and makes no partial game changes. Automatic records use empty metadata.
- Requested-action fields that cannot encode as JSON are replaced by `repr`
  in events and `EpisodeResult.to_dict()`. Raw action records are retained.
  The result conversion also turns tuples into lists, including any tuples
  inside metadata, so its output round-trips through JSON.
- Normal game content and the supplied bots have deterministic JSON results.
  The mandated `repr` fallback for an arbitrary non-JSON Python object may
  include that object's address; separate objects with address-based reprs
  are not reproducible inputs. No fallback is used for metadata errors.
- Bot learners recompute from complete local history, storing only their own
  RNG state. Aspiration counts distinct makers in every received offer,
  regardless of final offer status. It never reads `network_edges`.
- `RandomBot` uses the six invalid choices and the fixed point values from
  the brief, and otherwise samples uniformly among currently legal kinds,
  targets, and integer splits. All bots identify themselves in metadata;
  `ScriptedBot` uses `{"bot": "scripted"}`.
- The engine supports any `n_phases >= 2`, with the last accept-only. Configs
  remain unchanged and still require three phases. Bad injected orders raise
  `ValueError`, including missing, repeated, or non-node entries.
- The CLI averages members within each class for each episode, then averages
  those episode means. Its SD is the sample SD across episode means (`ddof=1`),
  or zero for a single episode. The second half starts at zero-based index
  `n_rounds // 2`, including the only round when `n_rounds=1`. Earnings and
  benchmarks print to six decimals. An undefined balanced outcome is blank.
- CLI episode seeds use exactly `derive_seed(seed, "simulate", network_id, i)`.
  It prints a deterministic context line, class table, and deals-per-round
  line. No result files are written.
- No Phase 1 source interfaces, schemas, tests, reference numbers, or
  prediction files were changed. The README adds engine/bot usage and marks
  Phase 2 as work written before the research sprint.

## Public interfaces

```python
# actions.py
Action(kind: str, to: str | None = None, my_points: Any = None,
       note: str | None = None)
Decision(action: Action | None, meta: Mapping[str, Any] = {})
Agent.act(observation: Observation) -> Decision
validate(action: Action | None, observation: Observation) -> ReasonCode | None
```

`AppliedAction` is `Literal["offer", "accept", "pass"]`. `ReasonCode` contains
the seven reason strings specified in the Phase 2 brief. `Decision.meta` uses
a default factory, so decisions do not share a mutable default dictionary.

`observation.py` defines the exact frozen dataclasses and fields from the brief:
`OfferView`, `NeighbourDeal`, `MyTurn`, `MyDeal`, `CurrentRound`, `PastRound`,
`LegalActions`, and `Observation`. `OfferStatus` has the six specified values.

```python
Observation.open_offers_to_me -> tuple[OfferView, ...]  # property
Observation.my_open_offer -> OfferView | None          # property

# engine.py
Episode(network: Network, *, knowledge: KnowledgeSetting, n_rounds: int,
        episode_seed: int, n_phases: int = 3,
        turn_order: Callable[[int, int], Sequence[str]] | None = None)
Episode.next_turn() -> PendingTurn | None
Episode.submit(decision: Decision) -> TurnRecord
Episode.finished -> bool  # property
Episode.result() -> EpisodeResult
run_episode(network: Network, agents: Mapping[str, Agent], *,
            knowledge: KnowledgeSetting, n_rounds: int, episode_seed: int,
            n_phases: int = 3, turn_order: TurnOrder | None = None) -> EpisodeResult
EpisodeResult.to_dict() -> dict[str, Any]

# bots.py
PassBot()
EqualSplitBot()
AspirationBot(rng: numpy.random.Generator, *, start=12, step=1,
              floor=1, ceiling=23, slack=3)
RandomBot(rng: numpy.random.Generator, *, p_invalid=0.1)
ScriptedBot(script: Mapping[tuple[int, int], Action | None])
make_bot(name: str, *, node: str, episode_seed: int, **params) -> Agent
# Each bot: act(observation: Observation) -> Decision

# simulate.py
main(argv: Sequence[str] | None = None) -> None
```

`PendingTurn`, `OfferRecord`, `DealRecord`, `TurnRecord`, and `EpisodeResult`
use the exact field names in the brief. `TurnOrder` is an alias for the
injected ordering callback. Only `pending.observation`, not the enclosing
pending turn or the engine, is passed to an agent.

## Verification

- Default suite: `267 passed, 1 deselected in 14.93s`.
- Slow suite: `1 passed, 267 deselected in 0.62s`.
- All S1–S8 scenarios passed, including S3b and both knowledge settings where
  applicable. Tests also cover the exact observation schemas, validation
  precedence, metadata isolation and rejection, note removal, event order,
  immutable snapshots, forced passes, independent threaded episodes, and
  complete deterministic JSON results.
- The required fuzz run covered 16 exchange networks × 20 seeds × 2 knowledge
  settings = **640 episodes**, each of 12 rounds. Matching, payoffs, final
  statuses, no-leak properties, and the absence of turns after a deal were
  checked throughout. Invalid requests occurred and had reason codes.
- All aspiration thresholds passed unchanged, with the required ten seeds
  per network. `line5` and `stem` points were identical across knowledge
  settings for every required seed. Equal-split checks passed on all exchange
  networks at five seeds each.
- A separately timed 24-round `sweep3` random-bot episode took **0.0182 s** and
  produced 508 turn records, comfortably below the two-second limit.
- CLI subprocess tests confirmed class rows, byte-identical stdout, and no
  result files. Both required demonstration commands ran successfully.
- No network access, model calls, commits, or pushes were made.
- The original script and all three Phase 1 prediction files matched their
  starting SHA-256 hashes after implementation. Phase 1 reference tests and
  source modules are unchanged.

The required demonstration outputs, with CLI defaults, were:

```text
network=star3 bot=aspiration knowledge=full_map episodes=10 rounds=24 seed=1
node_class mean std equal_split myerson position_value balanced
H 22.383333 0.351803 12.000000 18.000000 12.000000 24.000000
L1|L2|L3 0.538889 0.117268 12.000000 2.000000 4.000000 0.000000
mean_deals_per_round 1.000000 / 1

network=line4 bot=aspiration knowledge=full_map episodes=10 rounds=24 seed=1
node_class mean std equal_split myerson position_value balanced
A|D 10.275000 0.795483 12.000000 10.000000 10.000000 8.000000
B|C 13.225000 0.147248 12.000000 14.000000 14.000000 16.000000
mean_deals_per_round 1.958333 / 2
```

No unresolved discrepancies, changed thresholds, or deviations from the
requested scope remain. Phase 3 has not started.
