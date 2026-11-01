# Phase 4 implementation notes

Implemented on **1 November 2026**, before the Apart Research sprint.
This phase covers the model boundary, LLM agent, cost accounting, rules quiz
and smoke CLI. There is no experiment runner, persistent logging, budget
enforcement or concurrency across episodes. Nothing was committed or pushed.

## API boundary and SDK

- The runtime dependency is `openai>=3.35.1,<4`; the installed version is
  **3.42.0**, using HTTPX2. The user explicitly authorized downloading the SDK
  and its dependencies. No real model API call was made. All remaining checks
  were offline, using the brief's verified API facts rather than web research.
- `OpenAIChatClient` constructs one `openai.AsyncOpenAI` lazily, sets
  `max_retries=0`, and limits in-flight requests with a semaphore. Context is
  private to fakes; only the request's kwargs and timeout reach the SDK.
- The SDK exposes a named `prompt_cache_options` argument. We still send it
  through `extra_body`, as required by the brief. Caching off means explicit
  mode without breakpoints; implicit mode omits the override entirely.
- SDK errors become the harness's transient/fatal errors, retaining their
  original cause. Messages contain only error type/status and request ID,
  rather than copying potentially sensitive error bodies. Attempt metadata
  similarly records the exception class, not its raw message.
- Missing/null usage objects, detail objects and individual counters count as
  zero. Absent choices become an empty response and follow the normal retry
  policy. Request IDs come from the SDK reply's `_request_id`.
- Use one client in one async event loop. `aclose()` is an additive cleanup
  interface; the live smoke CLI calls it in `finally`. For repeated real calls,
  prefer `aact()` in a shared event loop over repeated synchronous `act()` calls.

## Retries and metadata

- Transient API failures and model failures have independent counters for each
  turn or quiz. Model failures retry immediately; transient failures back off.
  A successful attempt does not erase earlier usage, costs or warnings.
- The exact same `ChatRequest` object is resent on retries. Game-invalid actions
  that parse successfully still go to the engine unchanged. Exhausted retries
  raise `AgentTurnFailure`; they never silently become passes.
- Failed API calls without a response have zero recorded usage, cost and
  latency. A client error exposes no measured latency; the metadata does not
  invent a duration. This cannot account for any provider-side charge that was
  incurred without returned usage.
- Model-response attempts record the outcome string in `error` for unusable
  replies, and `None` on success. Transient attempts record the exception class.
  Fatal API errors propagate immediately, as required.
- Warning strings are deduplicated in first-seen order. The returned-model
  warning checks every reply, including unsuccessful attempts; a missing model
  also counts as a mismatch. Notes over 30 words remain unmodified.
- `cost_of` returns a float. If writes occur without a configured write price,
  it emits `UserWarning("cache_write_price_assumed")` and uses 1.25 times input.
  Turn/quiz metadata also retains that same warning string. Reasoning tokens
  are already in completion tokens and are never billed a second time.
- `CostTracker.to_dict()` is keyed by alias; each entry contains `calls`,
  `usage` (all five counters) and `cost_usd`. It returns independent snapshots.

## Shared rules and quiz

- The public `rules_block(Network, node, names, knowledge=..., n_rounds=...)`
  gives round-1/phase-1 opening rules. To use that same function inside
  `render_prompt` while keeping observation-only rendering, it additionally
  accepts an `Observation`. That path reads the actual round/phase and checks
  that the passed settings match. It does not reconstruct or look up a network.
  All nine earlier prompt fixtures remain unchanged.
- Own-links rules require names only for the agent and its neighbours. Whole
  network links and hidden names never appear in an own-links quiz. Full-map
  rules sort every edge by display name exactly as the game prompt does.
- `render_quiz` returns a string with no trailing newline. `quiz_orders` and
  `quiz_key` are small additive helpers so rendering, scoring and offline smoke
  previews can share precisely the same permutations and key.
- `parse_quiz` returns a three-answer dict or `None`. It requires exactly q1,
  q2 and q3 with uppercase A/B/C values, including rejecting additional keys
  in accordance with the strict schema. Explicit test orders must be three
  permutations of (0, 1, 2).
- Quiz metadata uses `prompt_version="q1"`; `quiz_raw` contains the successful
  response's raw content string. All other metadata keys match turn metadata.
  `QuizResult.to_dict()` supplies a JSON-ready dataclass copy; JSON represents
  its order/correctness tuples as arrays.
- The quiz key is available only in fake-client context. Each turn builds a
  fresh single user message from its observation; quiz answers never enter play.
- The versioned quiz wording assumes the study's 24-point pie, as specified.

## Validation and resolved clarification

