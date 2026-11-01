"""Keep every in-process test offline, including accidental future requests."""

import socket
from typing import Any

import pytest
import openai


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail immediately if a test tries to open a network connection."""
    def refuse(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Tests must not access the network.")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.fixture(autouse=True)
def no_sdk_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    """Catch accidental real-client construction before any request is possible."""
    def refuse(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Tests must use FakeChatClient, never an OpenAI SDK client.")

    monkeypatch.setattr(openai, "OpenAI", refuse)
    monkeypatch.setattr(openai, "AsyncOpenAI", refuse)
