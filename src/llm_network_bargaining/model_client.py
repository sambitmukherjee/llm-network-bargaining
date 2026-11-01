"""A small Chat Completions boundary shared by real and offline clients."""

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import os
import time
from typing import Any, Literal, Protocol

import openai

from .config import ModelSpec


@dataclass(frozen=True)
class ChatRequest:
    """SDK arguments and private fake-client context, which is never sent."""

    kwargs: Mapping[str, Any]
    timeout_s: float
    purpose: Literal["turn", "quiz", "smoke"]
    context: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Usage:
    """Reported token counts; reasoning is already part of completion_tokens."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0


@dataclass(frozen=True)
class ChatResponse:
    """The SDK-independent reply used by agents, quizzes and tests."""

    content: str | None
    refusal: str | None
    finish_reason: str | None
    model: str | None
    request_id: str | None
    system_fingerprint: str | None
    service_tier: str | None
    usage: Usage
    latency_s: float


class ModelClient(Protocol):
    """Only this method is needed to supply model replies."""

    async def complete(self, request: ChatRequest) -> ChatResponse:
        """Return a reply or raise one of our API errors."""
        ...


class TransientAPIError(Exception):
    """A timeout, connection failure or status worth retrying."""


class FatalAPIError(Exception):
    """A key, configuration or other API problem that must stop the call."""


def build_chat_kwargs(spec: ModelSpec, messages: Sequence[Mapping[str, str]],
                      response_format: Mapping[str, Any]) -> dict[str, Any]:
    """Build the complete body; send no sampling seed or tier override."""
    kwargs: dict[str, Any] = {
        "model": spec.model_id,
        "messages": messages,
        "response_format": response_format,
        "reasoning_effort": spec.reasoning_effort,
        "max_completion_tokens": spec.max_completion_tokens,
        "store": False,
    }
    if spec.prompt_cache == "off":
        kwargs["extra_body"] = {"prompt_cache_options": {"mode": "explicit"}}
    if spec.temperature is not None:
        kwargs["temperature"] = spec.temperature
    return kwargs


def classify_status(status: int) -> type[TransientAPIError] | type[FatalAPIError]:
    """Classify an HTTP error status without relying on SDK transport details."""
    if status in (408, 409, 429) or 500 <= status <= 599:
        return TransientAPIError
    if status >= 400:
        return FatalAPIError
    raise ValueError("Expected an HTTP error status (400 or greater).")


def to_chat_response(sdk_obj: Any, latency_s: float) -> ChatResponse:
    """Convert an SDK reply; absent or null usage details count as zero."""
    choices = getattr(sdk_obj, "choices", None) or []
    choice = choices[0] if choices else None
    message = getattr(choice, "message", None)
    usage = getattr(sdk_obj, "usage", None)
    prompt = getattr(usage, "prompt_tokens_details", None)
    completion = getattr(usage, "completion_tokens_details", None)
    return ChatResponse(
        content=getattr(message, "content", None),
        refusal=getattr(message, "refusal", None),
        finish_reason=getattr(choice, "finish_reason", None),
        model=getattr(sdk_obj, "model", None),
        request_id=getattr(sdk_obj, "_request_id", None),
        system_fingerprint=getattr(sdk_obj, "system_fingerprint", None),
        service_tier=getattr(sdk_obj, "service_tier", None),
        usage=Usage(
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            cached_tokens=getattr(prompt, "cached_tokens", 0) or 0,
            cache_write_tokens=getattr(prompt, "cache_write_tokens", 0) or 0,
            reasoning_tokens=getattr(completion, "reasoning_tokens", 0) or 0,
        ),
        latency_s=latency_s,
    )


def _api_error(exc: openai.OpenAIError) -> TransientAPIError | FatalAPIError:
    """Preserve useful status/ID information without copying raw error bodies."""
    if isinstance(exc, (openai.APITimeoutError, openai.APIConnectionError)):
        error_type = TransientAPIError
        description = f"OpenAI {type(exc).__name__}"
    elif isinstance(exc, openai.APIStatusError):
        error_type = classify_status(exc.status_code)
        description = f"OpenAI HTTP status {exc.status_code}"
    else:
        error_type = FatalAPIError
        description = f"OpenAI {type(exc).__name__}"
    request_id = getattr(exc, "request_id", None)
    if request_id:
        description += f" (request ID: {request_id})"
    return error_type(description)


class OpenAIChatClient:
    """One lazy SDK client, with application retries and bounded concurrency.

    Reuse it within one event loop and close it with ``await aclose()``.
    Constructing this wrapper reads no key and makes no network request.
    """

    def __init__(self, *, api_key: str | None = None, max_concurrency: int = 16) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be positive.")
        self._api_key = api_key
        self._client: openai.AsyncOpenAI | None = None
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def complete(self, request: ChatRequest) -> ChatResponse:
        """Send only kwargs and timeout; keep fake-client context private."""
        async with self._semaphore:
            start = time.monotonic()
            try:
                if self._client is None:
                    key = self._api_key or os.environ.get("OPENAI_API_KEY")
                    if not key:
                        raise FatalAPIError("Set OPENAI_API_KEY before making an OpenAI request.")
                    self._client = openai.AsyncOpenAI(api_key=key, max_retries=0)
                    self._api_key = None
                reply = await self._client.chat.completions.create(
                    **request.kwargs, timeout=request.timeout_s)
            except openai.OpenAIError as exc:
                raise _api_error(exc) from exc
            return to_chat_response(reply, time.monotonic() - start)

    async def aclose(self) -> None:
        """Release the SDK's connections, if it was ever constructed."""
        if self._client is not None:
            await self._client.close()
            self._client = None
