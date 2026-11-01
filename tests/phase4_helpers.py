"""Small, shared offline inputs for Phase 4 assertions."""

from llm_network_bargaining.config import ModelSpec
from llm_network_bargaining.model_client import ChatResponse, Usage

META_KEYS = {
    "agent_kind", "model_alias", "model_id", "prompt_version", "messages", "prompt_sha256",
    "attempts", "content", "refusal", "finish_reason", "parse", "usage", "cost_usd", "latency_s",
    "returned_model", "request_id", "system_fingerprint", "service_tier", "warnings",
}
ATTEMPT_KEYS = {"n", "outcome", "error", "request_id", "model", "finish_reason", "usage", "latency_s", "cost_usd"}
PASS = '{"action":"pass","to":null,"my_points":null,"note":""}'


def terra(**changes: object) -> ModelSpec:
    """Construct a validated spec independently of the example YAML files."""
    data = dict(provider="openai", model_id="gpt-6.1-terra", price_input_per_m=1.0,
                price_cached_input_per_m=0.05, price_cache_write_per_m=1.25, price_output_per_m=5.0)
    data.update(changes)
    return ModelSpec.model_validate(data)


def reply(content: str | None = PASS, *, refusal: str | None = None,
          finish_reason: str = "stop", model: str = "gpt-6.1-terra-2026-11-01",
          usage: Usage = Usage(1000, 50)) -> ChatResponse:
    """A complete SDK-independent reply with visible accounting values."""
    return ChatResponse(content, refusal, finish_reason, model, "req-fake", "fp-fake",
                        "default", usage, 0.25)
