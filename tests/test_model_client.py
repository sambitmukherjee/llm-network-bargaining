"""Request bodies, pure SDK conversion, status policy and offline guards."""

import asyncio
import json
from types import SimpleNamespace as NS

import openai
import pytest

from llm_network_bargaining.model_client import (
    ChatRequest, FatalAPIError, OpenAIChatClient, TransientAPIError, Usage,
    _api_error, build_chat_kwargs, classify_status, to_chat_response,
)
from phase4_helpers import terra


def test_request_body_and_optional_fields() -> None:
    messages = [{"role": "user", "content": "test"}]
    schema = {"type": "json_schema", "json_schema": {"name": "test"}}
    expected = dict(model="gpt-6.1-terra", messages=messages, response_format=schema,
                    reasoning_effort="none", max_completion_tokens=300, store=False,
                    extra_body={"prompt_cache_options": {"mode": "explicit"}})
    assert build_chat_kwargs(terra(), messages, schema) == expected
    kwargs = build_chat_kwargs(terra(prompt_cache="implicit", temperature=0.7), messages, schema)
    assert kwargs == {**{k: v for k, v in expected.items() if k != "extra_body"}, "temperature": 0.7}
    assert not {"seed", "user", "max_tokens", "top_p", "service_tier"}.intersection(kwargs)
    request = ChatRequest(expected, 60.0, "smoke", {"private": object()})
    assert json.loads(json.dumps(request.kwargs)) == expected


@pytest.mark.parametrize("status", [408, 409, 429, 500, 502, 503, 504, 599])
def test_transient_statuses(status: int) -> None:
    assert classify_status(status) is TransientAPIError


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422, 499, 600])
def test_fatal_statuses(status: int) -> None:
    assert classify_status(status) is FatalAPIError


def test_non_error_status_rejected() -> None:
    with pytest.raises(ValueError, match="400"):
        classify_status(200)


def test_conversion_full_details() -> None:
    sdk = NS(choices=[NS(message=NS(content="answer", refusal=None), finish_reason="stop")],
             model="gpt-6.1-terra", _request_id="req-1", system_fingerprint="fp-1", service_tier="default",
             usage=NS(prompt_tokens=1000, completion_tokens=50,
                      prompt_tokens_details=NS(cached_tokens=200, cache_write_tokens=300),
                      completion_tokens_details=NS(reasoning_tokens=5)))
    response = to_chat_response(sdk, 1.5)
    assert response.content == "answer" and response.refusal is None
    assert response.usage == Usage(1000, 50, 200, 300, 5)
    assert (response.model, response.request_id, response.system_fingerprint, response.service_tier,
            response.latency_s) == ("gpt-6.1-terra", "req-1", "fp-1", "default", 1.5)


@pytest.mark.parametrize("details", [{}, {"prompt_tokens_details": None, "completion_tokens_details": None},
                                   {"prompt_tokens_details": NS(cached_tokens=None, cache_write_tokens=None),
                                    "completion_tokens_details": NS(reasoning_tokens=None)}])
def test_missing_and_null_details_and_refusal(details: dict) -> None:
    sdk = NS(choices=[NS(message=NS(content=None, refusal="declined"), finish_reason="stop")],
             usage=NS(prompt_tokens=12, completion_tokens=3, **details))
    response = to_chat_response(sdk, 0.1)
    assert response.usage == Usage(12, 3)
    assert response.content is None and response.refusal == "declined"
    assert response.request_id is None
    assert to_chat_response(NS(), 0.0).usage == Usage()


@pytest.mark.parametrize("status,error_type", [(401, FatalAPIError), (429, TransientAPIError)])
def test_status_exception_mapping_hides_raw_body(status: int, error_type: type[Exception]) -> None:
    # These are plain data objects, not HTTP mocks or SDK clients.
    response = NS(status_code=status, request=NS(), headers={"x-request-id": "req-99"})
    exc = openai.APIStatusError("sensitive-error-body", response=response, body=None)
    mapped = _api_error(exc)
    assert isinstance(mapped, error_type)
    assert "req-99" in str(mapped) and str(status) in str(mapped)
    assert "sensitive-error-body" not in str(mapped)


def test_other_sdk_exception_types() -> None:
    for exc in (openai.APITimeoutError(request=NS()), openai.APIConnectionError(request=NS())):
        assert isinstance(_api_error(exc), TransientAPIError)
    assert isinstance(_api_error(openai.OpenAIError("sensitive-error-body")), FatalAPIError)


def test_sdk_constructors_are_blocked() -> None:
    for constructor in (openai.OpenAI, openai.AsyncOpenAI):
        with pytest.raises(AssertionError, match="FakeChatClient"):
            constructor(api_key="dummy")


def test_lazy_wrapper_and_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = OpenAIChatClient()
    request = ChatRequest({}, 60.0, "smoke")
    with pytest.raises(FatalAPIError, match="OPENAI_API_KEY"):
        asyncio.run(client.complete(request))
    asyncio.run(client.aclose())
    with pytest.raises(ValueError, match="max_concurrency"):
        OpenAIChatClient(max_concurrency=0)
