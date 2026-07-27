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


def _apparatus() -> dict[str, Any]:
    return {
        "control_root": "/srv/lean-pilot/control",
        "asset_manifest": [
            {"path": "tasks/A1.md", "sha256": _digest("task-brief")},
            {
                "path": "config/provider.json",
                "sha256": _digest("provider-config"),
            },
            {
                "path": "config/prompts.json",
                "sha256": _digest("prompt-config"),
            },
            {
                "path": "config/commands.json",
                "sha256": _digest("command-config"),
            },
            {
                "path": "config/treatments/direct.json",
                "sha256": _digest("direct-command"),
            },
            {
                "path": "config/treatments/coordinator.json",
                "sha256": _digest("coordinator-command"),
            },
            {
                "path": "config/treatments/orc.json",
                "sha256": _digest("orc-command"),
            },
        ],
        "task_path": "tasks/A1.md",
        "provider_config_path": "config/provider.json",
        "prompt_config_path": "config/prompts.json",
        "command_config_path": "config/commands.json",
        "environment": {
            "identity": _digest("environment"),
            "allowed_keys": ["HOME", "OPENAI_API_KEY", "PATH", "TMPDIR"],
            "credential_keys": ["OPENAI_API_KEY"],
        },
        "visible_check": {
            "argv": ["python", "-m", "pytest", "-q"],
            "timeout_milliseconds": 120_000,
        },
        "product_projection_exclusions": [".git", ".pilot/runtime"],
        "maximum_start_skew_milliseconds": 500,
        "quiescence_grace_milliseconds": 2_000,
    }


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
        "apparatus": _apparatus(),
        "randomization_seed": "seed-2026-07-26",
        "evidence_root": "/evidence/lean-pilot-001",
        "valid_block_count": 3,
        "max_live_attempt_count": 5,
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
                "command_config_path": "config/treatments/direct.json",
                "provider_call_bounds": {"minimum": 1, "maximum": 1},
            },
            {
                "treatment_id": "COORDINATOR",
                "source_digest": _digest("coordinator-source"),
                "command_digest": _digest("coordinator-command"),
                "command_config_path": "config/treatments/coordinator.json",
                "provider_call_bounds": {"minimum": 3, "maximum": 9},
            },
            {
                "treatment_id": "ORC",
                "source_digest": _digest("orc-source"),
                "command_digest": _digest("orc-command"),
                "command_config_path": "config/treatments/orc.json",
                "provider_call_bounds": {"minimum": 3, "maximum": 9},
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
    dimensions = (
        "TASK_COMPLETENESS",
        "BEHAVIORAL_CORRECTNESS",
        "MAINTAINABILITY",
        "SCOPE_CONTROL",
        "EVIDENCE_QUALITY",
    )

    def candidate(
        label: str,
        citation: str,
        guess: str,
    ) -> dict[str, Any]:
        return {
            "opaque_label": label,
            "evidence_citations": [citation],
            "dimension_assessments": [
                {
                    "dimension": dimension,
                    "assessment": "PASS",
                    "rationale": f"{dimension} is supported by the cited artifact.",
                    "evidence_citations": [citation],
                }
                for dimension in dimensions
            ],
            "sealed_treatment_guess": guess,
        }

    return {
        "record_kind": "review_result.v1",
        "review_id": "review-live-001-r1",
        "pilot_lock_digest": _digest("pilot-lock"),
        "reviewer_id": "reviewer-1",
        "session_id": "session-fresh-001",
        "review_class": "LIVE",
        "rubric_digest": _digest("rubric"),
        "candidates": [
            candidate(
                "candidate-alpha",
                "packages/live-001/candidate-alpha/diff.patch",
                "UNKNOWN",
            ),
            candidate(
                "candidate-beta",
                "packages/live-001/candidate-beta/checks.json",
                "DIRECT",
            ),
        ],
        "pairwise_results": [
            {
                "candidate_a_label": "candidate-alpha",
                "candidate_b_label": "candidate-beta",
                "outcome": "A",
                "rationale": "The cited evidence supports candidate alpha.",
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
    lifecycle_counts = {
        "COMPLETED": 3,
        "BLOCKED": 0,
        "EXHAUSTED": 0,
        "PROTOCOL_FAILURE": 0,
        "LAUNCH_FAILURE": 0,
        "TIMEOUT": 0,
        "NONZERO_EXIT": 0,
        "CHECK_FAILURE": 0,
    }
    failure_counts = {
        key: value
        for key, value in lifecycle_counts.items()
        if key != "COMPLETED"
    }

    def review_reference(block_id: str, reviewer_id: str) -> dict[str, Any]:
        review_id = f"review-{block_id}-{reviewer_id}"
        return {
            "review_id": review_id,
            "reviewer_id": reviewer_id,
            "review_result_digest": _digest(review_id),
            "review_path": f"reviews/{review_id}.json",
        }

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
        "comparison_counts": [
            {
                "comparison": "DIRECT_VS_ORC",
                "a_win_count": 3,
                "b_win_count": 0,
                "tie_count": 0,
                "indeterminate_count": 0,
                "tie_nonviable_count": 0,
            },
            {
                "comparison": "COORDINATOR_VS_ORC",
                "a_win_count": 3,
                "b_win_count": 0,
                "tie_count": 0,
                "indeterminate_count": 0,
                "tie_nonviable_count": 0,
            },
        ],
        "treatment_statistics": [
            {
                "treatment_id": treatment_id,
                "viable_count": 3,
                "nonviable_count": 0,
                "lifecycle_outcome_counts": dict(lifecycle_counts),
                "failure_class_counts": dict(failure_counts),
                "provider_call_counts": [call_count, call_count, call_count],
            }
            for treatment_id, call_count in (
                ("DIRECT", 1),
                ("COORDINATOR", 5),
                ("ORC", 7),
            )
        ],
        "review_diagnostics": {
            "agreement_count": 6,
            "disagreement_count": 0,
            "adjudication_count": 0,
            "blocks": [
                {
                    "block_id": block_id,
                    "package_id": block_id,
                    "package_manifest_digest": _digest(f"package-{block_id}"),
                    "initial_reviews_agree": True,
                    "disagreement_disposition": "NOT_APPLICABLE",
                    "initial_review_references": [
                        review_reference(block_id, "reviewer-1"),
                        review_reference(block_id, "reviewer-2"),
                    ],
                }
                for block_id in ("live-001", "live-002", "live-003")
            ],
            "guess_accuracy": {"numerator": 1, "denominator": 2},
            "guess_confusion": [
                {
                    "actual_treatment_id": actual,
                    "guessed_treatment_id": guessed,
                    "count": int(guessed in {actual, "UNKNOWN"}),
                }
                for actual in ("DIRECT", "COORDINATOR", "ORC")
                for guessed in ("DIRECT", "COORDINATOR", "ORC", "UNKNOWN")
            ],
        },
        "hard_contract_findings": [],
        "medians": [
            {
                "metric": metric,
                "treatment_id": treatment,
                "value": (
                    "UNKNOWN"
                    if metric == "cost_microunits"
                    else {"numerator": value, "denominator": 1}
                ),
            }
            for metric, values in (
                ("elapsed_milliseconds", (10, 20, 30)),
                ("cost_microunits", (0, 0, 0)),
                ("input_tokens", (100, 200, 300)),
                ("output_tokens", (50, 100, 150)),
            )
            for treatment, value in zip(
                ("DIRECT", "COORDINATOR", "ORC"),
                values,
                strict=True,
            )
        ],
        "ratios": [
            {
                "metric": metric,
                "numerator_treatment_id": "ORC",
                "denominator_treatment_id": denominator,
                "value": (
                    "UNKNOWN"
                    if metric == "cost_microunits"
                    else {
                        "numerator": 3,
                        "denominator": 1 if denominator == "DIRECT" else 2,
                    }
                ),
            }
            for metric in (
                "elapsed_milliseconds",
                "cost_microunits",
                "input_tokens",
                "output_tokens",
            )
            for denominator in ("DIRECT", "COORDINATOR")
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


def test_pilot_lock_accepts_explicit_locked_apparatus(
    contracts: ModuleType,
) -> None:
    record = _pilot_lock()

    assert record["apparatus"]["product_projection_exclusions"]
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


def test_pilot_lock_rejects_smoke_live_path_collision(
    contracts: ModuleType,
) -> None:
    record = _pilot_lock()
    record["smoke_id"] = record["live_attempt_ids"][0]

    with pytest.raises(contracts.PilotContractError):
        contracts.validate_record(record)


def test_pilot_lock_accepts_smoke_and_live_ids_without_fixture_identity(
    contracts: ModuleType,
) -> None:
    record = _pilot_lock()

    contracts.validate_record(record)


def test_pilot_lock_rejects_retired_fixture_identity(
    contracts: ModuleType,
) -> None:
    record = _pilot_lock()
    record["fixture_id"] = "fixture-001"

    with pytest.raises(contracts.PilotContractError):
        contracts.validate_record(record)


def test_pilot_lock_accepts_three_to_nine_multi_provider_call_bounds(
    contracts: ModuleType,
) -> None:
    record = _pilot_lock()

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
    ("path", "missing_field"),
    [
        (("apparatus",), "apparatus"),
        (("apparatus", "control_root"), "control_root"),
        (("apparatus", "asset_manifest"), "asset_manifest"),
        (("apparatus", "task_path"), "task_path"),
        (("apparatus", "provider_config_path"), "provider_config_path"),
        (("apparatus", "prompt_config_path"), "prompt_config_path"),
        (("apparatus", "command_config_path"), "command_config_path"),
        (("apparatus", "environment"), "environment"),
        (("apparatus", "environment", "identity"), "identity"),
        (("apparatus", "environment", "allowed_keys"), "allowed_keys"),
        (("apparatus", "environment", "credential_keys"), "credential_keys"),
        (("apparatus", "visible_check"), "visible_check"),
        (("apparatus", "visible_check", "argv"), "argv"),
        (
            ("apparatus", "visible_check", "timeout_milliseconds"),
            "timeout_milliseconds",
        ),
        (
            ("apparatus", "product_projection_exclusions"),
            "product_projection_exclusions",
        ),
        (
            ("apparatus", "maximum_start_skew_milliseconds"),
            "maximum_start_skew_milliseconds",
        ),
        (
            ("apparatus", "quiescence_grace_milliseconds"),
            "quiescence_grace_milliseconds",
        ),
        (("apparatus", "asset_manifest", 0, "path"), "path"),
        (("apparatus", "asset_manifest", 0, "sha256"), "sha256"),
        (("treatments", 0, "command_config_path"), "command_config_path"),
    ],
)
def test_pilot_lock_requires_complete_apparatus_fields(
    contracts: ModuleType,
    path: tuple[str | int, ...],
    missing_field: str,
) -> None:
    record = _pilot_lock()
    target: Any = record
    for component in path[:-1]:
        target = target[component]
    del target[path[-1]]

    with pytest.raises(contracts.PilotContractError, match=missing_field):
        contracts.validate_record(record)


@pytest.mark.parametrize(
    "bad_path",
    [
        "/absolute/path",
        "",
        ".",
        "..",
        "tasks/./A1.md",
        "tasks/../A1.md",
        "tasks//A1.md",
        "tasks/A1.md/",
        r"tasks\A1.md",
        "tasks/\x00A1.md",
    ],
)
def test_manifest_paths_are_canonical_relative_posix_text(
    contracts: ModuleType,
    bad_path: str,
) -> None:
    record = _pilot_lock()
    record["apparatus"]["asset_manifest"][0]["path"] = bad_path

    with pytest.raises(
        contracts.PilotContractError,
        match=r"\$\.apparatus\.asset_manifest\[0\]\.path",
    ):
        contracts.validate_record(record)


@pytest.mark.parametrize(
    "path",
    [
        ("apparatus", "task_path"),
        ("apparatus", "provider_config_path"),
        ("apparatus", "prompt_config_path"),
        ("apparatus", "command_config_path"),
        ("treatments", 0, "command_config_path"),
        ("apparatus", "product_projection_exclusions", 0),
    ],
)
def test_every_non_root_apparatus_path_rejects_absolute_text(
    contracts: ModuleType,
    path: tuple[str | int, ...],
) -> None:
    record = _pilot_lock()
    target: Any = record
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = "/absolute/path"

    with pytest.raises(contracts.PilotContractError):
        contracts.validate_record(record)


@pytest.mark.parametrize(
    "bad_root",
    [
        "relative/control",
        "/",
        "/srv//control",
        "/srv/./control",
        "/srv/../control",
        "/srv/control/",
        r"/srv\control",
        "/srv/\x00control",
    ],
)
def test_control_root_is_canonical_non_root_absolute_posix_text(
    contracts: ModuleType,
    bad_root: str,
) -> None:
    record = _pilot_lock()
    record["apparatus"]["control_root"] = bad_root

    with pytest.raises(
        contracts.PilotContractError,
        match=r"\$\.apparatus\.control_root",
    ):
        contracts.validate_record(record)


@pytest.mark.parametrize("different_digest", [False, True])
def test_asset_manifest_paths_are_unique_even_when_digests_differ(
    contracts: ModuleType,
    different_digest: bool,
) -> None:
    record = _pilot_lock()
    duplicate = copy.deepcopy(record["apparatus"]["asset_manifest"][0])
    if different_digest:
        duplicate["sha256"] = _digest("different")
    record["apparatus"]["asset_manifest"].append(duplicate)

    with pytest.raises(
        contracts.PilotContractError,
        match="duplicate_asset_manifest_path",
    ):
        contracts.validate_record(record)


@pytest.mark.parametrize(
    "role",
    [
        "task_path",
        "provider_config_path",
        "prompt_config_path",
        "command_config_path",
    ],
)
def test_apparatus_role_paths_must_name_manifest_assets(
    contracts: ModuleType,
    role: str,
) -> None:
    record = _pilot_lock()
    record["apparatus"][role] = f"missing/{role}.json"

    with pytest.raises(
        contracts.PilotContractError,
        match=rf"missing_apparatus_asset:{role}",
    ):
        contracts.validate_record(record)


def test_treatment_command_config_path_must_name_a_manifest_asset(
    contracts: ModuleType,
) -> None:
    record = _pilot_lock()
    record["treatments"][0]["command_config_path"] = "missing/direct.json"

    with pytest.raises(
        contracts.PilotContractError,
        match="missing_treatment_command_config_asset:DIRECT",
    ):
        contracts.validate_record(record)


def test_treatment_command_config_paths_are_distinct(
    contracts: ModuleType,
) -> None:
    record = _pilot_lock()
    record["treatments"][1]["command_config_path"] = (
        record["treatments"][0]["command_config_path"]
    )

    with pytest.raises(
        contracts.PilotContractError,
        match="duplicate_treatment_command_config_path",
    ):
        contracts.validate_record(record)


def test_treatment_command_digest_matches_its_manifest_asset(
    contracts: ModuleType,
) -> None:
    record = _pilot_lock()
    direct_path = record["treatments"][0]["command_config_path"]
    direct_asset = next(
        asset
        for asset in record["apparatus"]["asset_manifest"]
        if asset["path"] == direct_path
    )
    direct_asset["sha256"] = _digest("mismatched-direct-command")

    with pytest.raises(
        contracts.PilotContractError,
        match="treatment_command_digest_mismatch:DIRECT",
    ):
        contracts.validate_record(record)


def test_task_brief_digest_matches_its_manifest_asset(
    contracts: ModuleType,
) -> None:
    record = _pilot_lock()
    task_path = record["apparatus"]["task_path"]
    task_asset = next(
        asset
        for asset in record["apparatus"]["asset_manifest"]
        if asset["path"] == task_path
    )
    task_asset["sha256"] = _digest("mismatched-task-brief")

    with pytest.raises(
        contracts.PilotContractError,
        match="task_brief_digest_mismatch",
    ):
        contracts.validate_record(record)


@pytest.mark.parametrize(
    "allowed_keys",
    [
        [],
        [""],
        ["1INVALID"],
        ["INVALID-NAME"],
        ["INVALID NAME"],
        ["PATH", "PATH"],
    ],
)
def test_environment_allowed_keys_are_explicit_unique_names(
    contracts: ModuleType,
    allowed_keys: list[str],
) -> None:
    record = _pilot_lock()
    record["apparatus"]["environment"]["allowed_keys"] = allowed_keys

    with pytest.raises(
        contracts.PilotContractError,
        match=r"\$\.apparatus\.environment\.allowed_keys",
    ):
        contracts.validate_record(record)


@pytest.mark.parametrize(
    "credential_keys",
    [
        ["OPENAI_API_KEY", "OPENAI_API_KEY"],
        [""],
        ["1INVALID"],
        ["INVALID-NAME"],
    ],
)
def test_environment_credential_keys_are_unique_environment_names(
    contracts: ModuleType,
    credential_keys: list[str],
) -> None:
    record = _pilot_lock()
    record["apparatus"]["environment"]["credential_keys"] = credential_keys

    with pytest.raises(
        contracts.PilotContractError,
        match=r"\$\.apparatus\.environment\.credential_keys",
    ):
        contracts.validate_record(record)


@pytest.mark.parametrize(
    ("allowed_keys", "credential_keys", "expected"),
    [
        (
            ["HOME", "PATH", "TMPDIR"],
            ["OPENAI_API_KEY"],
            "credential_key_not_allowed:OPENAI_API_KEY",
        ),
        (
            ["HOME", "PATH", "TMPDIR"],
            ["HOME"],
            "controller_environment_key_cannot_be_credential:HOME",
        ),
        (
            ["HOME", "PATH", "TMPDIR"],
            ["TMPDIR"],
            "controller_environment_key_cannot_be_credential:TMPDIR",
        ),
        (
            ["PATH", "TMPDIR"],
            [],
            "missing_controller_environment_key:HOME",
        ),
        (
            ["HOME", "PATH"],
            [],
            "missing_controller_environment_key:TMPDIR",
        ),
    ],
)
def test_environment_partition_is_closed_in_the_lock(
    contracts: ModuleType,
    allowed_keys: list[str],
    credential_keys: list[str],
    expected: str,
) -> None:
    record = _pilot_lock()
    record["apparatus"]["environment"]["allowed_keys"] = allowed_keys
    record["apparatus"]["environment"]["credential_keys"] = credential_keys

    with pytest.raises(contracts.PilotContractError, match=expected):
        contracts.validate_record(record)


def test_visible_check_argv_is_explicit_and_nonempty(
    contracts: ModuleType,
) -> None:
    for bad_argv in ([], [""]):
        record = _pilot_lock()
        record["apparatus"]["visible_check"]["argv"] = bad_argv

        with pytest.raises(
            contracts.PilotContractError,
            match=r"\$\.apparatus\.visible_check\.argv",
        ):
            contracts.validate_record(record)


@pytest.mark.parametrize("bad_timeout", [0, -1])
def test_visible_check_timeout_is_positive(
    contracts: ModuleType,
    bad_timeout: int,
) -> None:
    record = _pilot_lock()
    record["apparatus"]["visible_check"]["timeout_milliseconds"] = bad_timeout

    with pytest.raises(
        contracts.PilotContractError,
        match=r"\$\.apparatus\.visible_check\.timeout_milliseconds",
    ):
        contracts.validate_record(record)


def test_product_projection_exclusions_may_be_explicitly_empty(
    contracts: ModuleType,
) -> None:
    record = _pilot_lock()
    record["apparatus"]["product_projection_exclusions"] = []

    assert contracts.validate_record(record) is None


@pytest.mark.parametrize(
    "exclusions",
    [
        ["/absolute"],
        ["product//cache"],
        ["product/cache/"],
        ["product/../cache"],
        [r"product\cache"],
        ["cache", "cache"],
    ],
)
def test_product_projection_exclusions_are_unique_canonical_paths(
    contracts: ModuleType,
    exclusions: list[str],
) -> None:
    record = _pilot_lock()
    record["apparatus"]["product_projection_exclusions"] = exclusions

    with pytest.raises(
        contracts.PilotContractError,
        match=r"\$\.apparatus\.product_projection_exclusions",
    ):
        contracts.validate_record(record)


@pytest.mark.parametrize(
    "field",
    [
        "maximum_start_skew_milliseconds",
        "quiescence_grace_milliseconds",
    ],
)
@pytest.mark.parametrize("bad_value", [0, -1])
def test_apparatus_timing_bounds_are_positive(
    contracts: ModuleType,
    field: str,
    bad_value: int,
) -> None:
    record = _pilot_lock()
    record["apparatus"][field] = bad_value

    with pytest.raises(
        contracts.PilotContractError,
        match=rf"\$\.apparatus\.{field}",
    ):
        contracts.validate_record(record)


@pytest.mark.parametrize(
    "path",
    [
        ("apparatus",),
        ("apparatus", "asset_manifest", 0),
        ("apparatus", "environment"),
        ("apparatus", "visible_check"),
    ],
)
def test_apparatus_unknown_fields_are_rejected_recursively(
    contracts: ModuleType,
    path: tuple[str | int, ...],
) -> None:
    record = _pilot_lock()
    target: Any = record
    for component in path:
        target = target[component]
    target["unexpected"] = "not allowed"

    with pytest.raises(contracts.PilotContractError, match="unexpected"):
        contracts.validate_record(record)


@pytest.mark.parametrize(
    "path",
    [
        ("apparatus", "maximum_start_skew_milliseconds"),
        ("apparatus", "visible_check", "timeout_milliseconds"),
    ],
)
def test_apparatus_rejects_float_values_before_schema_validation(
    contracts: ModuleType,
    path: tuple[str, ...],
) -> None:
    record = _pilot_lock()
    target: Any = record
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = 1.0

    with pytest.raises(
        contracts.PilotContractError,
        match="floating-point values are not permitted",
    ):
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


def test_block_attempt_rejects_retired_fixture_attempt_class(
    contracts: ModuleType,
) -> None:
    record = _block_attempt()
    record["attempt_class"] = "FIXTURE"

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


def test_review_requires_exactly_five_evidence_cited_dimension_assessments(
    contracts: ModuleType,
) -> None:
    record = _review_result()
    assessments = record["candidates"][0]["dimension_assessments"]

    assert {item["dimension"] for item in assessments} == {
        "TASK_COMPLETENESS",
        "BEHAVIORAL_CORRECTNESS",
        "MAINTAINABILITY",
        "SCOPE_CONTROL",
        "EVIDENCE_QUALITY",
    }
    contracts.validate_record(record)

    record["candidates"][0]["dimension_assessments"].pop()
    with pytest.raises(contracts.PilotContractError):
        contracts.validate_record(record)


def test_review_rejects_duplicate_or_unknown_dimension_assessments(
    contracts: ModuleType,
) -> None:
    duplicate = _review_result()
    duplicate["candidates"][0]["dimension_assessments"][4]["dimension"] = (
        "TASK_COMPLETENESS"
    )
    with pytest.raises(contracts.PilotContractError):
        contracts.validate_record(duplicate)

    unknown = _review_result()
    unknown["candidates"][0]["dimension_assessments"][0]["dimension"] = "NOVELTY"
    with pytest.raises(contracts.PilotContractError):
        contracts.validate_record(unknown)


@pytest.mark.parametrize(
    ("target", "field", "bad_value"),
    [
        ("dimension", "assessment", "MAYBE"),
        ("dimension", "rationale", "   "),
        ("dimension", "rationale", "x" * 4_097),
        ("dimension", "evidence_citations", []),
        ("pairwise", "rationale", " \n "),
        ("pairwise", "rationale", "x" * 4_097),
    ],
)
def test_review_assessments_and_pairwise_results_require_bounded_explanations(
    contracts: ModuleType,
    target: str,
    field: str,
    bad_value: object,
) -> None:
    record = _review_result()
    item = (
        record["candidates"][0]["dimension_assessments"][0]
        if target == "dimension"
        else record["pairwise_results"][0]
    )
    item[field] = bad_value

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
    "field",
    ["comparison_counts", "treatment_statistics", "review_diagnostics"],
)
def test_summary_requires_closed_reporting_sections(
    contracts: ModuleType,
    field: str,
) -> None:
    record = _pilot_summary()
    del record[field]

    with pytest.raises(contracts.PilotContractError):
        contracts.validate_record(record)

    record = _pilot_summary()
    target = record[field]
    if isinstance(target, dict):
        target["unexpected"] = True
    else:
        target[0]["unexpected"] = True
    with pytest.raises(contracts.PilotContractError):
        contracts.validate_record(record)


def test_summary_requires_exact_comparison_and_treatment_rows(
    contracts: ModuleType,
) -> None:
    record = _pilot_summary()
    record["comparison_counts"][1]["comparison"] = "DIRECT_VS_ORC"
    with pytest.raises(contracts.PilotContractError):
        contracts.validate_record(record)

    record = _pilot_summary()
    record["treatment_statistics"][2]["treatment_id"] = "DIRECT"
    with pytest.raises(contracts.PilotContractError):
        contracts.validate_record(record)


def test_summary_review_diagnostics_retain_originals_and_bind_adjudication(
    contracts: ModuleType,
) -> None:
    record = _pilot_summary()
    block = record["review_diagnostics"]["blocks"][0]
    block["initial_reviews_agree"] = False

    with pytest.raises(contracts.PilotContractError):
        contracts.validate_record(record)

    block["adjudicator_review_reference"] = {
        "review_id": "review-live-001-reviewer-3",
        "reviewer_id": "reviewer-3",
        "review_result_digest": _digest("review-live-001-reviewer-3"),
        "review_path": "reviews/review-live-001-reviewer-3.json",
    }
    block["disagreement_disposition"] = "LOCKED_ADJUDICATOR"
    record["review_diagnostics"]["agreement_count"] = 5
    record["review_diagnostics"]["disagreement_count"] = 1
    record["review_diagnostics"]["adjudication_count"] = 1
    contracts.validate_record(record)

    block["initial_reviews_agree"] = True
    with pytest.raises(contracts.PilotContractError):
        contracts.validate_record(record)


def test_summary_guess_confusion_is_an_exact_closed_matrix(
    contracts: ModuleType,
) -> None:
    record = _pilot_summary()
    record["review_diagnostics"]["guess_confusion"].pop()

    with pytest.raises(contracts.PilotContractError):
        contracts.validate_record(record)

    record = _pilot_summary()
    record["review_diagnostics"]["guess_confusion"][0]["unexpected"] = 1
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
    valid_count = 0 if status == "STOP_APPARATUS_NOT_VIABLE" else 2
    record["valid_blocks"] = record["valid_blocks"][:valid_count]
    for row in record["comparison_counts"]:
        row["a_win_count"] = valid_count
    for statistic in record["treatment_statistics"]:
        statistic["viable_count"] = valid_count
        statistic["lifecycle_outcome_counts"]["COMPLETED"] = valid_count
        statistic["provider_call_counts"] = statistic["provider_call_counts"][
            :valid_count
        ]
    record["review_diagnostics"]["agreement_count"] = valid_count * 2
    record["review_diagnostics"]["blocks"] = record["review_diagnostics"][
        "blocks"
    ][:valid_count]
    if valid_count == 0:
        record["review_diagnostics"]["guess_accuracy"] = "UNKNOWN"
        for cell in record["review_diagnostics"]["guess_confusion"]:
            cell["count"] = 0
        for item in (*record["medians"], *record["ratios"]):
            item["value"] = "UNKNOWN"
    record["terminal_reason_code"] = status

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
    counts = record["comparison_counts"][0]
    counts["a_win_count"] = 2
    counts[
        {
            "B_WIN": "b_win_count",
            "TIE": "tie_count",
            "TIE_NONVIABLE": "tie_nonviable_count",
            "A_WIN": "a_win_count",
        }[method_outcome]
    ] += 1

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


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("evidence_root", "relative/evidence"),
        ("evidence_root", "/"),
        ("smoke_id", "../smoke"),
        ("smoke_id", "nested/smoke"),
        ("smoke_id", "."),
    ],
)
def test_pilot_lock_requires_absolute_evidence_root_and_safe_attempt_ids(
    contracts: ModuleType,
    field: str,
    bad_value: str,
) -> None:
    record = _pilot_lock()
    record[field] = bad_value

    with pytest.raises(contracts.PilotContractError):
        contracts.validate_record(record)

    record = _pilot_lock()
    record["live_attempt_ids"][0] = bad_value
    if field == "evidence_root":
        return
    with pytest.raises(contracts.PilotContractError):
        contracts.validate_record(record)


def test_summary_requires_exact_metric_and_ratio_row_sets(
    contracts: ModuleType,
) -> None:
    record = _pilot_summary()
    record["medians"].pop()
    with pytest.raises(contracts.PilotContractError):
        contracts.validate_record(record)

    record = _pilot_summary()
    record["ratios"][0]["metric"] = "arbitrary_metric"
    with pytest.raises(contracts.PilotContractError):
        contracts.validate_record(record)


@pytest.mark.parametrize(
    "mutation",
    [
        "comparison_total",
        "viability_total",
        "lifecycle_total",
        "failure_projection",
        "provider_call_coverage",
        "review_block_coverage",
        "guess_accuracy",
    ],
)
def test_summary_rejects_cross_count_inconsistency(
    contracts: ModuleType,
    mutation: str,
) -> None:
    record = _pilot_summary()
    if mutation == "comparison_total":
        record["comparison_counts"][0]["a_win_count"] += 1
    elif mutation == "viability_total":
        record["treatment_statistics"][0]["viable_count"] -= 1
    elif mutation == "lifecycle_total":
        record["treatment_statistics"][0]["lifecycle_outcome_counts"][
            "COMPLETED"
        ] -= 1
    elif mutation == "failure_projection":
        record["treatment_statistics"][0]["failure_class_counts"]["TIMEOUT"] = 1
    elif mutation == "provider_call_coverage":
        record["treatment_statistics"][0]["provider_call_counts"].pop()
    elif mutation == "review_block_coverage":
        record["review_diagnostics"]["blocks"][0]["block_id"] = "other-block"
    else:
        record["review_diagnostics"]["guess_accuracy"] = {
            "numerator": 2,
            "denominator": 3,
        }

    with pytest.raises(contracts.PilotContractError):
        contracts.validate_record(record)


def test_terminal_reason_must_equal_terminal_status(
    contracts: ModuleType,
) -> None:
    record = _pilot_summary()
    record["status"] = "STOP_INSUFFICIENT_VALID_BLOCKS"
    record["valid_blocks"] = record["valid_blocks"][:2]
    record["terminal_reason_code"] = "STOP_APPARATUS_NOT_VIABLE"

    with pytest.raises(contracts.PilotContractError):
        contracts.validate_record(record)


def test_hard_contract_findings_are_closed_observed_dispositions(
    contracts: ModuleType,
) -> None:
    record = _pilot_summary()
    record["hard_contract_findings"] = [
        {
            "block_id": "live-001",
            "treatment_id": "ORC",
            "finding_class": "CHECK_FAILURE",
            "disposition": "TREATMENT_OUTCOME_RETAINED",
            "evidence_references": ["blocks/live-001/orc/checks.json"],
        }
    ]
    contracts.validate_record(record)

    record["hard_contract_findings"][0]["finding_class"] = "INFERRED_FAILURE"
    with pytest.raises(contracts.PilotContractError):
        contracts.validate_record(record)


def test_load_record_applies_apparatus_semantic_validation(
    contracts: ModuleType,
    tmp_path: Path,
) -> None:
    path = tmp_path / "pilot-lock.json"
    record = _pilot_lock()
    task_path = record["apparatus"]["task_path"]
    task_asset = next(
        asset
        for asset in record["apparatus"]["asset_manifest"]
        if asset["path"] == task_path
    )
    task_asset["sha256"] = _digest("load-time-mismatch")
    path.write_bytes(contracts.canonical_json_bytes(record))

    with pytest.raises(
        contracts.PilotContractError,
        match="task_brief_digest_mismatch",
    ):
        contracts.load_record(path, expected_kind="pilot_lock.v1")


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
