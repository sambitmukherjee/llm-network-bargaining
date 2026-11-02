"""Keep every in-process test offline, including accidental future requests."""

import socket
import asyncio
import gzip
import os
from pathlib import Path
import tempfile
from typing import Any

import pytest
import openai

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "lnb-matplotlib"))
os.environ.setdefault("MPLBACKEND", "Agg")

DUMMY_API_KEY = "phase5-dummy-key-must-never-appear-in-logs"


@pytest.fixture(scope="session", autouse=True)
def dummy_key_and_log_scan(tmp_path_factory: pytest.TempPathFactory):
    """Use a dummy environment key and inspect every test output, including gzip."""
    original = os.environ.get("OPENAI_API_KEY")
    os.environ["OPENAI_API_KEY"] = DUMMY_API_KEY
    try:
        yield
        for path in tmp_path_factory.getbasetemp().rglob("*"):
            if path.is_file():
                data = path.read_bytes()
                if path.name.endswith(".gz"):
                    data = gzip.decompress(data)
                assert DUMMY_API_KEY.encode() not in data, f"Dummy key leaked into {path}"
    finally:
        if original is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = original


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


@pytest.fixture(scope="session")
def analysis_logs(tmp_path_factory: pytest.TempPathFactory, dummy_key_and_log_scan):
    """Generate the required 36 aspiration-bot episodes once, fully offline."""
    from pathlib import Path
    from llm_network_bargaining.config import load_configs
    from llm_network_bargaining.runner import plan_jobs, run_jobs

    def refuse(*args, **kwargs):
        raise AssertionError("Analysis fixture must stay offline.")

    root = tmp_path_factory.mktemp("analysis_logs")
    configs = load_configs([Path(__file__).resolve().parents[1] / "configs" / name
                            for name in ("minimum_study.yaml", "own_links_arm.yaml", "pilot_own_links.yaml")])
    # Preserve the 12-round regression data and the 24-round pilot windows.
    for index, config in enumerate(configs):
        if not config.name.startswith("pilot_"):
            settings = config.settings.model_copy(update={"rounds": 12})
            configs[index] = config.model_copy(update={"settings": settings})
    with pytest.MonkeyPatch.context() as guard:
        guard.setattr(socket.socket, "connect", refuse)
        guard.setattr(socket, "create_connection", refuse)
        guard.setattr(openai, "OpenAI", refuse)
        guard.setattr(openai, "AsyncOpenAI", refuse)
        summary = asyncio.run(run_jobs(plan_jobs(configs, max_episodes=2), out_root=root,
                                        dry_run_bot="aspiration"))
    assert summary.done == 36
    return root


@pytest.fixture(scope="session")
def report_logs(analysis_logs, tmp_path_factory):
    """Add two full-map pilot episodes per condition in an independent root."""
    import shutil
    from llm_network_bargaining.config import load_config
    from llm_network_bargaining.runner import plan_jobs, run_jobs

    root = tmp_path_factory.mktemp("report_logs")
    shutil.copytree(analysis_logs, root, dirs_exist_ok=True)
    config = load_config(Path(__file__).resolve().parents[1] / "configs/pilot_full_map.yaml")
    with pytest.MonkeyPatch.context() as guard:
        def refuse(*args, **kwargs):
            raise AssertionError("Report fixtures must stay offline.")
        guard.setattr(socket.socket, "connect", refuse)
        guard.setattr(socket, "create_connection", refuse)
        guard.setattr(openai, "OpenAI", refuse)
        guard.setattr(openai, "AsyncOpenAI", refuse)
        summary = asyncio.run(run_jobs(plan_jobs([config], max_episodes=2), out_root=root, dry_run_bot="aspiration"))
    assert summary.done == 16
    return root
