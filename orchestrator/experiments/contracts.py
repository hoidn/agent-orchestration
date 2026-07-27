"""Canonical serialization and validation for lean-pilot records."""

from __future__ import annotations

import hashlib
import json
import math
from functools import lru_cache
from fractions import Fraction
from importlib import resources
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from ._contracts_pilot_lock import validate_pilot_lock


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


def _validate_summary_semantics(record: dict[str, Any]) -> None:
    valid_blocks = record["valid_blocks"]
    valid_ids = [block["block_id"] for block in valid_blocks]
    valid_id_set = set(valid_ids)
    if len(valid_id_set) != len(valid_ids):
        raise PilotContractError("$.valid_blocks: block_id values must be unique")
    excluded_ids = [
        block["block_id"] for block in record["excluded_block_references"]
    ]
    if (
        len(set(excluded_ids)) != len(excluded_ids)
        or valid_id_set.intersection(excluded_ids)
    ):
        raise PilotContractError(
            "$.excluded_block_references: block_id coverage is inconsistent"
        )

    outcome_keys = {
        "A_WIN": "a_win_count",
        "B_WIN": "b_win_count",
        "TIE": "tie_count",
        "INDETERMINATE": "indeterminate_count",
        "TIE_NONVIABLE": "tie_nonviable_count",
    }
    observed_comparisons: dict[str, dict[str, int]] = {}
    for block in valid_blocks:
        for outcome in block["method_outcomes"]:
            counts = observed_comparisons.setdefault(
                outcome["comparison"],
                {key: 0 for key in outcome_keys.values()},
            )
            counts[outcome_keys[outcome["method_outcome"]]] += 1
    for row in record["comparison_counts"]:
        observed = observed_comparisons.get(
            row["comparison"],
            {key: 0 for key in outcome_keys.values()},
        )
        if any(row[key] != observed[key] for key in outcome_keys.values()):
            raise PilotContractError(
                "$.comparison_counts: counts must match valid block outcomes"
            )

    valid_count = len(valid_blocks)
    failure_classes = (
        "BLOCKED",
        "EXHAUSTED",
        "PROTOCOL_FAILURE",
        "LAUNCH_FAILURE",
        "TIMEOUT",
        "NONZERO_EXIT",
        "CHECK_FAILURE",
    )
    for statistic in record["treatment_statistics"]:
        lifecycle = statistic["lifecycle_outcome_counts"]
        failures = statistic["failure_class_counts"]
        if (
            statistic["viable_count"] + statistic["nonviable_count"]
            != valid_count
            or sum(lifecycle.values()) != valid_count
            or statistic["viable_count"] != lifecycle["COMPLETED"]
            or statistic["nonviable_count"]
            != sum(lifecycle[key] for key in failure_classes)
            or any(failures[key] != lifecycle[key] for key in failure_classes)
            or len(statistic["provider_call_counts"]) != valid_count
        ):
            raise PilotContractError(
                "$.treatment_statistics: aggregate counts are inconsistent"
            )

    diagnostics = record["review_diagnostics"]
    diagnostic_ids = [block["block_id"] for block in diagnostics["blocks"]]
    if len(set(diagnostic_ids)) != len(diagnostic_ids) or set(
        diagnostic_ids
    ) != valid_id_set:
        raise PilotContractError(
            "$.review_diagnostics.blocks: coverage must match valid blocks"
        )
    comparison_capacity = valid_count * 2
    if (
        diagnostics["agreement_count"] + diagnostics["disagreement_count"]
        > comparison_capacity
        or diagnostics["adjudication_count"]
        > diagnostics["disagreement_count"]
    ):
        raise PilotContractError(
            "$.review_diagnostics: comparison counts are inconsistent"
        )
    adjudicator_blocks = sum(
        "adjudicator_review_reference" in block
        for block in diagnostics["blocks"]
    )
    if (
        (adjudicator_blocks == 0 and diagnostics["adjudication_count"] != 0)
        or diagnostics["adjudication_count"] < adjudicator_blocks
        or diagnostics["adjudication_count"] > adjudicator_blocks * 2
    ):
        raise PilotContractError(
            "$.review_diagnostics: adjudication count is inconsistent"
        )

    guess_cells = diagnostics["guess_confusion"]
    expected_guess_cells = {
        (actual, guessed)
        for actual in ("DIRECT", "COORDINATOR", "ORC")
        for guessed in ("DIRECT", "COORDINATOR", "ORC", "UNKNOWN")
    }
    observed_guess_cells = {
        (cell["actual_treatment_id"], cell["guessed_treatment_id"])
        for cell in guess_cells
    }
    if observed_guess_cells != expected_guess_cells:
        raise PilotContractError(
            "$.review_diagnostics.guess_confusion: cells must be exact"
        )
    total_guesses = sum(cell["count"] for cell in guess_cells)
    correct_guesses = sum(
        cell["count"]
        for cell in guess_cells
        if cell["actual_treatment_id"] == cell["guessed_treatment_id"]
    )
    accuracy = diagnostics["guess_accuracy"]
    if total_guesses == 0:
        if accuracy != "UNKNOWN":
            raise PilotContractError(
                "$.review_diagnostics.guess_accuracy: must be UNKNOWN"
            )
    else:
        expected_accuracy = {
            "numerator": Fraction(correct_guesses, total_guesses).numerator,
            "denominator": Fraction(correct_guesses, total_guesses).denominator,
        }
        if accuracy != expected_accuracy:
            raise PilotContractError(
                "$.review_diagnostics.guess_accuracy: fraction is inconsistent"
            )

    metrics = {
        "elapsed_milliseconds",
        "cost_microunits",
        "input_tokens",
        "output_tokens",
    }
    treatments = {"DIRECT", "COORDINATOR", "ORC"}
    median_rows = {
        (row["metric"], row["treatment_id"]) for row in record["medians"]
    }
    if median_rows != {
        (metric, treatment)
        for metric in metrics
        for treatment in treatments
    }:
        raise PilotContractError("$.medians: metric rows must be exact")
    ratio_rows = {
        (
            row["metric"],
            row["numerator_treatment_id"],
            row["denominator_treatment_id"],
        )
        for row in record["ratios"]
    }
    if ratio_rows != {
        (metric, "ORC", denominator)
        for metric in metrics
        for denominator in ("DIRECT", "COORDINATOR")
    }:
        raise PilotContractError("$.ratios: metric rows must be exact")

    finding_keys = [
        (finding["block_id"], finding["treatment_id"])
        for finding in record["hard_contract_findings"]
    ]
    if len(set(finding_keys)) != len(finding_keys) or any(
        block_id not in valid_id_set for block_id, _treatment in finding_keys
    ):
        raise PilotContractError(
            "$.hard_contract_findings: finding coverage is inconsistent"
        )


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

    if record_kind == "pilot_lock.v1":
        validate_pilot_lock(
            record,
            canonical_sha256=canonical_sha256,
            error=PilotContractError,
        )
    elif record_kind == "pilot_summary.v1":
        _validate_reduced_summary_fractions(record)
        _validate_summary_semantics(record)


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
