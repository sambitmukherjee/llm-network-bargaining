"""Validate experiment terminology, model assignments, expansion, and seeds."""

from copy import deepcopy
from pathlib import Path
from typing import Any

from pydantic import ValidationError
import pytest
import yaml

from llm_network_bargaining.config import (
    ExperimentConfig, expand_conditions, load_config, load_configs, total_episodes,
)
from llm_network_bargaining.seeds import derive_seed

ROOT = Path(__file__).resolve().parents[1]
COUNTS = {
    "pilot_full_map": (8, 24), "pilot_own_links": (2, 6), "minimum_study": (8, 80),
    "own_links_arm": (8, 80), "stretch_2f_h6": (4, 40), "stretch_2c_sweep": (4, 40),
    "stretch_2d_control": (1, 10),
}


def _data() -> dict[str, Any]:
    data = yaml.safe_load((ROOT / "configs" / "minimum_study.yaml").read_text())
    data["models"]["luna"] = deepcopy(data["models"]["terra"])
    return data


@pytest.mark.parametrize("name", COUNTS)
def test_example_counts_and_defaults(name: str) -> None:
    """Each shipped config expands to the requested condition/episode counts."""
    config = load_config(ROOT / "configs" / f"{name}.yaml")
    expected_conditions, expected_episodes = COUNTS[name]
    conditions = expand_conditions(config)
    assert len(conditions) == expected_conditions
    assert total_episodes(config) == expected_episodes
    assert sum(len(condition.episode_seeds) for condition in conditions) == expected_episodes
    assert config.seed == 20261106
    assert config.settings.rounds == (24 if name.startswith("pilot_") else 12)
    assert config.settings.phases == 3
    assert config.settings.phase3_accept_only is True
    for model in config.models.values():
        assert model.reasoning_effort == "none"
        assert model.max_completion_tokens == 300
        assert model.temperature is None


def test_all_config_keys_and_seeds_are_distinct() -> None:
    """Config names separate overlapping networks in all seven configs."""
    paths = [ROOT / "configs" / f"{name}.yaml" for name in COUNTS]
    configs = load_configs(paths)
    conditions = [condition for config in configs for condition in expand_conditions(config)]
    assert conditions == [condition for config in configs for condition in expand_conditions(config)]
    keys = [condition.key for condition in conditions]
    seeds = [condition.condition_seed for condition in conditions]
    seeds += [seed for condition in conditions for seed in condition.episode_seeds]
    assert len(set(keys)) == len(keys)
    assert len(set(seeds)) == len(seeds)
    for condition in conditions:
        assert condition.condition_seed == derive_seed(20261106, condition.key)
        assert condition.episode_seeds == [derive_seed(condition.condition_seed, "episode", i)
                                           for i in range(condition.settings.episodes_per_condition)]


def test_minimum_key_and_h6_assignments() -> None:
    """H6 swaps only hub models and the minimum study starts with the pair."""
    minimum = load_config(ROOT / "configs" / "minimum_study.yaml")
    first = expand_conditions(minimum)[0]
    assert first.key == "minimum_study/pair/full_map/terra"
    assert (first.config_name, first.network_id, first.knowledge_setting, first.assignment_name) == (
        "minimum_study", "pair", "full_map", "terra")
    h6 = load_config(ROOT / "configs" / "stretch_2f_h6.yaml")
    conditions = {(condition.network_id, condition.assignment_name): condition
                  for condition in expand_conditions(h6)}
    assert conditions["star3", "terra_hub"].node_models == {
        "H": "terra", "L1": "luna", "L2": "luna", "L3": "luna"}
    assert conditions["line3", "luna_hub"].node_models == {"A": "terra", "B": "luna", "C": "terra"}


def test_cartesian_order_and_class_overrides() -> None:
    """Networks vary slowest; a class override expands to all its members."""
    data = _data()
    data["networks"] = ["line3", "star3"]
    data["knowledge"] = ["full_map", "own_links"]
    data["assignments"] = [
        {"name": "first", "default": "terra", "per_network": {"line3": {"A|C": "luna", "A": "luna"}}},
        {"name": "second", "default": "luna"},
    ]
    conditions = expand_conditions(ExperimentConfig.model_validate(data))
    assert [condition.key for condition in conditions] == [
        f"minimum_study/{net}/{knowledge}/{assignment}"
        for net in ("line3", "star3") for knowledge in ("full_map", "own_links")
        for assignment in ("first", "second")]
    assert conditions[0].node_models == {"A": "luna", "B": "terra", "C": "luna"}


# Paths identify one field in the otherwise valid config; each case tests one error.
INVALID = [
    (("networks",), ["missing"], "Unknown network"),
    (("networks",), ["broker_parallel_1"], "Phase 8"),
    (("networks",), ["pair", "pair"], "at most once"),
    (("knowledge",), ["full_map", "full_map"], "at most once"),
    (("knowledge",), ["local"], "full_map"),
    (("assignments", 0, "default"), "missing", "Unknown model alias"),
    (("assignments", 0, "per_network"), {"line7": {"A": "terra"}}, "not listed"),
    (("assignments", 0, "per_network"), {"line3": {"Z": "terra"}}, "node or node-class"),
    (("assignments", 0, "per_network"), {"line3": {"B": "missing"}}, "Unknown model alias"),
    (("assignments", 0, "per_network"), {"line3": {"A|C": "terra", "A": "luna"}}, "Conflicting"),
    (("blocks",), [], "Extra inputs"),
    (("budget_usd",), 1.0, "Extra inputs"),
    (("budget_usd",), None, "Extra inputs"),
    (("settings", "typo"), 1, "Extra inputs"),
    (("models", "terra", "typo"), 1, "Extra inputs"),
    (("assignments", 0, "typo"), 1, "Extra inputs"),
    (("assignments", 0, "name"), "bad/name", "pattern"),
    (("assignments", 0, "name"), "bad name", "pattern"),
    (("name",), "Bad", "pattern"),
    (("settings", "phases"), 2, "3"),
    (("settings", "phase3_accept_only"), False, "True"),
    (("settings", "rounds"), 0, "greater than or equal to 1"),
    (("settings", "episodes_per_condition"), 0, "greater than or equal to 1"),
]


@pytest.mark.parametrize("path,value,message", INVALID)
def test_validation_errors(path: tuple[str | int, ...], value: Any, message: str) -> None:
    """Typos, unsupported protocols, and conflicting assignments fail clearly."""
    data = _data()
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValidationError, match=message):
        ExperimentConfig.model_validate(data)


def test_duplicate_assignments() -> None:
    """Two assignments cannot produce the same condition key."""
    data = _data()
    data["assignments"] *= 2
    with pytest.raises(ValidationError, match="Assignment names must be unique"):
        ExperimentConfig.model_validate(data)


def test_config_file_names_and_duplicate_configs(tmp_path: Path) -> None:
    """A config must match its file name and cannot be loaded twice."""
    wrong = tmp_path / "wrong.yaml"
    wrong.write_text(yaml.safe_dump(_data()), encoding="utf-8")
    with pytest.raises(ValueError, match="must match file name"):
        load_config(wrong)
    path = ROOT / "configs" / "minimum_study.yaml"
    with pytest.raises(ValueError, match="Config names must be unique"):
        load_configs([path, path])