- An autouse test fixture blocks both SDK constructors, in addition to the
  existing socket guard. SDK response conversion uses plain `SimpleNamespace`
  data. No tests mock the SDK's HTTP layer.
- The smoke preview builds four request bodies without reading a key. Its long
  prompt is the last asked hub observation from a 24-round, seed-1 `star4`
  aspiration-bot game. The two long bodies are identical (6,933 characters).
  Input estimates use one token per four characters, rounded up; the separate
  output estimate is the configured maximum, not a prediction of reply length.
- The CLI requires exactly one mode. Live mode without a key exits before
  constructing even the wrapper. Live API behavior remains for the user to test.
- The user resolved the random-bot equivalence conflict by keeping the default
  `p_invalid=0.1` and all invalid moves. In both runs, a small test-only wrapper
  calls each random bot once and replaces only `action=None` with
  `Action("dance")`, preserving metadata. This is still an invalid action;
  the engine records `unknown_action`. The other five invalid requests pass
  through unchanged. No production bot, parser, responder or retry policy was
  changed. Separate wrapper tests cover all six invalid choices, and an
  unwrapped None-returning bot behind `BotResponder` still yields three empty
  attempts followed by `AgentTurnFailure("empty")`.
- Final default suite: `525 passed, 1 deselected in 22.44s`. Slow suite:
  `1 passed, 525 deselected in 0.58s`. All 24 aspiration/random equivalence
  cases pass, each comparing 12-round plain and fake-client episodes. The
  protected script, prediction files and nine earlier golden prompts remain
  byte-identical. The dry-run output is saved in `phase4_report.md`.

## Public interfaces for later phases

```python
ChatRequest(kwargs: Mapping[str, Any], timeout_s: float,
            purpose: Literal["turn", "quiz", "smoke"], context: Mapping[str, Any] = {})
Usage(prompt_tokens=0, completion_tokens=0, cached_tokens=0,
      cache_write_tokens=0, reasoning_tokens=0)
ChatResponse(content, refusal, finish_reason, model, request_id,
             system_fingerprint, service_tier, usage: Usage, latency_s: float)
ModelClient.complete(request: ChatRequest) -> Awaitable[ChatResponse]
OpenAIChatClient(*, api_key: str | None = None, max_concurrency: int = 16)
OpenAIChatClient.aclose() -> Awaitable[None]
build_chat_kwargs(spec: ModelSpec, messages, response_format) -> dict[str, Any]
classify_status(status: int) -> type[TransientAPIError] | type[FatalAPIError]
to_chat_response(sdk_obj: Any, latency_s: float) -> ChatResponse

cost_of(usage: Usage, spec: ModelSpec) -> float
CostTracker.add(alias: str, usage: Usage, cost: float) -> None
CostTracker.total_usd -> float  # property
CostTracker.to_dict() -> dict[str, dict[str, Any]]

RetryPolicy(max_transient_attempts=8, max_model_attempts=3,
            base_delay_s=1.0, max_delay_s=60.0)
LLMAgent(*, node, names, model_alias, spec, client,
         version="v1", retry=RetryPolicy(), sleep=asyncio.sleep)
LLMAgent.aact(obs: Observation) -> Awaitable[Decision]
LLMAgent.act(obs: Observation) -> Decision
AgentTurnFailure(category: str, attempts: list[dict[str, Any]], cost_usd: float)

rules_block(network: Network | Observation, node, names, *, knowledge, n_rounds) -> list[str]
render_quiz(network, node, names, *, knowledge, n_rounds, episode_seed, orders=None) -> str
quiz_orders(episode_seed: int, node: str) -> tuple[tuple[int, ...], ...]
quiz_key(orders) -> dict[str, str]
quiz_response_format() -> dict[str, Any]
parse_quiz(content: str | None) -> dict[str, str] | None
run_rules_quiz(*, network, node, names, knowledge, n_rounds, episode_seed,
               model_alias, spec, client, retry=RetryPolicy(),
               sleep=asyncio.sleep) -> Awaitable[QuizResult]
QuizResult(node, quiz_version, orders, key, answers, correct, score, meta)
QuizResult.to_dict() -> dict[str, Any]

FakeChatClient(responder: Callable[[ChatRequest], ChatResponse | Exception])
FakeChatClient.scripted(items: Iterable[ChatResponse | Exception]) -> FakeChatClient
BotResponder(bots: Mapping[str, Agent], *, quiz_answers="correct")
build_smoke_requests(spec: ModelSpec) -> list[tuple[str, ChatRequest]]
```

`ModelSpec` adds `price_cache_write_per_m=None`, `prompt_cache="off"` and
`timeout_s=60.0`, and accepts all seven reasoning efforts from the brief.
All new mapping defaults in dataclasses use factories; signatures above use
`{}` only to show the resulting empty value.
