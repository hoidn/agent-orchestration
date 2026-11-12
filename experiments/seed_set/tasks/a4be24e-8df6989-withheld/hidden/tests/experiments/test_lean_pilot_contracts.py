from __future__ import annotations

import copy
import hashlib
import importlib
import json
import re
from importlib import resources
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


RECORD_KINDS = {
    "pilot_lock.v1",
    "block_attempt.v1",
    "review_result.v1",
    "pilot_summary.v1",
}


@pytest.fixture(scope="module")
def contracts() -> ModuleType:
    return importlib.import_module("orchestrator.experiments.contracts")


def _digest(label: str) -> str:
    return f"sha256:{hashlib.sha256(label.encode('utf-8')).hexdigest()}"


def _pilot_lock() -> dict[str, Any]:
    return {
        "record_kind": "pilot_lock.v1",
        "pilot_id": "lean-pilot-001",
        "task": {
            "task_id": "A1",
            "profile_digest": _digest("task-profile"),
            "brief_digest": _digest("task-brief"),
        },
        "archive": {
            "repository_identity": "example/demo_task_nanobragg_entrypoint_port",
            "revision_identity": "commit:0123456789abcdef",
            "archive_digest": _digest("source-archive"),
        },
        "provider_policy": {
            "family": "codex",
            "model": "gpt-example",
            "reasoning_effort": "high",
            "tool_policy": "workspace-write-no-network",
            "timeout_milliseconds": 900_000,
            "currency": "USD",
        },
        "review": {
            "reviewer_ids": ["reviewer-1", "reviewer-2"],
            "rubric_digest": _digest("rubric"),
            "calibration_evidence_digest": _digest("calibration"),
        },
        "randomization_seed": "seed-2026-07-26",
        "evidence_root": "evidence/lean-pilot-001",
        "valid_block_count": 3,
        "max_live_attempt_count": 5,
        "fixture_id": "fixture-001",
        "smoke_id": "smoke-001",
        "live_attempt_ids": [
            "live-001",
            "live-002",
            "live-003",
            "live-004",
            "live-005",
        ],
        "claim_level": "exploratory_controlled_task",
        "treatments": [
            {
                "treatment_id": "DIRECT",
                "source_digest": _digest("direct-source"),
                "command_digest": _digest("direct-command"),
                "provider_call_bounds": {"minimum": 1, "maximum": 1},
            },
            {
                "treatment_id": "COORDINATOR",
                "source_digest": _digest("coordinator-source"),
                "command_digest": _digest("coordinator-command"),
                "provider_call_bounds": {"minimum": 5, "maximum": 9},
            },
            {
                "treatment_id": "ORC",
                "source_digest": _digest("orc-source"),
                "command_digest": _digest("orc-command"),
                "provider_call_bounds": {"minimum": 5, "maximum": 9},
            },
        ],
    }


def _treatment_execution(
    treatment_id: str,
    opaque_arm_label: str,
    provider_call_count: int,
) -> dict[str, Any]:
    return {
        "opaque_arm_label": opaque_arm_label,
        "treatment_id": treatment_id,
        "command_digest": _digest(f"{treatment_id.lower()}-command"),
        "lifecycle_outcome": "COMPLETED",
        "product_frozen": True,
        "product_manifest_digest": _digest(f"{treatment_id.lower()}-product"),
        "provider_call_count": provider_call_count,
        "elapsed_milliseconds": 12_345,
        "evidence_references": [
            f"evidence/live-001/{opaque_arm_label}/stdout.txt",
            f"evidence/live-001/{opaque_arm_label}/checks.json",
        ],
        "token_counts": {"input": 1_000, "output": 500},
        "cost": {"cost_microunits": 125_000, "currency": "USD"},
    }


