"""Deterministic token estimation and prefix truncation.

The whole system uses ``estimate_tokens`` (chars / 4) so that window checks,
compaction budgets and stub previews all speak the same unit.
"""


def estimate_tokens(text: str) -> int:
    """Deterministic token estimate: max(1, (len(text) + 3) // 4) if text else 0."""
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def prefix_until_tokens(text: str, max_tokens: int) -> tuple[str, bool]:
    """Return the smallest char prefix reaching ``max_tokens`` tokens.

    If the whole text already fits, return ``(text, False)``. If max_tokens is
    not positive, return ``('', bool(text))``. Otherwise binary-search the
    smallest prefix whose token estimate is >= max_tokens and return it with a
    True flag (meaning the text was truncated).
    """
    if estimate_tokens(text) <= max_tokens:
        return (text, False)
    if max_tokens <= 0:
        return ("", bool(text))
    # Binary search the smallest prefix with estimate_tokens(prefix) >= max_tokens.
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi) // 2
        if estimate_tokens(text[:mid]) >= max_tokens:
            hi = mid
        else:
            lo = mid + 1
    return (text[:lo], True)
