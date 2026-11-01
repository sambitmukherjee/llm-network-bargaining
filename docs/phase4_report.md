# Phase 4 validation report

Status: **Phase 4 is complete**, including the user's clarified random-bot
equivalence tests. Phase 5 has not started. Nothing was committed or pushed,
and no real model API call was made.

## Files built or updated

| File | Purpose |
|---|---|
| `src/llm_network_bargaining/model_client.py` | SDK-independent requests/responses, lazy Chat Completions client, error classification and pure response conversion. |
| `src/llm_network_bargaining/fake_client.py` | Recorded scripted replies and bot-backed offline turn/quiz replies. |
| `src/llm_network_bargaining/costs.py` | Token cost calculations, cache-write fallback warning and per-alias totals. |
| `src/llm_network_bargaining/llm_agent.py` | Async/sync agent, independent retry limits, failure exceptions and complete turn metadata. |
| `src/llm_network_bargaining/quiz.py` | Versioned quiz rendering, seeded option orders, schema, parsing, scoring and metadata. |
| `src/llm_network_bargaining/smoke.py` | Four-request dry preview and user-operated live API checks. |
| `src/llm_network_bargaining/prompts.py` | Shared nine-line rules block; existing stimuli remain byte-identical. |
| `src/llm_network_bargaining/config.py` | Cache-write price, caching mode, timeout and all seven reasoning efforts. |
| `configs/*.yaml` (seven files) | Verified-date comment and explicit Terra/Luna cache-write prices. |
| `pyproject.toml` | Adds the sole new direct dependency, `openai>=3.35.1,<4`. |
| `tests/conftest.py` | Blocks both OpenAI SDK constructors alongside the existing socket guard. |
| `tests/phase4_helpers.py` | Shared test specs, replies and exact metadata key sets. |
| `tests/test_model_client.py` | Request, conversion, error classification and lazy-key checks. |
| `tests/test_costs.py` | Ground-truth costs, accumulated usage and new config validation. |
| `tests/test_llm_agent.py` | Retry table, costs/warnings, invalid moves, empty bot replies, test-only None wrapper and bot equivalence. |
| `tests/test_quiz.py` | Golden stimulus, rule parity, privacy across all 16 exchange networks, orders, parsing and scoring. |
| `tests/test_smoke.py` | Offline CLI behavior, repeated long body, costs and missing-key guard. |
| `tests/golden/QUIZ_EX1.txt` | Exact quiz example copied from the brief. |
| `docs/prompt_examples.md` | Generated bargaining-agent examples, committed at the user's request after Phase 4. |
| `README.md` | Setup, environment key handling, dry/live smoke commands and async usage. |
| `.gitignore` | Excludes local environment files and proposals/phase prompts, with the requested exception for `docs/prompt_examples.md`. |
| `docs/phase4_notes.md` | Implementation decisions and public interfaces for later phases. |

## Validation

Before changes: `390 passed, 1 deselected in 20.27s`.

Latest default run:

```text
525 passed, 1 deselected in 22.44s
```

Slow run:

```text
1 passed, 525 deselected in 0.58s
```

`pip check` reports no broken requirements.

All 24 equivalence cases pass: aspiration and random bots on `line3`, `stem`
and `star4`, with seeds 0 and 1, both knowledge settings and 12 rounds. Each
case compares a plain episode with a complete fake-client LLM episode: points,
deals, offers, and every turn's validity/reason agree. Request bodies are also
checked against the prompt and schema builders.

All nine existing golden prompt files, the prediction files, and
`preexisting/predict.py` are byte-identical to Git HEAD. The protected script's
SHA-256 remains:

```text
71a6d6d81954ef303cdd6f0a345afe9a961b56a17e63ea20d81431ec833bf0ec
```

Proposal files, phase prompts, `older_proposals/`, `older_prompts/`, and local
environment files remain ignored. No real key was read for the dry run,
printed, or written to a file. Tests use dummy values only. The only network
operation was the user-authorized SDK/dependency download.

## SDK and decisions

Installed `openai` version: **3.42.0**. The brief permits versions from
3.35.1 up to, but excluding, 4. This SDK exposes `prompt_cache_options` as a named
argument; the implementation still uses `extra_body` exactly as requested.
Actual model support, usage accounting and caching behavior await the user's
live smoke test.