def _block_attempt(
    *,
    status: str = "VALID",
    block_id: str = "live-001",
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "record_kind": "block_attempt.v1",
        "pilot_lock_digest": _digest("pilot-lock"),
        "attempt_class": "LIVE",
        "sequence_index": 0,
        "block_id": block_id,
        "status": status,
    }
    if status == "STARTED":
        record["treatment_executions"] = []
    elif status == "VALID":
        record["treatment_executions"] = [
            _treatment_execution("DIRECT", "arm-kilo", 1),
            _treatment_execution("COORDINATOR", "arm-lima", 5),
            _treatment_execution("ORC", "arm-mike", 7),
        ]
    else:
        record["reason_code"] = "SHARED_ARCHIVE_ALLOCATION_FAILED"
        record["treatment_executions"] = [
            _treatment_execution("DIRECT", "arm-kilo", 1)
        ]
    return record


def _review_result() -> dict[str, Any]:
    return {
        "record_kind": "review_result.v1",
        "review_id": "review-live-001-r1",
        "pilot_lock_digest": _digest("pilot-lock"),
        "reviewer_id": "reviewer-1",
        "session_id": "session-fresh-001",
        "review_class": "LIVE",
        "rubric_digest": _digest("rubric"),
        "candidates": [
            {
                "opaque_label": "candidate-alpha",
                "evidence_citations": [
                    "packages/live-001/candidate-alpha/diff.patch"
                ],
                "sealed_treatment_guess": "UNKNOWN",
            },
            {
                "opaque_label": "candidate-beta",
                "evidence_citations": [
                    "packages/live-001/candidate-beta/checks.json"
                ],
                "sealed_treatment_guess": "DIRECT",
            },
        ],
        "pairwise_results": [
            {
                "candidate_a_label": "candidate-alpha",
                "candidate_b_label": "candidate-beta",
                "outcome": "A",
                "evidence_citations": [
                    "packages/live-001/candidate-alpha/diff.patch",
                    "packages/live-001/candidate-beta/checks.json",
                ],
            }
        ],
    }


def _method_outcome(comparison: str) -> dict[str, Any]:
    return {
        "comparison": comparison,
        "viability_case": "A_ONLY",
        "method_outcome": "A_WIN",
        "product_quality_review": "NOT_APPLICABLE",
    }


def _valid_block_summary(block_id: str) -> dict[str, Any]:
    return {
        "block_id": block_id,
        "block_attempt_digest": _digest(f"block-{block_id}"),
        "method_outcomes": [
            _method_outcome("DIRECT_VS_ORC"),
            _method_outcome("COORDINATOR_VS_ORC"),
        ],
    }


def _pilot_summary() -> dict[str, Any]:
    return {
        "record_kind": "pilot_summary.v1",
        "summary_id": "summary-001",
        "pilot_lock_digest": _digest("pilot-lock"),
        "status": "EVIDENCE_COMPLETE_OWNER_DECISION_REQUIRED",
        "valid_blocks": [
            _valid_block_summary("live-001"),
            _valid_block_summary("live-002"),
            _valid_block_summary("live-003"),
        ],
        "excluded_block_references": [
            {
                "block_id": "live-004",
                "block_attempt_digest": _digest("block-live-004"),
                "status": "INVALID",
            },
            {
                "block_id": "live-005",
                "block_attempt_digest": _digest("block-live-005"),
                "status": "ABORTED",
            },
        ],
        "medians": [
            {
                "metric": "elapsed_milliseconds",
                "treatment_id": "ORC",
                "value": {"numerator": 24_691, "denominator": 2},
            },
            {
                "metric": "cost_microunits",
                "treatment_id": "DIRECT",
                "value": "UNKNOWN",
            },
        ],
        "ratios": [
            {
                "metric": "elapsed_milliseconds",
                "numerator_treatment_id": "ORC",
                "denominator_treatment_id": "DIRECT",
                "value": {"numerator": 3, "denominator": 2},
            },
            {
                "metric": "cost_microunits",
                "numerator_treatment_id": "ORC",
                "denominator_treatment_id": "DIRECT",
                "value": "UNKNOWN",
            },
        ],
    }


