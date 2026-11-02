"""Ground-truth prices, cache-write fallback and accumulated usage."""

from pathlib import Path
import json

from pydantic import ValidationError
import pytest

from llm_network_bargaining.config import load_config
from llm_network_bargaining.costs import CostTracker, cost_of
from llm_network_bargaining.model_client import Usage
from phase4_helpers import terra


def test_ground_truth_costs() -> None:
    assert cost_of(Usage(1000, 50), terra()) == pytest.approx(0.00125)
    assert cost_of(Usage(1000, 50, cached_tokens=200, cache_write_tokens=300), terra()) == pytest.approx(0.001135)
    luna = terra(model_id="gpt-6-luna", price_input_per_m=0.10, price_cached_input_per_m=0.01,
                 price_cache_write_per_m=0.125, price_output_per_m=0.50)
    assert cost_of(Usage(2000, 100, cached_tokens=1000), luna) == pytest.approx(0.00016)
    assert cost_of(Usage(1000, 50, reasoning_tokens=10), terra()) == cost_of(Usage(1000, 50), terra())
    assert cost_of(Usage(100, 0, cached_tokens=200), terra()) == pytest.approx(0.00001)


def test_assumed_write_price_warns_only_when_used() -> None:
    spec = terra(price_cache_write_per_m=None)
    with pytest.warns(UserWarning, match="cache_write_price_assumed"):
        assert cost_of(Usage(1000, 50, cache_write_tokens=300), spec) == pytest.approx(0.001325)
    assert cost_of(Usage(1000, 50), spec) == pytest.approx(0.00125)


def test_tracker_totals_are_independent_snapshots() -> None:
    tracker = CostTracker()
    assert tracker.total_usd == 0 and tracker.to_dict() == {}
    tracker.add("terra", Usage(1000, 50, reasoning_tokens=5), 0.00125)
    tracker.add("terra", Usage(1000, 50, 200, 300), 0.001135)
    tracker.add("luna", Usage(2000, 100, 1000), 0.00016)
    data = tracker.to_dict()
    assert data["terra"] == {"calls": 2, "usage": {
        "prompt_tokens": 2000, "completion_tokens": 100, "cached_tokens": 200,
        "cache_write_tokens": 300, "reasoning_tokens": 5}, "cost_usd": pytest.approx(0.002385)}
    assert tracker.total_usd == pytest.approx(0.002545)
    json.dumps(data)
    data["terra"]["usage"]["prompt_tokens"] = 0
    assert tracker.to_dict()["terra"]["usage"]["prompt_tokens"] == 2000


def test_new_defaults_and_example_prices() -> None:
    spec = terra(price_cache_write_per_m=None)
    assert spec.prompt_cache == "off" and spec.timeout_s == 60.0 and spec.price_cache_write_per_m is None
    paths = sorted(path for path in (Path(__file__).resolve().parents[1] / "configs").glob("*.yaml")
                   if path.name != "note_judge.yaml")
    assert len(paths) == 7
    for path in paths:
        config = load_config(path)
        assert config.models["terra"].price_cache_write_per_m == 1.25
        if "luna" in config.models:
            assert config.models["luna"].price_cache_write_per_m == 0.125
        assert "# Model IDs and prices checked against OpenAI's model pages on 1 November 2026." in path.read_text()


@pytest.mark.parametrize("field,value", [
    ("prompt_cache", "explicit"), ("prompt_cache", None), ("timeout_s", 0),
    ("timeout_s", -1), ("timeout_s", "forever"), ("timeout_s", float("inf")),
    ("timeout_s", float("nan")), ("price_cache_write_per_m", -1),
    ("price_cache_write_per_m", "unknown"), ("price_cache_write_per_m", float("nan")),
    ("price_cache_write_per_m", float("inf")), ("reasoning_effort", "maximum"),
])
def test_invalid_model_fields(field: str, value: object) -> None:
    with pytest.raises(ValidationError, match=field):
        terra(**{field: value})


@pytest.mark.parametrize("effort", ["none", "minimal", "low", "medium", "high", "xhigh", "max"])
def test_supported_reasoning_efforts(effort: str) -> None:
    assert terra(reasoning_effort=effort).reasoning_effort == effort
