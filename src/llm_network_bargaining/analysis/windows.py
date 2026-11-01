"""The registered outcome windows, using 1-based round numbers."""


def window_rounds(n_rounds: int, window: str = "second_half") -> range:
    """Return the rounds included in a primary, endgame-check or full window."""
    if n_rounds < 1:
        raise ValueError("n_rounds must be positive.")
    if window == "all":
        return range(1, n_rounds + 1)
    if window == "second_half":
        return range(n_rounds // 2 + 1, n_rounds + 1)
    if window == "second_half_no_last":
        return range(n_rounds // 2 + 1, n_rounds)
    raise ValueError(f"Unknown window: {window!r}.")
