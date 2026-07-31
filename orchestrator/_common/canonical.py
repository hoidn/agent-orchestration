"""Canonical JSON mechanics shared by byte-compatible internal records."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json_dumps(value: Any) -> str:
    """Return compact, sorted, ASCII JSON with the historical string fallback."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )


def sha256_json(value: Any) -> str:
    """Return the historical full prefixed digest of canonical JSON bytes."""
    canonical_bytes = canonical_json_dumps(value).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical_bytes).hexdigest()}"
