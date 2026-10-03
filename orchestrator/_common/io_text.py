"""Text reads that retain the digest of the bytes they decode."""

from __future__ import annotations

from hashlib import sha256
from io import BytesIO, TextIOWrapper
from pathlib import Path


def read_text_with_sha256(
    path: Path,
    *,
    encoding: str | None = None,
) -> tuple[str, str]:
    """Read raw bytes once, then decode with Path.read_text text semantics."""

    raw = path.read_bytes()
    digest = "sha256:" + sha256(raw).hexdigest()
    with TextIOWrapper(BytesIO(raw), encoding=encoding) as source:
        return source.read(), digest
