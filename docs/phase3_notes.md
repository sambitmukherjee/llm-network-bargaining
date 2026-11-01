# Phase 3 notes — 1 November 2026

Phase 3 adds display-name assignment, the fixed v1 prompt renderer, the
structured-output schema and parser, and an offline JSON bot adapter. The
implementation follows `phase3_prompt_updated.md` and the definitive proposal.
No API client, retries, cost tracking, file logger, or Phase 4 work was added.

## Starting state

- The earlier-phase baseline passed before edits:
  `267 passed, 1 deselected in 15.23s`.
- The original script matched its required SHA-256. All three Phase 1
  prediction files were also hashed before implementation and checked after.
- The existing observation and engine interfaces were read and used without
  modification. No earlier source module, schema, or test was changed.

## Clarified name validation

The user explicitly resolved the original brief's name-coverage ambiguity:

- `assign_names(network, ...)` guarantees full coverage by assigning a name
  to every node of the supplied network, in its canonical node order.
- `render_prompt` requires names only for nodes mentioned by the observation:
  the viewer and all neighbours; all full-map edge endpoints; all makers and
  recipients of current or historical offers; all neighbours and non-hidden
  partners in neighbour-deal records; and every partner in a past own deal.
  It does not examine raw requested-action targets, which may be invalid and
  must not be echoed into the prompt.
- A local observation can be rendered with only a partial roster. It is not
  an error to omit nodes the observation never mentions.
- `parse_reply` checks name uniqueness, not coverage. It has no network or
  observation from which to recover a complete roster. A known display name
  for a non-neighbour maps to that node; shared engine validation then rejects
  the offer as `not_a_neighbour`.
- Both functions reject duplicate display names using `str.casefold()`.
  No network-registry inference is used for these checks.
- Tests explicitly cover a missing visible neighbour, an omitted invisible
  node, case-insensitive duplicates in both functions, full-map endpoints,
  and all other categories of explicit history references.

## Rendering decisions

- The default 24-name pool and exact seeded `choice(..., replace=False)`
  sequence are those in the updated brief. Custom pools are checked for
  duplicate names and names that equal this network's node IDs.
- The renderer is a pure function. A prompt is one user message with no
  system message, no trailing newline, en dashes in links, straight quotes,
  and no hard wraps inside sentences. V1 rejects other versions and any phase
  count other than three.
- Neighbours, normalised map links, neighbour deals, and lists of names are
  sorted by display name. Offers retain the order they were made. This avoids
  systematically favouring the first canonical node in a list.
- Every history offer is retained, including replaced and unsuccessful ones.
  There is no history word limit. The separate private-note limit remains a
  diagnostic at 30 words; long notes are not truncated.
- Past rounds show offers, points, and neighbour outcomes in the brief's
  specified order. A local `mentioned` set prevents repeating neighbour deals
  already described in a lapsed-offer outcome. Shared-neighbour deals appear
  once, with the alphabetically earlier neighbour named first.
- Current-round lines are grouped by phase and report each offer's current
  status. They never invent an event order within a phase. Invalid actions
  use the fixed generic reason text, without echoing raw values, IDs, notes,
  or metadata. Forced passes are omitted from current-round narration.
- Only fields already present in the observation determine visible partners.
  The renderer does not reconstruct hidden partners from the name mapping
  or from graph structure.
- Helper functions isolate sentence joining, offer outcomes, history lines,
  current-round lines, and observation-name checks. Fixed stimulus wording
  remains literal so it can be compared directly with the brief.

## Parser and adapter decisions

- `response_format()` returns a fresh dictionary exactly matching section 4.7.
  It restricts output format, leaving recipient and payoff legality to the
  existing engine validator.
- Caller name-mapping errors raise `ValueError`. Reply errors instead return
  `ParseResult(action=None, error=..., details=...)`. Non-empty refusals take
  precedence over empty or malformed content.
- Wrapped Markdown fences are removed only when they enclose the complete
  reply. Plain and `json` fences are supported, including uppercase `JSON`.
  Text outside a fence is not silently salvaged.
- Unknown recipients use `"?" + str(raw)`. Case/whitespace normalisation is
  recorded in `to_raw` when it changes an otherwise recognised name. Intentional
  null recipients remain `None` without a `to_raw` entry.
- Action kinds are normalised only when strings. Point values remain unchanged
  for engine validation. Missing fields are listed in schema order; extra
  fields are ignored and listed in reply order.
- Notes remain unchanged when strings. Other note types become `None`.
  `note_words` and `note_over_limit` are always set for a parsed action.
- The inverse emits compact JSON in `action, to, my_points, note` order. As the
  brief requires, absent notes become empty strings, so an action with
  `note=None` returns from this round trip with `note=""`. That normalisation
  has no effect on game behaviour. No action becomes an empty reply.
