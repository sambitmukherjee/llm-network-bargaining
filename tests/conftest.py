"""Keep every in-process test offline, including accidental future requests."""

import socket
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail immediately if a test tries to open a network connection."""
    def refuse(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Phase 1 tests must not access the network.")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
