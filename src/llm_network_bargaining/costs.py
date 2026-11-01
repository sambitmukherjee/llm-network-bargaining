"""Token-based cost calculations and a small in-memory accumulator."""

from dataclasses import asdict
from typing import Any
import warnings

from .config import ModelSpec
from .model_client import Usage


def cost_of(usage: Usage, spec: ModelSpec) -> float:
    """Cost all reported tokens once, in US dollars, including cache writes."""
    write_price = spec.price_cache_write_per_m
    if write_price is None:
        write_price = 1.25 * spec.price_input_per_m
        if usage.cache_write_tokens:
            warnings.warn("cache_write_price_assumed", UserWarning, stacklevel=2)
    uncached = max(0, usage.prompt_tokens - usage.cached_tokens - usage.cache_write_tokens)
    return (
        uncached * spec.price_input_per_m
        + usage.cached_tokens * spec.price_cached_input_per_m
        + usage.cache_write_tokens * write_price
        + usage.completion_tokens * spec.price_output_per_m
    ) / 1_000_000


def sum_usage(usages: list[Usage]) -> Usage:
    """Sum each token counter without treating reasoning as extra output."""
    return Usage(**{name: sum(getattr(usage, name) for usage in usages)
                    for name in asdict(Usage())})


class CostTracker:
    """Accumulate calls, tokens and cost separately for each model alias."""

    def __init__(self) -> None:
        self._totals: dict[str, dict[str, Any]] = {}

    def add(self, alias: str, usage: Usage, cost: float) -> None:
        """Record one call, including calls whose model reply was unusable."""
        entry = self._totals.setdefault(alias, {"calls": 0, "usage": asdict(Usage()), "cost_usd": 0.0})
        entry["calls"] += 1
        for name, value in asdict(usage).items():
            entry["usage"][name] += value
        entry["cost_usd"] += cost

    @property
    def total_usd(self) -> float:
        """Return the cost across all aliases."""
        return sum(entry["cost_usd"] for entry in self._totals.values())

    def to_dict(self) -> dict[str, dict[str, Any]]:
        """Return independent JSON-ready totals, keyed by model alias."""
        return {alias: {**entry, "usage": dict(entry["usage"])}
                for alias, entry in self._totals.items()}
