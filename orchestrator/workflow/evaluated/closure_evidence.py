"""Canonical keys and strict rows for evaluated command evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


_BASES = {"workspace", "absolute", "package:orchestrator"}


def command_evidence_key(base: str, path: str, position: int | None = None) -> str:
    """Return the one canonical spelling for a logical evidence identity."""

    if not _valid_base(base) or not _valid_key_path(base, path):
        raise ValueError("implementation evidence key is malformed")
    if position is not None and not _valid_position(position):
        raise ValueError("implementation evidence key is malformed")
    value = json.dumps([base, path, position], ensure_ascii=False,
                       separators=(",", ":"), allow_nan=False)
    value.encode("utf-8")
    return value


def parse_command_evidence_key(value: str) -> tuple[str, str, int | None]:
    try:
        raw = json.loads(value)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("implementation evidence key is not canonical JSON") from exc
    if not isinstance(raw, list) or len(raw) != 3 or not _valid_base(raw[0]):
        raise ValueError("implementation evidence key is malformed")
    base, path, position = raw
    if not _valid_key_path(base, path) or (
        position is not None and not _valid_position(position)
    ):
        raise ValueError("implementation evidence key is malformed")
    if command_evidence_key(base, path, position) != value:
        raise ValueError("implementation evidence key is not canonical JSON")
    return base, path, position


def validate_implementation_evidence(value: Any) -> dict[str, dict[str, Any]]:
    """Validate an ordinary evidence map and return it in canonical key order."""

    if not isinstance(value, dict):
        raise ValueError("implementation evidence is not an object")
    checked: dict[str, dict[str, Any]] = {}
    for key, row in value.items():
        base, _path, _position = parse_command_evidence_key(key)
        checked[key] = _checked_row(row, base)
    return {key: checked[key] for key in sorted(checked)}


def target_spelling(
    path: Path, base: str, workspace_root: Path, package_root: Path
) -> str:
    """Encode one resolved target relative to its declared logical base."""

    root = workspace_root if base == "workspace" else package_root
    if base == "absolute":
        return str(path)
    try:
        relative = path.relative_to(root).as_posix() or "."
    except ValueError:
        return str(path)
    return f"package:orchestrator/{relative}" if base == "package:orchestrator" else relative


def _checked_row(row: Any, base: str) -> dict[str, Any]:
    if not isinstance(row, dict) or not {"kind", "digest"}.issubset(row):
        raise ValueError("implementation evidence row is malformed")
    if set(row) - {"kind", "digest", "target"}:
        raise ValueError("implementation evidence row is malformed")
    if not isinstance(row["kind"], str) or row["kind"] not in {"file", "directory"}:
        raise ValueError("implementation evidence kind is invalid")
    if not _valid_digest(row["digest"]):
        raise ValueError("implementation evidence digest is invalid")
    if "target" in row:
        _validate_target(row["target"], base)
    return {name: row[name] for name in sorted(row)}


def _valid_base(value: Any) -> bool:
    return isinstance(value, str) and value in _BASES


def _valid_key_path(base: str, value: Any) -> bool:
    if not isinstance(value, str) or not value or "\x00" in value:
        return False
    absolute = base == "absolute"
    return value.startswith("/") == absolute and _normalize_path(value, absolute) == value


def _normalize_path(value: str, absolute: bool) -> str:
    parts = [part for part in value.split("/") if part not in {"", "."}]
    joined = "/".join(parts)
    return f"/{joined}" if absolute and joined else "/" if absolute else joined or "."


def _valid_position(value: Any) -> bool:
    return type(value) is int and value >= 0


def _valid_digest(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 71
        and value.startswith("sha256:")
        and all(char in "0123456789abcdef" for char in value[7:])
    )


def _validate_target(value: Any, base: str) -> None:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError("implementation evidence target is malformed")
    absolute = _valid_resolved_absolute(value)
    if base == "workspace":
        valid = absolute or _valid_resolved_relative(value)
    elif base == "package:orchestrator":
        valid = absolute or (
            value.startswith("package:orchestrator/")
            and _valid_resolved_relative(value.removeprefix("package:orchestrator/"))
        )
    else:
        valid = absolute
    if not valid:
        raise ValueError("implementation evidence target is malformed")


def _valid_resolved_relative(value: str) -> bool:
    return value == "." or (
        bool(value)
        and all(part not in {"", ".", ".."} for part in value.split("/"))
    )


def _valid_resolved_absolute(value: str) -> bool:
    return value.startswith("/") and ".." not in value.split("/") and (
        _normalize_path(value, absolute=True) == value
    )


__all__ = [
    "command_evidence_key",
    "parse_command_evidence_key",
    "target_spelling",
    "validate_implementation_evidence",
]
