"""Managed-job identity hashing."""

from __future__ import annotations

import hashlib
import json
from typing import Mapping, Sequence


def compute_job_identity_hash(
    *,
    argv: Sequence[str],
    source_hashes: Mapping[str, str],
    config_hashes: Mapping[str, str],
    extractor_id: str,
    extractor_version: str,
    policy_entry_hash: str,
    snapshot_inputs: Sequence[str],
) -> str:
    """Return a stable short identity hash for one managed job."""

    payload = {
        "argv": list(argv),
        "source_hashes": dict(sorted(source_hashes.items())),
        "config_hashes": dict(sorted(config_hashes.items())),
        "extractor_id": extractor_id,
        "extractor_version": extractor_version,
        "policy_entry_hash": policy_entry_hash,
        "snapshot_inputs": list(snapshot_inputs),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]
