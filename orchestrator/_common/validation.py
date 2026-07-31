"""Scalar validation mechanics shared by byte-compatible internal records."""

from __future__ import annotations

from collections.abc import Mapping, Set
from typing import Any, cast


def closed_mapping(
    value: object,
    keys: Set[str],
    field: str,
) -> Mapping[str, Any]:
    """Return an exact-key mapping or raise an audited closed-object error."""
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ValueError(
            f"{field} must be a closed object with keys {sorted(keys)}"
        )
    return cast(Mapping[str, Any], value)


def nonempty_string(
    value: object,
    field: str,
) -> str:
    """Return a nonempty string or raise the shared typed diagnostic."""
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def ordinary_integer(
    value: object,
    field: str,
    *,
    minimum: int,
) -> int:
    """Return a non-bool integer at ``minimum`` with an audited diagnostic."""
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{field} must be an integer >= {minimum}")
    return value
