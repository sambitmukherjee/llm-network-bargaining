"""Small configs, normalized records and fault injection for offline runner tests."""

from dataclasses import replace
import json
from pathlib import Path
from typing import Any

import yaml

from llm_network_bargaining.config import load_config
from llm_network_bargaining.fake_client import FakeChatClient
from llm_network_bargaining.model_client import FatalAPIError
from llm_network_bargaining import runner

ROOT = Path(__file__).resolve().parents[1]
WALL_FIELDS = {"started_at", "finished_at", "duration_s", "latency_s", "git_commit", "git_dirty"}


def small_config(folder: Path, *, networks: tuple[str, ...] = ("line3",), episodes: int = 1,
                 rounds: int = 12):
    data = load_config(ROOT / "configs/minimum_study.yaml").model_dump()
    data.update(name="tiny", networks=list(networks), knowledge=["full_map"])
    data["settings"].update(rounds=rounds, episodes_per_condition=episodes)
    path = folder / "tiny.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data))
    return load_config(path)


def normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: normalize(item) for key, item in value.items() if key not in WALL_FIELDS}
    if isinstance(value, list):
        return [normalize(item) for item in value]
    return value


def install_fault(monkeypatch, predicate, *, fatal: bool = False):
    """Wrap the ordinary per-attempt fake client, changing selected responses only."""
    original = runner._make_dry_client
    clients = []

    def make(job, attempt, bot):
        base = original(job, attempt, bot)

        def respond(request):
            if predicate(job, attempt, request):
                if fatal:
                    return FatalAPIError("Injected configuration error")
                return replace(base.responder(request), content=None, refusal="Injected refusal")
            return base.responder(request)

        client = FakeChatClient(respond)
        clients.append(client)
        return client

    monkeypatch.setattr(runner, "_make_dry_client", make)
    return clients


def write_records(path: Path, records: list[dict]) -> None:
    """Write tampered fixture data without changing the production writer."""
    import gzip

    text = "".join(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n" for record in records)
    if path.suffix == ".gz":
        path.write_bytes(gzip.compress(text.encode(), mtime=0))
    else:
        path.write_text(text)
