"""Seeded display names, kept separate from the engine's canonical node IDs."""

from collections.abc import Mapping, Sequence

from .networks import Network
from .seeds import derive_seed, make_rng

NAME_POOL: tuple[str, ...] = (
    "Talin", "Orsa", "Pell", "Vash", "Bexa", "Calo", "Deni", "Fira",
    "Gorm", "Isko", "Jaro", "Kelt", "Lusa", "Mardo", "Nesh", "Oben",
    "Pira", "Rulo", "Sefi", "Tovi", "Ulan", "Veko", "Yara", "Zelo",
)


def _name_lookup(names: Mapping[str, str]) -> dict[str, str]:
    """Validate uniqueness and return case-insensitive display name -> node."""
    lookup = {}
    for node, name in names.items():
        key = name.casefold()
        if key in lookup:
            raise ValueError(f"Duplicate display name, ignoring case: {name!r}.")
        lookup[key] = node
    return lookup


def assign_names(network: Network, episode_seed: int,
                 pool: Sequence[str] = NAME_POOL) -> dict[str, str]:
    """Assign a distinct seeded name to every node, in canonical node order."""
    if len(network.nodes) > len(pool):
        raise ValueError("The network has more nodes than the display-name pool.")
    _name_lookup({str(i): name for i, name in enumerate(pool)})
    if {name.casefold() for name in pool}.intersection(node.casefold() for node in network.nodes):
        raise ValueError("Display names must not equal network node IDs.")
    rng = make_rng(derive_seed(episode_seed, "names"))
    indices = rng.choice(len(pool), size=len(network.nodes), replace=False)
    return {node: pool[int(indices[i])] for i, node in enumerate(network.nodes)}
