"""Workflow Lisp G6 verification gate manifest loader."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


G6_VERIFICATION_GATE_SCHEMA_VERSION = "workflow_lisp_g6_verification_gate.v1"
DEFAULT_GATE_RELPATH = "docs/workflow_lisp_g6_verification_gate.json"

SCOPE_CLASS_VALUES = frozenset({"proving_surface", "tranche_owned_shared"})
BUILTIN_STDLIB_STATUS_VALUES = frozenset({"landed", "stub", "pending"})


@dataclass(frozen=True)
class CountedSuiteRow:
    suite: str
    scope_class: str
    reason: str


@dataclass(frozen=True)
class BuiltinStdlibInventoryRow:
    module: str
    status: str
    owner: str


@dataclass(frozen=True)
class LaterTrancheSuiteRow:
    suite: str
    owner: str
    reason: str


@dataclass(frozen=True)
class VerificationGate:
    schema_version: str
    counted_suites: tuple[CountedSuiteRow, ...]
    builtin_stdlib_inventory: tuple[BuiltinStdlibInventoryRow, ...]
    later_tranche_suites: tuple[LaterTrancheSuiteRow, ...]
    path: Path | None = None


def load_verification_gate(path: Path | None = None) -> VerificationGate:
    """Load and schema-validate the checked-in G6 verification gate manifest."""

    manifest_path = path or (Path(__file__).resolve().parents[2] / DEFAULT_GATE_RELPATH)
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in `{manifest_path}`: {exc}") from exc
    except OSError as exc:
        raise ValueError(f"unable to read verification gate `{manifest_path}`: {exc}") from exc

    if not isinstance(payload, Mapping):
        raise ValueError("verification gate must be a JSON object")

    _require_exact_keys(
        payload,
        {
            "schema_version",
            "counted_suites",
            "builtin_stdlib_inventory",
            "later_tranche_suites",
        },
        field_path="",
    )
    if payload.get("schema_version") != G6_VERIFICATION_GATE_SCHEMA_VERSION:
        raise ValueError(f"schema_version must equal {G6_VERIFICATION_GATE_SCHEMA_VERSION}")

    return VerificationGate(
        schema_version=G6_VERIFICATION_GATE_SCHEMA_VERSION,
        counted_suites=_parse_counted_suites(payload.get("counted_suites"), field_path="counted_suites"),
        builtin_stdlib_inventory=_parse_builtin_inventory(
            payload.get("builtin_stdlib_inventory"),
            field_path="builtin_stdlib_inventory",
        ),
        later_tranche_suites=_parse_later_tranche_suites(
            payload.get("later_tranche_suites"),
            field_path="later_tranche_suites",
        ),
        path=manifest_path.resolve(),
    )


def counted_suite_paths(gate: VerificationGate) -> tuple[str, ...]:
    """Return the counted suite paths declared by a loaded verification gate."""

    return tuple(row.suite for row in gate.counted_suites)


def available_builtin_modules(gate: VerificationGate) -> tuple[str, ...]:
    """Return builtin stdlib modules declared available to counted suites."""

    return tuple(row.module for row in gate.builtin_stdlib_inventory if row.status in {"landed", "stub"})


def _parse_counted_suites(value: Any, *, field_path: str) -> tuple[CountedSuiteRow, ...]:
    rows = _require_list(value, field_path=field_path)
    parsed: list[CountedSuiteRow] = []
    for index, raw_row in enumerate(rows):
        row_path = f"{field_path}[{index}]"
        mapping = _require_mapping(raw_row, field_path=row_path)
        _require_exact_keys(mapping, {"suite", "scope_class", "reason"}, field_path=row_path)
        suite = _require_non_empty_string(mapping.get("suite"), field_path=f"{row_path}.suite")
        scope_class = _require_choice(
            mapping.get("scope_class"),
            choices=SCOPE_CLASS_VALUES,
            field_path=f"{row_path}.scope_class",
        )
        reason = _require_non_empty_string(mapping.get("reason"), field_path=f"{row_path}.reason")
        parsed.append(CountedSuiteRow(suite=suite, scope_class=scope_class, reason=reason))
    return tuple(parsed)


def _parse_builtin_inventory(
    value: Any,
    *,
    field_path: str,
) -> tuple[BuiltinStdlibInventoryRow, ...]:
    rows = _require_list(value, field_path=field_path)
    parsed: list[BuiltinStdlibInventoryRow] = []
    for index, raw_row in enumerate(rows):
        row_path = f"{field_path}[{index}]"
        mapping = _require_mapping(raw_row, field_path=row_path)
        _require_exact_keys(mapping, {"module", "status", "owner"}, field_path=row_path)
        module = _require_non_empty_string(mapping.get("module"), field_path=f"{row_path}.module")
        status = _require_choice(
            mapping.get("status"),
            choices=BUILTIN_STDLIB_STATUS_VALUES,
            field_path=f"{row_path}.status",
        )
        owner = _require_non_empty_string(mapping.get("owner"), field_path=f"{row_path}.owner")
        parsed.append(BuiltinStdlibInventoryRow(module=module, status=status, owner=owner))
    return tuple(parsed)


def _parse_later_tranche_suites(value: Any, *, field_path: str) -> tuple[LaterTrancheSuiteRow, ...]:
    rows = _require_list(value, field_path=field_path)
    parsed: list[LaterTrancheSuiteRow] = []
    for index, raw_row in enumerate(rows):
        row_path = f"{field_path}[{index}]"
        mapping = _require_mapping(raw_row, field_path=row_path)
        _require_exact_keys(mapping, {"suite", "owner", "reason"}, field_path=row_path)
        suite = _require_non_empty_string(mapping.get("suite"), field_path=f"{row_path}.suite")
        owner = _require_non_empty_string(mapping.get("owner"), field_path=f"{row_path}.owner")
        reason = _require_non_empty_string(mapping.get("reason"), field_path=f"{row_path}.reason")
        parsed.append(LaterTrancheSuiteRow(suite=suite, owner=owner, reason=reason))
    return tuple(parsed)


def _require_exact_keys(value: Mapping[str, Any], expected_keys: set[str], *, field_path: str) -> None:
    unknown_keys = sorted(set(value) - expected_keys)
    if unknown_keys:
        prefix = f"{field_path}." if field_path else ""
        raise ValueError(f"{prefix}{unknown_keys[0]} is not allowed")
    missing_keys = sorted(expected_keys - set(value))
    if missing_keys:
        prefix = f"{field_path}." if field_path else ""
        raise ValueError(f"{prefix}{missing_keys[0]} is required")


def _require_mapping(value: Any, *, field_path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_path} must be an object")
    return value


def _require_list(value: Any, *, field_path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{field_path} must be an array")
    return value


def _require_non_empty_string(value: Any, *, field_path: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_path} must be a non-empty string")
    return value


def _require_choice(value: Any, *, choices: frozenset[str], field_path: str) -> str:
    value = _require_non_empty_string(value, field_path=field_path)
    if value not in choices:
        raise ValueError(f"{field_path} must be one of {sorted(choices)}")
    return value
