"""Deterministic test sampling for quick broad runs (`pytest --sample PERCENT`)."""

import hashlib


def keep(nodeid: str, percent: float, seed: int) -> bool:
    """Return whether a test is in the sample; the same answer in every xdist worker."""
    digest = hashlib.sha256(f"{seed}:{nodeid}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64 * 100 < percent