Other recorded decisions include the observation-aware `rules_block` path,
strict quiz parsing, raw quiz content in `quiz_raw`, zero recorded latency for
API failures without a response, and a Python warning plus metadata warning
when a cache-write price is assumed. Signatures, metadata details and later-phase
interfaces are in [phase4_notes.md](phase4_notes.md#public-interfaces-for-later-phases).

## Interfaces for later phases

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

## Resolved clarification

Section 5.5 requests equivalence through the LLM path for random bots. The
existing random bot defaults to `p_invalid=0.1`, which can return `None`.
Section 4.7 correctly serializes that as empty content, while section 4.5
requires empty content to be retried, rather than becoming a game pass. Those
retries advance the bot's RNG and prevent exact plain-bot equivalence.

The user specified a test-only wrapper in both random-bot runs that calls the
bot once and replaces only `action=None` with `Action("dance")`. The default
`p_invalid=0.1` and the other five invalid requests remain unchanged, so the
test retains invalid actions without advancing the random stream on retries.
The separate unwrapped None-bot test still requires three empty replies and
`AgentTurnFailure("empty")`. No production behavior changed for this resolution.
There are no remaining open questions.

## Exact dry-run output

Input estimates use four characters per token, rounded up. The output line
shows the configured maximum cost; the actual replies can be much shorter.
The two long request bodies contain the same 6,933-character prompt.

```text
short_turn: {"kwargs": {"model": "gpt-6.1-terra", "messages": [{"role": "user", "content": "You are agent Orsa. You earn points by making deals with your neighbours.\nEach r ... r a pass, \"to\" and \"my_points\" are ignored. Any invalid action counts as a pass."}], "response_format": {"type": "json_schema", "json_schema": {"name": "bargaining_action", "strict": true, "schema": {"type": "object", "properties": {"action": {"type": "string", "enum": ["offer", "accept", "pass"]}, "to": {"type": ["string", "null"]}, "my_points": {"type": ["integer", "null"]}, "note": {"type": "string"}}, "required": ["action", "to", "my_points", "note"], "additionalProperties": false}}}, "reasoning_effort": "none", "max_completion_tokens": 300, "store": false, "extra_body": {"prompt_cache_options": {"mode": "explicit"}}}, "message_characters": [1457], "estimated_prompt_tokens": 365, "estimated_input_usd": 0.000365}
long_turn_1: {"kwargs": {"model": "gpt-6.1-terra", "messages": [{"role": "user", "content": "You are agent Tovi. You earn points by making deals with your neighbours.\nEach r ... r a pass, \"to\" and \"my_points\" are ignored. Any invalid action counts as a pass."}], "response_format": {"type": "json_schema", "json_schema": {"name": "bargaining_action", "strict": true, "schema": {"type": "object", "properties": {"action": {"type": "string", "enum": ["offer", "accept", "pass"]}, "to": {"type": ["string", "null"]}, "my_points": {"type": ["integer", "null"]}, "note": {"type": "string"}}, "required": ["action", "to", "my_points", "note"], "additionalProperties": false}}}, "reasoning_effort": "none", "max_completion_tokens": 300, "store": false, "extra_body": {"prompt_cache_options": {"mode": "explicit"}}}, "message_characters": [6933], "estimated_prompt_tokens": 1734, "estimated_input_usd": 0.001734}
long_turn_2: {"kwargs": {"model": "gpt-6.1-terra", "messages": [{"role": "user", "content": "You are agent Tovi. You earn points by making deals with your neighbours.\nEach r ... r a pass, \"to\" and \"my_points\" are ignored. Any invalid action counts as a pass."}], "response_format": {"type": "json_schema", "json_schema": {"name": "bargaining_action", "strict": true, "schema": {"type": "object", "properties": {"action": {"type": "string", "enum": ["offer", "accept", "pass"]}, "to": {"type": ["string", "null"]}, "my_points": {"type": ["integer", "null"]}, "note": {"type": "string"}}, "required": ["action", "to", "my_points", "note"], "additionalProperties": false}}}, "reasoning_effort": "none", "max_completion_tokens": 300, "store": false, "extra_body": {"prompt_cache_options": {"mode": "explicit"}}}, "message_characters": [6933], "estimated_prompt_tokens": 1734, "estimated_input_usd": 0.001734}
quiz: {"kwargs": {"model": "gpt-6.1-terra", "messages": [{"role": "user", "content": "You are agent Orsa. You earn points by making deals with your neighbours.\nEach r ... ou, or pass.\nReply with JSON only:\n{\"q1\": \"A|B|C\", \"q2\": \"A|B|C\", \"q3\": \"A|B|C\"}"}], "response_format": {"type": "json_schema", "json_schema": {"name": "rules_quiz", "strict": true, "schema": {"type": "object", "properties": {"q1": {"type": "string", "enum": ["A", "B", "C"]}, "q2": {"type": "string", "enum": ["A", "B", "C"]}, "q3": {"type": "string", "enum": ["A", "B", "C"]}}, "required": ["q1", "q2", "q3"], "additionalProperties": false}}}, "reasoning_effort": "none", "max_completion_tokens": 300, "store": false, "extra_body": {"prompt_cache_options": {"mode": "explicit"}}}, "message_characters": [1663], "estimated_prompt_tokens": 416, "estimated_input_usd": 0.000416}
Estimated input total (4 characters/token): $0.004249
Output adds up to $0.006000 at the configured limit of 300 completion tokens per request.
```