- `JsonBotAdapter` renders every asked turn, then encodes and parses the bot's
  decision. It preserves bot metadata and adds only `reply`, `prompt_chars`,
  and `parse_error`. It does not call models or write logs.

## Examples, CLI, and local files

- The nine golden files were copied verbatim from Appendix A, with no trailing
  newline. No expected text was changed to fit the renderer. All nine matched
  on the first replay/render comparison.
- One additional private module, `_prompt_examples.py`, holds the scripted
  `Scenario` helper and replay inputs. It is shared by the CLI and tests so
  the installed CLI does not import tests, read instruction files, or copy
  expected text at runtime. It captures real Phase 2 pending turns.
- `prompts examples` replays all nine scenarios and prints Markdown headings
  and text fences. `--out` writes that same review text. This generated
  `docs/prompt_examples.md` as requested.
- `prompts sample` uses `derive_seed(seed, "sample")` as its episode seed for
  the engine, bots, and `assign_names`. A requested turn that was not asked
  exits 1 with a message; invalid command arguments use argparse errors.
- The earlier request to keep proposal and prompt files untracked remains in
  force. Explicit `/older_proposals/` and `/older_prompts/` rules protect both
  folders in full. Existing generic prompt-file rules also keep the generated
  `docs/prompt_examples.md` review copy local. Its nine golden fixtures remain
  available for version control under `tests/golden/`.
- No new dependencies or earlier-phase interface changes were needed.

## Length audit

Run the repeatable offline audit with:

```sh
.venv/bin/python tests/measure_prompt_lengths.py
```

The audit uses aspiration bots on all eight core networks, ten seeds per
network, both knowledge settings, and `derive_seed(2026, network_id, i)` for
episode `i`. Names use that episode seed. The history distribution is measured
on **12-round games**, counting each history line each time it is presented
at an asked turn and excluding its `Round k:` prefix. Inclusive percentiles
are used. A separate run of the same combinations at 24 rounds measures long
prompts; it does not enter the 12-round history distribution.

| Measurement | Result |
| --- | ---: |
| History words p50 | 16 |
| History words p95 | 48 |
| History words maximum | 79 |
| History-line occurrences | 49,254 |
| Prompts in the 12-round audit | 8,460 |
| Longest 12-round prompt, characters | 6,019 |
| Prompts in the 24-round audit | 17,416 |
| Longest 24-round prompt, characters | 9,281 |

These are measurements, not thresholds or a reason to omit information.
Long lines retain all offers.

## Verification

- Default suite: `390 passed, 1 deselected in 19.88s`.
- Slow suite: `1 passed, 390 deselected in 0.72s`.
- Nine exact golden comparisons, parser/schema/name tests, all earlier-phase
  tests, and both CLI subcommands passed.
- Adapter equivalence covered four bots × five networks × three seeds × two
  knowledge settings = 120 paired comparisons (240 episodes), each of 12 rounds.
  Points, offers, deals, and all turn validity/reason pairs matched.
- Random-bot prompt fuzzing covered all 16 exchange networks × five seeds ×
  two settings = 160 episodes, rendering every asked turn. Tests checked all
  fixed lines and the dynamic region for node-ID and unassigned-name leaks.
- The required review copy was generated through the CLI. Two sample runs
  with the same arguments printed identical prompts, and a forced-pass target
  produced the specified failure message and exit code.
- The original script, reference values, and three prediction files remain
  unchanged. The original script's required SHA-256 remains
  `71a6d6d81954ef303cdd6f0a345afe9a961b56a17e63ea20d81431ec833bf0ec`.
- No network access, API calls, commits, or pushes were made.

## Interfaces for later phases

```python
NAME_POOL: tuple[str, ...]
assign_names(network: Network, episode_seed: int,
             pool: Sequence[str] = NAME_POOL) -> dict[str, str]

PROMPT_VERSION = "v1"
render_prompt(obs: Observation, names: Mapping[str, str], *,
              version: str = "v1") -> str
build_messages(obs: Observation, names: Mapping[str, str], *,
               version: str = "v1") -> list[dict[str, str]]

response_format() -> dict[str, Any]
ParseResult(action: Action | None, error: str | None, details: Mapping[str, Any])
parse_reply(content: str | None, names: Mapping[str, str], *,
            refusal: str | None = None) -> ParseResult
action_to_reply(action: Action | None, names: Mapping[str, str]) -> str

JsonBotAdapter(bot: Agent, names: Mapping[str, str])
JsonBotAdapter.act(obs: Observation) -> Decision
```

There are no unresolved questions or expected-text discrepancies. The additional
private scenario module is the only layout addition beyond the four requested
public modules. Phase 4 has not started.
