"""Validated YAML configs and deterministic expansion into conditions."""

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator
import yaml

from .networks import Network, get_network
from .seeds import derive_seed
from .structure import class_label, node_classes

KnowledgeSetting = Literal["full_map", "own_links"]


class _ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ModelSpec(_ConfigModel):
    """Provider, decoding settings, and per-million-token prices for one alias."""

    provider: Literal["openai"]
    model_id: str
    reasoning_effort: Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"] = "none"
    max_completion_tokens: int = Field(default=300, ge=1)
    temperature: float | None = None
    price_input_per_m: float = Field(ge=0, allow_inf_nan=False)
    price_cached_input_per_m: float = Field(ge=0, allow_inf_nan=False)
    price_output_per_m: float = Field(ge=0, allow_inf_nan=False)
    price_cache_write_per_m: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    prompt_cache: Literal["off", "implicit"] = "off"
    timeout_s: float = Field(default=60.0, gt=0, allow_inf_nan=False)


class ModelAssignment(_ConfigModel):
    """A default model alias, with optional overrides by node or node class."""

    name: str = Field(pattern=r"^[a-z0-9_]+$")
    default: str
    per_network: dict[str, dict[str, str]] = Field(default_factory=dict)


class GameSettings(_ConfigModel):
    """Game settings shared by every condition in a config."""

    rounds: int = Field(default=12, ge=1)
    phases: Literal[3] = 3
    phase3_accept_only: Literal[True] = True
    episodes_per_condition: int = Field(default=10, ge=1)
    framing: Literal["neutral"] = "neutral"
    communication: Literal["none"] = "none"
    prompt_version: str = "v1"
    outcome_window: Literal["second_half"] = "second_half"


def _resolve_models(net: Network, assignment: ModelAssignment,
                    aliases: set[str]) -> dict[str, str]:
    if assignment.default not in aliases:
        raise ValueError(f"Unknown model alias {assignment.default!r} in assignment "
                         f"{assignment.name!r}.")
    classes = {class_label(members): members for members in node_classes(net)}
    overrides: dict[str, str] = {}
    for label, alias in assignment.per_network.get(net.id, {}).items():
        if alias not in aliases:
            raise ValueError(f"Unknown model alias {alias!r} in {net.id!r}.")
        if label in net.nodes:
            members = (label,)
        elif label in classes:
            members = classes[label]
        else:
            raise ValueError(f"Unknown node or node-class label {label!r} "
                             f"in network {net.id!r}.")
        for node in members:
            if node in overrides and overrides[node] != alias:
                raise ValueError(f"Conflicting overrides for node {node!r} "
                                 f"in network {net.id!r}.")
            overrides[node] = alias
    return {node: overrides.get(node, assignment.default) for node in net.nodes}


class ExperimentConfig(_ConfigModel):
    """One config: all network × knowledge setting × assignment combinations."""

    name: str = Field(pattern=r"^[a-z0-9_]+$")
    description: str = ""
    seed: int = Field(ge=0)
    models: dict[str, ModelSpec] = Field(min_length=1)
    networks: list[str] = Field(min_length=1)
    knowledge: list[KnowledgeSetting] = Field(min_length=1)
    assignments: list[ModelAssignment] = Field(min_length=1)
    settings: GameSettings = Field(default_factory=GameSettings)
    _source_sha256: str | None = PrivateAttr(default=None)

    @property
    def source_sha256(self) -> str:
        """Hash the loaded file bytes, or canonical JSON for an in-memory config."""
        if self._source_sha256 is not None:
            return self._source_sha256
        import json

        data = json.dumps(self.model_dump(), sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(data).hexdigest()

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        """Check registry references, aliases, uniqueness, and override conflicts."""
        if len(set(self.networks)) != len(self.networks):
            raise ValueError("A network may appear at most once in networks.")
        if len(set(self.knowledge)) != len(self.knowledge):
            raise ValueError("A knowledge setting may appear at most once in knowledge.")
        names = [assignment.name for assignment in self.assignments]
        if len(set(names)) != len(names):
            raise ValueError("Assignment names must be unique within a config.")
        networks = []
        for identifier in self.networks:
            try:
                net = get_network(identifier)
            except KeyError:
                raise ValueError(f"Unknown network ID: {identifier!r}.") from None
            if net.kind == "broker":
                raise ValueError("Broker networks are not supported by configs yet; "
                                 "the broker protocol arrives in Phase 8.")
            networks.append(net)
        for assignment in self.assignments:
            for identifier in assignment.per_network:
                if identifier not in self.networks:
                    raise ValueError(f"per_network entry {identifier!r} is not listed "
                                     "in networks.")
            for net in networks:
                _resolve_models(net, assignment, set(self.models))
        return self


@dataclass(frozen=True)
class Condition:
    """One resolved condition, with aliases for every node and explicit seeds."""

    key: str
    config_name: str
    network_id: str
    knowledge_setting: KnowledgeSetting
    assignment_name: str
    settings: GameSettings
    node_models: dict[str, str]
    condition_seed: int
    episode_seeds: list[int]


def load_config(path: str | Path) -> ExperimentConfig:
    """Load and validate a YAML config whose name must match its file stem."""
    path = Path(path)
    source = path.read_bytes()
    data = yaml.safe_load(source.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Config {path} must contain a YAML mapping.")
    config = ExperimentConfig.model_validate(data)
    if config.name != path.stem:
        raise ValueError(f"Config name {config.name!r} must match file name {path.stem!r}.")
    config._source_sha256 = hashlib.sha256(source).hexdigest()
    return config


def load_configs(paths: list[str | Path]) -> list[ExperimentConfig]:
    """Load several configs in order, rejecting duplicate config names."""
    configs = [load_config(path) for path in paths]
    names = [config.name for config in configs]
    if len(set(names)) != len(names):
        raise ValueError("Config names must be unique when loading several configs.")
    return configs


def expand_conditions(config: ExperimentConfig) -> list[Condition]:
    """Expand networks × knowledge × assignments, with networks varying slowest."""
    conditions = []
    for identifier in config.networks:
        net = get_network(identifier)
        for knowledge in config.knowledge:
            for assignment in config.assignments:
                key = f"{config.name}/{identifier}/{knowledge}/{assignment.name}"
                seed = derive_seed(config.seed, key)
                conditions.append(Condition(
                    key=key, config_name=config.name, network_id=identifier,
                    knowledge_setting=knowledge, assignment_name=assignment.name,
                    settings=config.settings,
                    node_models=_resolve_models(net, assignment, set(config.models)),
                    condition_seed=seed,
                    episode_seeds=[derive_seed(seed, "episode", i)
                                   for i in range(config.settings.episodes_per_condition)],
                ))
    return conditions


def total_episodes(config: ExperimentConfig) -> int:
    """Count all episodes across every condition in a config."""
    return (len(config.networks) * len(config.knowledge) * len(config.assignments)
            * config.settings.episodes_per_condition)