def _all_records() -> list[dict[str, Any]]:
    return [_pilot_lock(), _block_attempt(), _review_result(), _pilot_summary()]


def test_canonical_json_is_sorted_compact_utf8(contracts: ModuleType) -> None:
    assert contracts.canonical_json_bytes({"z": 1, "a": "λ"}) == (
        '{"a":"λ","z":1}'.encode("utf-8")
    )


@pytest.mark.parametrize(
    "value",
    [
        {"value": 1.0},
        {"outer": [{"value": float("nan")}]},
        {1: "non-string key"},
        {"value": {"not-json"}},
        {"value": ("tuple",)},
        {"value": object()},
    ],
)
def test_canonical_json_rejects_noncanonical_values(
    contracts: ModuleType,
    value: object,
) -> None:
    with pytest.raises(contracts.PilotContractError):
        contracts.canonical_json_bytes(value)


def test_canonical_json_accepts_bool_distinct_from_rejected_float(
    contracts: ModuleType,
) -> None:
    assert contracts.canonical_json_bytes({"enabled": True}) == b'{"enabled":true}'


def test_canonical_sha256_uses_prefixed_lowercase_hex(
    contracts: ModuleType,
) -> None:
    digest = contracts.canonical_sha256({"a": 1})

    assert re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
    assert digest == contracts.canonical_sha256({"a": 1})


def test_schema_package_exposes_exactly_four_record_definitions(
    contracts: ModuleType,
) -> None:
    schema_path = resources.files("orchestrator.experiments.schemas").joinpath(
        "lean-pilot-records-v1.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    assert set(schema["$defs"]) == RECORD_KINDS


@pytest.mark.parametrize("record", _all_records(), ids=lambda item: item["record_kind"])
def test_all_four_record_kinds_validate(
    contracts: ModuleType,
    record: dict[str, Any],
) -> None:
    assert contracts.validate_record(record) is None


def test_record_kind_dispatch_is_exact(contracts: ModuleType) -> None:
    record = _pilot_lock()
    record["record_kind"] = "pilot_lock.v1 "

    with pytest.raises(contracts.PilotContractError, match="record_kind"):
        contracts.validate_record(record)


@pytest.mark.parametrize(
    ("record", "nested_object"),
    [
        (_pilot_lock(), ("task",)),
        (_block_attempt(), ("treatment_executions", 0)),
        (_review_result(), ("candidates", 0)),
        (_pilot_summary(), ("valid_blocks", 0, "method_outcomes", 0)),
    ],
)
def test_unknown_fields_are_rejected_recursively(
    contracts: ModuleType,
    record: dict[str, Any],
    nested_object: tuple[str | int, ...],
) -> None:
    target: Any = record
    for component in nested_object:
        target = target[component]
    target["unexpected"] = "not allowed"

    with pytest.raises(contracts.PilotContractError, match="unexpected"):
        contracts.validate_record(record)


def test_validation_errors_are_sorted_by_absolute_path(
    contracts: ModuleType,
) -> None:
    record = _pilot_lock()
    record["archive"]["archive_digest"] = "bad"
    record["task"]["task_id"] = 9

    with pytest.raises(contracts.PilotContractError) as exc_info:
        contracts.validate_record(record)

    message = str(exc_info.value)
    assert message.index("$.archive.archive_digest") < message.index("$.task.task_id")


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("valid_block_count", 2),
        ("max_live_attempt_count", 6),
        ("fixture_id", ""),
        ("smoke_id", ""),
        ("claim_level", "confirmatory"),
    ],
)
def test_pilot_lock_freezes_counts_ids_and_claim_level(
    contracts: ModuleType,
    field: str,
    bad_value: object,
) -> None:
    record = _pilot_lock()
    record[field] = bad_value

    with pytest.raises(contracts.PilotContractError):
        contracts.validate_record(record)


