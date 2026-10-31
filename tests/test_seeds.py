"""Seed derivation must not depend on Python's built-in hash function."""

import os
import subprocess
import sys

import pytest

from llm_network_bargaining.seeds import derive_seed, make_rng


def test_seed_labels_are_typed_ordered_and_delimited() -> None:
    """Distinct label types, orders, and boundaries produce distinct seeds."""
    sequences = [("a", "b"), ("b", "a"), ("ab",), ("a|b",), ("1",), (1,), (), ("",)]
    seeds = [derive_seed(20261106, *labels) for labels in sequences]
    assert len(set(seeds)) == len(seeds)
    assert all(0 <= seed < 2**63 for seed in seeds)
    assert derive_seed(20261106, "a", "b") == seeds[0]
    assert derive_seed(20261107, "a", "b") != seeds[0]
    assert derive_seed(0, "é", "雪") == derive_seed(0, "é", "雪")
    assert make_rng(seeds[0]).integers(1000, size=20).tolist() == make_rng(seeds[0]).integers(1000, size=20).tolist()


@pytest.mark.parametrize("hash_seed", ["0", "123", "random"])
def test_seed_survives_different_process_hash_seeds(hash_seed: str) -> None:
    """New processes with different hash randomisation derive the same seed."""
    code = "from llm_network_bargaining.seeds import derive_seed; print(derive_seed(42, 'episode', 3))"
    output = subprocess.check_output([sys.executable, "-c", code], text=True,
                                     env={**os.environ, "PYTHONHASHSEED": hash_seed})
    assert int(output) == derive_seed(42, "episode", 3)
