"""Stable seeds for configs, conditions, episodes, and later random streams."""

import hashlib
import json

import numpy as np


def derive_seed(parent: int, *labels: str | int) -> int:
    """Hash a typed, ordered JSON sequence to an integer in [0, 2**63).

    JSON distinguishes strings from integers and records sequence boundaries.
    Its encoding here is independent of Python's process-specific hash seed.
    """
    if type(parent) is not int:
        raise TypeError("The parent seed must be an integer.")
    if any(type(label) not in (str, int) for label in labels):
        raise TypeError("Seed labels must be strings or integers.")
    encoded = json.dumps(["seed-v1", parent, list(labels)],
                         ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    return int.from_bytes(hashlib.sha256(encoded).digest(), "big") % (2**63)


def make_rng(seed: int) -> np.random.Generator:
    """Create a fresh NumPy generator from an explicit seed."""
    return np.random.default_rng(seed)