def test_pilot_lock_requires_five_ordered_unique_live_attempt_ids(
    contracts: ModuleType,
) -> None:
    record = _pilot_lock()
    record["live_attempt_ids"] = ["live-001"] * 5

    with pytest.raises(contracts.PilotContractError):
        contracts.validate_record(record)

    record["live_attempt_ids"] = ["live-001", "live-002", "live-003", "live-004"]
    with pytest.raises(contracts.PilotContractError):
        contracts.validate_record(record)


@pytest.mark.parametrize(
    "mutation",
    ["missing_treatment", "duplicate_treatment", "wrong_direct_bound", "wrong_orc_bound"],
)
def test_pilot_lock_requires_exact_treatments_and_call_bounds(
    contracts: ModuleType,
    mutation: str,
) -> None:
    record = _pilot_lock()
    if mutation == "missing_treatment":
        record["treatments"].pop()
    elif mutation == "duplicate_treatment":
        record["treatments"][2]["treatment_id"] = "COORDINATOR"
    elif mutation == "wrong_direct_bound":
        record["treatments"][0]["provider_call_bounds"]["maximum"] = 2
    else:
        record["treatments"][2]["provider_call_bounds"]["minimum"] = 4

    with pytest.raises(contracts.PilotContractError):
        contracts.validate_record(record)


@pytest.mark.parametrize(
    ("path", "bad_value"),
    [
        (("task", "profile_digest"), "sha256:ABC"),
        (("archive", "archive_digest"), "sha256:123"),
        (("treatments", 0, "source_digest"), "bad"),
        (("treatments", 1, "command_digest"), "bad"),
        (("review", "rubric_digest"), "bad"),
        (("review", "calibration_evidence_digest"), "bad"),
        (("randomization_seed",), ""),
        (("evidence_root",), ""),
        (("provider_policy", "timeout_milliseconds"), 0),
    ],
)
def test_pilot_lock_binds_exact_identity_and_policy_fields(
    contracts: ModuleType,
    path: tuple[str | int, ...],
    bad_value: object,
) -> None:
    record = _pilot_lock()
    target: Any = record
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = bad_value

    with pytest.raises(contracts.PilotContractError):
        contracts.validate_record(record)


def test_started_block_allows_no_treatment_executions(
    contracts: ModuleType,
) -> None:
    record = _block_attempt(status="STARTED")
    contracts.validate_record(record)

    record["treatment_executions"] = [
        _treatment_execution("DIRECT", "arm-kilo", 1)
    ]
    with pytest.raises(contracts.PilotContractError):
        contracts.validate_record(record)


def test_valid_block_requires_all_three_locked_treatments(
    contracts: ModuleType,
) -> None:
    record = _block_attempt()
    record["treatment_executions"].pop()

    with pytest.raises(contracts.PilotContractError):
        contracts.validate_record(record)

    record = _block_attempt()
    record["treatment_executions"][2]["treatment_id"] = "DIRECT"
    with pytest.raises(contracts.PilotContractError):
        contracts.validate_record(record)


@pytest.mark.parametrize("status", ["INVALID", "ABORTED"])
def test_invalid_and_aborted_blocks_preserve_reason_and_launched_executions(
    contracts: ModuleType,
    status: str,
) -> None:
    record = _block_attempt(status=status)
    contracts.validate_record(record)

    record.pop("reason_code")
    with pytest.raises(contracts.PilotContractError):
        contracts.validate_record(record)


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("pilot_lock_digest", "bad"),
        ("attempt_class", "UNDECLARED"),
        ("sequence_index", -1),
        ("block_id", ""),
        ("status", "FINISHED"),
    ],
)
def test_block_attempt_binds_lock_class_sequence_id_and_status(
    contracts: ModuleType,
    field: str,
    bad_value: object,
) -> None:
    record = _block_attempt()
    record[field] = bad_value

    with pytest.raises(contracts.PilotContractError):
        contracts.validate_record(record)


