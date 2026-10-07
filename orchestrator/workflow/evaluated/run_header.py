"""Pure syntactic and structural checks for evaluated run headers."""

from __future__ import annotations

from collections.abc import Mapping
import json
import math
import os
from pathlib import Path, PurePosixPath
from typing import Any

from orchestrator.workflow.evaluated.interpreters import (
    _valid_digest,
    validate_command_interpreter_pin_shape,
)
from orchestrator.workflow.run_ref.contracts import canonical_json_bytes
from orchestrator.workflow_lisp.closed.program import REPRESENTATION

PROFILE = "evaluated_execution.v1"

SCHEMA_VERSION = "3.0"

_HEADER_FIELDS = {
    "schema_version", "result_persistence_profile", "run_id", "workflow_file",
    "workflow_checksum", "started_at", "program_digest", "input_digest",
    "bound_inputs", "representation", "interpreters",
}


class RunAuthorityError(ValueError):
    """An evaluated run lacks valid, mutually consistent authority."""

    code = "memo_inconsistent"

_RESUME_REQUEST_FIELDS = {
    "source_roots", "entry_workflow", "provider_externs_path", "prompt_externs_path",
    "imported_workflow_bundles_path", "command_boundaries_path", "input_file", "input_overrides",
}


def _validate_locator(value: object) -> None:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise RunAuthorityError("resume locator is empty or invalid")
    path = PurePosixPath(value)
    if not path.is_absolute() and ".." in path.parts:
        raise RunAuthorityError("resume locator is not normalized")
    if os.path.normpath(value) != value or value.startswith("//"):
        raise RunAuthorityError("resume locator is not canonical")
    if value.startswith("/dev/fd/") or (value.startswith("/proc/") and "fd" in path.parts):
        raise RunAuthorityError("process descriptor paths are not durable locators")


def _validate_run_ref_root(value: object) -> None:
    if not isinstance(value, str) or not PurePosixPath(value).is_absolute():
        raise RunAuthorityError("run-reference root is not an absolute locator")
    _validate_locator(value)
    path = PurePosixPath(value)
    if ".." in path.parts or value == "/dev/fd" or value.startswith("/dev/fd/"):
        raise RunAuthorityError("run-reference root is not a durable canonical path")


def _validate_result_root(value: object, run_id: object) -> None:
    """Check the workspace-relative run root by spelling only; no path IO."""
    if not isinstance(value, str) or not value or "\x00" in value:
        raise RunAuthorityError("result root is empty or invalid")
    if PurePosixPath(value).is_absolute() or os.path.normpath(value) != value:
        raise RunAuthorityError("result root is not a canonical relative path")
    if PurePosixPath(value).name != run_id:
        raise RunAuthorityError("result root does not end with the run id")


def _validate_json_value(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise RunAuthorityError("resume override keys are not strings")
            _validate_json_value(item)
    elif isinstance(value, list):
        for item in value:
            _validate_json_value(item)
    elif value is not None and type(value) not in (str, bool, int, float):
        raise RunAuthorityError("resume override is not JSON")
    elif isinstance(value, float) and not math.isfinite(value):
        raise RunAuthorityError("resume override is non-finite")


def _validate_requested_entry(entry: object) -> None:
    if not isinstance(entry, str) or not entry or "\x00" in entry:
        raise RunAuthorityError("requested entry is invalid")


def validate_resume_request(value: object) -> None:
    """Check the exact durable recipe without opening any of its locators."""
    if not isinstance(value, dict) or set(value) != _RESUME_REQUEST_FIELDS:
        raise RunAuthorityError("resume request has missing or unknown fields")
    if not isinstance(value["source_roots"], list):
        raise RunAuthorityError("resume source roots are not an array")
    for root in value["source_roots"]:
        _validate_locator(root)
    entry = value["entry_workflow"]
    if entry is not None:
        _validate_requested_entry(entry)
    for field in _RESUME_REQUEST_FIELDS - {"source_roots", "entry_workflow", "input_overrides"}:
        if value[field] is not None:
            _validate_locator(value[field])
    if not isinstance(value["input_overrides"], dict):
        raise RunAuthorityError("resume overrides are not an object")
    try:
        canonical_json_bytes(value)
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise RunAuthorityError("resume overrides are not finite transportable JSON") from exc
    _validate_json_value(value["input_overrides"])


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key {key!r}")
        value[key] = item
    return value


def _decode_header_json(payload: bytes) -> Any:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant {value}")

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=reject_constant,
        )
    except FileNotFoundError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise RunAuthorityError(f"invalid run header: {exc}") from exc
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise RunAuthorityError("run header contains a non-finite or non-JSON value") from exc
    return value


def _validate_header_shape(value: object) -> dict[str, Any]:
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise RunAuthorityError(
            "run header contains a non-finite or non-JSON value"
        ) from exc
    if not isinstance(value, dict):
        raise RunAuthorityError("run header has missing or unknown fields")
    fields = set(value)
    if not _HEADER_FIELDS <= fields or fields - (_HEADER_FIELDS | {"resume_request", "run_ref_root", "result_root"}):
        raise RunAuthorityError("run header has missing or unknown fields")
    if value.get("schema_version") != SCHEMA_VERSION:
        raise RunAuthorityError("unsupported evaluated run schema")
    if value.get("result_persistence_profile") != PROFILE:
        raise RunAuthorityError("unsupported result persistence profile")
    if "resume_request" in value:
        validate_resume_request(value["resume_request"])
        _validate_locator(value["workflow_file"])
    if "run_ref_root" in value:
        _validate_run_ref_root(value["run_ref_root"])
    if "result_root" in value:
        _validate_result_root(value["result_root"], value.get("run_id"))
    return value


def _validate_header_metadata(run_root: Path, header: Mapping[str, Any]) -> None:
    for field in ("workflow_file", "workflow_checksum", "started_at"):
        if not isinstance(header[field], str) or not header[field]:
            raise ValueError(f"{field} is missing")
    if header["run_id"] != run_root.name:
        raise ValueError("run id differs from its root")
    for field in ("program_digest", "input_digest"):
        if not _valid_digest(header[field]):
            raise ValueError(f"{field} is invalid")
    if header["representation"] != REPRESENTATION:
        raise ValueError("unsupported program representation")
    if not isinstance(header["bound_inputs"], dict) or not isinstance(header["interpreters"], dict):
        raise ValueError("bound inputs or interpreter pins are not objects")
    for pin in header["interpreters"].values():
        validate_command_interpreter_pin_shape(pin)
