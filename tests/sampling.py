"""Deterministic test sampling for quick broad runs (`pytest --sample PERCENT`)."""

import hashlib
import json
import random
from pathlib import Path

STATE_FILE = ".pytest-sample-seed.json"


def keep(nodeid: str, percent: float, seed: int) -> bool:
    """Return whether a test is in the sample; the same answer in every xdist worker."""
    digest = hashlib.sha256(f"{seed}:{nodeid}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64 * 100 < percent


def choose_seed(root: Path, percent: float) -> tuple[int, bool]:
    """Reuse the seed of a sampled run that did not pass; otherwise draw a new one."""
    try:
        state = json.loads((root / STATE_FILE).read_text())
        if state["percent"] == percent:
            return int(state["seed"]), True
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return random.SystemRandom().randrange(10**6), False


def record_outcome(root: Path, percent: float, seed: int, passed: bool) -> None:
    """A passing run clears the seed so the next run samples afresh; any other keeps it."""
    path = root / STATE_FILE
    if passed:
        path.unlink(missing_ok=True)
    else:
        path.write_text(json.dumps({"percent": percent, "seed": seed}))