@pytest.mark.parametrize(
    ("path", "bad_value"),
    [
        (("opaque_arm_label",), ""),
        (("command_digest",), "bad"),
        (("lifecycle_outcome",), ""),
        (("provider_call_count",), -1),
        (("elapsed_milliseconds",), -1),
        (("evidence_references",), []),
        (("token_counts", "input"), -1),
        (("cost", "cost_microunits"), -1),
        (("cost", "currency"), ""),
    ],
)
def test_treatment_execution_binds_lifecycle_usage_cost_and_evidence(
    contracts: ModuleType,
    path: tuple[str, ...],
    bad_value: object,
) -> None:
    record = _block_attempt()
    execution = record["treatment_executions"][0]
    target: Any = execution
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = bad_value

    with pytest.raises(contracts.PilotContractError):
        contracts.validate_record(record)


def test_frozen_execution_requires_product_manifest_digest(
    contracts: ModuleType,
) -> None:
    record = _block_attempt()
    record["treatment_executions"][0].pop("product_manifest_digest")

    with pytest.raises(contracts.PilotContractError):
        contracts.validate_record(record)

    record = _block_attempt()
    execution = record["treatment_executions"][0]
    execution["product_frozen"] = False
    execution.pop("product_manifest_digest")
    contracts.validate_record(record)


def test_unknown_usage_and_cost_are_explicit(contracts: ModuleType) -> None:
    record = _block_attempt()
    execution = record["treatment_executions"][0]
    execution["token_counts"] = "UNKNOWN"
    execution["cost"] = "UNKNOWN"

    contracts.validate_record(record)


@pytest.mark.parametrize("review_class", ["CALIBRATION", "LIVE"])
def test_review_results_bind_identity_class_evidence_and_guesses(
    contracts: ModuleType,
    review_class: str,
) -> None:
    record = _review_result()
    record["review_class"] = review_class

    contracts.validate_record(record)


@pytest.mark.parametrize("outcome", ["A", "B", "TIE", "INDETERMINATE"])
def test_review_pairwise_outcomes_are_closed(
    contracts: ModuleType,
    outcome: str,
) -> None:
    record = _review_result()
    record["pairwise_results"][0]["outcome"] = outcome

    contracts.validate_record(record)


@pytest.mark.parametrize(
    "guess",
    ["DIRECT", "COORDINATOR", "ORC", "UNKNOWN"],
)
def test_review_has_one_sealed_treatment_guess_per_candidate(
    contracts: ModuleType,
    guess: str,
) -> None:
    record = _review_result()
    record["candidates"][0]["sealed_treatment_guess"] = guess
    contracts.validate_record(record)

    record["candidates"][0].pop("sealed_treatment_guess")
    with pytest.raises(contracts.PilotContractError):
        contracts.validate_record(record)


def test_review_rejects_unsealed_or_uncited_results(contracts: ModuleType) -> None:
    record = _review_result()
    record["reviewer_id"] = ""
    record["session_id"] = ""
    record["candidates"][0]["opaque_label"] = ""
    record["pairwise_results"][0]["evidence_citations"] = []

    with pytest.raises(contracts.PilotContractError):
        contracts.validate_record(record)


def test_complete_summary_requires_exactly_three_valid_blocks(
    contracts: ModuleType,
) -> None:
    record = _pilot_summary()
    record["valid_blocks"].pop()

    with pytest.raises(contracts.PilotContractError):
        contracts.validate_record(record)


@pytest.mark.parametrize(
    "status",
    ["STOP_APPARATUS_NOT_VIABLE", "STOP_INSUFFICIENT_VALID_BLOCKS"],
)
def test_terminal_stop_summary_preserves_reason_and_partial_denominator(
    contracts: ModuleType,
    status: str,
) -> None:
    record = _pilot_summary()
    record["status"] = status
    record["valid_blocks"] = record["valid_blocks"][:2]
    record["terminal_reason_code"] = "LOCKED_TERMINAL_STOP"

    contracts.validate_record(record)

    record.pop("terminal_reason_code")
    with pytest.raises(contracts.PilotContractError):
        contracts.validate_record(record)


