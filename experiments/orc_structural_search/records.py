"""Append-only JSONL records and Workflow Lisp structural metrics."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from experiments.orc_structural_search.record_normalization import (
    CONTROL_HEADS,
    control_heads,
    provider_allocation,
    skeleton_hash,
)

UNAVAILABLE = "unavailable"


def append_record(log: Path, record: Mapping[str, object]) -> None:
    """Append `record` to `log` as one JSON line with sorted keys.

    Missing receipts are the caller's string "unavailable" and are written
    verbatim; nothing here substitutes zero.
    """
    with log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(dict(record), sort_keys=True) + "\n")


def read_records(log: Path) -> list[dict]:
    """Return every record in `log`, in append order."""
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]
