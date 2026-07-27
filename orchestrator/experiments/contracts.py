"""Canonical serialization and validation for lean-pilot records."""

from __future__ import annotations

import hashlib
import json
import math
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError


_SCHEMA_PACKAGE = "orchestrator.experiments.schemas"
_SCHEMA_NAME = "lean-pilot-records-v1.schema.json"


class PilotContractError(ValueError):
    """A value does not satisfy the lean-pilot record contract."""


def _value_path(path: tuple[str | int, ...]) -> str:
    rendered = "$"
    for component in path:
        if isinstance(component, int):
            rendered += f"[{component}]"
        else:
            rendered += f".{component}"
    return rendered


def _reject_noncanonical(
    value: object,
    path: tuple[str | int, ...] = (),
) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        raise PilotContractError(
            f"{_value_path(path)}: floating-point values are not permitted"
        )
    if isinstance(value, dict):
        for key, nested_value in value.items():
            if not isinstance(key, str):
                raise PilotContractError(
                    f"{_value_path(path)}: mapping keys must be strings"
                )
            _reject_noncanonical(nested_value, (*path, key))
        return
    if isinstance(value, list):
        for index, nested_value in enumerate(value):
            _reject_noncanonical(nested_value, (*path, index))
        return
    raise PilotContractError(
        f"{_value_path(path)}: {type(value).__name__} is not a JSON value"
    )


def canonical_json_bytes(value: object) -> bytes:
    """Return deterministic compact UTF-8 JSON after strict value checks."""

    _reject_noncanonical(value)
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def canonical_sha256(value: object) -> str:
    """Return the canonical JSON SHA-256 digest for *value*."""

    digest = hashlib.sha256(canonical_json_bytes(value)).hexdigest()
    return f"sha256:{digest}"


@lru_cache(maxsize=1)
def _load_schema() -> dict[str, Any]:
    schema_path = resources.files(_SCHEMA_PACKAGE).joinpath(_SCHEMA_NAME)
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    if not isinstance(schema, dict):
        raise PilotContractError("packaged lean-pilot schema is not an object")
    return schema


def _validation_error_key(
    error: ValidationError,
) -> tuple[tuple[tuple[int, int | str], ...], str]:
    path = tuple(
        (0, component) if isinstance(component, int) else (1, str(component))
        for component in error.absolute_path
    )
    return path, error.message


def _format_validation_error(error: ValidationError) -> str:
    path = _value_path(tuple(error.absolute_path))
    return f"{path}: {error.message}"


def _validate_reduced_summary_fractions(record: dict[str, Any]) -> None:
    for collection_name in ("medians", "ratios"):
        for index, item in enumerate(record[collection_name]):
            value = item["value"]
            if value == "UNKNOWN":
                continue
            numerator = value["numerator"]
            denominator = value["denominator"]
            if math.gcd(numerator, denominator) != 1:
                path = _value_path((collection_name, index, "value"))
                raise PilotContractError(f"{path}: fraction must be reduced")


def validate_record(record: object) -> None:
    """Validate one of the four exact lean-pilot record kinds."""

    _reject_noncanonical(record)
    if not isinstance(record, dict):
        raise PilotContractError("$: record must be an object")

    record_kind = record.get("record_kind")
    schema = _load_schema()
    definitions = schema.get("$defs")
    if not isinstance(record_kind, str) or not isinstance(definitions, dict):
        raise PilotContractError("$.record_kind: unsupported record_kind")
    record_schema = definitions.get(record_kind)
    if not isinstance(record_schema, dict):
        raise PilotContractError(
            f"$.record_kind: unsupported record_kind {record_kind!r}"
        )

    errors = sorted(
        Draft202012Validator(record_schema).iter_errors(record),
        key=_validation_error_key,
    )
    if errors:
        details = "\n".join(_format_validation_error(error) for error in errors)
        raise PilotContractError(f"record validation failed:\n{details}")

    if record_kind == "pilot_summary.v1":
        _validate_reduced_summary_fractions(record)


def load_record(
    path: str | Path,
    *,
    expected_kind: str,
) -> dict[str, Any]:
    """Load strict JSON, require *expected_kind*, and validate the record."""

    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PilotContractError(f"{path}: invalid JSON: {exc.msg}") from exc

    _reject_noncanonical(value)
    if not isinstance(value, dict):
        raise PilotContractError("$: record must be an object")
    actual_kind = value.get("record_kind")
    if actual_kind != expected_kind:
        raise PilotContractError(
            f"$.record_kind: expected {expected_kind!r}, got {actual_kind!r}"
        )
    validate_record(value)
    return value