@pytest.mark.parametrize(
    ("viability_case", "method_outcome", "product_quality_review"),
    [
        ("A_ONLY", "A_WIN", "NOT_APPLICABLE"),
        ("B_ONLY", "B_WIN", "NOT_APPLICABLE"),
        (
            "BOTH",
            "TIE",
            {
                "outcome": "TIE",
                "review_result_digests": [_digest("review-both")],
            },
        ),
        ("NEITHER", "TIE_NONVIABLE", "NOT_REVIEWABLE"),
        (
            "NEITHER",
            "TIE_NONVIABLE",
            {
                "outcome": "B",
                "review_result_digests": [_digest("review-nonviable")],
            },
        ),
    ],
)
def test_summary_method_outcomes_enforce_sole_viable_precedence(
    contracts: ModuleType,
    viability_case: str,
    method_outcome: str,
    product_quality_review: object,
) -> None:
    record = _pilot_summary()
    outcome = record["valid_blocks"][0]["method_outcomes"][0]
    outcome["viability_case"] = viability_case
    outcome["method_outcome"] = method_outcome
    outcome["product_quality_review"] = product_quality_review

    contracts.validate_record(record)


def test_summary_rejects_method_outcome_that_ignores_sole_viable_precedence(
    contracts: ModuleType,
) -> None:
    record = _pilot_summary()
    record["valid_blocks"][0]["method_outcomes"][0]["method_outcome"] = "B_WIN"

    with pytest.raises(contracts.PilotContractError):
        contracts.validate_record(record)


def test_summary_both_viable_method_outcome_matches_sealed_review(
    contracts: ModuleType,
) -> None:
    record = _pilot_summary()
    outcome = record["valid_blocks"][0]["method_outcomes"][0]
    outcome["viability_case"] = "BOTH"
    outcome["method_outcome"] = "A_WIN"
    outcome["product_quality_review"] = {
        "outcome": "B",
        "review_result_digests": [_digest("review-mismatch")],
    }

    with pytest.raises(contracts.PilotContractError):
        contracts.validate_record(record)


@pytest.mark.parametrize("status", ["INVALID", "ABORTED", "STARTED"])
def test_summary_retains_excluded_attempts_outside_valid_denominator(
    contracts: ModuleType,
    status: str,
) -> None:
    record = _pilot_summary()
    record["excluded_block_references"][0]["status"] = status

    contracts.validate_record(record)


@pytest.mark.parametrize(
    "bad_value",
    [
        {"numerator": 2, "denominator": 4},
        {"numerator": 1, "denominator": 0},
        {"numerator": 1.5, "denominator": 2},
        1.5,
    ],
)
def test_summary_medians_and_ratios_require_reduced_exact_fractions_or_unknown(
    contracts: ModuleType,
    bad_value: object,
) -> None:
    record = _pilot_summary()
    record["ratios"][0]["value"] = bad_value

    with pytest.raises(contracts.PilotContractError):
        contracts.validate_record(record)


def test_load_record_checks_expected_kind_and_validates(
    contracts: ModuleType,
    tmp_path: Path,
) -> None:
    path = tmp_path / "pilot-lock.json"
    path.write_bytes(contracts.canonical_json_bytes(_pilot_lock()))

    assert contracts.load_record(path, expected_kind="pilot_lock.v1") == _pilot_lock()

    with pytest.raises(contracts.PilotContractError, match="expected"):
        contracts.load_record(path, expected_kind="block_attempt.v1")


def test_load_record_rejects_noncanonical_json_values(
    contracts: ModuleType,
    tmp_path: Path,
) -> None:
    path = tmp_path / "pilot-lock.json"
    record = copy.deepcopy(_pilot_lock())
    record["valid_block_count"] = 3.0
    path.write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(contracts.PilotContractError):
        contracts.load_record(path, expected_kind="pilot_lock.v1")
