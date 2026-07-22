from __future__ import annotations

import json
import hashlib
import fcntl
import os
import re
import selectors
import shutil
import subprocess
import sys
import inspect
import time
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
import orchestrator.retirement as retirement
import orchestrator.retirement.broad_evidence as broad_evidence
import orchestrator.retirement.materialization as retirement_materialization
from orchestrator.retirement import safe_io

from orchestrator.retirement.broad_evidence import (
    _bound_subject_manifest_issues,
    ContractError,
    build_initial_execution_ledger,
    build_broad_known_failure_baseline,
    build_broad_outcome,
    build_pytest_temp_root_preflight,
    build_implementation_focused_report,
    build_implementation_verification_subject,
    apply_skip_change,
    canonical_sha256,
    compare_failure_sets,
    file_sha256,
    load_json_closed,
    normalize_failure_payload,
    parse_exit_bytes,
    parse_junit_outcomes,
    publish_immutable_review,
    validate_fixture_manifest,
    validate_implementation_focused_report,
    validate_execution_ledger,
    validate_bound_record,
    validate_record,
    write_json,
)
from orchestrator.retirement.materialization import (
    MaterializationError,
    materialize_transaction,
    materialize_pending,
    validate_generation,
)
from orchestrator.retirement.source_bindings import capture_workspace_baseline


def _ledger(plan_path: Path) -> dict[str, object]:
    tasks = [
        {
            "task_number": number,
            "title": f"Task {number}",
            "status": "in_progress" if number == 1 else "pending",
            "completed_step_count": 0,
            "total_step_count": 4,
            "evidence_bindings": [],
        }
        for number in range(1, 18)
    ]
    record: dict[str, object] = {
        "schema_version": "workflow_retirement_execution_ledger.v1",
        "plan_binding": {
            "path": plan_path.as_posix(),
            "sha256": f"sha256:{'1' * 64}",
        },
        "task_count": 17,
        "tasks": tasks,
        "current_task": 1,
        "last_transition": None,
        "normalized_ledger_sha256": "",
        "claims_not_made": [
            "This ledger does not authorize deletion, owner action, or workflow execution."
        ],
    }
    record["normalized_ledger_sha256"] = canonical_sha256(
        record, exclude={"normalized_ledger_sha256"}
    )
    return record


def _write_ledger_plan(path: Path) -> None:
    path.write_text(
        "\n".join(
            f"### Task {number}: Task {number}\n\n"
            + "\n".join(
                f"- [ ] **Step {step}: Work**" for step in range(1, 5)
            )
            for number in range(1, 18)
        )
        + "\n"
    )


def _prior_generation_binding(receipt) -> dict[str, object]:
    return {
        "request_path": receipt.request_path.as_posix(),
        "request_sha256": receipt.request_sha256,
        "snapshot_path": receipt.snapshot_path.as_posix(),
        "snapshot_sha256": receipt.snapshot_sha256,
        "generation": receipt.generation,
        "output_path": receipt.output_path.as_posix(),
    }


def _ledger_binding(receipt) -> dict[str, object]:
    return {
        "live_path": receipt.output_path.as_posix(),
        "byte_sha256": receipt.output_sha256,
        "schema_version": "workflow_retirement_execution_ledger.v1",
        "generation": receipt.generation,
        "request_path": receipt.request_path.as_posix(),
        "request_sha256": receipt.request_sha256,
        "snapshot_path": receipt.snapshot_path.as_posix(),
        "snapshot_sha256": receipt.snapshot_sha256,
    }


def _advance_bound_ledger(
    repository: Path,
    binding: dict[str, object],
    *,
    evidence_bindings: list[dict[str, object]] | None = None,
    future_paths: list[str] | None = None,
):
    """Canonically publish the child of an existing ledger binding."""

    prior = load_json_closed(repository / binding["snapshot_path"])
    request = load_json_closed(repository / binding["request_path"])
    receipt = retirement_materialization.MaterializationReceipt(
        request_path=Path(binding["request_path"]),
        request_sha256=binding["request_sha256"],
        snapshot_path=Path(binding["snapshot_path"]),
        snapshot_sha256=binding["snapshot_sha256"],
        generation=binding["generation"],
        output_path=Path(binding["live_path"]),
        output_sha256=binding["byte_sha256"],
    )
    record = _advance_ledger(
        prior,
        receipt,
        evidence_bindings=evidence_bindings,
        future_paths=future_paths,
    )
    approved_plan = next(
        Path(row["path"])
        for row in request["input_bindings"]
        if row["role"] == "approved_plan"
    )
    next_receipt = materialize_transaction(
        repository_root=repository,
        evidence_root=retirement_materialization._evidence_root_from_request_path(
            receipt.request_path
        ),
        record_kind="execution-ledger",
        output_path=receipt.output_path,
        generation=receipt.generation + 1,
        input_paths={"approved_plan": approved_plan},
        parameters={"record": record},
        prior_request=receipt.request_path,
        prior_snapshot=receipt.snapshot_path,
    )
    return record, next_receipt


def _advance_ledger(
    prior: dict[str, object],
    receipt,
    *,
    evidence_bindings: list[dict[str, object]] | None = None,
    future_paths: list[str] | None = None,
) -> dict[str, object]:
    record = deepcopy(prior)
    task_number = record["current_task"]
    assert isinstance(task_number, int)
    task = record["tasks"][task_number - 1]
    assert task["status"] == "in_progress"
    step_number = task["completed_step_count"] + 1
    evidence = list(evidence_bindings or [])
    task["completed_step_count"] = step_number
    task["evidence_bindings"] = sorted(
        [*task["evidence_bindings"], *evidence], key=lambda row: row["path"]
    )
    old_status = "in_progress"
    if step_number == task["total_step_count"]:
        task["status"] = "complete"
        new_status = "complete"
        if task_number == 17:
            record["current_task"] = None
        else:
            record["tasks"][task_number]["status"] = "in_progress"
            record["current_task"] = task_number + 1
    else:
        new_status = "in_progress"
    record["last_transition"] = {
        "prior_generation_binding": _prior_generation_binding(receipt),
        "task_number": task_number,
        "step_number": step_number,
        "old_status": old_status,
        "new_status": new_status,
        "prepared_at": "2026-01-01T00:00:00+00:00",
        "evidence_bindings": evidence,
        "future_bindings": [
            {"path": path, "sha256": None} for path in sorted(future_paths or [])
        ],
    }
    record["normalized_ledger_sha256"] = canonical_sha256(
        record, exclude={"normalized_ledger_sha256"}
    )
    return record


def test_duplicate_keys_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text('{"schema_version":"x","schema_version":"y"}\n')

    with pytest.raises(ContractError, match="duplicate_json_key"):
        load_json_closed(path)


def test_typed_issues_sort_by_path_then_code_then_message() -> None:
    issues = [
        broad_evidence.Issue("z-code", "$.a", "later"),
        broad_evidence.Issue("a-code", "$.b", "first-path-later"),
        broad_evidence.Issue("a-code", "$.a", "z-message"),
        broad_evidence.Issue("a-code", "$.a", "a-message"),
    ]

    assert sorted(issues) == [
        broad_evidence.Issue("a-code", "$.a", "a-message"),
        broad_evidence.Issue("a-code", "$.a", "z-message"),
        broad_evidence.Issue("z-code", "$.a", "later"),
        broad_evidence.Issue("a-code", "$.b", "first-path-later"),
    ]


def test_execution_ledger_is_closed_and_has_one_current_task(tmp_path: Path) -> None:
    ledger = _ledger(Path("docs/plans/plan.md"))
    assert validate_execution_ledger(ledger) == []

    ledger["unexpected"] = True
    issues = validate_execution_ledger(ledger)
    assert [issue.code for issue in issues] == ["record_keys_mismatch"]


def test_initial_ledger_is_derived_from_the_immutable_plan(tmp_path: Path) -> None:
    plan = tmp_path / "plan.md"
    plan.write_text(
        "\n".join(
            [
                f"### Task {number}: Title {number}\n\n"
                + "\n".join(
                    f"- [ ] **Step {step}: Work**" for step in range(1, (number % 3) + 2)
                )
                for number in range(1, 18)
            ]
        )
        + "\n"
    )
    ledger = build_initial_execution_ledger(
        plan_path=Path("plan.md"),
        plan_bytes=plan.read_bytes(),
    )
    assert ledger["task_count"] == 17
    assert ledger["current_task"] == 1
    assert ledger["tasks"][0]["status"] == "in_progress"
    assert ledger["tasks"][16]["title"] == "Title 17"
    assert ledger["tasks"][16]["total_step_count"] == 3
    assert validate_execution_ledger(ledger) == []


def test_initial_ledger_rejects_missing_or_noncontiguous_task(tmp_path: Path) -> None:
    plan = tmp_path / "plan.md"
    plan.write_text("### Task 1: Only\n\n- [ ] **Step 1: Work**\n")
    with pytest.raises(ContractError, match="plan_task_partition_invalid"):
        build_initial_execution_ledger(plan_path=Path("plan.md"), plan_bytes=plan.read_bytes())


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        (
            lambda ledger: ledger["tasks"][0].__setitem__(
                "evidence_bindings", "garbage"
            ),
            "ledger_evidence_bindings_invalid",
        ),
        (
            lambda ledger: ledger["tasks"][0].__setitem__(
                "completed_step_count", 999
            ),
            "ledger_step_count_invalid",
        ),
        (
            lambda ledger: ledger["tasks"][1].__setitem__("status", "complete"),
            "ledger_status_sequence_invalid",
        ),
        (
            lambda ledger: ledger.__setitem__("last_transition", "garbage"),
            "ledger_transition_invalid",
        ),
    ],
)
def test_execution_ledger_rejects_redigested_deep_tamper(
    mutation, expected_code: str
) -> None:
    ledger = _ledger(Path("plan.md"))
    mutation(ledger)
    ledger["normalized_ledger_sha256"] = canonical_sha256(
        ledger, exclude={"normalized_ledger_sha256"}
    )

    assert expected_code in {issue.code for issue in validate_record(ledger)}


def test_ledger_materializer_rejects_forged_plan_title(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    plan = repository / "plan.md"
    _write_ledger_plan(plan)
    ledger = _ledger(Path("plan.md"))
    ledger["plan_binding"]["sha256"] = file_sha256(plan)
    ledger["tasks"][0]["title"] = "Forged title"
    ledger["normalized_ledger_sha256"] = canonical_sha256(
        ledger, exclude={"normalized_ledger_sha256"}
    )

    with pytest.raises(MaterializationError, match="ledger_plan_task_mismatch"):
        materialize_transaction(
            repository_root=repository,
            evidence_root=Path("evidence"),
            record_kind="execution-ledger",
            output_path=Path("evidence/execution-ledger.json"),
            generation=1,
            input_paths={"approved_plan": Path("plan.md")},
            parameters={"record": ledger},
        )

    assert not (repository / "evidence").exists()


def test_normalization_only_rewrites_bound_prefixes() -> None:
    payload = (
        "/repo/tests/a.py\r\n"
        "/tmp/pytest-of-ci.user+gpu/pytest-12/test_case0/value.json\n"
        "/tmp/pytest-of-ci.user+gpu/pytest-13x/test_case0/value.json"
    )
    normalized = normalize_failure_payload(
        payload,
        repository_root=Path("/repo"),
        pytest_session_parent=Path("/tmp/pytest-of-ci.user+gpu"),
    )
    assert normalized == (
        "<repo>/tests/a.py\n"
        "<pytest-tmp>/test_case0/value.json\n"
        "/tmp/pytest-of-ci.user+gpu/pytest-13x/test_case0/value.json"
    )


@pytest.mark.parametrize("raw, expected", [(b"0\n", 0), (b"17\n", 17), (b"-9\n", -9)])
def test_exit_bytes_are_exact_base10_plus_lf(raw: bytes, expected: int) -> None:
    assert parse_exit_bytes(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [b"", b"0", b"00\n", b"+1\n", b" 1\n", b"1\r\n", b"1\n\n", b"x\n"],
)
def test_malformed_exit_bytes_fail_closed(raw: bytes) -> None:
    with pytest.raises(ContractError, match="invalid_exit_bytes"):
        parse_exit_bytes(raw)


@pytest.mark.parametrize(
    "lookalike",
    [
        "/tmp/pytest-of-ci.user+gpu/pytest-X/a",
        "/tmp/pytest-of-ci.user+gpu/pytest-12x/a",
        "relative/tmp/pytest-of-ci.user+gpu/pytest-12/a",
        "/tmp/pytest-of-ci_user_gpu/pytest-12/a",
        "embedded/tmp/pytest-of-ci.user+gpu/pytest-12/a",
    ],
)
def test_normalization_preserves_unbound_or_near_match_paths(lookalike: str) -> None:
    assert normalize_failure_payload(
        lookalike,
        repository_root=Path("/repo"),
        pytest_session_parent=Path("/tmp/pytest-of-ci.user+gpu"),
    ) == lookalike


@pytest.mark.parametrize("boundary", ["\u00a0", "\u2003", "\u2028", "\u202f"])
def test_normalization_does_not_treat_unicode_whitespace_as_a_path_boundary(
    boundary: str,
) -> None:
    payload = f"prefix{boundary}/tmp/pytest-of-u/pytest-12/test_case0/value.json"

    assert normalize_failure_payload(
        payload,
        repository_root=Path("/repo"),
        pytest_session_parent=Path("/tmp/pytest-of-u"),
    ) == payload


@pytest.mark.parametrize("boundary", [" ", "\t", "\r", "\n", "\f", "\v", '"', "'", "(", "[", "{", "=", ":", "`"])
def test_normalization_accepts_only_enumerated_ascii_path_boundaries(
    boundary: str,
) -> None:
    payload = f"prefix{boundary}/tmp/pytest-of-u/pytest-12/test_case0/value.json"

    assert normalize_failure_payload(
        payload,
        repository_root=Path("/repo"),
        pytest_session_parent=Path("/tmp/pytest-of-u"),
    ) == f"prefix{boundary}<pytest-tmp>/test_case0/value.json"


@pytest.mark.parametrize(
    ("field", "value", "expected_code"),
    [
        ("repository_root", "repo", "normalization_repository_root_invalid"),
        ("system_temp_root", "tmp", "normalization_system_temp_root_invalid"),
        ("pytest_session_parent", "tmp/pytest", "normalization_session_parent_invalid"),
        ("pytest_temp_root_preflight_binding", {}, "normalization_preflight_binding_invalid"),
        ("pytest_version", "0.0", "normalization_pytest_version_invalid"),
        ("pytest_root_component", "", "normalization_root_component_invalid"),
        ("pytest_root_component", "nested/name", "normalization_root_component_invalid"),
        ("pytest_session_parent", "/tmp/other", "normalization_session_parent_mismatch"),
        ("ordered_transforms", [], "normalization_transforms_invalid"),
        ("pytest_temp_prefix_rule", "other.v1", "normalization_rule_invalid"),
    ],
)
def test_failure_normalization_closes_deep_contract(
    field: str, value: object, expected_code: str
) -> None:
    record = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence/")
        / "broad_failure_payload_normalization.v1.json"
    )
    record[field] = value
    record["normalized_contract_sha256"] = canonical_sha256(
        record, exclude={"normalized_contract_sha256"}
    )

    assert expected_code in {issue.code for issue in validate_record(record)}


def test_failure_normalization_digest_is_authoritative() -> None:
    record = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence/")
        / "broad_failure_payload_normalization.v1.json"
    )
    record["normalized_contract_sha256"] = "sha256:" + "0" * 64
    assert "normalized_digest_mismatch" in {
        issue.code for issue in validate_record(record)
    }


def test_bound_failure_normalization_reopens_and_reconciles_preflight(
    tmp_path: Path,
) -> None:
    preflight = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence/")
        / "pytest_temp_root_preflight.v1.json"
    )
    preflight_path = tmp_path / "preflight.json"
    preflight_path.write_text(json.dumps(preflight, sort_keys=True) + "\n")
    record = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence/")
        / "broad_failure_payload_normalization.v1.json"
    )
    record["repository_root"] = tmp_path.as_posix()
    record["pytest_temp_root_preflight_binding"] = {
        "path": "preflight.json",
        "sha256": file_sha256(preflight_path),
    }
    record["pytest_root_component"] = "different"
    record["normalized_contract_sha256"] = canonical_sha256(
        record, exclude={"normalized_contract_sha256"}
    )

    assert "normalization_preflight_mismatch" in {
        issue.code for issue in validate_bound_record(record, tmp_path)
    }

    preflight_path.write_text("{}\n")
    assert "bound_file_unreadable" in {
        issue.code for issue in validate_bound_record(record, tmp_path)
    }


def test_unknown_schema_and_unknown_keys_fail_closed() -> None:
    assert validate_record({"schema_version": "not-a-schema.v1"})[0].code == "unknown_schema"


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        (lambda record: record.__setitem__("record_kind", "unknown"), "request_record_kind_invalid"),
        (lambda record: record.__setitem__("output_path", "../escape.json"), "request_output_path_invalid"),
        (lambda record: record.__setitem__("output_path", "evidence/wrong-name.json"), "request_output_slot_invalid"),
        (lambda record: record.__setitem__("generation", "1"), "request_generation_invalid"),
        (lambda record: record.__setitem__("input_bindings", {}), "request_input_bindings_invalid"),
        (lambda record: record.__setitem__("parameters", []), "request_parameters_invalid"),
        (
            lambda record: record.__setitem__(
                "expected_input_set_sha256", f"sha256:{'f' * 64}"
            ),
            "request_input_set_digest_mismatch",
        ),
        (
            lambda record: (
                record.__setitem__("generation", 2),
                record.__setitem__("prior_generation_binding", {}),
            ),
            "request_prior_generation_invalid",
        ),
    ],
)
def test_materialization_request_rejects_redigested_deep_tamper(
    tmp_path: Path, mutation, expected_code: str
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    _, _, receipt = _materialize_first_ledger(repository)
    request = load_json_closed(repository / receipt.request_path)
    mutation(request)
    request["normalized_request_sha256"] = canonical_sha256(
        request, exclude={"normalized_request_sha256"}
    )

    assert expected_code in {issue.code for issue in validate_record(request)}


def test_bound_record_validator_is_part_of_the_stable_public_surface() -> None:
    from orchestrator.retirement import validate_bound_record as public_validator

    assert public_validator is validate_bound_record


def test_fixture_manifest_reconciles_directory_in_both_directions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    root = Path("tests/fixtures/example")
    root.mkdir(parents=True)
    fixture = root / "row.json"
    fixture.write_text('{"schema_version":"review.v1"}\n')
    import hashlib

    row = {
        "path": "row.json",
        "schema_version": "review.v1",
        "lifecycle_role": "negative_incomplete_review",
        "expected_validation": "rejected",
        "file_sha256": f"sha256:{hashlib.sha256(fixture.read_bytes()).hexdigest()}",
    }
    manifest = {
        "schema_version": "retirement_fixture_manifest.v1",
        "fixture_root": "tests/fixtures/example",
        "rows": [row],
        "fixture_count": 1,
        "normalized_path_set_sha256": canonical_sha256(["row.json"]),
        "normalized_row_set_sha256": canonical_sha256([row]),
        "claims_not_made": ["Fixtures are not repository evidence."],
    }
    (root / "manifest.v1.json").write_text(json.dumps(manifest) + "\n")
    assert validate_fixture_manifest(root) == []

    (root / "extra.json").write_text("{}\n")
    assert validate_fixture_manifest(root)[0].code == "fixture_path_set_mismatch"


def test_fixture_manifest_rejects_wrong_declared_root_coordinate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    root = Path("tests/fixtures/actual")
    root.mkdir(parents=True)
    manifest = {
        "schema_version": "retirement_fixture_manifest.v1",
        "fixture_root": "tests/fixtures/different",
        "rows": [],
        "fixture_count": 0,
        "normalized_path_set_sha256": canonical_sha256([]),
        "normalized_row_set_sha256": canonical_sha256([]),
        "claims_not_made": ["Fixtures are not repository evidence."],
    }
    (root / "manifest.v1.json").write_text(json.dumps(manifest) + "\n")

    assert "fixture_root_mismatch" in {
        issue.code for issue in validate_fixture_manifest(root)
    }


@pytest.mark.parametrize(
    ("fixture_record", "declared_schema", "expected_validation", "expected_code"),
    [
        (
            {"schema_version": "invented_schema.v1"},
            "invented_schema.v1",
            "rejected",
            "fixture_schema_not_registered",
        ),
        (
            {"schema_version": "review.v1"},
            "broad_outcome.v1",
            "rejected",
            "fixture_schema_binding_mismatch",
        ),
        (
            load_json_closed(
                Path("tests/fixtures/retirement_broad_evidence/review.v1.json")
            ),
            "review.v1",
            "rejected",
            "fixture_expected_validation_mismatch",
        ),
        (
            {"schema_version": "review.v1"},
            "review.v1",
            "accepted",
            "fixture_expected_validation_mismatch",
        ),
    ],
)
def test_fixture_manifest_binds_registered_schema_and_observed_validation(
    tmp_path: Path,
    fixture_record: dict[str, object],
    declared_schema: str,
    expected_validation: str,
    expected_code: str,
) -> None:
    root = tmp_path / "fixtures"
    root.mkdir()
    fixture = root / "row.json"
    fixture.write_text(json.dumps(fixture_record, sort_keys=True) + "\n")
    row = {
        "path": "row.json",
        "schema_version": declared_schema,
        "lifecycle_role": "schema_validation_probe",
        "expected_validation": expected_validation,
        "file_sha256": file_sha256(fixture),
    }
    manifest = {
        "schema_version": "retirement_fixture_manifest.v1",
        "fixture_root": "tests/fixtures/example",
        "rows": [row],
        "fixture_count": 1,
        "normalized_path_set_sha256": canonical_sha256(["row.json"]),
        "normalized_row_set_sha256": canonical_sha256([row]),
        "claims_not_made": ["Fixtures are not repository evidence."],
    }
    (root / "manifest.v1.json").write_text(json.dumps(manifest) + "\n")

    assert expected_code in {
        issue.code for issue in validate_fixture_manifest(root)
    }


def test_fixture_manifest_rejects_malformed_row_values_before_sorting(
    tmp_path: Path,
) -> None:
    root = tmp_path / "fixtures"
    root.mkdir()
    manifest = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence/manifest.v1.json")
    )
    manifest["rows"][0]["path"] = None
    (root / "manifest.v1.json").write_text(json.dumps(manifest) + "\n")

    issues = validate_fixture_manifest(root)

    assert "fixture_row_values_invalid" in {issue.code for issue in issues}


def test_repository_fixture_manifest_owns_all_task1_contract_examples() -> None:
    root = Path("tests/fixtures/retirement_broad_evidence")
    required = {
        "execution_ledger.initial.v1.json",
        "execution_ledger.in_progress.v1.json",
        "execution_ledger.complete.v1.json",
        "retirement_materialization_request.v1.json",
        "pytest_temp_root_preflight.v1.json",
        "broad_failure_payload_normalization.v1.json",
        "workspace_baseline.v1.json",
        "bootstrap_workspace_baseline.v1.json",
        "non_target_queue_sources.v1.json",
        "query.v1.json",
        "precommit_control.v1.json",
        "broad_outcome.v1.json",
        "broad_outcome.exact_match.v1.json",
        "broad_outcome.reviewed_subset.v1.json",
        "implementation_focused_report.v1.json",
        "implementation_verification_subject.v1.json",
        "broad_evidence_bootstrap_subject.v1.json",
        "broad_known_failure_baseline.v1.json",
        "broad_failure_baseline_attestation.pending.v1.json",
        "broad_failure_baseline_attestation.confirmed.v1.json",
        "broad_failure_remediation.v1.json",
        "broad_skip_change.v1.json",
        "review.v1.json",
        "review_binding.v1.json",
        "execution_ledger.invalid.unknown_key.v1.json",
        "broad_outcome.invalid.digest.v1.json",
        "broad_failure_payload_normalization.invalid.order.v1.json",
        "review.invalid.result.v1.json",
        "broad_failure_baseline_attestation.invalid.pending_owner.v1.json",
        "workspace_baseline.invalid.unknown_key.v1.json",
        "bootstrap_workspace_baseline.invalid.archive_persisted.v1.json",
        "non_target_queue_sources.invalid.partition.v1.json",
        "query.invalid.partition.v1.json",
        "precommit_control.invalid.digest.v1.json",
    }
    manifest = load_json_closed(root / "manifest.v1.json")
    assert {row["path"] for row in manifest["rows"]} == required
    assert validate_fixture_manifest(root) == []


def test_materialization_request_fixture_is_exact_producer_output(
    tmp_path: Path,
) -> None:
    plan_path = Path(
        "docs/plans/2026-07-17-yaml-retirement-task-6-execution-plan.md"
    )
    destination = tmp_path / plan_path
    destination.parent.mkdir(parents=True)
    destination.write_bytes(plan_path.read_bytes())
    record = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence/")
        / "execution_ledger.initial.v1.json"
    )
    evidence_root = Path(
        "docs/plans/evidence/yaml-retirement/delete-non-survivor-estate"
    )

    receipt = materialize_transaction(
        repository_root=tmp_path,
        evidence_root=evidence_root,
        record_kind="execution-ledger",
        output_path=evidence_root / "execution-ledger.json",
        generation=1,
        input_paths={"approved_plan": plan_path},
        parameters={"record": record},
    )

    assert (tmp_path / receipt.request_path).read_bytes() == Path(
        "tests/fixtures/retirement_broad_evidence/"
        "retirement_materialization_request.v1.json"
    ).read_bytes()


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("extra_file", "fixture_path_set_mismatch"),
        ("missing_file", "fixture_path_set_mismatch"),
        ("duplicate_path", "fixture_path_set_mismatch"),
        ("duplicate_role", "fixture_lifecycle_role_duplicate"),
    ],
)
def test_fixture_manifest_proves_exact_bidirectional_inventory(
    tmp_path: Path, mutation: str, expected_code: str
) -> None:
    source = Path("tests/fixtures/retirement_broad_evidence")
    root = tmp_path / "fixtures"
    shutil.copytree(source, root)
    manifest_path = root / "manifest.v1.json"
    manifest = load_json_closed(manifest_path)
    if mutation == "extra_file":
        (root / "unregistered.json").write_text("{}\n")
    elif mutation == "missing_file":
        (root / manifest["rows"][0]["path"]).unlink()
    elif mutation == "duplicate_path":
        manifest["rows"].append(deepcopy(manifest["rows"][0]))
        manifest_path.write_text(json.dumps(manifest) + "\n")
    else:
        row = deepcopy(manifest["rows"][0])
        source_fixture = root / row["path"]
        row["path"] = "duplicate-lifecycle-role.json"
        (root / row["path"]).write_bytes(source_fixture.read_bytes())
        manifest["rows"].append(row)
        manifest["rows"] = sorted(manifest["rows"], key=lambda item: item["path"])
        manifest["fixture_count"] = len(manifest["rows"])
        manifest["normalized_path_set_sha256"] = canonical_sha256(
            [item["path"] for item in manifest["rows"]]
        )
        manifest["normalized_row_set_sha256"] = canonical_sha256(
            manifest["rows"]
        )
        manifest_path.write_text(json.dumps(manifest) + "\n")

    assert expected_code in {
        issue.code for issue in validate_fixture_manifest(root)
    }


@pytest.mark.parametrize(
    "fixture_name",
    [
        "execution_ledger.initial.v1.json",
        "execution_ledger.in_progress.v1.json",
        "execution_ledger.complete.v1.json",
        "retirement_materialization_request.v1.json",
        "pytest_temp_root_preflight.v1.json",
        "broad_failure_payload_normalization.v1.json",
        "broad_outcome.v1.json",
        "broad_outcome.exact_match.v1.json",
        "broad_outcome.reviewed_subset.v1.json",
        "implementation_focused_report.v1.json",
        "implementation_verification_subject.v1.json",
        "broad_evidence_bootstrap_subject.v1.json",
        "broad_known_failure_baseline.v1.json",
        "broad_failure_baseline_attestation.pending.v1.json",
        "broad_failure_baseline_attestation.confirmed.v1.json",
        "broad_failure_remediation.v1.json",
        "broad_skip_change.v1.json",
        "review.v1.json",
        "review_binding.v1.json",
    ],
)
def test_canonical_broad_fixture_passes_its_closed_shape(fixture_name: str) -> None:
    fixture = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence") / fixture_name
    )
    assert validate_record(fixture) == []


def test_validate_record_returns_issues_for_non_string_schema_version() -> None:
    issues = validate_record({"schema_version": []})

    assert isinstance(issues, list)
    assert [issue.code for issue in issues] == ["unknown_schema"]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda record: record.__setitem__("observed_totals", None),
        lambda record: record["observed_failed_node_ids"].__setitem__(0, None),
        lambda record: record["observed_totals"].__setitem__("collected", False),
        lambda record: record["collection_binding"].__setitem__(
            "node_id_count", False
        ),
    ],
)
def test_bootstrap_subject_rejects_malformed_and_boolean_totals_without_raising(
    mutation,
) -> None:
    record = load_json_closed(
        Path(
            "tests/fixtures/retirement_broad_evidence/broad_evidence_bootstrap_subject.v1.json"
        )
    )
    mutation(record)
    record["normalized_subject_sha256"] = canonical_sha256(
        record, exclude={"normalized_subject_sha256"}
    )

    issues = validate_record(record)

    assert isinstance(issues, list)
    assert issues


@pytest.mark.parametrize("failure_count", [5, 7])
def test_bootstrap_subject_requires_exactly_six_failure_or_error_rows(
    failure_count: int,
) -> None:
    record = load_json_closed(
        Path(
            "tests/fixtures/retirement_broad_evidence/broad_evidence_bootstrap_subject.v1.json"
        )
    )
    record["observed_failed_node_ids"] = [
        f"tests/synthetic.py::test_{index}" for index in range(failure_count)
    ]
    record["observed_totals"]["failed"] = failure_count
    record["observed_totals"]["errors"] = 0
    record["observed_totals"]["collected"] = (
        record["observed_totals"]["passed"]
        + record["observed_totals"]["failed"]
        + record["observed_totals"]["errors"]
        + record["observed_totals"]["skipped"]
    )
    record["collection_binding"]["node_id_count"] = record["observed_totals"][
        "collected"
    ]
    record["normalized_subject_sha256"] = canonical_sha256(
        record, exclude={"normalized_subject_sha256"}
    )

    assert "observed_failure_count_invalid" in {
        issue.code for issue in validate_record(record)
    }
    assert "observed_failure_count_invalid" in {
        issue.code for issue in validate_bound_record(record, Path("."))
    }


@pytest.mark.parametrize("field", ["completed_step_count", "total_step_count"])
def test_execution_ledger_rejects_boolean_step_counts(field: str) -> None:
    record = load_json_closed(
        Path(
            "tests/fixtures/retirement_broad_evidence/execution_ledger.in_progress.v1.json"
        )
    )
    record["tasks"][0][field] = False
    record["normalized_ledger_sha256"] = canonical_sha256(
        record, exclude={"normalized_ledger_sha256"}
    )

    assert "ledger_step_count_invalid" in {
        issue.code for issue in validate_record(record)
    }


@pytest.mark.parametrize(
    ("fixture_name", "field", "value", "expected_code"),
    [
        (
            "execution_ledger.initial.v1.json",
            "task_count",
            17.0,
            "ledger_task_count_invalid",
        ),
        (
            "execution_ledger.in_progress.v1.json",
            "current_task",
            True,
            "ledger_current_task_mismatch",
        ),
        (
            "execution_ledger.in_progress.v1.json",
            "current_task",
            1.0,
            "ledger_current_task_mismatch",
        ),
        (
            "implementation_focused_report.v1.json",
            "command_count",
            True,
            "focused_command_count_mismatch",
        ),
        (
            "implementation_focused_report.v1.json",
            "command_count",
            1.0,
            "focused_command_count_mismatch",
        ),
    ],
)
def test_broad_records_require_exact_integer_selector_and_count_types(
    fixture_name: str, field: str, value: object, expected_code: str
) -> None:
    record = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence") / fixture_name
    )
    record[field] = value
    digest_field = broad_evidence.DIGEST_FIELDS[record["schema_version"]]
    assert digest_field is not None
    record[digest_field] = canonical_sha256(record, exclude={digest_field})

    assert expected_code in {issue.code for issue in validate_record(record)}


def test_focused_record_requires_observed_roles_to_match_authoritative_roles() -> None:
    record = load_json_closed(
        Path(
            "tests/fixtures/retirement_broad_evidence/"
            "implementation_focused_report.v1.json"
        )
    )
    record["commands"][0]["role_id"] = "different-role"
    record["normalized_report_sha256"] = canonical_sha256(
        record, exclude={"normalized_report_sha256"}
    )

    assert "focused_command_contract_mismatch" in {
        issue.code for issue in validate_record(record)
    }


def _json_value_paths(value: object, prefix: tuple[object, ...] = ()):
    if isinstance(value, dict):
        for key, child in value.items():
            path = (*prefix, key)
            yield path
            yield from _json_value_paths(child, path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            path = (*prefix, index)
            yield path
            yield from _json_value_paths(child, path)


def _alternate_json_category_values(value: object) -> list[object]:
    candidates: list[object] = [None, False, True, 0, 1, 0.0, 1.0, "", [], {}]
    if type(value) is int:
        candidates.append(float(value))
    result: list[object] = []
    for candidate in candidates:
        if type(candidate) is type(value):
            continue
        coordinate = (type(candidate), repr(candidate))
        if any((type(item), repr(item)) == coordinate for item in result):
            continue
        result.append(candidate)
    return result


def _mutate_json_path(
    record: object, path: tuple[object, ...], replacement: object
) -> None:
    parent = record
    for component in path[:-1]:
        parent = parent[component]
    leaf = path[-1]
    parent[leaf] = replacement


def test_all_accepted_broad_fixtures_have_total_json_type_validation() -> None:
    fixture_root = Path("tests/fixtures/retirement_broad_evidence")
    manifest = load_json_closed(fixture_root / "manifest.v1.json")
    accepted = [
        row
        for row in manifest["rows"]
        if row["expected_validation"] == "accepted"
        and row["schema_version"] in broad_evidence.SCHEMA_KEYS
    ]
    assert accepted
    accepted_category_changes: set[
        tuple[str, tuple[object, ...], str, str]
    ] = set()
    for row in accepted:
        canonical = load_json_closed(fixture_root / row["path"])
        assert validate_record(canonical) == [], row["path"]
        digest_field = broad_evidence.DIGEST_FIELDS[row["schema_version"]]
        for path in _json_value_paths(canonical):
            original = canonical
            for component in path:
                original = original[component]
            for replacement in _alternate_json_category_values(original):
                mutated = deepcopy(canonical)
                _mutate_json_path(mutated, path, replacement)
                if digest_field is not None and path != (digest_field,):
                    mutated[digest_field] = canonical_sha256(
                        mutated, exclude={digest_field}
                    )
                issues = validate_record(mutated)
                assert isinstance(issues, list)
                if not issues:
                    accepted_category_changes.add(
                        (
                            row["path"],
                            path,
                            type(replacement).__name__,
                            repr(replacement),
                        )
                    )
    assert accepted_category_changes == {
        (
            "broad_evidence_bootstrap_subject.v1.json",
            ("collection_binding", "environment", "PYTEST_DEBUG_TEMPROOT"),
            "NoneType",
            "None",
        ),
        (
            "broad_known_failure_baseline.v1.json",
            ("collection_binding", "environment", "PYTEST_DEBUG_TEMPROOT"),
            "NoneType",
            "None",
        ),
        (
            "pytest_temp_root_preflight.v1.json",
            ("environment_binding", "PYTEST_DEBUG_TEMPROOT"),
            "str",
            "''",
        ),
    }


def test_broad_outcome_requires_top_and_collection_environment_equality() -> None:
    record = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence/broad_outcome.v1.json")
    )
    record["environment"]["PYTEST_DEBUG_TEMPROOT"] = None
    record["normalized_outcome_sha256"] = canonical_sha256(
        record, exclude={"normalized_outcome_sha256"}
    )

    assert broad_evidence.Issue(
        "broad_environment_mismatch", "$.environment"
    ) in validate_record(record)


def test_bound_broad_outcome_reconciles_preflight_environment(
    tmp_path: Path,
) -> None:
    candidate, ledger = _producer_candidate_and_ledger(tmp_path)
    inputs = _producer_broad_builder_inputs(tmp_path, candidate, ledger)
    outcome = build_broad_outcome(**inputs)
    binding = outcome["pytest_temp_root_preflight"]
    preflight_path = tmp_path / binding["path"]
    preflight = load_json_closed(preflight_path)
    preflight["environment_binding"]["PYTEST_DEBUG_TEMPROOT"] = (
        "/tmp/different-root"
    )
    preflight["normalized_record_sha256"] = canonical_sha256(
        preflight, exclude={"normalized_record_sha256"}
    )
    _write_producer_json(tmp_path, binding["path"], preflight)
    new_binding = {
        "path": binding["path"],
        "sha256": file_sha256(preflight_path),
    }
    outcome["pytest_temp_root_preflight"] = new_binding
    outcome["failure_normalization"][
        "pytest_temp_root_preflight_binding"
    ] = new_binding
    outcome["failure_normalization"]["normalized_contract_sha256"] = (
        canonical_sha256(
            outcome["failure_normalization"],
            exclude={"normalized_contract_sha256"},
        )
    )
    outcome["normalized_outcome_sha256"] = canonical_sha256(
        outcome, exclude={"normalized_outcome_sha256"}
    )

    assert broad_evidence.Issue(
        "preflight_environment_mismatch"
    ) in validate_bound_record(outcome, tmp_path)


def test_known_failure_baseline_rejects_digest_consistent_one_row_table() -> None:
    record = load_json_closed(
        Path(
            "tests/fixtures/retirement_broad_evidence/"
            "broad_known_failure_baseline.v1.json"
        )
    )
    record["failures"] = [record["failures"][0]]
    record["normalized_failure_set_sha256"] = canonical_sha256(record["failures"])
    record["classification_summary"] = {"queue_owned": 1, "external": 0}
    record["totals"] = {
        "collected": 1,
        "passed": 0,
        "failed": 1,
        "errors": 0,
        "skipped": 0,
    }
    record["collection_binding"]["node_id_count"] = 1
    record["collection_binding"]["node_id_list_sha256"] = canonical_sha256(
        [record["failures"][0]["node_id"]]
    )

    assert [issue.code for issue in validate_record(record)] == [
        "baseline_failure_count_invalid"
    ]


@pytest.mark.parametrize(
    "fixture_name",
    [
        "execution_ledger.invalid.unknown_key.v1.json",
        "broad_outcome.invalid.digest.v1.json",
        "broad_failure_payload_normalization.invalid.order.v1.json",
        "review.invalid.result.v1.json",
        "broad_failure_baseline_attestation.invalid.pending_owner.v1.json",
    ],
)
def test_negative_broad_fixture_fails_closed(fixture_name: str) -> None:
    fixture = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence") / fixture_name
    )
    assert validate_record(fixture)


def test_review_contract_uses_the_plan_canonical_keys_and_kind_enum() -> None:
    review = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence/review.v1.json")
    )
    assert set(review) == {
        "schema_version",
        "review_kind",
        "reviewer",
        "reviewed_at",
        "subject",
        "result",
        "issues",
        "claims_not_made",
    }
    review["review_kind"] = "code_quality"
    assert validate_record(review) == []


def test_review_binding_contract_uses_the_plan_canonical_keys() -> None:
    binding = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence/review_binding.v1.json")
    )
    assert set(binding) == {
        "schema_version",
        "logical_path",
        "immutable_path",
        "sha256",
        "review_kind",
        "reviewer",
        "reviewed_at",
        "result",
        "subject",
        "normalized_binding_sha256",
        "claims_not_made",
    }


@pytest.mark.parametrize(
    ("fixture_name", "field"),
    [
        ("broad_outcome.v1.json", "candidate_binding"),
        (
            "broad_evidence_bootstrap_subject.v1.json",
            "bootstrap_workspace_baseline_binding",
        ),
        ("implementation_verification_subject.v1.json", "broad_outcome_binding"),
    ],
)
def test_redigested_empty_nested_bindings_fail_closed(
    fixture_name: str, field: str
) -> None:
    fixture = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence") / fixture_name
    )
    fixture[field] = {}
    digest_field = (
        "normalized_outcome_sha256"
        if fixture_name == "broad_outcome.v1.json"
        else "normalized_subject_sha256"
    )
    fixture[digest_field] = canonical_sha256(fixture, exclude={digest_field})

    assert "nested_binding_invalid" in {
        issue.code for issue in validate_record(fixture)
    }


@pytest.mark.parametrize(
    ("fixture_name", "field"),
    [
        ("broad_outcome.v1.json", "collection"),
        ("broad_outcome.v1.json", "command"),
        ("broad_outcome.v1.json", "environment"),
        ("broad_outcome.v1.json", "outcomes"),
        ("broad_evidence_bootstrap_subject.v1.json", "task_contract_binding"),
        ("broad_evidence_bootstrap_subject.v1.json", "execution_ledger_binding"),
        ("broad_evidence_bootstrap_subject.v1.json", "focused_report_binding"),
        ("broad_evidence_bootstrap_subject.v1.json", "collection_binding"),
    ],
)
def test_redigested_garbage_nested_records_fail_closed(
    fixture_name: str, field: str
) -> None:
    fixture = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence") / fixture_name
    )
    fixture[field] = {"garbage": 1}
    digest_field = (
        "normalized_outcome_sha256"
        if fixture_name == "broad_outcome.v1.json"
        else "normalized_subject_sha256"
    )
    fixture[digest_field] = canonical_sha256(fixture, exclude={digest_field})

    assert validate_record(fixture)


@pytest.mark.parametrize("mutation", ["missing", "extra"])
def test_subject_candidate_manifest_matches_non_evidence_projection_both_directions(
    mutation: str,
) -> None:
    subject = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence")
        / "implementation_verification_subject.v1.json"
    )
    source_row = {
        "path": "src/example.py",
        "sha256": f"sha256:{'1' * 64}",
        "size": 1,
        "state": "added",
    }
    subject["candidate_binding"] = {
        "head": "1" * 40,
        "head_tree": "2" * 40,
        "index_sha256": f"sha256:{'3' * 64}",
        "evidence_root_exclusion": "evidence",
        "candidate_paths": [source_row],
        "candidate_path_set_sha256": canonical_sha256([source_row]),
    }
    subject["candidate_path_manifest"] = (
        []
        if mutation == "missing"
        else [
            source_row,
            {
                "path": "src/unbound.py",
                "sha256": f"sha256:{'4' * 64}",
                "size": 1,
                "state": "added",
            },
        ]
    )
    subject["normalized_subject_sha256"] = canonical_sha256(
        subject, exclude={"normalized_subject_sha256"}
    )

    assert "candidate_manifest_projection_mismatch" in {
        issue.code for issue in validate_record(subject)
    }


def test_bootstrap_subject_manifest_requires_every_inline_evidence_binding() -> None:
    subject = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence")
        / "broad_evidence_bootstrap_subject.v1.json"
    )
    digest = f"sha256:{'0' * 64}"
    subject["bootstrap_workspace_baseline_binding"]["path"] = (
        "evidence/bootstrap-baseline.json"
    )
    subject["execution_ledger_binding"].update(
        {
            "live_path": "evidence/execution-ledger.json",
            "request_path": "evidence/materialization-inputs/ledger-request.json",
            "snapshot_path": "evidence/immutable-outputs/ledger-snapshot.json",
        }
    )
    subject["focused_report_binding"]["path"] = "evidence/focused/report.json"
    for row in subject["raw_broad_bindings"]:
        row["path"] = f"evidence/raw/{row['role_id']}"
    by_role = {row["role_id"]: row for row in subject["raw_broad_bindings"]}
    for role, field in (
        ("collection-log", "log_binding"),
        ("collection-exit", "exit_binding"),
        ("collected-node-ids", "node_ids_binding"),
    ):
        subject["collection_binding"][field] = {
            key: by_role[role][key] for key in ("path", "sha256", "size")
        }
    evidence_bindings = [
        (subject["bootstrap_workspace_baseline_binding"]["path"], digest, 0),
        (
            subject["execution_ledger_binding"]["live_path"],
            subject["execution_ledger_binding"]["byte_sha256"],
            0,
        ),
        (
            subject["execution_ledger_binding"]["request_path"],
            subject["execution_ledger_binding"]["request_sha256"],
            0,
        ),
        (
            subject["execution_ledger_binding"]["snapshot_path"],
            subject["execution_ledger_binding"]["snapshot_sha256"],
            0,
        ),
        (
            subject["focused_report_binding"]["path"],
            subject["focused_report_binding"]["sha256"],
            0,
        ),
        *[(row["path"], row["sha256"], row["size"]) for row in by_role.values()],
    ]
    evidence_rows = [
        {"path": path, "sha256": sha256, "size": size, "state": "added"}
        for path, sha256, size in evidence_bindings
    ]
    subject["candidate_path_manifest"] = sorted(
        [*subject["candidate_binding"]["candidate_paths"], *evidence_rows],
        key=lambda row: row["path"],
    )
    subject["normalized_subject_sha256"] = canonical_sha256(
        subject, exclude={"normalized_subject_sha256"}
    )
    assert validate_record(subject) == []

    subject["candidate_path_manifest"] = [
        row
        for row in subject["candidate_path_manifest"]
        if row["path"] != "evidence/execution-ledger.json"
    ]
    subject["normalized_subject_sha256"] = canonical_sha256(
        subject, exclude={"normalized_subject_sha256"}
    )
    assert "candidate_manifest_evidence_projection_mismatch" in {
        issue.code for issue in validate_record(subject)
    }


def test_bootstrap_subject_rejects_nonbaseline_bytes_at_bound_baseline_path() -> None:
    subject = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence")
        / "broad_evidence_bootstrap_subject.v1.json"
    )
    decoy = Path("docs/index.md")
    subject["bootstrap_workspace_baseline_binding"]["path"] = decoy.as_posix()
    subject["bootstrap_workspace_baseline_binding"]["sha256"] = file_sha256(decoy)
    subject["normalized_subject_sha256"] = canonical_sha256(
        subject, exclude={"normalized_subject_sha256"}
    )

    assert "bootstrap_baseline_record_invalid" in {
        issue.code for issue in validate_bound_record(subject, Path("."))
    }


def test_implementation_subject_reopens_and_matches_bound_candidate(
    tmp_path: Path,
) -> None:
    fixture_root = Path("tests/fixtures/retirement_broad_evidence")
    focused = load_json_closed(fixture_root / "implementation_focused_report.v1.json")
    broad = load_json_closed(fixture_root / "broad_outcome.v1.json")
    subject = load_json_closed(
        fixture_root / "implementation_verification_subject.v1.json"
    )
    focused["candidate_binding"] = {
        "path": "different-candidate.json",
        "sha256": f"sha256:{'1' * 64}",
    }
    focused["normalized_report_sha256"] = canonical_sha256(
        focused, exclude={"normalized_report_sha256"}
    )
    focused_path = tmp_path / "focused.json"
    broad_path = tmp_path / "broad.json"
    focused_path.write_text(json.dumps(focused, sort_keys=True) + "\n")
    broad_path.write_text(json.dumps(broad, sort_keys=True) + "\n")
    subject["focused_report_binding"] = {
        "path": "focused.json",
        "sha256": file_sha256(focused_path),
    }
    subject["broad_outcome_binding"] = {
        "path": "broad.json",
        "sha256": file_sha256(broad_path),
    }
    subject["normalized_subject_sha256"] = canonical_sha256(
        subject, exclude={"normalized_subject_sha256"}
    )

    assert "subject_candidate_mismatch" in {
        issue.code for issue in validate_bound_record(subject, tmp_path)
    }


def test_bootstrap_subject_reopens_every_raw_and_manifest_binding(
    tmp_path: Path,
) -> None:
    subject = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence")
        / "broad_evidence_bootstrap_subject.v1.json"
    )
    subject["raw_broad_bindings"] = [
        {
            "role_id": "raw-log",
            "path": "missing.log",
            "sha256": f"sha256:{'0' * 64}",
            "size": 1,
        }
    ]
    subject["candidate_path_manifest"] = [
        {
            "path": "missing.log",
            "sha256": f"sha256:{'0' * 64}",
            "size": 1,
            "state": "added",
        }
    ]
    subject["normalized_subject_sha256"] = canonical_sha256(
        subject, exclude={"normalized_subject_sha256"}
    )

    codes = {issue.code for issue in validate_bound_record(subject, tmp_path)}
    assert "bound_file_unreadable" in codes


def test_bootstrap_subject_parses_rebound_collection_exit_bytes(
    tmp_path: Path,
) -> None:
    subject = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence")
        / "broad_evidence_bootstrap_subject.v1.json"
    )
    exit_path = tmp_path / "garbage.exit"
    exit_path.write_bytes(b"garbage\n")
    binding = {
        "path": "garbage.exit",
        "sha256": file_sha256(exit_path),
        "size": exit_path.stat().st_size,
    }
    subject["collection_binding"]["exit_binding"] = binding
    raw_row = next(
        row
        for row in subject["raw_broad_bindings"]
        if row["role_id"] == "collection-exit"
    )
    raw_row.update(binding)
    subject["normalized_subject_sha256"] = canonical_sha256(
        subject, exclude={"normalized_subject_sha256"}
    )

    assert "collection_exit_invalid" in {
        issue.code for issue in validate_bound_record(subject, tmp_path)
    }


def test_bootstrap_subject_reconciles_all_rebound_raw_semantics(
    tmp_path: Path,
) -> None:
    subject = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence")
        / "broad_evidence_bootstrap_subject.v1.json"
    )

    def rebind(role: str, data: bytes) -> dict[str, object]:
        path = tmp_path / f"{role}.raw"
        path.write_bytes(data)
        binding: dict[str, object] = {
            "path": path.name,
            "sha256": file_sha256(path),
            "size": len(data),
        }
        next(row for row in subject["raw_broad_bindings"] if row["role_id"] == role).update(binding)
        return binding

    subject["collection_binding"]["exit_binding"] = rebind(
        "collection-exit", b"0\n"
    )
    subject["collection_binding"]["log_binding"] = rebind(
        "collection-log", b"not the collected node\n"
    )
    subject["collection_binding"]["node_ids_binding"] = rebind(
        "collected-node-ids", b"tests/example.py::test_example\n"
    )
    subject["collection_binding"]["node_id_list_sha256"] = canonical_sha256(
        ["tests/example.py::test_example"]
    )
    rebind("pytest-temp-root-preflight", b"not json\n")
    rebind("broad-junit", b"not xml\n")
    rebind("broad-exit", b"0\n")
    rebind("broad-rs-log", b"arbitrary\n")
    subject["normalized_subject_sha256"] = canonical_sha256(
        subject, exclude={"normalized_subject_sha256"}
    )

    codes = {issue.code for issue in validate_bound_record(subject, tmp_path)}
    assert {
        "collection_log_node_mismatch",
        "preflight_record_invalid",
        "junit_outcome_invalid",
        "broad_exit_mismatch",
        "rs_log_outcome_mismatch",
    } <= codes


def test_broad_outcome_reopens_every_raw_binding(tmp_path: Path) -> None:
    outcome = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence/broad_outcome.v1.json")
    )

    assert "bound_file_unreadable" in {
        issue.code for issue in validate_bound_record(outcome, tmp_path)
    }


def test_bound_broad_outcome_rejects_raw_exit_xml_preflight_and_log_tamper(
    tmp_path: Path,
) -> None:
    outcome = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence/broad_outcome.v1.json")
    )

    def bind(path: str, data: bytes) -> dict[str, str]:
        absolute = tmp_path / path
        absolute.parent.mkdir(parents=True, exist_ok=True)
        absolute.write_bytes(data)
        return {"path": path, "sha256": file_sha256(absolute)}

    outcome["collection"]["log_binding"] = bind("collect.log", b"arbitrary\n")
    outcome["collection"]["exit_binding"] = bind("collect.exit", b"999\n")
    outcome["collection"]["node_ids_binding"] = bind("nodes.txt", b"")
    outcome["exit_result"]["binding"] = bind("pytest.exit", b"0\n")
    outcome["exit_result"]["parsed_exit"] = 99
    outcome["junit_report"] = bind("pytest.xml", b"not xml\n")
    outcome["pytest_temp_root_preflight"] = bind("preflight.json", b"not json\n")
    outcome["failure_normalization"]["pytest_temp_root_preflight_binding"] = outcome[
        "pytest_temp_root_preflight"
    ]
    outcome["failure_normalization"]["normalized_contract_sha256"] = canonical_sha256(
        outcome["failure_normalization"], exclude={"normalized_contract_sha256"}
    )
    outcome["rs_log"] = bind("pytest.log", b"arbitrary\n")
    outcome["normalized_outcome_sha256"] = canonical_sha256(
        outcome, exclude={"normalized_outcome_sha256"}
    )

    codes = {issue.code for issue in validate_bound_record(outcome, tmp_path)}
    assert {
        "collection_exit_mismatch",
        "broad_exit_mismatch",
        "preflight_record_invalid",
        "junit_outcome_invalid",
        "rs_log_outcome_mismatch",
    } <= codes


def test_broad_outcome_rejects_internally_consistent_nonsemantic_pytest_exit() -> None:
    outcome = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence/broad_outcome.v1.json")
    )
    node_id = "tests/example.py::test_example"
    outcome["collected_node_ids"] = [node_id]
    outcome["collection"]["node_id_count"] = 1
    outcome["collection"]["node_id_list_sha256"] = canonical_sha256([node_id])
    outcome["outcomes"] = {
        "outcome": "baseline_candidate",
        "totals": {
            "collected": 1,
            "passed": 0,
            "failed": 1,
            "errors": 0,
            "skipped": 0,
        },
        "failures": [
            {
                "node_id": node_id,
                "outcome_kind": "failure",
                "failure_payload_sha256": f"sha256:{'1' * 64}",
                "normalized_payload": "failed",
            }
        ],
        "skipped_node_ids": [],
    }
    outcome["exit_result"]["parsed_exit"] = 99
    outcome["normalized_outcome_sha256"] = canonical_sha256(
        outcome, exclude={"normalized_outcome_sha256"}
    )

    assert "broad_exit_semantics_invalid" in {
        issue.code for issue in validate_record(outcome)
    }


def test_bound_later_broad_reopens_complete_baseline_authority_graph(
    tmp_path: Path,
) -> None:
    outcome = _later_broad_outcome()
    codes = {
        (issue.code, issue.path) for issue in validate_bound_record(outcome, tmp_path)
    }
    assert (
        "bound_file_unreadable",
        "$.known_failure_baseline_binding.owner_attestation",
    ) in codes
    assert (
        "bound_file_unreadable",
        "$.known_failure_baseline_binding.outcome",
    ) in codes


def _redigest_task1_broad_record(record: dict[str, object]) -> None:
    digest_fields = {
        "workflow_retirement_execution_ledger.v1": "normalized_ledger_sha256",
        "retirement_materialization_request.v1": "normalized_request_sha256",
        "pytest_temp_root_preflight.v1": "normalized_record_sha256",
        "implementation_focused_report.v1": "normalized_report_sha256",
        "implementation_verification_subject.v1": "normalized_subject_sha256",
        "broad_evidence_bootstrap_subject.v1": "normalized_subject_sha256",
        "broad_outcome.v1": "normalized_outcome_sha256",
        "broad_failure_remediation.v1": "normalized_remediation_sha256",
        "broad_skip_change.v1": "normalized_skip_change_sha256",
        "review_binding.v1": "normalized_binding_sha256",
    }
    digest_field = digest_fields.get(record["schema_version"])
    if digest_field is not None:
        record[digest_field] = canonical_sha256(record, exclude={digest_field})


@pytest.mark.parametrize(
    "fixture_name",
    [
        "execution_ledger.initial.v1.json",
        "retirement_materialization_request.v1.json",
        "pytest_temp_root_preflight.v1.json",
        "implementation_focused_report.v1.json",
        "implementation_verification_subject.v1.json",
        "broad_evidence_bootstrap_subject.v1.json",
        "broad_outcome.v1.json",
        "broad_known_failure_baseline.v1.json",
        "broad_failure_remediation.v1.json",
        "broad_skip_change.v1.json",
        "broad_failure_baseline_attestation.pending.v1.json",
        "review.v1.json",
        "review_binding.v1.json",
    ],
)
@pytest.mark.parametrize("invalid_claims", [[], [""], [7], "not-a-list"])
def test_every_task1_broad_claim_boundary_requires_nonempty_strings(
    fixture_name: str, invalid_claims: object
) -> None:
    record = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence") / fixture_name
    )
    record["claims_not_made"] = invalid_claims
    _redigest_task1_broad_record(record)

    assert "claims_not_made_invalid" in {
        issue.code for issue in validate_record(record)
    }


@pytest.mark.parametrize("invalid_claims", [[], [""], [7], "not-a-list"])
def test_fixture_manifest_requires_nonempty_string_claims(
    tmp_path: Path, invalid_claims: object
) -> None:
    root = tmp_path / "fixtures"
    root.mkdir()
    manifest = {
        "schema_version": "retirement_fixture_manifest.v1",
        "fixture_root": "tests/fixtures/example",
        "rows": [],
        "fixture_count": 0,
        "normalized_path_set_sha256": canonical_sha256([]),
        "normalized_row_set_sha256": canonical_sha256([]),
        "claims_not_made": invalid_claims,
    }
    (root / "manifest.v1.json").write_text(json.dumps(manifest) + "\n")

    assert "fixture_claims_invalid" in {
        issue.code for issue in validate_fixture_manifest(root)
    }


def _closed_test_review_binding(
    *,
    logical_path: str,
    review_kind: str,
    reviewer: str,
    subject_kind: str,
    subject_path: str,
    subject_sha256: str,
) -> dict[str, object]:
    binding: dict[str, object] = {
        "schema_version": "review_binding.v1",
        "logical_path": logical_path,
        "immutable_path": (
            "immutable-reviews/"
            f"{'1' * 64}/{'2' * 64}/{review_kind}-{'3' * 64}.json"
        ),
        "sha256": f"sha256:{'3' * 64}",
        "review_kind": review_kind,
        "reviewer": {"identity": reviewer},
        "reviewed_at": "2026-01-01T00:00:00+00:00",
        "result": "approved",
        "subject": {
            "kind": subject_kind,
            "path": subject_path,
            "sha256": subject_sha256,
        },
        "normalized_binding_sha256": "",
        "claims_not_made": ["fixture binding only"],
    }
    binding["normalized_binding_sha256"] = canonical_sha256(
        binding, exclude={"normalized_binding_sha256"}
    )
    return binding


def _test_review_pair_bindings(
    *,
    directory: str,
    name_prefix: str,
    subject_kind: str,
    subject_path: str,
    subject_sha256: str,
    review_suffix: bool = False,
) -> tuple[dict[str, object], dict[str, object]]:
    separator = "-" if name_prefix else ""
    review_tail = "-review" if review_suffix else ""
    return (
        _closed_test_review_binding(
            logical_path=(
                f"{directory}/{name_prefix}{separator}specification{review_tail}.json"
            ),
            review_kind="specification",
            reviewer="spec-reviewer",
            subject_kind=subject_kind,
            subject_path=subject_path,
            subject_sha256=subject_sha256,
        ),
        _closed_test_review_binding(
            logical_path=(
                f"{directory}/{name_prefix}{separator}quality{review_tail}.json"
            ),
            review_kind="code_quality",
            reviewer="quality-reviewer",
            subject_kind=subject_kind,
            subject_path=subject_path,
            subject_sha256=subject_sha256,
        ),
    )


def _later_broad_outcome() -> dict[str, object]:
    return load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence")
        / "broad_outcome.exact_match.v1.json"
    )


def test_broad_outcome_accepts_closed_baseline_and_later_lifecycles() -> None:
    baseline = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence/broad_outcome.v1.json")
    )
    assert validate_record(baseline) == []

    later = _later_broad_outcome()
    assert validate_record(later) == []

    subset = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence")
        / "broad_outcome.reviewed_subset.v1.json"
    )
    assert validate_record(subset) == []
    assert len(baseline["outcomes"]["failures"]) == 6
    assert len(later["outcomes"]["failures"]) == 6
    assert len(subset["outcomes"]["failures"]) == 4
    assert subset["baseline_comparison"]["removed_failure_node_ids"] == [
        "tests/synthetic_alpha.py::test_alpha",
        "tests/synthetic_beta.py::test_beta",
    ]


@pytest.mark.parametrize(
    ("field", "invalid_value", "expected_code"),
    [
        ("run_root_snapshots", [], "run_root_snapshots_invalid"),
        ("run_root_snapshots", [{}], "run_root_snapshots_invalid"),
        ("known_failure_baseline_binding", {}, "baseline_binding_invalid"),
        ("approved_remediation_bindings", [{}], "remediation_bindings_invalid"),
        ("approved_skip_change_bindings", [{}], "skip_change_bindings_invalid"),
        ("baseline_comparison", {}, "baseline_comparison_invalid"),
    ],
)
def test_broad_outcome_rejects_redigested_invalid_lifecycle_shapes(
    field: str, invalid_value: object, expected_code: str
) -> None:
    outcome = _later_broad_outcome()
    outcome[field] = invalid_value
    _redigest_task1_broad_record(outcome)

    assert expected_code in {issue.code for issue in validate_record(outcome)}


def test_broad_outcome_rejects_snapshot_mutation_and_lifecycle_crossovers() -> None:
    baseline = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence/broad_outcome.v1.json")
    )
    baseline["run_root_snapshots"][0]["after_snapshot_sha256"] = f"sha256:{'f' * 64}"
    _redigest_task1_broad_record(baseline)
    assert "run_root_snapshot_changed" in {
        issue.code for issue in validate_record(baseline)
    }

    later = _later_broad_outcome()
    later["known_failure_baseline_binding"] = None
    later["baseline_comparison"] = None
    _redigest_task1_broad_record(later)
    assert "broad_lifecycle_invalid" in {
        issue.code for issue in validate_record(later)
    }

    baseline = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence/broad_outcome.v1.json")
    )
    baseline["known_failure_baseline_binding"] = _later_broad_outcome()[
        "known_failure_baseline_binding"
    ]
    _redigest_task1_broad_record(baseline)
    assert "broad_lifecycle_invalid" in {
        issue.code for issue in validate_record(baseline)
    }


def test_broad_outcome_requires_sorted_review_prefixes_and_comparison_digests() -> None:
    outcome = _later_broad_outcome()
    record = {
        "path": "remediation/failure-remediation.json",
        "sha256": f"sha256:{'7' * 64}",
    }
    specification, quality = _test_review_pair_bindings(
        directory="remediation",
        name_prefix="remediation",
        subject_kind="broad_failure_remediation",
        subject_path=record["path"],
        subject_sha256=record["sha256"],
        review_suffix=True,
    )
    triple = {
        "record": record,
        "specification_review": specification,
        "quality_review": quality,
    }
    outcome["approved_remediation_bindings"] = [triple, deepcopy(triple)]
    outcome["baseline_comparison"]["approved_remediation_set_sha256"] = canonical_sha256(
        outcome["approved_remediation_bindings"]
    )
    _redigest_task1_broad_record(outcome)
    assert "remediation_bindings_invalid" in {
        issue.code for issue in validate_record(outcome)
    }

    outcome = _later_broad_outcome()
    outcome["baseline_comparison"]["observed_skip_set_sha256"] = f"sha256:{'a' * 64}"
    _redigest_task1_broad_record(outcome)
    assert "baseline_comparison_mismatch" in {
        issue.code for issue in validate_record(outcome)
    }


def test_pending_baseline_attestation_rejects_owner_or_affirmative_confirmation() -> None:
    fixture = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence/")
        / "broad_failure_baseline_attestation.pending.v1.json"
    )
    fixture["owner"] = {"identity": "not-yet-adopted"}
    assert "pending_owner_fields_nonnull" in {
        issue.code for issue in validate_record(fixture)
    }
    fixture["owner"] = None
    fixture["owner_confirmations"]["reviews_confirmed"] = True
    assert "pending_confirmation_affirmative" in {
        issue.code for issue in validate_record(fixture)
    }


@pytest.mark.parametrize(
    ("fixture_name", "mutations", "expected_codes"),
    [
        (
            "broad_failure_baseline_attestation.pending.v1.json",
            {
                "baseline_binding": {},
                "failure_set_binding": {},
                "normalization_binding": {},
                "classification_summary": {},
                "specification_review_binding": {},
                "quality_review_binding": {},
                "prepared_by": {},
                "prepared_at": "not-a-timestamp",
            },
            {
                "attestation_baseline_binding_invalid",
                "attestation_failure_set_binding_invalid",
                "attestation_normalization_binding_invalid",
                "attestation_classification_summary_invalid",
                "attestation_review_binding_invalid",
                "attestation_prepared_identity_invalid",
                "attestation_prepared_at_invalid",
            },
        ),
        (
            "broad_failure_baseline_attestation.confirmed.v1.json",
            {
                "baseline_binding": {},
                "failure_set_binding": {},
                "normalization_binding": {},
                "classification_summary": {},
                "specification_review_binding": {},
                "quality_review_binding": {},
                "owner": {},
                "owner_adoption": {},
                "prepared_by": {},
                "prepared_at": "not-a-timestamp",
            },
            {
                "attestation_baseline_binding_invalid",
                "attestation_failure_set_binding_invalid",
                "attestation_normalization_binding_invalid",
                "attestation_classification_summary_invalid",
                "attestation_review_binding_invalid",
                "attestation_owner_invalid",
                "attestation_owner_adoption_invalid",
                "attestation_prepared_identity_invalid",
                "attestation_prepared_at_invalid",
            },
        ),
    ],
)
def test_baseline_attestation_rejects_adversarial_nested_garbage(
    fixture_name: str,
    mutations: dict[str, object],
    expected_codes: set[str],
) -> None:
    record = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence") / fixture_name
    )
    record.update(mutations)

    assert expected_codes <= {issue.code for issue in validate_record(record)}


@pytest.mark.parametrize(
    ("field", "value", "expected_code"),
    [
        ("prepared_at", "2026-01-01T00:00:01", "attestation_prepared_at_invalid"),
        ("owner_confirmations.confirmed_at", "not-a-time", "attestation_confirmation_timestamp_invalid"),
        ("owner_adoption.adopted_at", "not-a-time", "attestation_adoption_timestamp_invalid"),
        ("owner_adoption.identity", "different-owner", "attestation_owner_adoption_invalid"),
    ],
)
def test_confirmed_baseline_attestation_closes_identity_and_timestamp_fields(
    field: str, value: object, expected_code: str
) -> None:
    record = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence/")
        / "broad_failure_baseline_attestation.confirmed.v1.json"
    )
    target: dict[str, object] = record
    parts = field.split(".")
    for part in parts[:-1]:
        target = target[part]
    target[parts[-1]] = value

    assert expected_code in {issue.code for issue in validate_record(record)}


def test_confirmed_baseline_attestation_rejects_timestamp_reversal() -> None:
    record = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence/")
        / "broad_failure_baseline_attestation.confirmed.v1.json"
    )
    record["prepared_at"] = "2026-01-01T00:00:03+00:00"
    record["owner_confirmations"]["confirmed_at"] = "2026-01-01T00:00:02+00:00"
    record["owner_adoption"]["adopted_at"] = "2026-01-01T00:00:01+00:00"

    assert "attestation_timestamp_order_invalid" in {
        issue.code for issue in validate_record(record)
    }


def test_baseline_attestation_rejects_review_pair_timestamp_reversal() -> None:
    record = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence/")
        / "broad_failure_baseline_attestation.confirmed.v1.json"
    )
    record["specification_review_binding"]["reviewed_at"] = (
        "2026-01-01T00:00:02+00:00"
    )
    record["quality_review_binding"]["reviewed_at"] = (
        "2026-01-01T00:00:01+00:00"
    )
    for field in ("specification_review_binding", "quality_review_binding"):
        record[field]["normalized_binding_sha256"] = canonical_sha256(
            record[field], exclude={"normalized_binding_sha256"}
        )
    record["prepared_at"] = "2026-01-01T00:00:03+00:00"
    record["owner_confirmations"]["confirmed_at"] = (
        "2026-01-01T00:00:04+00:00"
    )
    record["owner_adoption"]["adopted_at"] = "2026-01-01T00:00:04+00:00"

    assert broad_evidence.Issue(
        "review_pair_timestamp_order_invalid",
        "$.quality_review_binding.reviewed_at",
    ) in validate_record(record)


def test_pending_baseline_attestation_must_be_prepared_after_bound_reviews() -> None:
    record = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence/")
        / "broad_failure_baseline_attestation.pending.v1.json"
    )
    record["prepared_at"] = "2025-12-31T23:59:59+00:00"

    assert "attestation_timestamp_order_invalid" in {
        issue.code for issue in validate_record(record)
    }


def test_bound_baseline_attestation_reopens_and_reconciles_baseline_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence/")
        / "broad_known_failure_baseline.v1.json"
    )
    baseline_path = tmp_path / "known-failure-baseline.json"
    baseline_path.write_text(json.dumps(baseline, sort_keys=True) + "\n")
    record = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence/")
        / "broad_failure_baseline_attestation.confirmed.v1.json"
    )
    record["baseline_binding"].update(
        {
            "path": baseline_path.name,
            "sha256": file_sha256(baseline_path),
        }
    )
    for binding in (
        record["specification_review_binding"],
        record["quality_review_binding"],
    ):
        binding["subject"].update(
            {
                "path": baseline_path.name,
                "sha256": file_sha256(baseline_path),
            }
        )
        binding["normalized_binding_sha256"] = canonical_sha256(
            binding, exclude={"normalized_binding_sha256"}
        )
    monkeypatch.setattr(broad_evidence, "validate_review_pair", lambda **_: [])

    assert validate_bound_record(record, tmp_path) == []

    record["failure_set_binding"]["normalized_failure_set_sha256"] = (
        f"sha256:{'f' * 64}"
    )
    assert "attestation_baseline_record_mismatch" in {
        issue.code for issue in validate_bound_record(record, tmp_path)
    }


def test_skip_change_accumulates_exact_node_transition() -> None:
    fixture = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence/broad_skip_change.v1.json")
    )
    assert apply_skip_change(
        ["tests/keep.py::test_keep", "tests/old.py::test_old"], fixture
    ) == ["tests/keep.py::test_keep", "tests/new.py::test_new"]


def test_baseline_remediation_and_skip_contracts_reject_empty_partitions() -> None:
    root = Path("tests/fixtures/retirement_broad_evidence")
    baseline = load_json_closed(root / "broad_known_failure_baseline.v1.json")
    remediation = load_json_closed(root / "broad_failure_remediation.v1.json")
    baseline["failures"] = []
    baseline["normalized_failure_set_sha256"] = canonical_sha256([])
    remediation["removed_failure_rows"] = []
    remediation["production_diff"] = []
    remediation["normalized_remediation_sha256"] = canonical_sha256(
        remediation, exclude={"normalized_remediation_sha256"}
    )
    assert validate_record(baseline)
    assert validate_record(remediation)


def test_focused_report_rejects_empty_or_task_contract_drifted_command_set() -> None:
    fixture = load_json_closed(
        Path(
            "tests/fixtures/retirement_broad_evidence/"
            "implementation_focused_report.v1.json"
        )
    )

    empty = deepcopy(fixture)
    empty["required_commands"] = []
    empty["commands"] = []
    empty["command_count"] = 0
    empty["command_set_sha256"] = canonical_sha256([])
    empty["task_contract_binding"]["required_command_set_sha256"] = canonical_sha256([])
    empty["normalized_report_sha256"] = canonical_sha256(
        empty, exclude={"normalized_report_sha256"}
    )
    assert "focused_commands_empty" in {
        issue.code for issue in validate_record(empty)
    }

    required = {
        "role_id": "check",
        "argv": ["pytest", "-q", "tests/test_example.py"],
        "cwd": ".",
        "environment": {"LC_ALL": "C.UTF-8", "PYTHONHASHSEED": "0"},
    }
    fixture["required_commands"] = [required]
    fixture["commands"] = [{"role_id": "check"}]
    fixture["command_count"] = 1
    fixture["command_set_sha256"] = canonical_sha256([required])
    fixture["task_contract_binding"]["required_command_set_sha256"] = (
        f"sha256:{'f' * 64}"
    )
    fixture["normalized_report_sha256"] = canonical_sha256(
        fixture, exclude={"normalized_report_sha256"}
    )

    assert "focused_task_command_set_mismatch" in {
        issue.code for issue in validate_record(fixture)
    }


def test_skip_change_uses_the_exact_plan_shape() -> None:
    fixture = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence/broad_skip_change.v1.json")
    )
    assert set(fixture) == {
        "schema_version",
        "execution_ledger_binding",
        "candidate_binding",
        "predecessor_skip_set_binding",
        "added_skip_node_ids",
        "removed_skip_node_ids",
        "authorized_diff",
        "focused_regression_evidence",
        "resulting_skip_set_sha256",
        "normalized_skip_change_sha256",
        "claims_not_made",
    }

    fixture["resulting_skip_set_sha256"] = canonical_sha256([])
    fixture["normalized_skip_change_sha256"] = canonical_sha256(
        fixture, exclude={"normalized_skip_change_sha256"}
    )
    with pytest.raises(ContractError, match="skip_change_invalid"):
        apply_skip_change(["tests/keep.py::test_keep", "tests/old.py::test_old"], fixture)


def test_deep_failure_and_skip_contracts_reject_reconciled_tampering() -> None:
    root = Path("tests/fixtures/retirement_broad_evidence")

    baseline = load_json_closed(root / "broad_known_failure_baseline.v1.json")
    baseline["classification_summary"]["queue_owned"] = 0
    assert "baseline_classification_summary_invalid" in {
        issue.code for issue in validate_record(baseline)
    }

    remediation = load_json_closed(root / "broad_failure_remediation.v1.json")
    remediation["removed_failure_rows"][0]["ownership_class"] = "external"
    remediation["removed_failure_rows"][0]["authorized_remediation_scope"] = []
    remediation["normalized_remediation_sha256"] = canonical_sha256(
        remediation, exclude={"normalized_remediation_sha256"}
    )
    assert "remediation_failure_rows_invalid" in {
        issue.code for issue in validate_record(remediation)
    }

    skip = load_json_closed(root / "broad_skip_change.v1.json")
    skip["predecessor_skip_set_binding"]["skip_set_sha256"] = canonical_sha256([])
    skip["normalized_skip_change_sha256"] = canonical_sha256(
        skip, exclude={"normalized_skip_change_sha256"}
    )
    assert "nested_binding_invalid" in {
        issue.code for issue in validate_record(skip)
    }


@pytest.mark.parametrize(
    "fixture_name",
    [
        "broad_known_failure_baseline.v1.json",
        "broad_failure_remediation.v1.json",
        "broad_skip_change.v1.json",
    ],
)
def test_reviewable_failure_and_skip_records_reopen_their_bound_files(
    tmp_path: Path, fixture_name: str
) -> None:
    record = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence") / fixture_name
    )

    assert "bound_file_unreadable" in {
        issue.code for issue in validate_bound_record(record, tmp_path)
    }


def test_implementation_subject_deep_validates_its_bound_broad_outcome(
    tmp_path: Path,
) -> None:
    fixture_root = Path("tests/fixtures/retirement_broad_evidence")
    focused = load_json_closed(fixture_root / "implementation_focused_report.v1.json")
    broad = load_json_closed(fixture_root / "broad_outcome.v1.json")
    subject = load_json_closed(
        fixture_root / "implementation_verification_subject.v1.json"
    )
    source = tmp_path / "source.py"
    source.write_bytes(b"x")
    source_row = {
        "path": "source.py",
        "sha256": file_sha256(source),
        "size": 1,
        "state": "added",
    }
    candidate = deepcopy(subject["candidate_binding"])
    candidate["candidate_paths"] = [source_row]
    candidate["candidate_path_set_sha256"] = canonical_sha256([source_row])
    task_contract = deepcopy(subject["task_contract_binding"])
    task_contract["required_command_set_sha256"] = canonical_sha256(
        focused["required_commands"]
    )
    plan = tmp_path / task_contract["plan_path"]
    plan.write_text("approved plan\n")
    task_contract["plan_sha256"] = file_sha256(plan)
    for related in (focused, broad, subject):
        related["candidate_binding"] = candidate
        related["execution_ledger_binding"] = subject["execution_ledger_binding"]
    focused["task_contract_binding"] = task_contract
    subject["task_contract_binding"] = task_contract
    subject["candidate_path_manifest"] = [source_row]
    log = tmp_path / "task/focused/logs/check.log"
    exit_file = tmp_path / "task/focused/exits/check.exit"
    log.parent.mkdir(parents=True)
    exit_file.parent.mkdir(parents=True)
    log.write_text("passed\n")
    exit_file.write_bytes(b"0\n")
    focused["commands"][0]["log_binding"]["sha256"] = file_sha256(log)
    focused["commands"][0]["exit_binding"]["sha256"] = file_sha256(exit_file)
    focused["normalized_report_sha256"] = canonical_sha256(
        focused, exclude={"normalized_report_sha256"}
    )
    broad["normalized_outcome_sha256"] = canonical_sha256(
        broad, exclude={"normalized_outcome_sha256"}
    )
    report_path = tmp_path / "task/focused/report.json"
    broad_path = tmp_path / "task/broad-outcome.json"
    report_path.write_text(json.dumps(focused, sort_keys=True) + "\n")
    broad_path.write_text(json.dumps(broad, sort_keys=True) + "\n")
    subject["focused_report_binding"] = {
        "path": "task/focused/report.json",
        "sha256": file_sha256(report_path),
        "normalized_report_sha256": focused["normalized_report_sha256"],
    }
    subject["broad_outcome_binding"] = {
        "path": "task/broad-outcome.json",
        "sha256": file_sha256(broad_path),
    }
    subject["candidate_path_manifest"] = sorted(
        [
            source_row,
            {
                "path": subject["execution_ledger_binding"]["live_path"],
                "sha256": subject["execution_ledger_binding"]["byte_sha256"],
                "size": 0,
                "state": "added",
            },
            {
                "path": subject["execution_ledger_binding"]["request_path"],
                "sha256": subject["execution_ledger_binding"]["request_sha256"],
                "size": 0,
                "state": "added",
            },
            {
                "path": subject["execution_ledger_binding"]["snapshot_path"],
                "sha256": subject["execution_ledger_binding"]["snapshot_sha256"],
                "size": 0,
                "state": "added",
            },
            {
                "path": "task/focused/report.json",
                "sha256": file_sha256(report_path),
                "size": report_path.stat().st_size,
                "state": "added",
            },
            {
                "path": "task/broad-outcome.json",
                "sha256": file_sha256(broad_path),
                "size": broad_path.stat().st_size,
                "state": "added",
            },
        ],
        key=lambda row: row["path"],
    )
    subject["normalized_subject_sha256"] = canonical_sha256(
        subject, exclude={"normalized_subject_sha256"}
    )

    assert "bound_record_invalid" in {
        issue.code for issue in validate_bound_record(subject, tmp_path)
    }


@pytest.mark.parametrize(
    ("fixture_name", "mutate", "expected_code"),
    [
        (
            "broad_known_failure_baseline.v1.json",
            lambda record: record["failures"][0].__setitem__("outcome_kind", []),
            "baseline_failures_invalid",
        ),
        (
            "broad_failure_remediation.v1.json",
            lambda record: record["production_diff"][0].__setitem__("state", []),
            "remediation_production_diff_invalid",
        ),
        (
            "broad_skip_change.v1.json",
            lambda record: record["authorized_diff"][0].__setitem__("state", []),
            "skip_authorized_diff_invalid",
        ),
    ],
)
def test_failure_and_skip_validators_return_issues_for_json_compatible_bad_types(
    fixture_name: str, mutate, expected_code: str
) -> None:
    record = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence") / fixture_name
    )
    mutate(record)
    digest_field = {
        "broad_failure_remediation.v1.json": "normalized_remediation_sha256",
        "broad_skip_change.v1.json": "normalized_skip_change_sha256",
    }.get(fixture_name)
    if digest_field is not None:
        record[digest_field] = canonical_sha256(record, exclude={digest_field})

    assert expected_code in {issue.code for issue in validate_record(record)}


def test_bound_validator_stops_before_relational_work_on_malformed_record(
    tmp_path: Path,
) -> None:
    record = load_json_closed(
        Path(
            "tests/fixtures/retirement_broad_evidence/"
            "broad_failure_remediation.v1.json"
        )
    )
    record["production_diff"] = 7
    record["normalized_remediation_sha256"] = canonical_sha256(
        record, exclude={"normalized_remediation_sha256"}
    )

    assert "remediation_production_diff_invalid" in {
        issue.code for issue in validate_bound_record(record, tmp_path)
    }


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("argv", "pytest -q"),
        ("cwd", "elsewhere"),
        ("environment", {"LC_ALL": "C.UTF-8", "EXTRA": "1"}),
    ],
)
def test_focused_report_closes_required_and_observed_command_values(
    field: str, bad_value: object
) -> None:
    record = load_json_closed(
        Path(
            "tests/fixtures/retirement_broad_evidence/"
            "implementation_focused_report.v1.json"
        )
    )
    record["required_commands"][0][field] = bad_value
    record["commands"][0][field] = bad_value
    record["command_set_sha256"] = canonical_sha256(record["required_commands"])
    record["task_contract_binding"]["required_command_set_sha256"] = record[
        "command_set_sha256"
    ]
    record["normalized_report_sha256"] = canonical_sha256(
        record, exclude={"normalized_report_sha256"}
    )

    assert validate_record(record)


def test_strong_focused_report_reopens_task_plan_and_rejects_bad_input_types(
    tmp_path: Path,
) -> None:
    record = load_json_closed(
        Path(
            "tests/fixtures/retirement_broad_evidence/"
            "implementation_focused_report.v1.json"
        )
    )
    log = tmp_path / "focused/logs/check.log"
    exit_file = tmp_path / "focused/exits/check.exit"
    log.parent.mkdir(parents=True)
    exit_file.parent.mkdir(parents=True)
    log.write_text("passed\n")
    exit_file.write_bytes(b"0\n")
    record["commands"][0]["log_binding"]["sha256"] = file_sha256(log)
    record["commands"][0]["exit_binding"]["sha256"] = file_sha256(exit_file)
    record["normalized_report_sha256"] = canonical_sha256(
        record, exclude={"normalized_report_sha256"}
    )

    assert "focused_plan_binding_mismatch" in {
        issue.code
        for issue in validate_implementation_focused_report(record, tmp_path)
    }

    plan = tmp_path / record["task_contract_binding"]["plan_path"]
    plan.write_text("approved plan\n")
    record["task_contract_binding"]["plan_sha256"] = file_sha256(plan)
    record["commands"][0]["input_bindings"] = [
        {"path": [], "sha256": f"sha256:{'0' * 64}"}
    ]
    record["normalized_report_sha256"] = canonical_sha256(
        record, exclude={"normalized_report_sha256"}
    )
    assert validate_implementation_focused_report(record, tmp_path)


def test_implementation_subject_runs_strong_focused_report_validation(
    tmp_path: Path,
) -> None:
    fixture_root = Path("tests/fixtures/retirement_broad_evidence")
    focused = load_json_closed(fixture_root / "implementation_focused_report.v1.json")
    broad = load_json_closed(fixture_root / "broad_outcome.v1.json")
    subject = load_json_closed(
        fixture_root / "implementation_verification_subject.v1.json"
    )
    log_path = tmp_path / "task/focused/logs/check.log"
    exit_path = tmp_path / "task/focused/exits/check.exit"
    report_path = tmp_path / "task/focused/report.json"
    broad_path = tmp_path / "task/broad-outcome.json"
    log_path.parent.mkdir(parents=True)
    exit_path.parent.mkdir(parents=True)
    log_path.write_text("passed\n")
    exit_path.write_bytes(b"1\n")
    focused["commands"][0]["log_binding"]["sha256"] = file_sha256(log_path)
    focused["commands"][0]["exit_binding"]["sha256"] = file_sha256(exit_path)
    focused["normalized_report_sha256"] = canonical_sha256(
        focused, exclude={"normalized_report_sha256"}
    )
    report_path.write_text(json.dumps(focused, sort_keys=True) + "\n")
    broad_path.write_text(json.dumps(broad, sort_keys=True) + "\n")
    subject["focused_report_binding"] = {
        "path": "task/focused/report.json",
        "sha256": file_sha256(report_path),
        "normalized_report_sha256": focused["normalized_report_sha256"],
    }
    subject["broad_outcome_binding"] = {
        "path": "task/broad-outcome.json",
        "sha256": file_sha256(broad_path),
    }
    subject["normalized_subject_sha256"] = canonical_sha256(
        subject, exclude={"normalized_subject_sha256"}
    )

    assert validate_record(focused) == []
    assert "bound_record_invalid" in {
        issue.code for issue in validate_bound_record(subject, tmp_path)
    }


def test_focused_report_rejects_observed_role_reordering(tmp_path: Path) -> None:
    fixture = load_json_closed(
        Path(
            "tests/fixtures/retirement_broad_evidence/"
            "implementation_focused_report.v1.json"
        )
    )
    required = deepcopy(fixture["required_commands"])
    required.append({**deepcopy(required[0]), "role_id": "other"})
    commands = deepcopy(fixture["commands"])
    commands.append({**deepcopy(commands[0]), "role_id": "other"})
    for command in commands:
        role = command["role_id"]
        log = tmp_path / f"focused/logs/{role}.log"
        exit_file = tmp_path / f"focused/exits/{role}.exit"
        log.parent.mkdir(parents=True, exist_ok=True)
        exit_file.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("passed\n")
        exit_file.write_bytes(b"0\n")
        command["log_binding"] = {
            "path": f"focused/logs/{role}.log",
            "sha256": file_sha256(log),
        }
        command["exit_binding"] = {
            "path": f"focused/exits/{role}.exit",
            "sha256": file_sha256(exit_file),
        }
    fixture["required_commands"] = required
    fixture["commands"] = list(reversed(commands))
    fixture["command_count"] = 2
    fixture["command_set_sha256"] = canonical_sha256(required)
    fixture["task_contract_binding"]["required_command_set_sha256"] = canonical_sha256(
        required
    )
    fixture["normalized_report_sha256"] = canonical_sha256(
        fixture, exclude={"normalized_report_sha256"}
    )

    assert "focused_role_order_mismatch" in {
        issue.code for issue in validate_implementation_focused_report(fixture, tmp_path)
    }


def test_focused_report_rejects_symlinked_evidence_directory_parent(
    tmp_path: Path,
) -> None:
    fixture = load_json_closed(
        Path(
            "tests/fixtures/retirement_broad_evidence/"
            "implementation_focused_report.v1.json"
        )
    )
    outside = tmp_path / "outside"
    log = outside / "focused/logs/check.log"
    exit_file = outside / "focused/exits/check.exit"
    log.parent.mkdir(parents=True)
    exit_file.parent.mkdir(parents=True)
    log.write_text("passed\n")
    exit_file.write_bytes(b"0\n")
    (tmp_path / "alias").symlink_to(outside, target_is_directory=True)
    fixture["commands"][0]["log_binding"]["sha256"] = file_sha256(log)
    fixture["commands"][0]["exit_binding"]["sha256"] = file_sha256(exit_file)
    fixture["normalized_report_sha256"] = canonical_sha256(
        fixture, exclude={"normalized_report_sha256"}
    )

    assert "focused_log_binding_mismatch" in {
        issue.code
        for issue in validate_implementation_focused_report(
            fixture, tmp_path, evidence_directory=Path("alias")
        )
    }


def test_subject_bound_reader_rejects_symlinked_parent_component(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    report = outside / "report.json"
    report.write_text("{}\n")
    (tmp_path / "evidence").symlink_to(outside, target_is_directory=True)
    subject = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence")
        / "implementation_verification_subject.v1.json"
    )
    subject["focused_report_binding"].update(
        {"path": "evidence/report.json", "sha256": file_sha256(report)}
    )
    subject["normalized_subject_sha256"] = canonical_sha256(
        subject, exclude={"normalized_subject_sha256"}
    )

    assert ("bound_file_unreadable", "$.focused_report_binding") in {
        (issue.code, issue.path) for issue in validate_bound_record(subject, tmp_path)
    }


def test_subject_manifest_rebases_focused_raw_paths_from_task_directory(
    tmp_path: Path,
) -> None:
    subject = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence")
        / "implementation_verification_subject.v1.json"
    )
    subject["candidate_binding"]["candidate_paths"] = []
    subject["candidate_binding"]["candidate_path_set_sha256"] = canonical_sha256([])
    coordinates: list[tuple[str, bytes, dict[str, object], str]] = []

    _plan, _ledger_record, ledger_receipt = _materialize_first_ledger(tmp_path)
    ledger = _ledger_binding(ledger_receipt)
    subject["execution_ledger_binding"] = ledger
    focused_path = "evidence/task/focused/report.json"
    subject["focused_report_binding"]["path"] = focused_path
    coordinates.append(
        (
            focused_path,
            b"focused-report\n",
            subject["focused_report_binding"],
            "sha256",
        )
    )
    broad_path = "evidence/task/broad-outcome.json"
    subject["broad_outcome_binding"]["path"] = broad_path
    coordinates.append(
        (broad_path, b"broad-outcome\n", subject["broad_outcome_binding"], "sha256")
    )
    for path, data, binding, digest_field in coordinates:
        absolute = tmp_path / path
        absolute.parent.mkdir(parents=True, exist_ok=True)
        absolute.write_bytes(data)
        binding[digest_field] = file_sha256(absolute)
    focused = {
        "commands": [
            {
                "log_binding": {
                    "path": "focused/logs/check.log",
                    "sha256": "",
                },
                "exit_binding": {
                    "path": "focused/exits/check.exit",
                    "sha256": "",
                },
            }
        ]
    }
    for lane, data in (("log_binding", b"passed\n"), ("exit_binding", b"0\n")):
        relative = focused["commands"][0][lane]["path"]
        absolute = tmp_path / "evidence/task" / relative
        absolute.parent.mkdir(parents=True, exist_ok=True)
        absolute.write_bytes(data)
        focused["commands"][0][lane]["sha256"] = file_sha256(absolute)
    rows = []
    for path in (
        ledger["live_path"],
        ledger["request_path"],
        ledger["snapshot_path"],
        focused_path,
        broad_path,
        "evidence/task/focused/logs/check.log",
        "evidence/task/focused/exits/check.exit",
    ):
        absolute = tmp_path / path
        rows.append(
            {
                "path": path,
                "sha256": file_sha256(absolute),
                "size": absolute.stat().st_size,
                "state": "added",
            }
        )
    subject["candidate_path_manifest"] = sorted(rows, key=lambda row: row["path"])

    assert _bound_subject_manifest_issues(
        subject, tmp_path, focused=focused, broad=None
    ) == []


def test_materialization_retains_prior_generation(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    evidence = Path("evidence")
    output = evidence / "execution-ledger.json"
    plan = repository / "plan.md"
    _write_ledger_plan(plan)
    first_record = _ledger(Path("plan.md"))
    import hashlib

    first_record["plan_binding"]["sha256"] = (
        f"sha256:{hashlib.sha256(plan.read_bytes()).hexdigest()}"
    )
    first_record["normalized_ledger_sha256"] = canonical_sha256(
        first_record, exclude={"normalized_ledger_sha256"}
    )

    first = materialize_transaction(
        repository_root=repository,
        evidence_root=evidence,
        record_kind="execution-ledger",
        output_path=output,
        generation=1,
        input_paths={"approved_plan": Path("plan.md")},
        parameters={"record": first_record},
    )
    first_snapshot = repository / first.snapshot_path
    first_bytes = first_snapshot.read_bytes()

    second_record = _advance_ledger(first_record, first)
    second = materialize_transaction(
        repository_root=repository,
        evidence_root=evidence,
        record_kind="execution-ledger",
        output_path=output,
        generation=2,
        input_paths={"approved_plan": Path("plan.md")},
        parameters={"record": second_record},
        prior_request=first.request_path,
        prior_snapshot=first.snapshot_path,
    )

    assert first_snapshot.read_bytes() == first_bytes
    assert (repository / output).read_bytes() == (repository / second.snapshot_path).read_bytes()
    assert validate_generation(repository, first.request_path, first.snapshot_path) == []


def test_ledger_materialization_rejects_plan_binding_mismatch(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    plan = repository / "plan.md"
    _write_ledger_plan(plan)
    record = _ledger(Path("plan.md"))
    with pytest.raises(
        MaterializationError,
        match="output_contract_invalid:ledger_plan_binding_unreadable",
    ):
        materialize_transaction(
            repository_root=repository,
            evidence_root=Path("evidence"),
            record_kind="execution-ledger",
            output_path=Path("evidence/execution-ledger.json"),
            generation=1,
            input_paths={"approved_plan": Path("plan.md")},
            parameters={"record": record},
        )


@pytest.mark.parametrize("generation", [0, 100_000_000])
def test_materialization_rejects_generation_outside_closed_range(
    tmp_path: Path, generation: int
) -> None:
    with pytest.raises(MaterializationError, match="generation_out_of_range"):
        materialize_transaction(
            repository_root=tmp_path,
            evidence_root=Path("evidence"),
            record_kind="execution-ledger",
            output_path=Path("evidence/execution-ledger.json"),
            generation=generation,
            input_paths={},
            parameters={"record": {}},
        )


def test_materialization_rejects_output_escape(tmp_path: Path) -> None:
    with pytest.raises(MaterializationError, match="path_not_repository_relative"):
        materialize_transaction(
            repository_root=tmp_path,
            evidence_root=Path("evidence"),
            record_kind="execution-ledger",
            output_path=Path("../outside.json"),
            generation=1,
            input_paths={},
            parameters={"record": {}},
        )


def _materialize_first_ledger(repository: Path):
    plan = repository / "plan.md"
    _write_ledger_plan(plan)
    record = _ledger(Path("plan.md"))
    record["plan_binding"]["sha256"] = f"sha256:{hashlib.sha256(plan.read_bytes()).hexdigest()}"
    record["normalized_ledger_sha256"] = canonical_sha256(
        record, exclude={"normalized_ledger_sha256"}
    )
    receipt = materialize_transaction(
        repository_root=repository,
        evidence_root=Path("evidence"),
        record_kind="execution-ledger",
        output_path=Path("evidence/execution-ledger.json"),
        generation=1,
        input_paths={"approved_plan": Path("plan.md")},
        parameters={"record": record},
    )
    return plan, record, receipt


def _materialize_next_ledger(
    repository: Path,
    prior_record: dict[str, object],
    prior_receipt,
    *,
    evidence_bindings: list[dict[str, object]] | None = None,
    future_paths: list[str] | None = None,
):
    record = _advance_ledger(
        prior_record,
        prior_receipt,
        evidence_bindings=evidence_bindings,
        future_paths=future_paths,
    )
    receipt = materialize_transaction(
        repository_root=repository,
        evidence_root=Path("evidence"),
        record_kind="execution-ledger",
        output_path=prior_receipt.output_path,
        generation=prior_receipt.generation + 1,
        input_paths={"approved_plan": Path("plan.md")},
        parameters={"record": record},
        prior_request=prior_receipt.request_path,
        prior_snapshot=prior_receipt.snapshot_path,
    )
    return record, receipt


def _forge_ledger_generation(
    repository: Path,
    record: dict[str, object],
    generation: int,
    prior_receipt,
):
    """Write a structurally valid historical generation without publication checks."""

    output_path = prior_receipt.output_path
    capture = retirement_materialization._input_binding(
        repository, "approved_plan", Path("plan.md")
    )
    bindings = [dict(capture.binding)]
    request: dict[str, object] = {
        "schema_version": "retirement_materialization_request.v1",
        "record_kind": "execution-ledger",
        "output_path": output_path.as_posix(),
        "generation": generation,
        "prior_generation_binding": _prior_generation_binding(prior_receipt),
        "input_bindings": bindings,
        "parameters": {"record": record},
        "expected_input_set_sha256": canonical_sha256(bindings),
        "normalized_request_sha256": "",
        "claims_not_made": [
            "This request does not authorize owner action or source mutation."
        ],
    }
    request["normalized_request_sha256"] = canonical_sha256(
        request, exclude={"normalized_request_sha256"}
    )
    request_path = retirement_materialization._request_path(
        Path("evidence"),
        output_path,
        generation,
        request["normalized_request_sha256"],
    )
    output_data = retirement_materialization._json_output(record)
    output_sha256 = f"sha256:{hashlib.sha256(output_data).hexdigest()}"
    snapshot_path = retirement_materialization._snapshot_path(
        Path("evidence"), output_path, generation, output_sha256
    )
    for relative, data in (
        (request_path, retirement_materialization._json_output(request)),
        (snapshot_path, output_data),
    ):
        absolute = repository / relative
        absolute.parent.mkdir(parents=True, exist_ok=True)
        absolute.write_bytes(data)
    request_data = (repository / request_path).read_bytes()
    return retirement_materialization.MaterializationReceipt(
        request_path=request_path,
        request_sha256=f"sha256:{hashlib.sha256(request_data).hexdigest()}",
        snapshot_path=snapshot_path,
        snapshot_sha256=output_sha256,
        generation=generation,
        output_path=output_path,
        output_sha256=output_sha256,
    )


def _invalidate_ledger_binding_history(
    repository: Path,
    binding: dict[str, object],
    defect: str,
) -> dict[str, object]:
    invalid = deepcopy(binding)
    if defect == "request_record_mismatch":
        old_request_path = Path(invalid["request_path"])
        request = load_json_closed(repository / old_request_path)
        request_record = request["parameters"]["record"]
        request_record["claims_not_made"] = [
            "This valid ledger record is not the materialized snapshot."
        ]
        request_record["normalized_ledger_sha256"] = canonical_sha256(
            request_record, exclude={"normalized_ledger_sha256"}
        )
        request["normalized_request_sha256"] = canonical_sha256(
            request, exclude={"normalized_request_sha256"}
        )
        evidence_root = retirement_materialization._evidence_root_from_request_path(
            old_request_path
        )
        new_request_path = retirement_materialization._request_path(
            evidence_root,
            Path(request["output_path"]),
            request["generation"],
            request["normalized_request_sha256"],
        )
        (repository / old_request_path).unlink()
        absolute = repository / new_request_path
        absolute.write_text(json.dumps(request, sort_keys=True) + "\n")
        invalid["request_path"] = new_request_path.as_posix()
        invalid["request_sha256"] = file_sha256(absolute)
    elif defect == "arbitrary_snapshot_coordinate":
        source = repository / invalid["snapshot_path"]
        arbitrary = source.parent / "arbitrary-snapshot.json"
        arbitrary.write_bytes(source.read_bytes())
        invalid["snapshot_path"] = arbitrary.relative_to(repository).as_posix()
    elif defect == "invalid_ancestry":
        assert invalid["generation"] >= 3
        latest_request = load_json_closed(repository / invalid["request_path"])
        second_request = load_json_closed(
            repository
            / latest_request["prior_generation_binding"]["request_path"]
        )
        genesis_request = (
            repository
            / second_request["prior_generation_binding"]["request_path"]
        )
        genesis_request.write_bytes(b"{}\n")
    else:
        raise AssertionError(defect)
    return invalid


def test_ledger_generation_one_must_equal_plan_derived_genesis(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    plan = repository / "plan.md"
    _write_ledger_plan(plan)
    record = _ledger(Path("plan.md"))
    record["plan_binding"]["sha256"] = file_sha256(plan)
    record["tasks"][0]["completed_step_count"] = 1
    record["normalized_ledger_sha256"] = canonical_sha256(
        record, exclude={"normalized_ledger_sha256"}
    )

    with pytest.raises(
        MaterializationError,
        match="ledger_generation_invalid:ledger_genesis_mismatch",
    ):
        materialize_transaction(
            repository_root=repository,
            evidence_root=Path("evidence"),
            record_kind="execution-ledger",
            output_path=Path("evidence/execution-ledger.json"),
            generation=1,
            input_paths={"approved_plan": Path("plan.md")},
            parameters={"record": record},
        )

    assert not (repository / "evidence").exists()


@pytest.mark.parametrize(
    "invalid_transition",
    [
        "null_transition",
        "prior_alias",
        "step_skip",
        "wrong_task",
        "wrong_old_status",
        "wrong_new_status",
        "unaccounted_target_evidence",
        "transition_evidence_not_applied",
        "unrelated_task_evidence",
        "immutable_claim_drift",
    ],
)
def test_ledger_generation_rejects_nonsemantic_single_step_transition(
    tmp_path: Path, invalid_transition: str
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    _, first_record, first = _materialize_first_ledger(repository)
    record = _advance_ledger(first_record, first)
    transition = record["last_transition"]
    assert isinstance(transition, dict)
    evidence_path = repository / "evidence/already-existing.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text("{}\n")
    evidence_binding = {
        "path": "evidence/already-existing.json",
        "sha256": file_sha256(evidence_path),
    }
    if invalid_transition == "null_transition":
        record["last_transition"] = None
    elif invalid_transition == "prior_alias":
        alias_request = repository / "evidence/aliases/prior-request.json"
        alias_snapshot = repository / "evidence/aliases/prior-snapshot.json"
        alias_request.parent.mkdir(parents=True)
        alias_request.write_bytes((repository / first.request_path).read_bytes())
        alias_snapshot.write_bytes((repository / first.snapshot_path).read_bytes())
        transition["prior_generation_binding"]["request_path"] = (
            alias_request.relative_to(repository).as_posix()
        )
        transition["prior_generation_binding"]["snapshot_path"] = (
            alias_snapshot.relative_to(repository).as_posix()
        )
    elif invalid_transition == "step_skip":
        transition["step_number"] = 2
    elif invalid_transition == "wrong_task":
        transition["task_number"] = 2
    elif invalid_transition == "wrong_old_status":
        transition["old_status"] = "pending"
    elif invalid_transition == "wrong_new_status":
        transition["new_status"] = "complete"
    elif invalid_transition == "unaccounted_target_evidence":
        record["tasks"][0]["evidence_bindings"] = [evidence_binding]
    elif invalid_transition == "transition_evidence_not_applied":
        transition["evidence_bindings"] = [evidence_binding]
    elif invalid_transition == "unrelated_task_evidence":
        record["tasks"][1]["evidence_bindings"] = [evidence_binding]
    elif invalid_transition == "immutable_claim_drift":
        record["claims_not_made"] = ["A different claim boundary."]
    record["normalized_ledger_sha256"] = canonical_sha256(
        record, exclude={"normalized_ledger_sha256"}
    )

    with pytest.raises(MaterializationError, match="ledger_generation_invalid"):
        materialize_transaction(
            repository_root=repository,
            evidence_root=Path("evidence"),
            record_kind="execution-ledger",
            output_path=first.output_path,
            generation=2,
            input_paths={"approved_plan": Path("plan.md")},
            parameters={"record": record},
            prior_request=first.request_path,
            prior_snapshot=first.snapshot_path,
        )

    assert not list(
        (repository / "evidence/materialization-inputs").rglob("00000002-*.json")
    )
    assert not list(
        (repository / "evidence/immutable-outputs").rglob("00000002-*.json")
    )


def test_ledger_transition_rejects_future_path_that_is_also_evidence(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    plan, first_record, first = _materialize_first_ledger(repository)
    binding = {
        "path": "evidence/shared.json",
        "sha256": f"sha256:{'1' * 64}",
    }
    record = _advance_ledger(
        first_record,
        first,
        evidence_bindings=[binding],
        future_paths=[binding["path"]],
    )

    issues = retirement_materialization._execution_ledger_generation_issues(
        record,
        repository_root=repository,
        generation=2,
        plan_path=plan.relative_to(repository),
        plan_bytes=plan.read_bytes(),
        prior_record=first_record,
        request_prior_binding=_prior_generation_binding(first),
    )

    assert [issue.code for issue in issues] == ["ledger_future_binding_overlap"]


def test_ledger_history_rejects_locally_valid_child_of_invalid_ancestor(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    _, first_record, first = _materialize_first_ledger(repository)
    invalid_second = _advance_ledger(first_record, first)
    invalid_second["tasks"][0]["completed_step_count"] = 2
    invalid_second["last_transition"]["step_number"] = 2
    invalid_second["normalized_ledger_sha256"] = canonical_sha256(
        invalid_second, exclude={"normalized_ledger_sha256"}
    )
    second = _forge_ledger_generation(repository, invalid_second, 2, first)
    locally_valid_third = _advance_ledger(
        invalid_second,
        second,
        future_paths=[
            "evidence/implementation-commits/task-01-bootstrap/"
            "specification-review.json",
            "evidence/implementation-commits/task-01-bootstrap/quality-review.json",
        ],
    )
    third = _forge_ledger_generation(repository, locally_valid_third, 3, second)

    issues = validate_generation(repository, third.request_path, third.snapshot_path)

    assert any(
        issue.code == "prior_generation_invalid"
        and issue.message == "ledger_transition_coordinate_mismatch"
        for issue in issues
    )


def test_task1_ledger_generations_are_contiguous_and_historical_after_future_reviews(
    tmp_path: Path,
) -> None:
    repository = tmp_path
    candidate, binding, bootstrap = _producer_task1_candidate_ledger_and_bootstrap(
        repository
    )
    generations = [deepcopy(binding)]
    for _ in range(2):
        _, receipt = _advance_bound_ledger(repository, binding)
        binding = _ledger_binding(receipt)
        generations.append(deepcopy(binding))
    future_reviews = [
        "evidence/implementation-commits/task-01-bootstrap/specification-review.json",
        "evidence/implementation-commits/task-01-bootstrap/quality-review.json",
    ]
    record, receipt = _advance_bound_ledger(
        repository, binding, future_paths=future_reviews
    )
    binding = _ledger_binding(receipt)
    generations.append(deepcopy(binding))

    subject_path, specification_binding, quality_binding = (
        _producer_bootstrap_subject_and_reviews(
            repository,
            candidate=candidate,
            ledger=binding,
            bootstrap=bootstrap,
        )
    )
    specification_path = Path(specification_binding["logical_path"])
    quality_path = Path(quality_binding["logical_path"])
    assert validate_generation(
        repository, Path(binding["request_path"]), Path(binding["snapshot_path"])
    ) == []

    closing_evidence = [
        {
            "path": path.as_posix(),
            "sha256": file_sha256(repository / path),
        }
        for path in sorted(
            [subject_path, specification_path, quality_path]
        )
    ]
    record, receipt = _advance_bound_ledger(
        repository,
        binding,
        evidence_bindings=closing_evidence,
    )
    generations.append(_ledger_binding(receipt))
    assert record["tasks"][0]["status"] == "complete"
    assert record["tasks"][0]["completed_step_count"] == 4
    assert record["tasks"][0]["evidence_bindings"] == closing_evidence
    assert record["tasks"][1]["status"] == "in_progress"
    assert record["current_task"] == 2
    assert [item["generation"] for item in generations] == [1, 2, 3, 4, 5]
    for item in generations:
        assert validate_generation(
            repository, Path(item["request_path"]), Path(item["snapshot_path"])
        ) == []
    assert broad_evidence.validate_review_pair(
        specification_binding=specification_binding,
        quality_binding=quality_binding,
        repository_root=repository,
        expected_subject_kind="broad_evidence_bootstrap",
        expected_subject_binding={
            "path": subject_path.as_posix(),
            "sha256": file_sha256(repository / subject_path),
        },
    ) == []


def test_task1_rereview_history_is_subject_bound_and_completes_ledger(
    tmp_path: Path,
) -> None:
    candidate, binding, bootstrap, prior_specification, prior_quality = (
        _producer_task1_prior_review_history(tmp_path)
    )

    subject_path, specification, quality = _producer_bootstrap_subject_and_reviews(
        tmp_path,
        candidate=candidate,
        ledger=binding,
        bootstrap=bootstrap,
        prior_specification_binding=prior_specification,
        prior_quality_binding=prior_quality,
        specification_reviewed_at="2026-01-02T00:00:00+00:00",
        quality_reviewed_at="2026-01-02T00:00:01+00:00",
    )
    subject = load_json_closed(tmp_path / subject_path)
    manifest_paths = {row["path"] for row in subject["candidate_path_manifest"]}
    assert prior_quality is None
    assert prior_specification["immutable_path"] in manifest_paths
    assert broad_evidence.validate_review_pair(
        specification_binding=specification,
        quality_binding=quality,
        repository_root=tmp_path,
        expected_subject_kind="broad_evidence_bootstrap",
    ) == []

    closing_evidence = [
        {"path": path.as_posix(), "sha256": file_sha256(tmp_path / path)}
        for path in sorted(
            [
                subject_path,
                Path(specification["logical_path"]),
                Path(quality["logical_path"]),
            ]
        )
    ]
    record, _receipt = _advance_bound_ledger(
        tmp_path, binding, evidence_bindings=closing_evidence
    )
    assert record["tasks"][0]["status"] == "complete"

    unrelated_subject_path = Path(
        "evidence/implementation-commits/task-02-unrelated/subject.json"
    )
    unrelated_review_path = unrelated_subject_path.with_name(
        "specification-review.json"
    )
    unrelated_review = {
        "schema_version": "review.v1",
        "review_kind": "specification",
        "reviewer": {"identity": "later-reviewer"},
        "subject": {
            "kind": "implementation_candidate",
            "path": unrelated_subject_path.as_posix(),
            "sha256": f"sha256:{'2' * 64}",
        },
        "result": "approved",
        "issues": [],
        "reviewed_at": "2026-01-03T00:00:00+00:00",
        "claims_not_made": ["Synthetic unrelated later review."],
    }
    unrelated_bytes = json.dumps(unrelated_review, sort_keys=True).encode() + b"\n"
    unrelated_binding = broad_evidence.derive_review_binding(
        evidence_root=Path("evidence"),
        review_path=unrelated_review_path,
        review_bytes=unrelated_bytes,
    )
    unrelated_path = tmp_path / unrelated_binding["immutable_path"]
    unrelated_path.parent.mkdir(parents=True, exist_ok=True)
    unrelated_path.write_bytes(unrelated_bytes)

    assert unrelated_binding["immutable_path"] not in manifest_paths
    assert broad_evidence.validate_review_pair(
        specification_binding=specification,
        quality_binding=quality,
        repository_root=tmp_path,
        expected_subject_kind="broad_evidence_bootstrap",
    ) == []


@pytest.mark.parametrize("defect", ["tampered", "structurally_named_extra"])
def test_bootstrap_builder_rejects_invalid_prior_immutable_review_history(
    tmp_path: Path, defect: str
) -> None:
    candidate, binding, bootstrap, prior_specification, prior_quality = (
        _producer_task1_prior_review_history(tmp_path)
    )
    prior_path = tmp_path / prior_specification["immutable_path"]
    if defect == "tampered":
        prior_path.chmod(0o600)
        prior_path.write_bytes(b"{}\n")
    else:
        extra = prior_path.with_name(f"specification-{'f' * 64}.json")
        extra.write_bytes(prior_path.read_bytes())

    with pytest.raises(ContractError, match="immutable_review_path_invalid"):
        _producer_bootstrap_subject_and_reviews(
            tmp_path,
            candidate=candidate,
            ledger=binding,
            bootstrap=bootstrap,
            prior_specification_binding=prior_specification,
            prior_quality_binding=prior_quality,
            specification_reviewed_at="2026-01-02T00:00:00+00:00",
            quality_reviewed_at="2026-01-02T00:00:01+00:00",
        )


@pytest.mark.parametrize("defect", ["missing", "tampered", "unaccounted"])
def test_task1_review_pair_rejects_lost_or_unaccounted_prior_history(
    tmp_path: Path, defect: str
) -> None:
    candidate, binding, bootstrap, prior_specification, prior_quality = (
        _producer_task1_prior_review_history(tmp_path)
    )
    _subject_path, specification, quality = _producer_bootstrap_subject_and_reviews(
        tmp_path,
        candidate=candidate,
        ledger=binding,
        bootstrap=bootstrap,
        prior_specification_binding=prior_specification,
        prior_quality_binding=prior_quality,
        specification_reviewed_at="2026-01-02T00:00:00+00:00",
        quality_reviewed_at="2026-01-02T00:00:01+00:00",
    )
    prior_path = tmp_path / prior_specification["immutable_path"]
    if defect == "missing":
        prior_path.unlink()
    elif defect == "tampered":
        prior_path.chmod(0o600)
        prior_path.write_bytes(b"{}\n")
    else:
        review = load_json_closed(tmp_path / specification["logical_path"])
        review["reviewed_at"] = "2026-01-03T00:00:00+00:00"
        review_bytes = json.dumps(review, sort_keys=True).encode() + b"\n"
        extra_binding = broad_evidence.derive_review_binding(
            evidence_root=Path("evidence"),
            review_path=Path(specification["logical_path"]),
            review_bytes=review_bytes,
        )
        extra_path = tmp_path / extra_binding["immutable_path"]
        extra_path.parent.mkdir(parents=True, exist_ok=True)
        extra_path.write_bytes(review_bytes)

    assert broad_evidence.Issue(
        "review_pair_subject_invalid", "$.subject"
    ) in broad_evidence.validate_review_pair(
        specification_binding=specification,
        quality_binding=quality,
        repository_root=tmp_path,
        expected_subject_kind="broad_evidence_bootstrap",
    )


def _task1_generation_three(repository: Path) -> dict[str, object]:
    _candidate, binding, _bootstrap = _producer_task1_candidate_ledger_and_bootstrap(
        repository
    )
    for _ in range(2):
        _, receipt = _advance_bound_ledger(repository, binding)
        binding = _ledger_binding(receipt)
    return binding


@pytest.mark.parametrize(
    "future_paths",
    [
        [],
        [
            "evidence/implementation-commits/task-01-bootstrap/"
            "specification-review.json"
        ],
        [
            "evidence/implementation-commits/task-01-bootstrap/"
            "specification-review.json",
            "evidence/implementation-commits/task-01-bootstrap/quality-review.json",
            "evidence/implementation-commits/task-01-bootstrap/unexpected.json",
        ],
        [
            "evidence/implementation-commits/task-01-bootstrap/"
            "specification-review.json",
            "evidence/wrong/quality-review.json",
        ],
        [
            "evidence/implementation-commits/task-01-bootstrap/subject.json",
            "evidence/implementation-commits/task-01-bootstrap/"
            "specification-review.json",
            "evidence/implementation-commits/task-01-bootstrap/quality-review.json",
        ],
    ],
)
def test_task1_generation_four_requires_exact_review_reservation(
    tmp_path: Path, future_paths: list[str]
) -> None:
    binding = _task1_generation_three(tmp_path)

    with pytest.raises(
        MaterializationError,
        match="ledger_generation_invalid:ledger_completion_reservation_mismatch",
    ):
        _advance_bound_ledger(tmp_path, binding, future_paths=future_paths)


@pytest.mark.parametrize(
    ("defect", "expected_code"),
    [
        ("missing", "ledger_completion_evidence_mismatch"),
        ("extra", "ledger_completion_evidence_mismatch"),
        ("wrong_path", "ledger_completion_evidence_mismatch"),
        ("wrong_kind", "ledger_completion_review_pair_invalid"),
        ("wrong_subject", "ledger_completion_review_pair_invalid"),
        ("wrong_order", "ledger_completion_review_pair_invalid"),
    ],
)
def test_task1_generation_five_requires_exact_reviewed_subject_handoff(
    tmp_path: Path, defect: str, expected_code: str
) -> None:
    candidate, binding, bootstrap = _producer_task1_candidate_ledger_and_bootstrap(
        tmp_path
    )
    for _ in range(2):
        _, receipt = _advance_bound_ledger(tmp_path, binding)
        binding = _ledger_binding(receipt)
    future_paths = [
        "evidence/implementation-commits/task-01-bootstrap/"
        "specification-review.json",
        "evidence/implementation-commits/task-01-bootstrap/quality-review.json",
    ]
    _, receipt = _advance_bound_ledger(
        tmp_path, binding, future_paths=future_paths
    )
    binding = _ledger_binding(receipt)
    subject, specification_binding, quality_binding = (
        _producer_bootstrap_subject_and_reviews(
            tmp_path,
            candidate=candidate,
            ledger=binding,
            bootstrap=bootstrap,
        )
    )
    specification = Path(specification_binding["logical_path"])
    quality = Path(quality_binding["logical_path"])
    paths = [subject, specification, quality]
    if defect == "missing":
        paths.pop()
    elif defect == "extra":
        extra = Path("evidence/implementation-commits/task-01-bootstrap/extra.json")
        _write_producer_json(tmp_path, extra.as_posix(), {})
        paths.append(extra)
    elif defect == "wrong_path":
        wrong = Path("evidence/implementation-commits/task-01-bootstrap/wrong.json")
        (tmp_path / wrong).write_bytes((tmp_path / quality).read_bytes())
        paths[-1] = wrong
    elif defect in {"wrong_kind", "wrong_subject", "wrong_order"}:
        review_path = specification if defect != "wrong_subject" else quality
        review = load_json_closed(tmp_path / review_path)
        if defect == "wrong_kind":
            review["review_kind"] = "code_quality"
        elif defect == "wrong_subject":
            review["subject"]["sha256"] = f"sha256:{'0' * 64}"
        else:
            review["reviewed_at"] = "2026-01-01T00:00:02+00:00"
        _write_producer_json(tmp_path, review_path.as_posix(), review)
    evidence = [
        {"path": path.as_posix(), "sha256": file_sha256(tmp_path / path)}
        for path in sorted(paths)
    ]

    with pytest.raises(
        MaterializationError,
        match=rf"ledger_generation_invalid:{expected_code}",
    ):
        _advance_bound_ledger(tmp_path, binding, evidence_bindings=evidence)


def test_task1_generation_five_rejects_nested_bootstrap_subject_tamper(
    tmp_path: Path,
) -> None:
    candidate, binding, bootstrap = _producer_task1_candidate_ledger_and_bootstrap(
        tmp_path
    )
    for _ in range(2):
        _, receipt = _advance_bound_ledger(tmp_path, binding)
        binding = _ledger_binding(receipt)
    future_paths = [
        "evidence/implementation-commits/task-01-bootstrap/quality-review.json",
        "evidence/implementation-commits/task-01-bootstrap/specification-review.json",
    ]
    _, receipt = _advance_bound_ledger(
        tmp_path, binding, future_paths=future_paths
    )
    binding = _ledger_binding(receipt)
    subject_path, specification_binding, quality_binding = (
        _producer_bootstrap_subject_and_reviews(
            tmp_path,
            candidate=candidate,
            ledger=binding,
            bootstrap=bootstrap,
        )
    )
    subject = load_json_closed(tmp_path / subject_path)
    focused_path = Path(subject["focused_report_binding"]["path"])
    focused = load_json_closed(tmp_path / focused_path)
    log_path = (
        focused_path.parent.parent
        / focused["commands"][0]["log_binding"]["path"]
    )
    (tmp_path / log_path).write_text("tampered\n")
    evidence = [
        {"path": path.as_posix(), "sha256": file_sha256(tmp_path / path)}
        for path in sorted(
            [
                subject_path,
                Path(specification_binding["logical_path"]),
                Path(quality_binding["logical_path"]),
            ]
        )
    ]

    with pytest.raises(
        MaterializationError,
        match="ledger_generation_invalid:ledger_completion_subject_invalid",
    ):
        _advance_bound_ledger(tmp_path, binding, evidence_bindings=evidence)


def test_task1_generation_five_rejects_unrelated_evidence_root_addition(
    tmp_path: Path,
) -> None:
    candidate, binding, bootstrap = _producer_task1_candidate_ledger_and_bootstrap(
        tmp_path
    )
    for _ in range(2):
        _, receipt = _advance_bound_ledger(tmp_path, binding)
        binding = _ledger_binding(receipt)
    future_paths = [
        "evidence/implementation-commits/task-01-bootstrap/quality-review.json",
        "evidence/implementation-commits/task-01-bootstrap/specification-review.json",
    ]
    _, receipt = _advance_bound_ledger(
        tmp_path, binding, future_paths=future_paths
    )
    binding = _ledger_binding(receipt)
    subject_path, specification_binding, quality_binding = (
        _producer_bootstrap_subject_and_reviews(
            tmp_path,
            candidate=candidate,
            ledger=binding,
            bootstrap=bootstrap,
        )
    )
    _write_producer_json(tmp_path, "evidence/unrelated.json", {})
    evidence = [
        {"path": path.as_posix(), "sha256": file_sha256(tmp_path / path)}
        for path in sorted(
            [
                subject_path,
                Path(specification_binding["logical_path"]),
                Path(quality_binding["logical_path"]),
            ]
        )
    ]

    with pytest.raises(
        MaterializationError,
        match="ledger_generation_invalid:ledger_completion_subject_invalid",
    ):
        _advance_bound_ledger(tmp_path, binding, evidence_bindings=evidence)


def test_ledger_future_path_created_before_live_publication_leaves_exact_replayable_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    _, first_record, first = _materialize_first_ledger(repository)
    future_path = Path("evidence/reviews/future-review.json")
    second_record = _advance_ledger(
        first_record, first, future_paths=[future_path.as_posix()]
    )
    kwargs = {
        "repository_root": repository,
        "evidence_root": Path("evidence"),
        "record_kind": "execution-ledger",
        "output_path": first.output_path,
        "generation": 2,
        "input_paths": {"approved_plan": Path("plan.md")},
        "parameters": {"record": second_record},
        "prior_request": first.request_path,
        "prior_snapshot": first.snapshot_path,
    }

    def create_future_at_boundary(boundary: str) -> None:
        if boundary == "before_live_publication":
            absolute = repository / future_path
            absolute.parent.mkdir(parents=True, exist_ok=True)
            absolute.write_text("review now exists\n")

    monkeypatch.setattr(
        retirement_materialization,
        "_materialization_boundary",
        create_future_at_boundary,
    )
    with pytest.raises(
        MaterializationError,
        match="output_contract_invalid:ledger_future_binding_already_exists",
    ):
        materialize_transaction(**kwargs)

    request_prefix = sorted(
        (repository / "evidence/materialization-inputs").rglob(
            "00000002-*.json"
        )
    )
    snapshot_prefix = sorted(
        (repository / "evidence/immutable-outputs").rglob(
            "00000002-*.json"
        )
    )
    assert len(request_prefix) == len(snapshot_prefix) == 1
    assert (repository / first.output_path).read_bytes() == (
        repository / first.snapshot_path
    ).read_bytes()

    (repository / future_path).unlink()
    monkeypatch.setattr(
        retirement_materialization,
        "_materialization_boundary",
        lambda _boundary: None,
    )
    second = materialize_transaction(**kwargs)

    assert sorted(
        (repository / "evidence/materialization-inputs").rglob(
            "00000002-*.json"
        )
    ) == request_prefix
    assert sorted(
        (repository / "evidence/immutable-outputs").rglob(
            "00000002-*.json"
        )
    ) == snapshot_prefix
    assert (repository / second.output_path).read_bytes() == (
        repository / second.snapshot_path
    ).read_bytes()


def test_existing_future_path_rejects_before_new_generation_prefix(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    _, first_record, first = _materialize_first_ledger(repository)
    future_path = Path("evidence/reviews/future-review.json")
    absolute_future = repository / future_path
    absolute_future.parent.mkdir(parents=True)
    absolute_future.write_text("already exists\n")
    second_record = _advance_ledger(
        first_record, first, future_paths=[future_path.as_posix()]
    )

    with pytest.raises(
        MaterializationError,
        match="output_contract_invalid:ledger_future_binding_already_exists",
    ):
        materialize_transaction(
            repository_root=repository,
            evidence_root=Path("evidence"),
            record_kind="execution-ledger",
            output_path=first.output_path,
            generation=2,
            input_paths={"approved_plan": Path("plan.md")},
            parameters={"record": second_record},
            prior_request=first.request_path,
            prior_snapshot=first.snapshot_path,
        )

    assert not list(
        (repository / "evidence/materialization-inputs").rglob(
            "00000002-*.json"
        )
    )
    assert not list(
        (repository / "evidence/immutable-outputs").rglob(
            "00000002-*.json"
        )
    )
    assert (repository / first.output_path).read_bytes() == (
        repository / first.snapshot_path
    ).read_bytes()


def test_ledger_future_path_created_after_live_publication_preserves_history(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    _, first_record, first = _materialize_first_ledger(repository)
    future_path = Path("evidence/reviews/future-review.json")
    _, second = _materialize_next_ledger(
        repository,
        first_record,
        first,
        future_paths=[future_path.as_posix()],
    )

    absolute = repository / future_path
    absolute.parent.mkdir(parents=True, exist_ok=True)
    absolute.write_text("review created after publication\n")

    assert validate_generation(
        repository, second.request_path, second.snapshot_path
    ) == []


def test_task17_final_step_returns_current_task_to_null(tmp_path: Path) -> None:
    plan = tmp_path / "plan.md"
    _write_ledger_plan(plan)
    prior = build_initial_execution_ledger(
        plan_path=Path("plan.md"), plan_bytes=plan.read_bytes()
    )
    for row in prior["tasks"][:-1]:
        row["status"] = "complete"
        row["completed_step_count"] = row["total_step_count"]
    prior["tasks"][-1]["status"] = "in_progress"
    prior["tasks"][-1]["completed_step_count"] = 3
    prior["current_task"] = 17
    prior["normalized_ledger_sha256"] = canonical_sha256(
        prior, exclude={"normalized_ledger_sha256"}
    )
    prior_binding = {
        "request_path": "evidence/materialization-inputs/prior.json",
        "request_sha256": f"sha256:{'1' * 64}",
        "snapshot_path": "evidence/immutable-outputs/prior.json",
        "snapshot_sha256": f"sha256:{'2' * 64}",
        "generation": 98,
        "output_path": "evidence/execution-ledger.json",
    }
    record = deepcopy(prior)
    record["tasks"][-1]["status"] = "complete"
    record["tasks"][-1]["completed_step_count"] = 4
    record["current_task"] = None
    record["last_transition"] = {
        "prior_generation_binding": prior_binding,
        "task_number": 17,
        "step_number": 4,
        "old_status": "in_progress",
        "new_status": "complete",
        "prepared_at": "2026-01-01T00:00:00+00:00",
        "evidence_bindings": [],
        "future_bindings": [],
    }
    record["normalized_ledger_sha256"] = canonical_sha256(
        record, exclude={"normalized_ledger_sha256"}
    )

    assert retirement_materialization._execution_ledger_generation_issues(
        record,
        repository_root=tmp_path,
        generation=99,
        plan_path=Path("plan.md"),
        plan_bytes=plan.read_bytes(),
        prior_record=prior,
        request_prior_binding=prior_binding,
    ) == []


def test_adapter_output_slots_reject_wrong_lifecycle_name_before_history(
    tmp_path: Path,
) -> None:
    ledger_repository = tmp_path / "ledger"
    ledger_repository.mkdir()
    plan = ledger_repository / "plan.md"
    _write_ledger_plan(plan)
    ledger = _ledger(Path("plan.md"))
    ledger["plan_binding"]["sha256"] = file_sha256(plan)
    ledger["normalized_ledger_sha256"] = canonical_sha256(
        ledger, exclude={"normalized_ledger_sha256"}
    )
    with pytest.raises(MaterializationError, match="output_slot_invalid"):
        materialize_transaction(
            repository_root=ledger_repository,
            evidence_root=Path("evidence"),
            record_kind="execution-ledger",
            output_path=Path("evidence/wrong-name.json"),
            generation=1,
            input_paths={"approved_plan": Path("plan.md")},
            parameters={"record": ledger},
        )
    assert not (ledger_repository / "evidence").exists()

    query_repository = tmp_path / "query"
    query_repository.mkdir()
    handoff = query_repository / "handoff.json"
    handoff.write_text(
        json.dumps(
            {
                "yaml_retirement_handoff": {
                    "schema_version": "procedure_first_yaml_retirement_handoff.v1",
                    "captured_at_commit": "1" * 40,
                    "queues": [{"queue_id": "selected", "paths": ["a.yaml"]}],
                }
            }
        )
        + "\n"
    )
    with pytest.raises(MaterializationError, match="output_slot_invalid"):
        materialize_transaction(
            repository_root=query_repository,
            evidence_root=Path("evidence"),
            record_kind="query",
            output_path=Path("evidence/wrong-name.json"),
            generation=1,
            input_paths={"handoff": Path("handoff.json")},
            parameters={"queue_id": "selected", "capture_commit": "1" * 40},
        )
    assert not (query_repository / "evidence").exists()

    pending_repository = tmp_path / "pending"
    pending_repository.mkdir()
    pending_inputs = _write_pending_materializer_inputs(pending_repository)
    with pytest.raises(MaterializationError, match="output_slot_invalid"):
        materialize_pending(
            repository_root=pending_repository,
            evidence_root=Path("evidence"),
            record_kind="broad-failure-baseline-attestation",
            output_path=Path("evidence/wrong-name.json"),
            generation=1,
            input_paths=pending_inputs,
            parameters={
                "prepared_by": {"identity": "mechanical-writer"},
                "prepared_at": "2026-01-01T00:00:00+00:00",
            },
        )
    assert not (pending_repository / "evidence/materialization-inputs").exists()
    assert not (pending_repository / "evidence/immutable-outputs").exists()
    assert not (pending_repository / "evidence/attestations").exists()


def test_ledger_materializer_builds_from_the_exact_nofollow_captured_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    plan = repository / "plan.md"
    _write_ledger_plan(plan)
    captured_bytes = plan.read_bytes()
    outside = tmp_path / "outside-plan.md"
    outside.write_text("# raced plan\n")
    record = _ledger(Path("plan.md"))
    record["plan_binding"]["sha256"] = (
        f"sha256:{hashlib.sha256(captured_bytes).hexdigest()}"
    )
    record["normalized_ledger_sha256"] = canonical_sha256(
        record, exclude={"normalized_ledger_sha256"}
    )
    original = retirement_materialization._input_binding

    def capture_then_swap(root: Path, role: str, path: Path):
        binding = original(root, role, path)
        plan.unlink()
        plan.symlink_to(outside)
        return binding

    monkeypatch.setattr(retirement_materialization, "_input_binding", capture_then_swap)

    receipt = materialize_transaction(
        repository_root=repository,
        evidence_root=Path("evidence"),
        record_kind="execution-ledger",
        output_path=Path("evidence/execution-ledger.json"),
        generation=1,
        input_paths={"approved_plan": Path("plan.md")},
        parameters={"record": record},
    )

    request = load_json_closed(repository / receipt.request_path)
    assert request["input_bindings"][0]["sha256"] == record["plan_binding"]["sha256"]
    assert plan.is_symlink()
    assert outside.read_text() == "# raced plan\n"


def test_query_materializer_builds_from_the_exact_nofollow_captured_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    handoff = repository / "handoff.json"
    original_handoff = {
        "yaml_retirement_handoff": {
            "schema_version": "procedure_first_yaml_retirement_handoff.v1",
            "queues": [{"queue_id": "selected", "paths": ["old.yaml"]}],
        }
    }
    handoff.write_text(json.dumps(original_handoff) + "\n")
    captured_digest = file_sha256(handoff)
    outside = tmp_path / "outside-handoff.json"
    raced_handoff = json.loads(json.dumps(original_handoff))
    raced_handoff["yaml_retirement_handoff"]["queues"][0]["paths"] = ["new.yaml"]
    outside.write_text(json.dumps(raced_handoff) + "\n")
    original = retirement_materialization._input_binding

    def capture_then_swap(root: Path, role: str, path: Path):
        binding = original(root, role, path)
        handoff.unlink()
        handoff.symlink_to(outside)
        return binding

    monkeypatch.setattr(retirement_materialization, "_input_binding", capture_then_swap)

    receipt = materialize_transaction(
        repository_root=repository,
        evidence_root=Path("evidence"),
        record_kind="query",
        output_path=Path("evidence/query.json"),
        generation=1,
        input_paths={"handoff": Path("handoff.json")},
        parameters={"queue_id": "selected", "capture_commit": "1" * 40},
    )

    request = load_json_closed(repository / receipt.request_path)
    output = load_json_closed(repository / receipt.output_path)
    assert request["input_bindings"][0]["sha256"] == captured_digest
    assert output["authority"]["sha256"] == captured_digest
    assert output["paths"] == ["old.yaml"]
    assert handoff.is_symlink()


def test_pending_materializer_builds_from_exact_nofollow_captured_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    inputs = _write_pending_materializer_inputs(repository)
    specification_path = repository / inputs["specification_review"]
    captured_specification_bytes = specification_path.read_bytes()
    captured_specification = load_json_closed(specification_path)
    outside = tmp_path / "outside-specification.json"
    raced_specification = json.loads(json.dumps(captured_specification))
    raced_specification["reviewer"] = {"identity": "raced-reviewer"}
    outside.write_text(json.dumps(raced_specification, sort_keys=True) + "\n")
    original = retirement_materialization._input_binding

    def capture_then_swap(root: Path, role: str, path: Path):
        binding = original(root, role, path)
        if role == "specification_review":
            specification_path.unlink()
            specification_path.symlink_to(outside)
        return binding

    monkeypatch.setattr(retirement_materialization, "_input_binding", capture_then_swap)

    receipt = materialize_pending(
        repository_root=repository,
        evidence_root=Path("evidence"),
        record_kind="broad-failure-baseline-attestation",
        output_path=Path(
            "evidence/attestations/pre-implementation/broad-failure-baseline.json"
        ),
        generation=1,
        input_paths=inputs,
        parameters={
            "prepared_by": {"identity": "mechanical-writer"},
            "prepared_at": "2026-01-01T00:00:00+00:00",
        },
    )

    output = load_json_closed(repository / receipt.output_path)
    assert output["specification_review_binding"]["logical_path"] == inputs[
        "specification_review"
    ].as_posix()
    assert output["specification_review_binding"]["reviewer"] == captured_specification[
        "reviewer"
    ]
    assert output["specification_review_binding"]["sha256"] == (
        f"sha256:{hashlib.sha256(captured_specification_bytes).hexdigest()}"
    )
    assert specification_path.is_symlink()
    assert outside.read_bytes() != json.dumps(captured_specification, sort_keys=True).encode()


def test_materialization_rejects_stale_live_and_generation_gap(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    plan, record, first = _materialize_first_ledger(repository)
    record = _advance_ledger(record, first)
    (repository / first.output_path).write_text("stale\n")
    with pytest.raises(MaterializationError, match="stale_live_output"):
        materialize_transaction(
            repository_root=repository,
            evidence_root=Path("evidence"),
            record_kind="execution-ledger",
            output_path=first.output_path,
            generation=2,
            input_paths={"approved_plan": Path("plan.md")},
            parameters={"record": record},
            prior_request=first.request_path,
            prior_snapshot=first.snapshot_path,
        )
    (repository / first.output_path).write_bytes((repository / first.snapshot_path).read_bytes())
    with pytest.raises(MaterializationError, match="generation_not_contiguous"):
        materialize_transaction(
            repository_root=repository,
            evidence_root=Path("evidence"),
            record_kind="execution-ledger",
            output_path=first.output_path,
            generation=3,
            input_paths={"approved_plan": Path("plan.md")},
            parameters={"record": record},
            prior_request=first.request_path,
            prior_snapshot=first.snapshot_path,
        )


def test_generation_validation_reopens_prior_generation_binding(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    _, record, first = _materialize_first_ledger(repository)
    record = _advance_ledger(record, first)
    second = materialize_transaction(
        repository_root=repository,
        evidence_root=Path("evidence"),
        record_kind="execution-ledger",
        output_path=first.output_path,
        generation=2,
        input_paths={"approved_plan": Path("plan.md")},
        parameters={"record": record},
        prior_request=first.request_path,
        prior_snapshot=first.snapshot_path,
    )
    (repository / first.request_path).write_text("{}\n")
    assert "prior_generation_changed" in {
        issue.code
        for issue in validate_generation(repository, second.request_path, second.snapshot_path)
    }


def test_generation_validation_rejects_snapshot_tamper(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    _, _, receipt = _materialize_first_ledger(repository)
    (repository / receipt.snapshot_path).write_text("tampered\n")
    assert {issue.code for issue in validate_generation(
        repository, receipt.request_path, receipt.snapshot_path
    )} == {"snapshot_path_mismatch", "snapshot_output_mismatch"}


def test_generation_validation_rejects_relocated_wrong_prefix_output_slot(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    _, _, receipt = _materialize_first_ledger(repository)
    assert validate_generation(
        repository, receipt.request_path, receipt.snapshot_path
    ) == []

    old_request = repository / receipt.request_path
    old_snapshot = repository / receipt.snapshot_path
    request = load_json_closed(old_request)
    request["output_path"] = "outside-evidence/execution-ledger.json"
    request["normalized_request_sha256"] = canonical_sha256(
        request, exclude={"normalized_request_sha256"}
    )
    request_bytes = (
        json.dumps(request, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8")
        + b"\n"
    )
    relocated_request = retirement_materialization._request_path(
        Path("evidence"),
        Path(request["output_path"]),
        request["generation"],
        request["normalized_request_sha256"],
    )
    relocated_snapshot = retirement_materialization._snapshot_path(
        Path("evidence"),
        Path(request["output_path"]),
        request["generation"],
        receipt.snapshot_sha256,
    )
    relocated_request_absolute = repository / relocated_request
    relocated_snapshot_absolute = repository / relocated_snapshot
    relocated_request_absolute.parent.mkdir(parents=True)
    relocated_snapshot_absolute.parent.mkdir(parents=True)
    relocated_request_absolute.write_bytes(request_bytes)
    old_request.unlink()
    old_snapshot.replace(relocated_snapshot_absolute)

    assert "generation_output_slot_invalid" in {
        issue.code
        for issue in validate_generation(
            repository, relocated_request, relocated_snapshot
        )
    }


def test_query_generation_validation_uses_the_same_exact_output_slot_contract(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    handoff = repository / "handoff.json"
    handoff.write_text(
        json.dumps(
            {
                "yaml_retirement_handoff": {
                    "schema_version": "procedure_first_yaml_retirement_handoff.v1",
                    "queues": [{"queue_id": "selected", "paths": ["old.yaml"]}],
                }
            }
        )
        + "\n"
    )
    receipt = materialize_transaction(
        repository_root=repository,
        evidence_root=Path("evidence"),
        record_kind="query",
        output_path=Path("evidence/query.json"),
        generation=1,
        input_paths={"handoff": Path("handoff.json")},
        parameters={"queue_id": "selected", "capture_commit": "1" * 40},
    )
    assert validate_generation(
        repository, receipt.request_path, receipt.snapshot_path
    ) == []

    old_request = repository / receipt.request_path
    old_snapshot = repository / receipt.snapshot_path
    request = load_json_closed(old_request)
    request["output_path"] = "outside-evidence/query.json"
    request["normalized_request_sha256"] = canonical_sha256(
        request, exclude={"normalized_request_sha256"}
    )
    relocated_request = retirement_materialization._request_path(
        Path("evidence"),
        Path(request["output_path"]),
        request["generation"],
        request["normalized_request_sha256"],
    )
    relocated_snapshot = retirement_materialization._snapshot_path(
        Path("evidence"),
        Path(request["output_path"]),
        request["generation"],
        receipt.snapshot_sha256,
    )
    relocated_request_absolute = repository / relocated_request
    relocated_snapshot_absolute = repository / relocated_snapshot
    relocated_request_absolute.parent.mkdir(parents=True)
    relocated_snapshot_absolute.parent.mkdir(parents=True)
    relocated_request_absolute.write_bytes(
        json.dumps(request, indent=2, sort_keys=True, ensure_ascii=False).encode(
            "utf-8"
        )
        + b"\n"
    )
    old_request.unlink()
    old_snapshot.replace(relocated_snapshot_absolute)

    assert "generation_output_slot_invalid" in {
        issue.code
        for issue in validate_generation(
            repository, relocated_request, relocated_snapshot
        )
    }


def test_generation_validation_reopens_inputs_and_rebuilds_output(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    plan, _, receipt = _materialize_first_ledger(repository)
    plan.write_text("changed after publication\n")
    assert "generation_input_changed" in {
        issue.code
        for issue in validate_generation(repository, receipt.request_path, receipt.snapshot_path)
    }


def test_generation_validation_rejects_alternate_snapshot_preimage(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    _, _, receipt = _materialize_first_ledger(repository)
    old = repository / receipt.snapshot_path
    alternate = b"{}\n"
    alternate_sha = hashlib.sha256(alternate).hexdigest()
    renamed = old.with_name(f"00000001-{alternate_sha}.json")
    old.unlink()
    renamed.write_bytes(alternate)
    alternate_path = renamed.relative_to(repository)
    assert "snapshot_output_mismatch" in {
        issue.code
        for issue in validate_generation(repository, receipt.request_path, alternate_path)
    }


def test_generation_validation_rejects_extra_same_generation_slot(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    _, _, receipt = _materialize_first_ledger(repository)
    extra = (repository / receipt.request_path).with_name(
        f"00000001-{'f' * 64}.json"
    )
    extra.write_text("{}\n")
    assert "generation_request_slot_extra" in {
        issue.code
        for issue in validate_generation(repository, receipt.request_path, receipt.snapshot_path)
    }


@pytest.mark.parametrize(
    ("component_kind", "parent_index"),
    [("request", 0), ("request", 1), ("snapshot", 0), ("snapshot", 1)],
)
def test_generation_validation_rejects_symlinked_immutable_directory_component(
    tmp_path: Path, component_kind: str, parent_index: int
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    _, _, receipt = _materialize_first_ledger(repository)
    assert validate_generation(repository, receipt.request_path, receipt.snapshot_path) == []
    relative = (
        receipt.request_path if component_kind == "request" else receipt.snapshot_path
    )
    directory = repository / relative.parents[parent_index]
    retained = directory.with_name(f"{directory.name}-retained")
    directory.rename(retained)
    directory.symlink_to(retained.name, target_is_directory=True)

    codes = {
        issue.code
        for issue in validate_generation(
            repository, receipt.request_path, receipt.snapshot_path
        )
    }

    assert (
        "generation_unreadable" if component_kind == "request" else "snapshot_unreadable"
    ) in codes


def test_generation_validation_rejects_symlinked_input_directory_component(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    inputs = repository / "inputs"
    inputs.mkdir()
    plan = inputs / "plan.md"
    _write_ledger_plan(plan)
    record = _ledger(Path("inputs/plan.md"))
    record["plan_binding"]["sha256"] = file_sha256(plan)
    record["normalized_ledger_sha256"] = canonical_sha256(
        record, exclude={"normalized_ledger_sha256"}
    )
    receipt = materialize_transaction(
        repository_root=repository,
        evidence_root=Path("evidence"),
        record_kind="execution-ledger",
        output_path=Path("evidence/execution-ledger.json"),
        generation=1,
        input_paths={"approved_plan": Path("inputs/plan.md")},
        parameters={"record": record},
    )
    assert validate_generation(repository, receipt.request_path, receipt.snapshot_path) == []
    retained = repository / "inputs-retained"
    inputs.rename(retained)
    inputs.symlink_to(retained.name, target_is_directory=True)

    assert "generation_input_changed" in {
        issue.code
        for issue in validate_generation(
            repository, receipt.request_path, receipt.snapshot_path
        )
    }


def test_generation_validation_reports_missing_input_without_escaping_validator(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    plan, _, receipt = _materialize_first_ledger(repository)
    plan.unlink()

    assert "generation_input_changed" in {
        issue.code
        for issue in validate_generation(
            repository, receipt.request_path, receipt.snapshot_path
        )
    }


@pytest.mark.parametrize("prior_kind", ["request", "snapshot"])
def test_generation_validation_rejects_symlinked_prior_generation_file(
    tmp_path: Path, prior_kind: str
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    _, record, first = _materialize_first_ledger(repository)
    record = _advance_ledger(record, first)
    second = materialize_transaction(
        repository_root=repository,
        evidence_root=Path("evidence"),
        record_kind="execution-ledger",
        output_path=first.output_path,
        generation=2,
        input_paths={"approved_plan": Path("plan.md")},
        parameters={"record": record},
        prior_request=first.request_path,
        prior_snapshot=first.snapshot_path,
    )
    assert validate_generation(repository, second.request_path, second.snapshot_path) == []
    relative = first.request_path if prior_kind == "request" else first.snapshot_path
    original = repository / relative
    retained = original.with_name(f"retained-{original.name}")
    original.rename(retained)
    original.symlink_to(retained.name)

    assert "prior_generation_changed" in {
        issue.code
        for issue in validate_generation(
            repository, second.request_path, second.snapshot_path
        )
    }


def test_materialization_replay_rejects_symlinked_live_file(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    _, record, receipt = _materialize_first_ledger(repository)
    live = repository / receipt.output_path
    retained = live.with_name(f"retained-{live.name}")
    live.rename(retained)
    live.symlink_to(retained.name)

    with pytest.raises(MaterializationError, match="publication_path_symlink"):
        materialize_transaction(
            repository_root=repository,
            evidence_root=Path("evidence"),
            record_kind="execution-ledger",
            output_path=receipt.output_path,
            generation=1,
            input_paths={"approved_plan": Path("plan.md")},
            parameters={"record": record},
        )

    assert live.is_symlink()
    assert retained.read_bytes() == (repository / receipt.snapshot_path).read_bytes()


def test_generation_slot_enumeration_rejects_symlinked_extra_entry(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    _, _, receipt = _materialize_first_ledger(repository)
    extra_target = repository / "outside-request.json"
    extra_target.write_text("{}\n")
    extra = (repository / receipt.request_path).with_name(
        f"00000001-{'f' * 64}.json"
    )
    extra.symlink_to(extra_target)

    assert "generation_request_slot_extra" in {
        issue.code
        for issue in validate_generation(
            repository, receipt.request_path, receipt.snapshot_path
        )
    }


def test_materialization_rejects_extra_parameter_before_publication(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    plan = repository / "plan.md"
    _write_ledger_plan(plan)
    with pytest.raises(MaterializationError, match="parameter_names_mismatch"):
        materialize_transaction(
            repository_root=repository,
            evidence_root=Path("evidence"),
            record_kind="execution-ledger",
            output_path=Path("evidence/execution-ledger.json"),
            generation=1,
            input_paths={"approved_plan": Path("plan.md")},
            parameters={"record": {}, "extra": True},
        )
    assert not (repository / "evidence").exists()


@pytest.mark.parametrize(
    ("symlink_component", "output_path"),
    [
        (Path("evidence/materialization-inputs"), Path("evidence/execution-ledger.json")),
        (Path("evidence/immutable-outputs"), Path("evidence/execution-ledger.json")),
        (Path("evidence"), Path("evidence/execution-ledger.json")),
    ],
)
def test_materialization_rejects_symlinked_publication_path_components(
    tmp_path: Path, symlink_component: Path, output_path: Path
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    plan = repository / "plan.md"
    _write_ledger_plan(plan)
    record = _ledger(Path("plan.md"))
    record["plan_binding"]["sha256"] = file_sha256(plan)
    record["normalized_ledger_sha256"] = canonical_sha256(
        record, exclude={"normalized_ledger_sha256"}
    )
    outside = tmp_path / "outside"
    outside.mkdir()
    absolute_component = repository / symlink_component
    absolute_component.parent.mkdir(parents=True, exist_ok=True)
    absolute_component.symlink_to(outside, target_is_directory=True)

    with pytest.raises(MaterializationError, match="publication_path_symlink"):
        materialize_transaction(
            repository_root=repository,
            evidence_root=Path("evidence"),
            record_kind="execution-ledger",
            output_path=output_path,
            generation=1,
            input_paths={"approved_plan": Path("plan.md")},
            parameters={"record": record},
        )

    assert list(outside.iterdir()) == []


def test_materialization_atomic_output_rejects_symlinked_final_slot(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("owner bytes\n")
    (repository / "output.json").symlink_to(outside)

    with pytest.raises(MaterializationError, match="publication_path_symlink"):
        retirement_materialization._atomic_publish(
            repository, Path("output.json"), b"new bytes\n"
        )

    assert outside.read_text() == "owner bytes\n"


def test_materialization_atomic_output_replaces_regular_final_slot(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    output = repository / "output.json"
    output.write_text("old bytes\n")

    retirement_materialization._atomic_publish(
        repository, Path("output.json"), b"new bytes\n"
    )

    assert output.is_file()
    assert not output.is_symlink()
    assert output.read_bytes() == b"new bytes\n"


def test_materialization_atomic_output_rejects_slot_swapped_before_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    output = repository / "output.json"
    output.write_text("old bytes\n")
    outside = tmp_path / "outside.json"
    outside.write_text("owner bytes\n")
    real_capture = retirement_materialization.capture_regular_file_at
    raced = False

    def race_final_slot(parent_fd, name, logical_path, *, missing_ok):
        nonlocal raced
        if not raced:
            raced = True
            output.unlink()
            output.symlink_to(outside)
        return real_capture(
            parent_fd, name, logical_path, missing_ok=missing_ok
        )

    monkeypatch.setattr(
        retirement_materialization, "capture_regular_file_at", race_final_slot
    )

    with pytest.raises(MaterializationError, match="publication_path_symlink"):
        retirement_materialization._atomic_publish(
            repository, Path("output.json"), b"new bytes\n"
        )

    assert output.is_symlink()
    assert outside.read_text() == "owner bytes\n"


def test_materialization_atomic_output_restores_entry_raced_after_last_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from orchestrator.retirement import safe_io

    repository = tmp_path / "repo"
    repository.mkdir()
    output = repository / "output.json"
    output.write_text("old bytes\n")
    outside = tmp_path / "outside.json"
    outside.write_text("owner bytes\n")
    real_renameat2 = safe_io._renameat2
    raced = False

    def race_after_capture(parent, old_name, new_name, flags):
        nonlocal raced
        if not raced:
            raced = True
            output.unlink()
            output.symlink_to(outside)
        return real_renameat2(parent, old_name, new_name, flags)

    monkeypatch.setattr(safe_io, "_renameat2", race_after_capture)

    with pytest.raises(MaterializationError, match="publication_concurrent_mutation"):
        retirement_materialization._atomic_publish(
            repository, Path("output.json"), b"new bytes\n"
        )

    assert output.is_symlink()
    assert output.resolve() == outside
    assert outside.read_bytes() == b"owner bytes\n"


def test_materialization_atomic_output_noreplace_preserves_raced_absent_slot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from orchestrator.retirement import safe_io

    repository = tmp_path / "repo"
    repository.mkdir()
    output = repository / "output.json"
    outside = tmp_path / "outside.json"
    outside.write_text("owner bytes\n")
    real_renameat2 = safe_io._renameat2
    raced = False

    def race_after_absence_capture(parent, old_name, new_name, flags):
        nonlocal raced
        if not raced:
            raced = True
            output.symlink_to(outside)
        return real_renameat2(parent, old_name, new_name, flags)

    monkeypatch.setattr(safe_io, "_renameat2", race_after_absence_capture)

    with pytest.raises(MaterializationError, match="publication_concurrent_mutation"):
        retirement_materialization._atomic_publish(
            repository, Path("output.json"), b"new bytes\n"
        )

    assert output.is_symlink()
    assert output.resolve() == outside
    assert outside.read_bytes() == b"owner bytes\n"


def test_materialization_atomic_output_fails_closed_without_atomic_primitive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from orchestrator.retirement import safe_io

    repository = tmp_path / "repo"
    repository.mkdir()
    output = repository / "output.json"
    output.write_text("old bytes\n")

    def unavailable(*_args):
        raise safe_io.AtomicPublishError("atomic_rename_unavailable")

    monkeypatch.setattr(safe_io, "_renameat2", unavailable)

    with pytest.raises(
        MaterializationError, match="publication_atomic_rename_unavailable"
    ):
        retirement_materialization._atomic_publish(
            repository, Path("output.json"), b"new bytes\n"
        )

    assert output.read_bytes() == b"old bytes\n"


def test_materialization_atomic_output_restores_in_place_mode_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from orchestrator.retirement import safe_io

    repository = tmp_path / "repo"
    repository.mkdir()
    output = repository / "output.json"
    output.write_text("old bytes\n")
    output.chmod(0o600)
    real_renameat2 = safe_io._renameat2
    raced = False

    def chmod_after_capture(parent, old_name, new_name, flags):
        nonlocal raced
        if not raced:
            raced = True
            output.chmod(0o640)
        return real_renameat2(parent, old_name, new_name, flags)

    monkeypatch.setattr(safe_io, "_renameat2", chmod_after_capture)

    with pytest.raises(MaterializationError, match="publication_concurrent_mutation"):
        retirement_materialization._atomic_publish(
            repository, Path("output.json"), b"new bytes\n"
        )

    assert output.stat().st_mode & 0o777 == 0o640
    assert output.read_bytes() == b"old bytes\n"


def test_safe_io_bound_file_identity_includes_changed_ns(tmp_path: Path) -> None:
    directory = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        (tmp_path / "entry").write_bytes(b"same bytes\n")
        observed = safe_io.capture_regular_file_at(
            directory, "entry", "entry", missing_ok=False
        )
        assert observed is not None
        changed = replace(observed, changed_ns=observed.changed_ns + 1)
        assert not safe_io._same_bound_file(observed, changed)
    finally:
        os.close(directory)


def test_materialization_rollback_preserves_second_concurrent_owner_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    output = repository / "output.json"
    output.write_bytes(b"original owner bytes\n")
    real_renameat2 = safe_io._renameat2
    calls = 0

    def race_each_exchange(parent, old_name, new_name, flags):
        nonlocal calls
        calls += 1
        if calls == 1:
            output.chmod(0o640)
        elif calls == 2:
            output.unlink()
            output.write_bytes(b"second concurrent owner bytes\n")
        return real_renameat2(parent, old_name, new_name, flags)

    monkeypatch.setattr(safe_io, "_renameat2", race_each_exchange)

    with pytest.raises(MaterializationError, match="publication_concurrent_mutation"):
        retirement_materialization._atomic_publish(
            repository, Path("output.json"), b"publisher bytes\n"
        )

    assert output.read_bytes() == b"second concurrent owner bytes\n"
    retained = [
        path.read_bytes()
        for path in repository.iterdir()
        if path.is_file() and path != output
    ]
    assert b"original owner bytes\n" in retained


def test_materialization_rollback_preserves_owner_arriving_after_exchange(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    output = repository / "output.json"
    output.write_bytes(b"original owner bytes\n")
    real_renameat2 = safe_io._renameat2
    real_boundary = safe_io._conditional_publish_boundary
    raced_exchange = False
    raced_after_rollback = False

    def force_rollback(parent, old_name, new_name, flags):
        nonlocal raced_exchange
        if not raced_exchange:
            raced_exchange = True
            output.chmod(0o640)
        return real_renameat2(parent, old_name, new_name, flags)

    def owner_after_rollback(stage, parent, temporary_name, destination_name):
        nonlocal raced_after_rollback
        if stage == "after_rollback_exchange" and not raced_after_rollback:
            raced_after_rollback = True
            output.unlink()
            output.write_bytes(b"post-rollback owner bytes\n")
        return real_boundary(stage, parent, temporary_name, destination_name)

    monkeypatch.setattr(safe_io, "_renameat2", force_rollback)
    monkeypatch.setattr(
        safe_io, "_conditional_publish_boundary", owner_after_rollback
    )

    with pytest.raises(MaterializationError, match="publication_concurrent_mutation"):
        retirement_materialization._atomic_publish(
            repository, Path("output.json"), b"publisher bytes\n"
        )

    assert output.read_bytes() == b"post-rollback owner bytes\n"
    retained = [
        path.read_bytes()
        for path in repository.iterdir()
        if path.is_file() and path != output
    ]
    assert b"original owner bytes\n" in retained
    assert b"publisher bytes\n" in retained


def test_materialization_exclusive_write_rejects_detached_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    evidence = repository / "evidence"
    evidence.mkdir()
    detached = repository / "detached"
    real_boundary = safe_io._conditional_publish_boundary
    raced = False

    def detach_before_create(stage, parent, temporary_name, destination_name):
        nonlocal raced
        if stage == "before_parent_validation" and not raced:
            raced = True
            evidence.rename(detached)
            evidence.mkdir()
        return real_boundary(stage, parent, temporary_name, destination_name)

    monkeypatch.setattr(
        safe_io, "_conditional_publish_boundary", detach_before_create
    )

    with pytest.raises(MaterializationError, match="concurrent_mutation"):
        retirement_materialization._exclusive_identical(
            repository, Path("evidence/record.json"), b"publisher bytes\n"
        )

    assert not (evidence / "record.json").exists()
    assert not (detached / "record.json").exists()


def test_materialization_prior_binding_rejects_validate_use_symlink_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    _, record, first = _materialize_first_ledger(repository)
    request = repository / first.request_path
    outside = tmp_path / "outside-request.json"
    outside.write_bytes(request.read_bytes())
    real_boundary = retirement_materialization._prior_binding_boundary
    swapped = False

    def capture_then_swap(boundary):
        nonlocal swapped
        if not swapped:
            swapped = True
            request.unlink()
            request.symlink_to(outside)
        return real_boundary(boundary)

    monkeypatch.setattr(
        retirement_materialization, "_prior_binding_boundary", capture_then_swap
    )
    record = _advance_ledger(record, first)

    with pytest.raises(MaterializationError, match="prior_generation_invalid"):
        materialize_transaction(
            repository_root=repository,
            evidence_root=Path("evidence"),
            record_kind="execution-ledger",
            output_path=first.output_path,
            generation=2,
            input_paths={"approved_plan": Path("plan.md")},
            parameters={"record": record},
            prior_request=first.request_path,
            prior_snapshot=first.snapshot_path,
        )


def test_materialization_prior_binding_rejects_final_prepublication_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    _, record, first = _materialize_first_ledger(repository)
    request = repository / first.request_path
    outside = tmp_path / "outside-request.json"
    outside.write_bytes(request.read_bytes())
    real_boundary = retirement_materialization._prior_binding_boundary
    swapped = False

    def swap_before_prepublication_check(boundary):
        nonlocal swapped
        if boundary == "before_prior_prepublication_check" and not swapped:
            swapped = True
            request.unlink()
            request.symlink_to(outside)
        return real_boundary(boundary)

    monkeypatch.setattr(
        retirement_materialization,
        "_prior_binding_boundary",
        swap_before_prepublication_check,
    )
    record = _advance_ledger(record, first)

    with pytest.raises(MaterializationError, match="prior_generation_invalid"):
        materialize_transaction(
            repository_root=repository,
            evidence_root=Path("evidence"),
            record_kind="execution-ledger",
            output_path=first.output_path,
            generation=2,
            input_paths={"approved_plan": Path("plan.md")},
            parameters={"record": record},
            prior_request=first.request_path,
            prior_snapshot=first.snapshot_path,
        )

    assert (repository / first.output_path).read_bytes() == (
        repository / first.snapshot_path
    ).read_bytes()
    assert len(
        list((repository / "evidence/materialization-inputs").rglob("00000002-*.json"))
    ) == 0


def test_materialization_prior_binding_postcheck_rolls_back_new_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    _, record, first = _materialize_first_ledger(repository)
    prior_live = (repository / first.snapshot_path).read_bytes()
    request = repository / first.request_path
    outside = tmp_path / "outside-request.json"
    outside.write_bytes(request.read_bytes())
    real_boundary = retirement_materialization._prior_binding_boundary
    swapped = False

    def swap_before_postcheck(boundary):
        nonlocal swapped
        if boundary == "before_prior_postpublication_check" and not swapped:
            swapped = True
            request.unlink()
            request.symlink_to(outside)
        return real_boundary(boundary)

    monkeypatch.setattr(
        retirement_materialization,
        "_prior_binding_boundary",
        swap_before_postcheck,
    )
    record = _advance_ledger(record, first)

    with pytest.raises(MaterializationError, match="prior_generation_invalid"):
        materialize_transaction(
            repository_root=repository,
            evidence_root=Path("evidence"),
            record_kind="execution-ledger",
            output_path=first.output_path,
            generation=2,
            input_paths={"approved_plan": Path("plan.md")},
            parameters={"record": record},
            prior_request=first.request_path,
            prior_snapshot=first.snapshot_path,
        )

    assert (repository / first.output_path).read_bytes() == prior_live
    assert len(
        list((repository / "evidence/materialization-inputs").rglob("00000002-*.json"))
    ) == 0
    assert len(
        list((repository / "evidence/immutable-outputs").rglob("00000002-*.json"))
    ) == 0


def _three_generation_ledger_chain(repository: Path):
    _, record, first = _materialize_first_ledger(repository)
    record, second = _materialize_next_ledger(repository, record, first)
    record, third = _materialize_next_ledger(repository, record, second)
    return record, (first, second, third)


def _replace_with_identical_bytes(path: Path) -> None:
    replacement = path.with_name(f".{path.name}.identical-replacement")
    replacement.write_bytes(path.read_bytes())
    replacement.replace(path)


def _materialize_fourth_ledger_generation(repository: Path, record, third):
    return _materialize_next_ledger(
        repository,
        record,
        third,
        future_paths=[
            "evidence/implementation-commits/task-01-bootstrap/quality-review.json",
            "evidence/implementation-commits/task-01-bootstrap/specification-review.json",
        ],
    )


def test_validate_generation_rejects_deep_identical_ancestry_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    _, (first, _, third) = _three_generation_ledger_chain(repository)
    deep_request = repository / first.request_path
    replaced = False

    def replace_at_final_boundary(boundary: str) -> None:
        nonlocal replaced
        if boundary == "before_final_identity_check" and not replaced:
            replaced = True
            _replace_with_identical_bytes(deep_request)

    monkeypatch.setattr(
        retirement_materialization,
        "_generation_validation_boundary",
        replace_at_final_boundary,
    )

    issues = validate_generation(repository, third.request_path, third.snapshot_path)

    assert "prior_generation_changed" in {issue.code for issue in issues}
    assert replaced is True


def test_materialization_rejects_deep_ancestry_replacement_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    record, (first, _, third) = _three_generation_ledger_chain(repository)
    prior_live = (repository / third.snapshot_path).read_bytes()
    deep_request = repository / first.request_path
    replaced = False

    def replace_before_prepublication_check(boundary: str) -> None:
        nonlocal replaced
        if boundary == "before_prior_prepublication_check" and not replaced:
            replaced = True
            _replace_with_identical_bytes(deep_request)

    monkeypatch.setattr(
        retirement_materialization,
        "_prior_binding_boundary",
        replace_before_prepublication_check,
    )

    with pytest.raises(MaterializationError, match="prior_generation_invalid"):
        _materialize_fourth_ledger_generation(repository, record, third)

    assert (repository / third.output_path).read_bytes() == prior_live
    assert not list(
        (repository / "evidence/materialization-inputs").rglob("00000004-*.json")
    )
    assert not list(
        (repository / "evidence/immutable-outputs").rglob("00000004-*.json")
    )


def test_materialization_rolls_back_deep_ancestry_replacement_after_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    record, (first, _, third) = _three_generation_ledger_chain(repository)
    prior_live = (repository / third.snapshot_path).read_bytes()
    deep_request = repository / first.request_path
    replaced = False

    def replace_before_postpublication_check(boundary: str) -> None:
        nonlocal replaced
        if boundary == "before_prior_postpublication_check" and not replaced:
            replaced = True
            _replace_with_identical_bytes(deep_request)

    monkeypatch.setattr(
        retirement_materialization,
        "_prior_binding_boundary",
        replace_before_postpublication_check,
    )

    with pytest.raises(MaterializationError, match="prior_generation_invalid"):
        _materialize_fourth_ledger_generation(repository, record, third)

    assert (repository / third.output_path).read_bytes() == prior_live
    assert not list(
        (repository / "evidence/materialization-inputs").rglob("00000004-*.json")
    )
    assert not list(
        (repository / "evidence/immutable-outputs").rglob("00000004-*.json")
    )


def test_materialization_accepts_unchanged_full_ancestry(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    record, (_, _, third) = _three_generation_ledger_chain(repository)

    assert validate_generation(
        repository, third.request_path, third.snapshot_path
    ) == []
    _, fourth = _materialize_fourth_ledger_generation(repository, record, third)
    assert validate_generation(
        repository, fourth.request_path, fourth.snapshot_path
    ) == []


def test_materialization_postcheck_rollback_preserves_concurrent_live_writer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    _, record, first = _materialize_first_ledger(repository)
    request = repository / first.request_path
    live = repository / first.output_path
    request_bytes = request.read_bytes()
    concurrent_live_bytes = b'{"ordinary_concurrent_writer":true}\n'
    real_boundary = retirement_materialization._prior_binding_boundary
    replaced = False

    def replace_live_and_rewrite_prior(boundary):
        nonlocal replaced
        if boundary == "before_prior_postpublication_check" and not replaced:
            replaced = True
            live_replacement = live.with_name(f".{live.name}.concurrent")
            live_replacement.write_bytes(concurrent_live_bytes)
            live_replacement.replace(live)
            request_replacement = request.with_name(f".{request.name}.rewrite")
            request_replacement.write_bytes(request_bytes)
            request_replacement.replace(request)
        return real_boundary(boundary)

    monkeypatch.setattr(
        retirement_materialization,
        "_prior_binding_boundary",
        replace_live_and_rewrite_prior,
    )
    record = _advance_ledger(record, first)

    with pytest.raises(
        MaterializationError,
        match="materialization_rollback_concurrent_mutation",
    ):
        materialize_transaction(
            repository_root=repository,
            evidence_root=Path("evidence"),
            record_kind="execution-ledger",
            output_path=first.output_path,
            generation=2,
            input_paths={"approved_plan": Path("plan.md")},
            parameters={"record": record},
            prior_request=first.request_path,
            prior_snapshot=first.snapshot_path,
        )

    assert live.read_bytes() == concurrent_live_bytes
    assert len(
        list((repository / "evidence/materialization-inputs").rglob("00000002-*.json"))
    ) == 1
    assert len(
        list((repository / "evidence/immutable-outputs").rglob("00000002-*.json"))
    ) == 1


@pytest.mark.parametrize(
    ("changed_input", "expected_issue"),
    [("request", "generation_unreadable"), ("snapshot", "snapshot_unreadable")],
)
def test_validate_generation_rejects_identical_input_symlink_after_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    changed_input: str,
    expected_issue: str,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    _, _, first = _materialize_first_ledger(repository)
    target = repository / (
        first.request_path if changed_input == "request" else first.snapshot_path
    )
    outside = tmp_path / f"outside-{changed_input}.json"
    outside.write_bytes(target.read_bytes())
    swapped = False

    def swap_after_validation(boundary):
        nonlocal swapped
        if boundary == "before_final_identity_check" and not swapped:
            swapped = True
            target.unlink()
            target.symlink_to(outside)

    monkeypatch.setattr(
        retirement_materialization,
        "_generation_validation_boundary",
        swap_after_validation,
        raising=False,
    )

    issues = validate_generation(repository, first.request_path, first.snapshot_path)

    assert [issue.code for issue in issues] == [expected_issue]


def test_validate_generation_rejects_detached_request_parent_after_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    _, _, first = _materialize_first_ledger(repository)
    request = repository / first.request_path
    parent = request.parent
    detached = parent.with_name(f"{parent.name}-detached")
    request_bytes = request.read_bytes()
    swapped = False

    def detach_after_validation(boundary):
        nonlocal swapped
        if boundary == "before_final_identity_check" and not swapped:
            swapped = True
            parent.rename(detached)
            parent.mkdir()
            (parent / request.name).write_bytes(request_bytes)

    monkeypatch.setattr(
        retirement_materialization,
        "_generation_validation_boundary",
        detach_after_validation,
        raising=False,
    )

    issues = validate_generation(repository, first.request_path, first.snapshot_path)

    assert [issue.code for issue in issues] == ["generation_unreadable"]


def test_repository_absence_rejects_detached_and_recreated_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    parent = repository / "evidence" / "candidate"
    parent.mkdir(parents=True)
    detached = parent.with_name("candidate-detached")
    raced = False

    def detach_after_absence(stage, _parent_fd, logical_path):
        nonlocal raced
        if stage == "after_absence_observation" and not raced:
            raced = True
            parent.rename(detached)
            parent.mkdir()
            (parent / Path(logical_path).name).write_bytes(b"new logical owner\n")

    monkeypatch.setattr(
        broad_evidence,
        "_repository_absence_boundary",
        detach_after_absence,
        raising=False,
    )

    assert not broad_evidence._repository_path_absent_no_follow(
        repository, "evidence/candidate/retired.yaml"
    )


def test_conditional_quarantine_rejects_detached_logical_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    parent = repository / "evidence"
    parent.mkdir(parents=True)
    destination = parent / "record.json"
    destination.write_bytes(b"owned bytes\n")
    parent_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    detached = repository / "evidence-detached"
    real_boundary = getattr(
        safe_io,
        "_conditional_quarantine_boundary",
        lambda *_args: None,
    )
    raced = False
    try:
        expected = safe_io.capture_regular_file_at(
            parent_fd, destination.name, "evidence/record.json", missing_ok=False
        )
        assert expected is not None
        logical_parent = safe_io.bind_logical_parent(
            repository, Path("evidence"), parent_fd
        )

        def detach_after_move(stage, fd, destination_name, quarantine_name):
            nonlocal raced
            if stage == "after_quarantine_move" and not raced:
                raced = True
                parent.rename(detached)
                parent.mkdir()
            return real_boundary(stage, fd, destination_name, quarantine_name)

        monkeypatch.setattr(
            safe_io,
            "_conditional_quarantine_boundary",
            detach_after_move,
            raising=False,
        )

        with pytest.raises(safe_io.AtomicPublishError, match="logical_parent_changed"):
            safe_io.conditional_quarantine_file_at(
                parent_fd,
                destination.name,
                expected,
                "evidence/record.json",
                logical_parent=logical_parent,
            )
    finally:
        os.close(parent_fd)

    assert not destination.exists()
    assert any(path.read_bytes() == b"owned bytes\n" for path in detached.iterdir())


def test_conditional_quarantine_preserves_destination_recreated_after_move(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    parent = repository / "evidence"
    parent.mkdir(parents=True)
    destination = parent / "record.json"
    destination.write_bytes(b"owned bytes\n")
    parent_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    real_boundary = getattr(
        safe_io,
        "_conditional_quarantine_boundary",
        lambda *_args: None,
    )
    raced = False
    try:
        expected = safe_io.capture_regular_file_at(
            parent_fd, destination.name, "evidence/record.json", missing_ok=False
        )
        assert expected is not None
        logical_parent = safe_io.bind_logical_parent(
            repository, Path("evidence"), parent_fd
        )

        def replace_after_move(stage, fd, destination_name, quarantine_name):
            nonlocal raced
            if stage == "after_quarantine_move" and not raced:
                raced = True
                owner_fd = os.open(
                    destination_name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=fd,
                )
                try:
                    os.write(owner_fd, b"concurrent owner bytes\n")
                finally:
                    os.close(owner_fd)
            return real_boundary(stage, fd, destination_name, quarantine_name)

        monkeypatch.setattr(
            safe_io,
            "_conditional_quarantine_boundary",
            replace_after_move,
            raising=False,
        )

        with pytest.raises(safe_io.AtomicPublishError, match="concurrent_mutation"):
            safe_io.conditional_quarantine_file_at(
                parent_fd,
                destination.name,
                expected,
                "evidence/record.json",
                logical_parent=logical_parent,
            )
    finally:
        os.close(parent_fd)

    assert destination.read_bytes() == b"concurrent owner bytes\n"
    retained = [path.read_bytes() for path in parent.iterdir() if path != destination]
    assert b"owned bytes\n" in retained


def test_materialization_successful_rollback_removes_displaced_recovery_anchor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    output = repository / "output.json"
    output.write_bytes(b"original owner bytes\n")
    real_renameat2 = safe_io._renameat2
    raced = False

    def force_rollback(parent, old_name, new_name, flags):
        nonlocal raced
        if not raced:
            raced = True
            output.chmod(0o640)
        return real_renameat2(parent, old_name, new_name, flags)

    monkeypatch.setattr(safe_io, "_renameat2", force_rollback)

    with pytest.raises(MaterializationError, match="publication_concurrent_mutation"):
        retirement_materialization._atomic_publish(
            repository, Path("output.json"), b"publisher bytes\n"
        )

    assert output.read_bytes() == b"original owner bytes\n"
    assert list(repository.iterdir()) == [output]


def test_materialization_anchor_cleanup_preserves_late_owner_and_displaced_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    output = repository / "output.json"
    output.write_bytes(b"original owner bytes\n")
    real_renameat2 = safe_io._renameat2
    real_boundary = safe_io._conditional_publish_boundary
    forced_rollback = False
    late_owner = False

    def force_rollback(parent, old_name, new_name, flags):
        nonlocal forced_rollback
        if not forced_rollback:
            forced_rollback = True
            output.chmod(0o640)
        return real_renameat2(parent, old_name, new_name, flags)

    def replace_before_anchor_cleanup(stage, parent, temporary_name, destination_name):
        nonlocal late_owner
        if stage == "before_recovery_anchor_cleanup" and not late_owner:
            late_owner = True
            output.unlink()
            output.write_bytes(b"late owner bytes\n")
        return real_boundary(stage, parent, temporary_name, destination_name)

    monkeypatch.setattr(safe_io, "_renameat2", force_rollback)
    monkeypatch.setattr(
        safe_io, "_conditional_publish_boundary", replace_before_anchor_cleanup
    )

    with pytest.raises(MaterializationError, match="publication_concurrent_mutation"):
        retirement_materialization._atomic_publish(
            repository, Path("output.json"), b"publisher bytes\n"
        )

    assert output.read_bytes() == b"late owner bytes\n"
    retained = [path.read_bytes() for path in repository.iterdir() if path != output]
    assert b"original owner bytes\n" in retained
    assert b"publisher bytes\n" in retained


def _remove_materialization_component(repository: Path, path: Path) -> None:
    absolute = repository / path
    absolute.unlink()


@pytest.mark.parametrize(
    "retained_components",
    [
        frozenset({"request"}),
        frozenset({"request", "snapshot"}),
        frozenset({"request", "snapshot", "live"}),
    ],
)
def test_materialization_replays_every_valid_crash_prefix(
    tmp_path: Path, retained_components: frozenset[str]
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    _, record, receipt = _materialize_first_ledger(repository)
    paths = {
        "request": receipt.request_path,
        "snapshot": receipt.snapshot_path,
        "live": receipt.output_path,
    }
    for component, path in paths.items():
        if component not in retained_components:
            _remove_materialization_component(repository, path)

    replay = materialize_transaction(
        repository_root=repository,
        evidence_root=Path("evidence"),
        record_kind="execution-ledger",
        output_path=receipt.output_path,
        generation=1,
        input_paths={"approved_plan": Path("plan.md")},
        parameters={"record": record},
    )

    assert replay == receipt


@pytest.mark.parametrize(
    "retained_components",
    [
        frozenset({"snapshot"}),
        frozenset({"live"}),
        frozenset({"request", "live"}),
    ],
)
def test_materialization_rejects_nonprefix_crash_states_without_writing(
    tmp_path: Path, retained_components: frozenset[str]
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    _, record, receipt = _materialize_first_ledger(repository)
    paths = {
        "request": receipt.request_path,
        "snapshot": receipt.snapshot_path,
        "live": receipt.output_path,
    }
    retained_bytes = {
        component: (repository / path).read_bytes()
        for component, path in paths.items()
        if component in retained_components
    }
    for component, path in paths.items():
        if component not in retained_components:
            _remove_materialization_component(repository, path)

    with pytest.raises(MaterializationError, match="materialization_nonprefix_state"):
        materialize_transaction(
            repository_root=repository,
            evidence_root=Path("evidence"),
            record_kind="execution-ledger",
            output_path=receipt.output_path,
            generation=1,
            input_paths={"approved_plan": Path("plan.md")},
            parameters={"record": record},
        )

    for component, path in paths.items():
        absolute = repository / path
        if component in retained_components:
            assert absolute.read_bytes() == retained_bytes[component]
        else:
            assert not absolute.exists()


def _failure(node_id: str, digest: str, ownership: str) -> dict[str, object]:
    return {
        "node_id": node_id,
        "outcome_kind": "failure",
        "failure_payload_sha256": f"sha256:{digest * 64}",
        "ownership_class": ownership,
        "ownership_basis": ["tests/example.py"],
        "authorized_remediation_scope": ["tests/example.py"] if ownership == "queue_owned" else [],
    }


def test_failure_comparison_accepts_exact_match_and_reviewed_owned_subset() -> None:
    owned = _failure("tests/a.py::test_a", "a", "queue_owned")
    external = _failure("tests/b.py::test_b", "b", "external")
    baseline = [owned, external]
    assert compare_failure_sets(
        baseline_rows=baseline, observed_rows=baseline, remediated_rows=[]
    )["outcome"] == "known_failures_matched"
    assert compare_failure_sets(
        baseline_rows=baseline, observed_rows=[external], remediated_rows=[owned]
    )["outcome"] == "approved_failure_subset"


def test_failure_comparison_rejects_external_removal_new_or_changed_failure() -> None:
    owned = _failure("tests/a.py::test_a", "a", "queue_owned")
    external = _failure("tests/b.py::test_b", "b", "external")
    with pytest.raises(ContractError, match="external_failure_removed"):
        compare_failure_sets(
            baseline_rows=[owned, external], observed_rows=[owned], remediated_rows=[external]
        )
    with pytest.raises(ContractError, match="unapproved_failure_observed"):
        compare_failure_sets(
            baseline_rows=[owned],
            observed_rows=[_failure("tests/a.py::test_a", "c", "queue_owned")],
            remediated_rows=[],
        )


def _git_output(repository: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ["git", *args],
        cwd=repository,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout


def test_retirement_public_surface_exports_all_evidence_producers() -> None:
    expected = {
        "build_broad_evidence_bootstrap_subject",
        "build_broad_known_failure_baseline",
        "build_broad_outcome",
        "build_implementation_verification_subject",
        "derive_broad_baseline_comparison",
        "publish_immutable_review",
    }

    assert expected <= set(retirement.__all__)
    assert all(callable(getattr(retirement, name)) for name in expected)


def test_retirement_public_surface_is_cold_lazy_and_cli_sets_are_exact() -> None:
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json,sys; import orchestrator.retirement as r; "
            "print(json.dumps({'exports': sorted(r.__all__), "
            "'modules': sorted(name for name in sys.modules "
            "if name.startswith('orchestrator.retirement'))}))",
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert probe.returncode == 0
    assert probe.stderr == ""
    observed = json.loads(probe.stdout)
    assert observed["modules"] == ["orchestrator.retirement"]
    assert observed["exports"] == sorted(
        {
            "ContractError",
            "Issue",
            "MaterializationError",
            "MaterializationReceipt",
            "apply_skip_change",
            "build_broad_evidence_bootstrap_subject",
            "build_broad_known_failure_baseline",
            "build_broad_outcome",
            "build_implementation_focused_report",
            "build_implementation_verification_subject",
            "build_initial_execution_ledger",
            "canonical_json_bytes",
            "canonical_sha256",
            "compare_failure_sets",
            "derive_broad_baseline_comparison",
            "derive_review_binding",
            "failure_signature",
            "load_json_closed",
            "materialize_pending",
            "materialize_transaction",
            "normalize_failure_payload",
            "parse_exit_bytes",
            "parse_junit_outcomes",
            "publish_immutable_review",
            "validate_bound_record",
            "validate_fixture_manifest",
            "validate_generation",
            "validate_implementation_focused_report",
            "validate_record",
            "validate_review_binding_pair",
            "validate_review_pair",
            "validate_review_subject",
        }
    )

    expected_commands = {
        "orchestrator.retirement.broad_evidence": {
            "probe-pytest-temp-root"
        },
        "orchestrator.retirement.source_bindings": {
            "adopt-bootstrap-workspace",
            "build-non-target-sources",
            "build-precommit-control",
            "capture-workspace-baseline",
            "materialize-query",
            "validate-bootstrap-workspace",
            "validate-commit-boundary",
            "validate-non-target-sources",
            "validate-workspace-baseline",
        },
    }
    for module, expected in expected_commands.items():
        help_result = subprocess.run(
            [sys.executable, "-m", module, "--help"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert help_result.returncode == 0
        assert help_result.stderr == ""
        match = re.search(r"\{([^}]+)\}", help_result.stdout)
        assert match is not None
        assert set(match.group(1).split(",")) == expected


def _write_producer_json(repository: Path, logical_path: str, value: object) -> Path:
    path = repository / logical_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n")
    return path


def _producer_candidate_and_ledger(
    repository: Path, *, ledger_generation: int = 1
) -> tuple[dict[str, object], dict[str, object]]:
    _initialize_candidate_repository(repository)
    plan, ledger_record, receipt = _materialize_first_ledger(repository)
    for _ in range(2, ledger_generation + 1):
        ledger_record, receipt = _materialize_next_ledger(
            repository, ledger_record, receipt
        )
    _git_output(repository, "add", "--", plan.relative_to(repository).as_posix())
    _git_output(repository, "commit", "-q", "-m", "bind plan")
    source = repository / "source.py"
    source.write_text("candidate = True\n")
    row = {
        "path": "source.py",
        "sha256": file_sha256(source),
        "size": source.stat().st_size,
        "state": "added",
    }
    candidate: dict[str, object] = {
        "head": "0" * 40,
        "head_tree": "0" * 40,
        "index_sha256": "sha256:" + "0" * 64,
        "evidence_root_exclusion": "evidence",
        "candidate_paths": [row],
        "candidate_path_set_sha256": canonical_sha256([row]),
    }
    _bind_candidate_to_repository(repository, candidate)
    ledger = _ledger_binding(receipt)
    return candidate, ledger


def _producer_task1_candidate_ledger_and_bootstrap(
    repository: Path,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    """Capture the bootstrap baseline before the first evidence write."""

    _initialize_candidate_repository(repository)
    plan = repository / "plan.md"
    _write_ledger_plan(plan)
    _git_output(repository, "add", "--", "plan.md")
    _git_output(repository, "commit", "-q", "-m", "bind plan")
    bootstrap = capture_workspace_baseline(repository)
    bootstrap["schema_version"] = "bootstrap_workspace_baseline.v1"
    bootstrap["bootstrap_capture_bindings"] = {
        "producer_contract_version": "task1_first_write_capture.v1",
        "head_file_sha256": f"sha256:{'0' * 64}",
        "status_file_sha256": f"sha256:{'0' * 64}",
        "index_entries_file_sha256": f"sha256:{'0' * 64}",
        "index_file_sha256": bootstrap["index_sha256"],
        "archive_sha256": f"sha256:{'0' * 64}",
        "tar_stderr_sha256": f"sha256:{'0' * 64}",
    }
    bootstrap["raw_archive_not_persisted"] = True
    bootstrap["normalized_baseline_sha256"] = canonical_sha256(
        bootstrap, exclude={"normalized_baseline_sha256"}
    )
    record = build_initial_execution_ledger(
        plan_path=Path("plan.md"), plan_bytes=plan.read_bytes()
    )
    receipt = materialize_transaction(
        repository_root=repository,
        evidence_root=Path("evidence"),
        record_kind="execution-ledger",
        output_path=Path("evidence/execution-ledger.json"),
        generation=1,
        input_paths={"approved_plan": Path("plan.md")},
        parameters={"record": record},
    )
    source = repository / "source.py"
    source.write_text("candidate = True\n")
    row = {
        "path": "source.py",
        "sha256": file_sha256(source),
        "size": source.stat().st_size,
        "state": "added",
    }
    candidate: dict[str, object] = {
        "head": "0" * 40,
        "head_tree": "0" * 40,
        "index_sha256": "sha256:" + "0" * 64,
        "evidence_root_exclusion": "evidence",
        "candidate_paths": [row],
        "candidate_path_set_sha256": canonical_sha256([row]),
    }
    _bind_candidate_to_repository(repository, candidate)
    return candidate, _ledger_binding(receipt), bootstrap


def _producer_bootstrap_subject_and_reviews(
    repository: Path,
    *,
    candidate: dict[str, object],
    ledger: dict[str, object],
    bootstrap: dict[str, object],
    prior_specification_binding: dict[str, object] | None = None,
    prior_quality_binding: dict[str, object] | None = None,
    specification_reviewed_at: str = "2026-01-01T00:00:00+00:00",
    quality_reviewed_at: str = "2026-01-01T00:00:01+00:00",
) -> tuple[Path, dict[str, object], dict[str, object]]:
    """Build the real generation-bound subject and publish its review pair."""

    task, focused_path = _producer_focused_report(repository, candidate, ledger)
    raw_paths = _producer_raw_broad(repository)
    directory = Path("evidence/implementation-commits/task-01-bootstrap")
    subject_path = directory / "subject.json"
    baseline_path = _write_producer_json(
        repository,
        "evidence/implementation-baseline/bootstrap-workspace-baseline.json",
        bootstrap,
    )
    subject = broad_evidence.build_broad_evidence_bootstrap_subject(
        repository_root=repository,
        subject_path=subject_path,
        task_contract_binding=task,
        candidate_binding=candidate,
        execution_ledger_binding=ledger,
        bootstrap_workspace_baseline_path=baseline_path.relative_to(repository),
        focused_report_path=focused_path.relative_to(repository),
        collection_argv=["pytest", "--collect-only", "-q"],
        environment={
            "LC_ALL": "C.UTF-8",
            "PYTHONHASHSEED": "0",
            "PYTEST_DEBUG_TEMPROOT": None,
        },
        **raw_paths,
    )
    _write_producer_json(repository, subject_path.as_posix(), subject)
    specification, quality = _publish_producer_review_pair(
        repository,
        evidence_root=Path("evidence"),
        subject_path=subject_path,
        subject_kind="broad_evidence_bootstrap",
        specification_name=(
            "implementation-commits/task-01-bootstrap/specification-review.json"
        ),
        quality_name="implementation-commits/task-01-bootstrap/quality-review.json",
        specification_reviewed_at=specification_reviewed_at,
        quality_reviewed_at=quality_reviewed_at,
        prior_review_bindings={
            "specification": prior_specification_binding,
            "code_quality": prior_quality_binding,
        },
    )
    return subject_path, specification, quality


def _producer_task1_prior_review_history(
    repository: Path,
) -> tuple[
    dict[str, object],
    dict[str, object],
    dict[str, object],
    dict[str, object],
    None,
]:
    """Preserve one specification review, then remove the mutable review surface."""

    candidate, binding, bootstrap = _producer_task1_candidate_ledger_and_bootstrap(
        repository
    )
    for _ in range(2):
        _, receipt = _advance_bound_ledger(repository, binding)
        binding = _ledger_binding(receipt)
    future_paths = [
        "evidence/implementation-commits/task-01-bootstrap/"
        "specification-review.json",
        "evidence/implementation-commits/task-01-bootstrap/quality-review.json",
    ]
    _, receipt = _advance_bound_ledger(
        repository, binding, future_paths=future_paths
    )
    binding = _ledger_binding(receipt)
    subject_path, specification, quality = _producer_bootstrap_subject_and_reviews(
        repository,
        candidate=candidate,
        ledger=binding,
        bootstrap=bootstrap,
    )
    for path in (
        subject_path,
        Path(specification["logical_path"]),
        Path(quality["logical_path"]),
    ):
        (repository / path).unlink()
    (repository / quality["immutable_path"]).unlink()
    return candidate, binding, bootstrap, specification, None


def _producer_focused_report(
    repository: Path,
    candidate: dict[str, object],
    ledger: dict[str, object],
) -> tuple[dict[str, object], Path]:
    required = [{
        "role_id": "focused-check",
        "argv": ["pytest", "-q", "tests/test_example.py"],
        "cwd": ".",
        "environment": {"LC_ALL": "C.UTF-8", "PYTHONHASHSEED": "0"},
    }]
    task = {
        "plan_path": "plan.md",
        "plan_sha256": file_sha256(repository / "plan.md"),
        "task_number": 1,
        "required_command_set_sha256": canonical_sha256(required),
    }
    lane = "evidence/implementation-baseline"
    _write_producer_json(repository, f"{lane}/focused/logs/.keep.json", {})
    (repository / f"{lane}/focused/logs/.keep.json").unlink()
    (repository / f"{lane}/focused/logs/focused-check.log").write_text("passed\n")
    (repository / f"{lane}/focused/exits").mkdir(parents=True, exist_ok=True)
    (repository / f"{lane}/focused/exits/focused-check.exit").write_bytes(b"0\n")
    report = build_implementation_focused_report(
        repository_root=repository,
        task_contract_binding=task,
        candidate_binding=candidate,
        execution_ledger_binding=ledger,
        required_commands=required,
        observations=[{
            "role_id": "focused-check",
            "input_paths": ["plan.md"],
            "started_at": "2026-01-01T00:00:00+00:00",
            "finished_at": "2026-01-01T00:00:01+00:00",
            "log_path": "focused/logs/focused-check.log",
            "exit_path": "focused/exits/focused-check.exit",
        }],
        evidence_directory=Path(lane),
    )
    path = _write_producer_json(repository, f"{lane}/focused/report.json", report)
    return task, path


_PRODUCER_FAILURE_NODE_IDS = (
    "tests/synthetic_alpha.py::test_alpha",
    "tests/synthetic_beta.py::test_beta",
    "tests/synthetic_delta.py::test_delta",
    "tests/synthetic_epsilon.py::test_epsilon",
    "tests/synthetic_gamma.py::test_gamma",
    "tests/synthetic_zeta.py::test_zeta",
)


def _producer_raw_broad(
    repository: Path,
    *,
    failure_node_ids: tuple[str, ...] = _PRODUCER_FAILURE_NODE_IDS,
) -> dict[str, str]:
    pass_node_id = "tests/synthetic_pass.py::test_pass"
    nodes = sorted((*failure_node_ids, pass_node_id))
    raw = repository / "evidence/implementation-baseline"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "collect.log").write_text("\n".join(nodes) + "\n")
    (raw / "collect.exit").write_bytes(b"0\n")
    (raw / "collected-node-ids.txt").write_text("\n".join(nodes) + "\n")
    (raw / "pytest-rs.log").write_text(
        "".join(f"FAILED {node_id} - assertion\n" for node_id in failure_node_ids)
        + f"================ {len(failure_node_ids)} failed, 1 passed in 0.01s ================\n"
    )
    (raw / "pytest.exit").write_bytes(b"1\n")
    (raw / "pytest.junit.xml").write_text(
        f'<testsuite tests="{len(nodes)}" failures="{len(failure_node_ids)}" errors="0" skipped="0">'
        + "".join(
            f'<testcase file="{node_id.partition("::")[0]}" '
            f'name="{node_id.partition("::")[2]}"><failure>'
            f'{repository}/source.py failed for {node_id}'
            '</failure></testcase>'
            for node_id in failure_node_ids
        )
        + '<testcase file="tests/synthetic_pass.py" name="test_pass"/>'
        + '</testsuite>\n'
    )
    with pytest.MonkeyPatch.context() as preflight_environment:
        preflight_environment.delenv("PYTEST_DEBUG_TEMPROOT", raising=False)
        preflight = build_pytest_temp_root_preflight(
            Path(sys.executable).with_name("pytest")
        )
    _write_producer_json(repository, "evidence/implementation-baseline/pytest-temp-root-preflight.json", preflight)
    return {
        "collection_log_path": "evidence/implementation-baseline/collect.log",
        "collection_exit_path": "evidence/implementation-baseline/collect.exit",
        "collected_node_ids_path": "evidence/implementation-baseline/collected-node-ids.txt",
        "rs_log_path": "evidence/implementation-baseline/pytest-rs.log",
        "broad_exit_path": "evidence/implementation-baseline/pytest.exit",
        "junit_path": "evidence/implementation-baseline/pytest.junit.xml",
        "pytest_temp_root_preflight_path": "evidence/implementation-baseline/pytest-temp-root-preflight.json",
    }


def test_producer_raw_broad_uses_declared_null_temp_root_and_restores_ambient(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ambient_root = tmp_path / "ambient-non-null-pytest-temp-root"
    ambient_root.mkdir()
    monkeypatch.setenv("PYTEST_DEBUG_TEMPROOT", str(ambient_root))

    paths = _producer_raw_broad(tmp_path)

    assert os.environ["PYTEST_DEBUG_TEMPROOT"] == str(ambient_root)
    preflight = load_json_closed(
        tmp_path / paths["pytest_temp_root_preflight_path"]
    )
    assert preflight["environment_binding"] == {
        "PYTEST_DEBUG_TEMPROOT": None
    }
    assert validate_record(preflight) == []


def _producer_broad_builder_inputs(
    repository: Path,
    candidate: dict[str, object],
    ledger: dict[str, object],
) -> dict[str, object]:
    root_digest = canonical_sha256([])
    return {
        "repository_root": repository,
        "candidate_binding": candidate,
        "execution_ledger_binding": ledger,
        "collection_argv": ["pytest", "--collect-only", "-q"],
        "broad_argv": ["pytest", "-q"],
        "environment": {
            "LC_ALL": "C.UTF-8",
            "PYTHONHASHSEED": "0",
            "PYTEST_DEBUG_TEMPROOT": None,
        },
        "run_root_snapshots": [
            {
                "root_path": (repository / "runs").as_posix(),
                "root_path_sha256": canonical_sha256(
                    (repository / "runs").as_posix()
                ),
                "scope_basis": "planning_candidate",
                "before_snapshot_sha256": root_digest,
                "after_snapshot_sha256": root_digest,
            }
        ],
        **_producer_raw_broad(repository),
    }


_REAL_BARE_SUMMARY = (
    "6 failed, 6418 passed, 17 skipped, 33 warnings "
    "in 137.23s (0:02:17)"
)


def _write_real_bare_summary_raw_set(
    repository: Path, paths: dict[str, object]
) -> None:
    nodes = [
        f"tests/generated.py::test_{index:04d}" for index in range(6441)
    ]
    failed = set(nodes[:6])
    skipped = set(nodes[6:23])
    node_bytes = ("\n".join(nodes) + "\n").encode()
    (repository / str(paths["collection_log_path"])).write_bytes(node_bytes)
    (repository / str(paths["collected_node_ids_path"])).write_bytes(
        node_bytes
    )

    def testcase(node_id: str) -> str:
        name = node_id.partition("::")[2]
        if node_id in failed:
            payload = "<failure>assertion</failure>"
        elif node_id in skipped:
            payload = "<skipped>grouped reason</skipped>"
        else:
            payload = ""
        return (
            f'<testcase file="tests/generated.py" name="{name}">'
            f"{payload}</testcase>"
        )

    junit = (
        '<testsuite tests="6441" failures="6" errors="0" skipped="17">'
        + "".join(testcase(node_id) for node_id in nodes)
        + "</testsuite>\n"
    )
    (repository / str(paths["junit_path"])).write_text(junit)
    (repository / str(paths["rs_log_path"])).write_text(
        _REAL_BARE_SUMMARY + "\n"
    )


def test_broad_builder_and_bound_outcome_accept_exact_real_bare_summary(
    tmp_path: Path,
) -> None:
    candidate, ledger = _producer_candidate_and_ledger(tmp_path)
    inputs = _producer_broad_builder_inputs(tmp_path, candidate, ledger)
    _write_real_bare_summary_raw_set(tmp_path, inputs)

    outcome = build_broad_outcome(**inputs)

    assert outcome["outcomes"]["totals"] == {
        "collected": 6441,
        "passed": 6418,
        "failed": 6,
        "errors": 0,
        "skipped": 17,
    }
    assert validate_bound_record(outcome, tmp_path) == []


def test_bound_bootstrap_subject_accepts_exact_real_bare_summary(
    tmp_path: Path,
) -> None:
    candidate, ledger, bootstrap = (
        _producer_task1_candidate_ledger_and_bootstrap(tmp_path)
    )
    task, focused_path = _producer_focused_report(tmp_path, candidate, ledger)
    raw_paths = _producer_raw_broad(tmp_path)
    _write_real_bare_summary_raw_set(tmp_path, raw_paths)
    baseline_path = _write_producer_json(
        tmp_path,
        "evidence/implementation-baseline/bootstrap-workspace-baseline.json",
        bootstrap,
    )

    subject = broad_evidence.build_broad_evidence_bootstrap_subject(
        repository_root=tmp_path,
        subject_path=Path(
            "evidence/implementation-commits/task-01-bootstrap/subject.json"
        ),
        task_contract_binding=task,
        candidate_binding=candidate,
        execution_ledger_binding=ledger,
        bootstrap_workspace_baseline_path=baseline_path.relative_to(tmp_path),
        focused_report_path=focused_path.relative_to(tmp_path),
        collection_argv=["pytest", "--collect-only", "-q"],
        environment={
            "LC_ALL": "C.UTF-8",
            "PYTHONHASHSEED": "0",
            "PYTEST_DEBUG_TEMPROOT": None,
        },
        **raw_paths,
    )

    assert subject["observed_totals"] == {
        "collected": 6441,
        "passed": 6418,
        "failed": 6,
        "errors": 0,
        "skipped": 17,
    }
    assert validate_bound_record(subject, tmp_path) == []


def test_broad_builder_accepts_terminal_summary_wall_clock_suffix(
    tmp_path: Path,
) -> None:
    candidate, ledger = _producer_candidate_and_ledger(tmp_path)
    inputs = _producer_broad_builder_inputs(tmp_path, candidate, ledger)
    raw_log = tmp_path / inputs["rs_log_path"]
    raw_log.write_text(
        raw_log.read_text().replace(
            "6 failed, 1 passed in 0.01s",
            "6 failed, 1 passed, 33 warnings in 137.23s (0:02:17)",
        )
    )

    outcome = build_broad_outcome(**inputs)

    assert outcome["outcomes"]["totals"] == {
        "collected": 7,
        "passed": 1,
        "failed": 6,
        "errors": 0,
        "skipped": 0,
    }
    assert validate_bound_record(outcome, tmp_path) == []


def test_broad_builder_accepts_grouped_skips_and_abbreviated_failure_log(
    tmp_path: Path,
) -> None:
    candidate, ledger = _producer_candidate_and_ledger(tmp_path)
    inputs = _producer_broad_builder_inputs(tmp_path, candidate, ledger)
    failed = _PRODUCER_FAILURE_NODE_IDS[0]
    skipped = _PRODUCER_FAILURE_NODE_IDS[1:]
    passed = "tests/synthetic_pass.py::test_pass"

    def testcase(node_id: str, outcome: str) -> str:
        path, _, name = node_id.partition("::")
        payload = {
            "failed": "<failure>assertion</failure>",
            "skipped": "<skipped>grouped reason</skipped>",
            "passed": "",
        }[outcome]
        return f'<testcase file="{path}" name="{name}">{payload}</testcase>'

    junit = (
        '<testsuite tests="7" failures="1" errors="0" skipped="5">'
        + testcase(failed, "failed")
        + "".join(testcase(node_id, "skipped") for node_id in skipped)
        + testcase(passed, "passed")
        + "</testsuite>\n"
    )
    (tmp_path / inputs["junit_path"]).write_text(junit)
    raw_log = (
        "Fsssss. [100%]\n"
        "FAILED synthetic_alpha - assertion\n"
        "SKIPPED [5] grouped synthetic skip reason\n"
        "================ 1 failed, 1 passed, 5 skipped in 0.02s ================\n"
    )
    assert failed not in raw_log
    assert all(node_id not in raw_log for node_id in skipped)
    (tmp_path / inputs["rs_log_path"]).write_text(raw_log)

    outcome = build_broad_outcome(**inputs)

    assert [row["node_id"] for row in outcome["outcomes"]["failures"]] == [
        failed
    ]
    assert outcome["outcomes"]["skipped_node_ids"] == list(skipped)
    assert validate_bound_record(outcome, tmp_path) == []


@pytest.mark.parametrize(
    "defect",
    [
        "mismatched",
        "duplicate",
        "malformed",
        "empty",
        "trailing",
        "open_only",
        "close_only",
    ],
)
def test_broad_builder_rejects_nonexact_terminal_summary(
    tmp_path: Path, defect: str
) -> None:
    candidate, ledger = _producer_candidate_and_ledger(tmp_path)
    inputs = _producer_broad_builder_inputs(tmp_path, candidate, ledger)
    raw_log = tmp_path / inputs["rs_log_path"]
    text = raw_log.read_text()
    if defect == "mismatched":
        text = text.replace("6 failed", "5 failed")
    elif defect == "duplicate":
        text += text.splitlines(keepends=True)[-1]
    elif defect == "malformed":
        text = text.replace("in 0.01s", "in 0..01s")
    elif defect == "empty":
        text = " \n\t"
    elif defect == "trailing":
        text += "trailing non-summary output\n"
    elif defect == "open_only":
        text = text.replace(
            " in 0.01s ================\n", " in 0.01s\n"
        )
    else:
        text = text.replace(
            "================ 6 failed", "6 failed"
        )
    raw_log.write_text(text)

    with pytest.raises(ContractError, match="rs_log_outcome_mismatch"):
        build_broad_outcome(**inputs)


@pytest.mark.parametrize("defect", ["junit_identity", "collection_partition"])
def test_broad_builder_keeps_junit_collection_identity_fail_closed(
    tmp_path: Path, defect: str
) -> None:
    candidate, ledger = _producer_candidate_and_ledger(tmp_path)
    inputs = _producer_broad_builder_inputs(tmp_path, candidate, ledger)
    if defect == "junit_identity":
        junit = tmp_path / inputs["junit_path"]
        junit.write_text(junit.read_text().replace("test_alpha", "test_missing"))
    else:
        removed = _PRODUCER_FAILURE_NODE_IDS[0]
        remaining = [
            node
            for node in (tmp_path / inputs["collected_node_ids_path"])
            .read_text()
            .splitlines()
            if node != removed
        ]
        content = "\n".join(remaining) + "\n"
        (tmp_path / inputs["collected_node_ids_path"]).write_text(content)
        (tmp_path / inputs["collection_log_path"]).write_text(content)

    with pytest.raises(ContractError, match="junit_"):
        build_broad_outcome(**inputs)


@pytest.mark.parametrize("consumer", ["broad_outcome", "bootstrap_subject"])
@pytest.mark.parametrize("defect", ["empty", "trailing"])
def test_bound_raw_log_consumers_reject_empty_or_trailing_summary(
    tmp_path: Path, consumer: str, defect: str
) -> None:
    if consumer == "broad_outcome":
        candidate, ledger = _producer_candidate_and_ledger(tmp_path)
        inputs = _producer_broad_builder_inputs(tmp_path, candidate, ledger)
        record = build_broad_outcome(**inputs)
        raw_binding = record["rs_log"]
        digest_field = "normalized_outcome_sha256"
    else:
        candidate, ledger, bootstrap = (
            _producer_task1_candidate_ledger_and_bootstrap(tmp_path)
        )
        task, focused_path = _producer_focused_report(
            tmp_path, candidate, ledger
        )
        raw_paths = _producer_raw_broad(tmp_path)
        baseline_path = _write_producer_json(
            tmp_path,
            "evidence/implementation-baseline/bootstrap-workspace-baseline.json",
            bootstrap,
        )
        record = broad_evidence.build_broad_evidence_bootstrap_subject(
            repository_root=tmp_path,
            subject_path=Path(
                "evidence/implementation-commits/task-01-bootstrap/subject.json"
            ),
            task_contract_binding=task,
            candidate_binding=candidate,
            execution_ledger_binding=ledger,
            bootstrap_workspace_baseline_path=baseline_path.relative_to(
                tmp_path
            ),
            focused_report_path=focused_path.relative_to(tmp_path),
            collection_argv=["pytest", "--collect-only", "-q"],
            environment={
                "LC_ALL": "C.UTF-8",
                "PYTHONHASHSEED": "0",
                "PYTEST_DEBUG_TEMPROOT": None,
            },
            **raw_paths,
        )
        raw_binding = next(
            row
            for row in record["raw_broad_bindings"]
            if row["role_id"] == "broad-rs-log"
        )
        digest_field = "normalized_subject_sha256"
    assert validate_bound_record(record, tmp_path) == []

    raw_log = tmp_path / raw_binding["path"]
    replacement = (
        b" \n\t"
        if defect == "empty"
        else raw_log.read_bytes() + b"trailing non-summary output\n"
    )
    raw_log.write_bytes(replacement)
    raw_binding["sha256"] = file_sha256(raw_log)
    if "size" in raw_binding:
        raw_binding["size"] = len(replacement)
    if consumer == "bootstrap_subject":
        manifest_row = next(
            row
            for row in record["candidate_path_manifest"]
            if row["path"] == raw_binding["path"]
        )
        manifest_row["sha256"] = raw_binding["sha256"]
        manifest_row["size"] = len(replacement)
    record[digest_field] = canonical_sha256(
        record, exclude={digest_field}
    )

    assert broad_evidence.Issue(
        "rs_log_outcome_mismatch"
    ) in validate_bound_record(record, tmp_path)


def _publish_producer_review_pair(
    repository: Path,
    *,
    evidence_root: Path,
    subject_path: Path,
    subject_kind: str,
    specification_name: str,
    quality_name: str,
    specification_reviewed_at: str = "2026-01-01T00:00:00+00:00",
    quality_reviewed_at: str = "2026-01-01T00:00:00+00:00",
    prior_review_bindings: Mapping[str, dict[str, object] | None] | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    bindings = []
    for review_kind, name, reviewed_at in (
        ("specification", specification_name, specification_reviewed_at),
        ("code_quality", quality_name, quality_reviewed_at),
    ):
        review_path = evidence_root / name
        review = {
            "schema_version": "review.v1",
            "review_kind": review_kind,
            "reviewer": {"identity": f"{review_kind}-reviewer"},
            "reviewed_at": reviewed_at,
            "subject": {
                "kind": subject_kind,
                "path": subject_path.as_posix(),
                "sha256": file_sha256(repository / subject_path),
            },
            "result": "approved",
            "issues": [],
            "claims_not_made": ["Synthetic approval for producer integration testing."],
        }
        _write_producer_json(repository, review_path.as_posix(), review)
        bindings.append(
            publish_immutable_review(
                repository_root=repository,
                evidence_root=evidence_root,
                subject_path=subject_path,
                review_path=review_path,
                prior_review_binding=(prior_review_bindings or {}).get(
                    review_kind
                ),
            )
        )
    return bindings[0], bindings[1]


def test_producers_create_bound_outcome_baseline_and_subject(tmp_path: Path) -> None:
    candidate, ledger = _producer_candidate_and_ledger(tmp_path)
    task, focused_path = _producer_focused_report(tmp_path, candidate, ledger)
    raw_paths = _producer_raw_broad(tmp_path)
    environment = {
        "LC_ALL": "C.UTF-8",
        "PYTHONHASHSEED": "0",
        "PYTEST_DEBUG_TEMPROOT": None,
    }
    snapshot_digest = canonical_sha256([])
    outcome = build_broad_outcome(
        repository_root=tmp_path,
        candidate_binding=candidate,
        execution_ledger_binding=ledger,
        collection_argv=["pytest", "--collect-only", "-q"],
        broad_argv=["pytest", "-q", "-rs", "-n", "16", "--dist=worksteal"],
        environment=environment,
        run_root_snapshots=[{
            "root_path": (tmp_path / "runs").as_posix(),
            "root_path_sha256": canonical_sha256((tmp_path / "runs").as_posix()),
            "scope_basis": "planning_candidate",
            "before_snapshot_sha256": snapshot_digest,
            "after_snapshot_sha256": snapshot_digest,
        }],
        **raw_paths,
    )
    outcome_path = _write_producer_json(tmp_path, "evidence/implementation-baseline/outcome.json", outcome)
    assert validate_bound_record(outcome, tmp_path) == []

    ownership_classifications = [
        {
            "node_id": node_id,
            "ownership_class": "queue_owned",
            "ownership_basis": ["source.py"],
            "authorized_remediation_scope": ["source.py"],
        }
        for node_id in _PRODUCER_FAILURE_NODE_IDS
    ]
    baseline = build_broad_known_failure_baseline(
        repository_root=tmp_path,
        broad_outcome_path=outcome_path.relative_to(tmp_path),
        ownership_classifications=ownership_classifications,
    )
    assert [row["node_id"] for row in baseline["failures"]] == list(
        _PRODUCER_FAILURE_NODE_IDS
    )
    assert validate_bound_record(baseline, tmp_path) == []
    wrong_outcome_path = _write_producer_json(
        tmp_path, "evidence/different-directory/not-outcome.json", outcome
    )
    wrong_outcome_baseline = deepcopy(baseline)
    wrong_outcome_baseline["broad_outcome_binding"] = {
        "path": wrong_outcome_path.relative_to(tmp_path).as_posix(),
        "sha256": file_sha256(wrong_outcome_path),
    }
    assert "baseline_outcome_path_invalid" in {
        issue.code for issue in validate_bound_record(wrong_outcome_baseline, tmp_path)
    }
    original_outcome_bytes = outcome_path.read_bytes()
    split_rs_log = tmp_path / "evidence/different-directory/pytest-rs.log"
    split_rs_log.write_bytes(
        (tmp_path / "evidence/implementation-baseline/pytest-rs.log").read_bytes()
    )
    split_outcome = deepcopy(outcome)
    split_outcome["rs_log"] = {
        "path": split_rs_log.relative_to(tmp_path).as_posix(),
        "sha256": file_sha256(split_rs_log),
    }
    split_outcome["normalized_outcome_sha256"] = canonical_sha256(
        split_outcome, exclude={"normalized_outcome_sha256"}
    )
    outcome_path.write_text(json.dumps(split_outcome, sort_keys=True) + "\n")
    split_baseline = deepcopy(baseline)
    split_baseline["broad_outcome_binding"]["sha256"] = file_sha256(outcome_path)
    assert "subject_evidence_directory_mismatch" in {
        issue.code for issue in validate_bound_record(split_baseline, tmp_path)
    }
    outcome_path.write_bytes(original_outcome_bytes)
    baseline_path = _write_producer_json(
        tmp_path, "evidence/implementation-baseline/known-failure-baseline.json", baseline
    )
    specification, quality = _publish_producer_review_pair(
        tmp_path,
        evidence_root=Path("evidence/implementation-baseline"),
        subject_path=baseline_path.relative_to(tmp_path),
        subject_kind="implementation_failure_baseline",
        specification_name="implementation-baseline-specification.json",
        quality_name="implementation-baseline-quality.json",
    )
    attestation = {
        "schema_version": "broad_failure_baseline_attestation.v1",
        "evidence_status": "owner_confirmed",
        "baseline_binding": {
            "path": baseline_path.relative_to(tmp_path).as_posix(),
            "sha256": file_sha256(baseline_path),
            "schema_version": "broad_known_failure_baseline.v1",
            "candidate_path_set_sha256": candidate["candidate_path_set_sha256"],
        },
        "failure_set_binding": {
            "failure_count": len(baseline["failures"]),
            "normalized_failure_set_sha256": baseline[
                "normalized_failure_set_sha256"
            ],
        },
        "normalization_binding": {
            "schema_version": "broad_failure_payload_normalization.v1",
            "normalized_contract_sha256": baseline["failure_normalization"][
                "normalized_contract_sha256"
            ],
        },
        "classification_summary": baseline["classification_summary"],
        "specification_review_binding": specification,
        "quality_review_binding": quality,
        "prepared_by": {"identity": "fixture-writer"},
        "prepared_at": "2026-01-01T00:00:00+00:00",
        "owner": {"identity": "Fixture Owner", "role": "owner"},
        "owner_confirmations": {
            "exact_failure_table_confirmed": True,
            "normalization_contract_confirmed": True,
            "classification_partition_confirmed": True,
            "reviews_confirmed": True,
            "comparison_only_confirmed": True,
            "no_out_of_scope_repair_confirmed": True,
            "confirmed_at": "2026-01-01T00:00:00+00:00",
        },
        "owner_adoption": {
            "identity": "Fixture Owner",
            "adopted_at": "2026-01-01T00:00:00+00:00",
            "statement": "I personally adopt this exact baseline for comparison only.",
        },
        "claims_not_made": ["Synthetic owner-confirmed integration record."],
    }
    attestation_path = _write_producer_json(
        tmp_path,
        "evidence/implementation-baseline/attestations/broad-failure-baseline.json",
        attestation,
    )
    assert validate_bound_record(attestation, tmp_path) == []
    baseline_authority = {
        "outcome": {
            "path": outcome_path.relative_to(tmp_path).as_posix(),
            "sha256": file_sha256(outcome_path),
        },
        "record": {
            "path": baseline_path.relative_to(tmp_path).as_posix(),
            "sha256": file_sha256(baseline_path),
        },
        "specification_review": specification,
        "quality_review": quality,
        "owner_attestation": {
            "path": attestation_path.relative_to(tmp_path).as_posix(),
            "sha256": file_sha256(attestation_path),
        },
    }
    comparison, lifecycle = broad_evidence.derive_broad_baseline_comparison(
        repository_root=tmp_path,
        known_failure_baseline_binding=baseline_authority,
        approved_remediation_bindings=[],
        approved_skip_change_bindings=[],
        failure_normalization=outcome["failure_normalization"],
        observed_failures=outcome["outcomes"]["failures"],
        observed_skipped_node_ids=outcome["outcomes"]["skipped_node_ids"],
    )
    assert lifecycle == "known_failures_matched"
    assert comparison["removed_failure_node_ids"] == []
    later = deepcopy(outcome)
    later["known_failure_baseline_binding"] = baseline_authority
    later["baseline_comparison"] = comparison
    later["outcomes"]["outcome"] = lifecycle
    later["normalized_outcome_sha256"] = canonical_sha256(
        later, exclude={"normalized_outcome_sha256"}
    )
    assert validate_bound_record(later, tmp_path) == []
    tampered_comparison = deepcopy(later)
    tampered_comparison["baseline_comparison"][
        "baseline_failure_set_sha256"
    ] = canonical_sha256([])
    tampered_comparison["normalized_outcome_sha256"] = canonical_sha256(
        tampered_comparison, exclude={"normalized_outcome_sha256"}
    )
    assert "baseline_comparison_authority_mismatch" in {
        issue.code for issue in validate_bound_record(tampered_comparison, tmp_path)
    }
    task_scope_path = _write_producer_json(
        tmp_path, "evidence/remediation/task-scope.json", {"scope": "source.py"}
    )
    remediation = {
        "schema_version": "broad_failure_remediation.v1",
        "execution_ledger_binding": ledger,
        "candidate_binding": candidate,
        "task_scope_binding": {
            "path": task_scope_path.relative_to(tmp_path).as_posix(),
            "sha256": file_sha256(task_scope_path),
        },
        "baseline_binding": baseline_authority["record"],
        "removed_failure_rows": baseline["failures"],
        "production_diff": candidate["candidate_paths"],
        "focused_regression_evidence": {
            "path": focused_path.relative_to(tmp_path).as_posix(),
            "sha256": file_sha256(focused_path),
        },
        "normalized_remediation_sha256": "",
        "claims_not_made": ["Synthetic reviewed remediation integration record."],
    }
    remediation["normalized_remediation_sha256"] = canonical_sha256(
        remediation, exclude={"normalized_remediation_sha256"}
    )
    remediation_path = _write_producer_json(
        tmp_path, "evidence/remediation/failure-remediation.json", remediation
    )
    assert validate_bound_record(remediation, tmp_path) == []
    remediation_specification, remediation_quality = _publish_producer_review_pair(
        tmp_path,
        evidence_root=Path("evidence/remediation"),
        subject_path=remediation_path.relative_to(tmp_path),
        subject_kind="broad_failure_remediation",
        specification_name="remediation-specification-review.json",
        quality_name="remediation-quality-review.json",
    )
    reviewed_remediation = {
        "record": {
            "path": remediation_path.relative_to(tmp_path).as_posix(),
            "sha256": file_sha256(remediation_path),
        },
        "specification_review": remediation_specification,
        "quality_review": remediation_quality,
    }
    subset_comparison, subset_lifecycle = (
        broad_evidence.derive_broad_baseline_comparison(
            repository_root=tmp_path,
            known_failure_baseline_binding=baseline_authority,
            approved_remediation_bindings=[reviewed_remediation],
            approved_skip_change_bindings=[],
            failure_normalization=outcome["failure_normalization"],
            observed_failures=[],
            observed_skipped_node_ids=[],
        )
    )
    assert subset_lifecycle == "approved_failure_subset"
    assert subset_comparison["removed_failure_node_ids"] == list(
        _PRODUCER_FAILURE_NODE_IDS
    )
    with pytest.raises(ContractError, match="observed_failure_authority_mismatch"):
        broad_evidence.derive_broad_baseline_comparison(
            repository_root=tmp_path,
            known_failure_baseline_binding=baseline_authority,
            approved_remediation_bindings=[],
            approved_skip_change_bindings=[],
            failure_normalization=outcome["failure_normalization"],
            observed_failures=[],
            observed_skipped_node_ids=[],
        )
    with pytest.raises(ContractError, match="observed_failure_authority_mismatch"):
        broad_evidence.derive_broad_baseline_comparison(
            repository_root=tmp_path,
            known_failure_baseline_binding=baseline_authority,
            approved_remediation_bindings=[reviewed_remediation],
            approved_skip_change_bindings=[],
            failure_normalization=outcome["failure_normalization"],
            observed_failures=outcome["outcomes"]["failures"],
            observed_skipped_node_ids=[],
        )
    added_skip = ["tests/synthetic_pass.py::test_pass"]
    skip_change = {
        "schema_version": "broad_skip_change.v1",
        "execution_ledger_binding": ledger,
        "candidate_binding": candidate,
        "predecessor_skip_set_binding": {
            "path": outcome_path.relative_to(tmp_path).as_posix(),
            "sha256": file_sha256(outcome_path),
            "skip_node_ids": [],
            "skip_set_sha256": canonical_sha256([]),
        },
        "added_skip_node_ids": added_skip,
        "removed_skip_node_ids": [],
        "authorized_diff": candidate["candidate_paths"],
        "focused_regression_evidence": {
            "path": focused_path.relative_to(tmp_path).as_posix(),
            "sha256": file_sha256(focused_path),
        },
        "resulting_skip_set_sha256": canonical_sha256(added_skip),
        "normalized_skip_change_sha256": "",
        "claims_not_made": ["Synthetic reviewed skip integration record."],
    }
    skip_change["normalized_skip_change_sha256"] = canonical_sha256(
        skip_change, exclude={"normalized_skip_change_sha256"}
    )
    skip_path = _write_producer_json(
        tmp_path, "evidence/skip/skip-change.json", skip_change
    )
    assert validate_bound_record(skip_change, tmp_path) == []
    skip_specification, skip_quality = _publish_producer_review_pair(
        tmp_path,
        evidence_root=Path("evidence/skip"),
        subject_path=skip_path.relative_to(tmp_path),
        subject_kind="broad_skip_change",
        specification_name="skip-change-specification-review.json",
        quality_name="skip-change-quality-review.json",
    )
    reviewed_skip = {
        "record": {
            "path": skip_path.relative_to(tmp_path).as_posix(),
            "sha256": file_sha256(skip_path),
        },
        "specification_review": skip_specification,
        "quality_review": skip_quality,
    }
    skip_comparison, _ = broad_evidence.derive_broad_baseline_comparison(
        repository_root=tmp_path,
        known_failure_baseline_binding=baseline_authority,
        approved_remediation_bindings=[],
        approved_skip_change_bindings=[reviewed_skip],
        failure_normalization=outcome["failure_normalization"],
        observed_failures=outcome["outcomes"]["failures"],
        observed_skipped_node_ids=added_skip,
    )
    assert skip_comparison["predecessor_skip_set_sha256"] == canonical_sha256([])
    assert skip_comparison["observed_skip_set_sha256"] == canonical_sha256(
        added_skip
    )
    with pytest.raises(ContractError, match="observed_skip_authority_mismatch"):
        broad_evidence.derive_broad_baseline_comparison(
            repository_root=tmp_path,
            known_failure_baseline_binding=baseline_authority,
            approved_remediation_bindings=[],
            approved_skip_change_bindings=[reviewed_skip],
            failure_normalization=outcome["failure_normalization"],
            observed_failures=outcome["outcomes"]["failures"],
            observed_skipped_node_ids=[],
        )

    subject = build_implementation_verification_subject(
        repository_root=tmp_path,
        task_contract_binding=task,
        candidate_binding=candidate,
        execution_ledger_binding=ledger,
        focused_report_path=focused_path.relative_to(tmp_path),
        broad_outcome_path=outcome_path.relative_to(tmp_path),
    )
    assert validate_bound_record(subject, tmp_path) == []
    manifest_paths = {row["path"] for row in subject["candidate_path_manifest"]}
    assert {
        "source.py",
        "evidence/implementation-baseline/focused/report.json",
        "evidence/implementation-baseline/outcome.json",
        "evidence/implementation-baseline/pytest.junit.xml",
        ledger["request_path"],
    } <= manifest_paths

    wrong_task = deepcopy(task)
    wrong_task["task_number"] = 2
    with pytest.raises(ContractError, match="subject_ledger_task_join_invalid"):
        build_implementation_verification_subject(
            repository_root=tmp_path,
            task_contract_binding=wrong_task,
            candidate_binding=candidate,
            execution_ledger_binding=ledger,
            focused_report_path=focused_path.relative_to(tmp_path),
            broad_outcome_path=outcome_path.relative_to(tmp_path),
        )

    assert "baseline_comparison" not in inspect.signature(build_broad_outcome).parameters
    displaced = tmp_path / "evidence/other/outcome.json"
    displaced.parent.mkdir(parents=True)
    displaced.write_bytes(outcome_path.read_bytes())
    with pytest.raises(ContractError, match="subject_evidence_directory_mismatch"):
        build_implementation_verification_subject(
            repository_root=tmp_path,
            task_contract_binding=task,
            candidate_binding=candidate,
            execution_ledger_binding=ledger,
            focused_report_path=focused_path.relative_to(tmp_path),
            broad_outcome_path=displaced.relative_to(tmp_path),
        )
    displaced_subject = deepcopy(subject)
    displaced_subject["broad_outcome_binding"]["path"] = "evidence/other/outcome.json"
    manifest_row = next(
        row
        for row in displaced_subject["candidate_path_manifest"]
        if row["path"] == "evidence/implementation-baseline/outcome.json"
    )
    manifest_row["path"] = "evidence/other/outcome.json"
    displaced_subject["candidate_path_manifest"] = sorted(
        displaced_subject["candidate_path_manifest"], key=lambda row: row["path"]
    )
    displaced_subject["normalized_subject_sha256"] = canonical_sha256(
        displaced_subject, exclude={"normalized_subject_sha256"}
    )
    assert "subject_evidence_directory_mismatch" in {
        issue.code for issue in validate_bound_record(displaced_subject, tmp_path)
    }

    task_mismatch_subject = deepcopy(subject)
    task_mismatch_subject["task_contract_binding"]["task_number"] = 2
    task_mismatch_subject["normalized_subject_sha256"] = canonical_sha256(
        task_mismatch_subject, exclude={"normalized_subject_sha256"}
    )
    assert "subject_ledger_task_join_mismatch" in {
        issue.code for issue in validate_bound_record(task_mismatch_subject, tmp_path)
    }
    (tmp_path / "evidence/implementation-baseline/pytest.junit.xml").write_text("<tampered/>\n")
    with pytest.raises(ContractError, match="broad_outcome_invalid"):
        build_implementation_verification_subject(
            repository_root=tmp_path,
            task_contract_binding=task,
            candidate_binding=candidate,
            execution_ledger_binding=ledger,
            focused_report_path=focused_path.relative_to(tmp_path),
            broad_outcome_path=outcome_path.relative_to(tmp_path),
        )


def test_baseline_builder_rejects_missing_and_extra_classifications(tmp_path: Path) -> None:
    candidate, ledger = _producer_candidate_and_ledger(tmp_path)
    _producer_focused_report(tmp_path, candidate, ledger)
    raw_paths = _producer_raw_broad(tmp_path)
    split_log = tmp_path / "evidence/different-directory/pytest-rs.log"
    split_log.parent.mkdir(parents=True)
    split_log.write_bytes((tmp_path / raw_paths["rs_log_path"]).read_bytes())
    split_raw_paths = {**raw_paths, "rs_log_path": split_log.relative_to(tmp_path).as_posix()}
    digest = canonical_sha256([])
    with pytest.raises(ContractError, match="broad_evidence_directory_mismatch"):
        build_broad_outcome(
            repository_root=tmp_path,
            candidate_binding=candidate,
            execution_ledger_binding=ledger,
            collection_argv=["pytest", "--collect-only", "-q"],
            broad_argv=["pytest", "-q"],
            environment={"LC_ALL": "C.UTF-8", "PYTHONHASHSEED": "0", "PYTEST_DEBUG_TEMPROOT": None},
            run_root_snapshots=[{
                "root_path": (tmp_path / "runs").as_posix(),
                "root_path_sha256": canonical_sha256((tmp_path / "runs").as_posix()),
                "scope_basis": "planning_candidate",
                "before_snapshot_sha256": digest,
                "after_snapshot_sha256": digest,
            }],
            **split_raw_paths,
        )
    outcome = build_broad_outcome(
        repository_root=tmp_path,
        candidate_binding=candidate,
        execution_ledger_binding=ledger,
        collection_argv=["pytest", "--collect-only", "-q"],
        broad_argv=["pytest", "-q"],
        environment={"LC_ALL": "C.UTF-8", "PYTHONHASHSEED": "0", "PYTEST_DEBUG_TEMPROOT": None},
        run_root_snapshots=[{
            "root_path": (tmp_path / "runs").as_posix(),
            "root_path_sha256": canonical_sha256((tmp_path / "runs").as_posix()),
            "scope_basis": "planning_candidate",
            "before_snapshot_sha256": digest,
            "after_snapshot_sha256": digest,
        }],
        **raw_paths,
    )
    outcome_path = _write_producer_json(tmp_path, "evidence/implementation-baseline/outcome.json", outcome)
    displaced_outcome = _write_producer_json(
        tmp_path, "evidence/different-directory/not-outcome.json", outcome
    )
    with pytest.raises(ContractError, match="baseline_outcome_path_invalid"):
        build_broad_known_failure_baseline(
            repository_root=tmp_path,
            broad_outcome_path=displaced_outcome.relative_to(tmp_path),
            ownership_classifications=[{
                "node_id": "tests/example.py::test_failure",
                "ownership_class": "queue_owned",
                "ownership_basis": ["source.py"],
                "authorized_remediation_scope": ["source.py"],
            }],
        )

    with pytest.raises(ContractError, match="ownership_classification_partition_invalid"):
        build_broad_known_failure_baseline(
            repository_root=tmp_path,
            broad_outcome_path=outcome_path.relative_to(tmp_path),
            ownership_classifications=[],
        )
    with pytest.raises(ContractError, match="ownership_classification_partition_invalid"):
        build_broad_known_failure_baseline(
            repository_root=tmp_path,
            broad_outcome_path=outcome_path.relative_to(tmp_path),
            ownership_classifications=[{
                "node_id": "tests/example.py::test_extra",
                "ownership_class": "external",
                "ownership_basis": ["tests/example.py"],
                "authorized_remediation_scope": [],
            }],
        )


@pytest.mark.parametrize(
    "defect",
    [
        "request_record_mismatch",
        "arbitrary_snapshot_coordinate",
        "invalid_ancestry",
    ],
)
def test_broad_outcome_builder_and_validator_require_canonical_ledger_generation(
    tmp_path: Path, defect: str
) -> None:
    generation = 3 if defect == "invalid_ancestry" else 1
    candidate, ledger = _producer_candidate_and_ledger(
        tmp_path, ledger_generation=generation
    )
    inputs = _producer_broad_builder_inputs(tmp_path, candidate, ledger)
    outcome = build_broad_outcome(**inputs)
    invalid = _invalidate_ledger_binding_history(tmp_path, ledger, defect)
    outcome["execution_ledger_binding"] = invalid
    outcome["normalized_outcome_sha256"] = canonical_sha256(
        outcome, exclude={"normalized_outcome_sha256"}
    )

    assert "ledger_generation_invalid" in {
        issue.code for issue in validate_bound_record(outcome, tmp_path)
    }

    inputs["execution_ledger_binding"] = invalid
    with pytest.raises(
        ContractError,
        match="execution_ledger_binding_invalid:ledger_generation_invalid",
    ):
        build_broad_outcome(**inputs)


def test_broad_outcome_historical_ledger_binding_accepts_canonical_descendant_live(
    tmp_path: Path,
) -> None:
    candidate, ledger = _producer_candidate_and_ledger(tmp_path)
    inputs = _producer_broad_builder_inputs(tmp_path, candidate, ledger)
    outcome = build_broad_outcome(**inputs)

    _advance_bound_ledger(tmp_path, ledger)

    assert validate_bound_record(outcome, tmp_path) == []
    with pytest.raises(
        ContractError,
        match=(
            "execution_ledger_binding_invalid:ledger_generation_invalid:"
            "\\$"
        ),
    ):
        build_broad_outcome(**inputs)


def test_broad_builder_rechecks_strict_current_after_final_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate, ledger = _producer_candidate_and_ledger(tmp_path)
    inputs = _producer_broad_builder_inputs(tmp_path, candidate, ledger)
    original = broad_evidence.validate_bound_record
    advanced = False

    def validate_then_advance(
        record: object, repository_root: Path, **kwargs: object
    ) -> list[broad_evidence.Issue]:
        nonlocal advanced
        if (
            isinstance(record, dict)
            and record.get("schema_version") == "broad_outcome.v1"
            and not advanced
        ):
            advanced = True
            _advance_bound_ledger(tmp_path, ledger)
        return original(record, repository_root, **kwargs)

    monkeypatch.setattr(
        broad_evidence, "validate_bound_record", validate_then_advance
    )

    with pytest.raises(
        ContractError,
        match="broad_outcome_invalid:ledger_generation_invalid",
    ):
        build_broad_outcome(**inputs)
    assert advanced is True


def test_broad_outcome_builder_and_validator_reject_integer_ledger_generation_mismatch(
    tmp_path: Path,
) -> None:
    candidate, ledger = _producer_candidate_and_ledger(tmp_path)
    inputs = _producer_broad_builder_inputs(tmp_path, candidate, ledger)
    outcome = build_broad_outcome(**inputs)
    invalid = deepcopy(ledger)
    invalid["generation"] += 1
    outcome["execution_ledger_binding"] = invalid
    outcome["normalized_outcome_sha256"] = canonical_sha256(
        outcome, exclude={"normalized_outcome_sha256"}
    )

    assert broad_evidence.Issue(
        "ledger_generation_invalid",
        "$.execution_ledger_binding",
        "generation_binding_coordinate_invalid",
    ) in validate_bound_record(outcome, tmp_path)

    inputs["execution_ledger_binding"] = invalid
    with pytest.raises(
        ContractError,
        match="execution_ledger_binding_invalid:ledger_generation_invalid",
    ):
        build_broad_outcome(**inputs)


def test_baseline_builder_rejects_one_observed_failure(tmp_path: Path) -> None:
    candidate, ledger = _producer_candidate_and_ledger(tmp_path)
    _producer_focused_report(tmp_path, candidate, ledger)
    failure_node_id = _PRODUCER_FAILURE_NODE_IDS[0]
    raw_paths = _producer_raw_broad(
        tmp_path, failure_node_ids=(failure_node_id,)
    )
    snapshot_digest = canonical_sha256([])
    outcome = build_broad_outcome(
        repository_root=tmp_path,
        candidate_binding=candidate,
        execution_ledger_binding=ledger,
        collection_argv=["pytest", "--collect-only", "-q"],
        broad_argv=["pytest", "-q"],
        environment={
            "LC_ALL": "C.UTF-8",
            "PYTHONHASHSEED": "0",
            "PYTEST_DEBUG_TEMPROOT": None,
        },
        run_root_snapshots=[{
            "root_path": (tmp_path / "runs").as_posix(),
            "root_path_sha256": canonical_sha256((tmp_path / "runs").as_posix()),
            "scope_basis": "planning_candidate",
            "before_snapshot_sha256": snapshot_digest,
            "after_snapshot_sha256": snapshot_digest,
        }],
        **raw_paths,
    )
    outcome_path = _write_producer_json(
        tmp_path, "evidence/implementation-baseline/outcome.json", outcome
    )

    with pytest.raises(
        ContractError,
        match="broad_failure_baseline_invalid:baseline_failure_count_invalid",
    ):
        build_broad_known_failure_baseline(
            repository_root=tmp_path,
            broad_outcome_path=outcome_path.relative_to(tmp_path),
            ownership_classifications=[{
                "node_id": failure_node_id,
                "ownership_class": "queue_owned",
                "ownership_basis": ["source.py"],
                "authorized_remediation_scope": ["source.py"],
            }],
        )


def test_bootstrap_subject_builder_derives_raw_totals_and_recursive_manifest(
    tmp_path: Path,
) -> None:
    _initialize_candidate_repository(tmp_path)
    plan = tmp_path / "plan.md"
    _write_ledger_plan(plan)
    _git_output(tmp_path, "add", "--", "plan.md")
    _git_output(tmp_path, "commit", "-q", "-m", "bind plan")
    bootstrap = capture_workspace_baseline(tmp_path)
    bootstrap["schema_version"] = "bootstrap_workspace_baseline.v1"
    bootstrap["bootstrap_capture_bindings"] = {
        "producer_contract_version": "task1_first_write_capture.v1",
        "head_file_sha256": f"sha256:{'0' * 64}",
        "status_file_sha256": f"sha256:{'0' * 64}",
        "index_entries_file_sha256": f"sha256:{'0' * 64}",
        "index_file_sha256": bootstrap["index_sha256"],
        "archive_sha256": f"sha256:{'0' * 64}",
        "tar_stderr_sha256": f"sha256:{'0' * 64}",
    }
    bootstrap["raw_archive_not_persisted"] = True
    bootstrap["normalized_baseline_sha256"] = canonical_sha256(
        bootstrap, exclude={"normalized_baseline_sha256"}
    )
    ledger_record = _ledger(Path("plan.md"))
    ledger_record["plan_binding"]["sha256"] = file_sha256(plan)
    ledger_record["normalized_ledger_sha256"] = canonical_sha256(
        ledger_record, exclude={"normalized_ledger_sha256"}
    )
    receipt = materialize_transaction(
        repository_root=tmp_path,
        evidence_root=Path("evidence"),
        record_kind="execution-ledger",
        output_path=Path("evidence/execution-ledger.json"),
        generation=1,
        input_paths={"approved_plan": Path("plan.md")},
        parameters={"record": ledger_record},
    )
    ledger = {
        "live_path": receipt.output_path.as_posix(),
        "byte_sha256": receipt.output_sha256,
        "schema_version": "workflow_retirement_execution_ledger.v1",
        "generation": receipt.generation,
        "request_path": receipt.request_path.as_posix(),
        "request_sha256": receipt.request_sha256,
        "snapshot_path": receipt.snapshot_path.as_posix(),
        "snapshot_sha256": receipt.snapshot_sha256,
    }
    source = tmp_path / "source.py"
    source.write_text("candidate = True\n")
    source_row = {
        "path": "source.py",
        "sha256": file_sha256(source),
        "size": source.stat().st_size,
        "state": "added",
    }
    candidate: dict[str, object] = {
        "head": "0" * 40,
        "head_tree": "0" * 40,
        "index_sha256": "sha256:" + "0" * 64,
        "evidence_root_exclusion": "evidence",
        "candidate_paths": [source_row],
        "candidate_path_set_sha256": canonical_sha256([source_row]),
    }
    _bind_candidate_to_repository(tmp_path, candidate)
    task, focused_path = _producer_focused_report(tmp_path, candidate, ledger)
    raw_paths = _producer_raw_broad(tmp_path)
    baseline_path = _write_producer_json(
        tmp_path, "evidence/implementation-baseline/bootstrap-workspace-baseline.json", bootstrap
    )
    subject = broad_evidence.build_broad_evidence_bootstrap_subject(
        repository_root=tmp_path,
        subject_path=Path(
            "evidence/implementation-commits/task-01-bootstrap/subject.json"
        ),
        task_contract_binding=task,
        candidate_binding=candidate,
        execution_ledger_binding=ledger,
        bootstrap_workspace_baseline_path=baseline_path.relative_to(tmp_path),
        focused_report_path=focused_path.relative_to(tmp_path),
        collection_argv=["pytest", "--collect-only", "-q"],
        environment={
            "LC_ALL": "C.UTF-8",
            "PYTHONHASHSEED": "0",
            "PYTEST_DEBUG_TEMPROOT": None,
        },
        **raw_paths,
    )

    assert subject["observed_totals"] == {
        "collected": 7,
        "passed": 1,
        "failed": 6,
        "errors": 0,
        "skipped": 0,
    }
    assert subject["observed_failed_node_ids"] == list(_PRODUCER_FAILURE_NODE_IDS)
    assert validate_bound_record(subject, tmp_path) == []
    assert {
        "source.py",
        "evidence/implementation-baseline/bootstrap-workspace-baseline.json",
        "evidence/implementation-baseline/focused/report.json",
        "evidence/implementation-baseline/pytest.junit.xml",
        ledger["snapshot_path"],
    } <= {row["path"] for row in subject["candidate_path_manifest"]}

    five_failure_paths = _producer_raw_broad(
        tmp_path, failure_node_ids=_PRODUCER_FAILURE_NODE_IDS[:-1]
    )
    with pytest.raises(
        ContractError,
        match="bootstrap_subject_invalid:observed_failure_count_invalid",
    ):
        broad_evidence.build_broad_evidence_bootstrap_subject(
            repository_root=tmp_path,
            subject_path=Path(
                "evidence/implementation-commits/task-01-bootstrap/subject.json"
            ),
            task_contract_binding=task,
            candidate_binding=candidate,
            execution_ledger_binding=ledger,
            bootstrap_workspace_baseline_path=baseline_path.relative_to(tmp_path),
            focused_report_path=focused_path.relative_to(tmp_path),
            collection_argv=["pytest", "--collect-only", "-q"],
            environment={
                "LC_ALL": "C.UTF-8",
                "PYTHONHASHSEED": "0",
                "PYTEST_DEBUG_TEMPROOT": None,
            },
            **five_failure_paths,
        )


def _initialize_candidate_repository(repository: Path) -> None:
    _git_output(repository, "init", "-q")
    _git_output(repository, "config", "user.email", "fixture@example.invalid")
    _git_output(repository, "config", "user.name", "Fixture")
    _git_output(repository, "commit", "-q", "--allow-empty", "-m", "baseline")


def _bind_candidate_to_repository(
    repository: Path, binding: dict[str, object]
) -> None:
    binding["head"] = _git_output(repository, "rev-parse", "HEAD").decode().strip()
    binding["head_tree"] = _git_output(
        repository, "rev-parse", "HEAD^{tree}"
    ).decode().strip()
    binding["index_sha256"] = (
        "sha256:" + hashlib.sha256((repository / ".git/index").read_bytes()).hexdigest()
    )


@pytest.mark.parametrize("state", ["added", "modified", "deleted"])
def test_candidate_binding_reconciles_git_identity_and_worktree_state(
    tmp_path: Path, state: str
) -> None:
    _initialize_candidate_repository(tmp_path)
    candidate = tmp_path / "source.py"
    before = b"before\n"
    if state != "added":
        candidate.write_bytes(before)
        _git_output(tmp_path, "add", "--", "source.py")
        _git_output(tmp_path, "commit", "-q", "-m", "add source")
    if state == "added":
        candidate.write_bytes(b"after\n")
        bound = candidate.read_bytes()
    elif state == "modified":
        candidate.write_bytes(b"after\n")
        bound = candidate.read_bytes()
    else:
        candidate.unlink()
        bound = before
    row = {
        "path": "source.py",
        "sha256": "sha256:" + hashlib.sha256(bound).hexdigest(),
        "size": len(bound),
        "state": state,
    }
    binding: dict[str, object] = {
        "head": "0" * 40,
        "head_tree": "0" * 40,
        "index_sha256": "sha256:" + "0" * 64,
        "evidence_root_exclusion": "evidence",
        "candidate_paths": [row],
        "candidate_path_set_sha256": canonical_sha256([row]),
    }
    _bind_candidate_to_repository(tmp_path, binding)
    record = {"candidate_binding": binding}

    assert broad_evidence._candidate_binding_live_issues(record, tmp_path) == []

    for field, fictional in (
        ("head", "1" * 40),
        ("head_tree", "2" * 40),
        ("index_sha256", "sha256:" + "3" * 64),
    ):
        actual = binding[field]
        binding[field] = fictional
        assert "candidate_git_identity_mismatch" in {
            issue.code
            for issue in broad_evidence._candidate_binding_live_issues(record, tmp_path)
        }
        binding[field] = actual

    row["state"] = "modified" if state != "modified" else "added"
    binding["candidate_path_set_sha256"] = canonical_sha256([row])
    assert {
        issue.code
        for issue in broad_evidence._candidate_binding_live_issues(record, tmp_path)
    } & {"candidate_path_git_state_mismatch", "candidate_path_live_mismatch"}


def test_candidate_binding_rejects_bytes_outside_the_actual_git_diff(
    tmp_path: Path,
) -> None:
    _initialize_candidate_repository(tmp_path)
    (tmp_path / ".git/info/exclude").write_text("source.py\n")
    candidate = tmp_path / "source.py"
    candidate.write_bytes(b"ignored\n")
    row = {
        "path": "source.py",
        "sha256": file_sha256(candidate),
        "size": candidate.stat().st_size,
        "state": "added",
    }
    binding: dict[str, object] = {
        "head": "0" * 40,
        "head_tree": "0" * 40,
        "index_sha256": "sha256:" + "0" * 64,
        "evidence_root_exclusion": "evidence",
        "candidate_paths": [row],
        "candidate_path_set_sha256": canonical_sha256([row]),
    }
    _bind_candidate_to_repository(tmp_path, binding)

    assert "candidate_path_git_state_mismatch" in {
        issue.code
        for issue in broad_evidence._candidate_binding_live_issues(
            {"candidate_binding": binding}, tmp_path
        )
    }


def test_candidate_binding_reconciles_complete_nonexcluded_diff_both_directions(
    tmp_path: Path,
) -> None:
    _initialize_candidate_repository(tmp_path)
    candidate = tmp_path / "source.py"
    ambient = tmp_path / "ambient.py"
    candidate.write_bytes(b"candidate\n")
    ambient.write_bytes(b"preexisting\n")
    row = {
        "path": "source.py",
        "sha256": file_sha256(candidate),
        "size": candidate.stat().st_size,
        "state": "added",
    }
    binding: dict[str, object] = {
        "head": "0" * 40,
        "head_tree": "0" * 40,
        "index_sha256": "sha256:" + "0" * 64,
        "evidence_root_exclusion": "evidence",
        "candidate_paths": [row],
        "candidate_path_set_sha256": canonical_sha256([row]),
    }
    _bind_candidate_to_repository(tmp_path, binding)
    record = {"candidate_binding": binding}

    assert "candidate_path_set_live_mismatch" in {
        issue.code for issue in broad_evidence._candidate_binding_live_issues(record, tmp_path)
    }
    assert broad_evidence._candidate_binding_live_issues(
        record, tmp_path, permitted_ambient_paths=["ambient.py"]
    ) == []

    ambient.unlink()
    assert "candidate_ambient_path_set_invalid" in {
        issue.code
        for issue in broad_evidence._candidate_binding_live_issues(
            record, tmp_path, permitted_ambient_paths=["ambient.py"]
        )
    }


def _write_focused_test_ledger_binding(
    repository: Path,
    *,
    prefix: str = "focused/ledger-history",
    generation: int = 1,
) -> dict[str, object]:
    plan_path = Path(prefix) / "approved-plan.md"
    plan = repository / plan_path
    plan.parent.mkdir(parents=True, exist_ok=True)
    _write_ledger_plan(plan)
    record = build_initial_execution_ledger(
        plan_path=plan_path,
        plan_bytes=plan.read_bytes(),
    )
    receipt = materialize_transaction(
        repository_root=repository,
        evidence_root=Path(prefix),
        record_kind="execution-ledger",
        output_path=Path(prefix) / "execution-ledger.json",
        generation=1,
        input_paths={"approved_plan": plan_path},
        parameters={"record": record},
    )
    for next_generation in range(2, generation + 1):
        record = _advance_ledger(record, receipt)
        receipt = materialize_transaction(
            repository_root=repository,
            evidence_root=Path(prefix),
            record_kind="execution-ledger",
            output_path=receipt.output_path,
            generation=next_generation,
            input_paths={"approved_plan": plan_path},
            parameters={"record": record},
            prior_request=receipt.request_path,
            prior_snapshot=receipt.snapshot_path,
        )
    return _ledger_binding(receipt)


def test_focused_report_requires_exact_roles_and_persisted_zero_exit(tmp_path: Path) -> None:
    _initialize_candidate_repository(tmp_path)
    log = tmp_path / "focused/logs/check.log"
    exit_file = tmp_path / "focused/exits/check.exit"
    log.parent.mkdir(parents=True)
    exit_file.parent.mkdir(parents=True)
    log.write_text("passed\n")
    exit_file.write_bytes(b"0\n")
    required = {
        "role_id": "check",
        "argv": ["python", "-m", "compileall", "package"],
        "cwd": ".",
        "environment": {"LC_ALL": "C.UTF-8", "PYTHONHASHSEED": "0"},
    }
    command = {
        **required,
        "input_bindings": [],
        "started_at": "2026-01-01T00:00:00+00:00",
        "finished_at": "2026-01-01T00:00:01+00:00",
        "log_binding": {"path": "focused/logs/check.log", "sha256": file_sha256(log)},
        "exit_binding": {"path": "focused/exits/check.exit", "sha256": file_sha256(exit_file)},
        "parsed_exit": 0,
        "outcome": "passed",
    }
    binding_fixture = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence/implementation_focused_report.v1.json")
    )
    candidate = tmp_path / "source.py"
    candidate.write_bytes(b"x")
    binding_fixture["candidate_binding"]["candidate_paths"][0].update(
        {"size": 1, "sha256": file_sha256(candidate)}
    )
    binding_fixture["candidate_binding"]["candidate_path_set_sha256"] = canonical_sha256(
        binding_fixture["candidate_binding"]["candidate_paths"]
    )
    binding_fixture["candidate_binding"]["evidence_root_exclusion"] = "focused"
    task_contract_binding = deepcopy(binding_fixture["task_contract_binding"])
    task_contract_binding["required_command_set_sha256"] = canonical_sha256([required])
    plan = tmp_path / task_contract_binding["plan_path"]
    plan.write_text("approved plan\n")
    task_contract_binding["plan_sha256"] = file_sha256(plan)
    _git_output(tmp_path, "add", "--", plan.relative_to(tmp_path).as_posix())
    _git_output(tmp_path, "commit", "-q", "-m", "bind plan")
    _bind_candidate_to_repository(tmp_path, binding_fixture["candidate_binding"])
    record = {
        "schema_version": "implementation_focused_report.v1",
        "task_contract_binding": task_contract_binding,
        "candidate_binding": binding_fixture["candidate_binding"],
        "execution_ledger_binding": _write_focused_test_ledger_binding(tmp_path),
        "required_commands": [required],
        "commands": [command],
        "command_count": 1,
        "command_set_sha256": canonical_sha256([required]),
        "outcome": "passed",
        "normalized_report_sha256": "",
        "claims_not_made": ["No broad outcome is claimed."],
    }
    record["normalized_report_sha256"] = canonical_sha256(
        record, exclude={"normalized_report_sha256"}
    )
    assert validate_implementation_focused_report(record, tmp_path) == []

    candidate.write_bytes(b"y")
    assert "candidate_path_live_mismatch" in {
        issue.code for issue in validate_implementation_focused_report(record, tmp_path)
    }
    candidate.write_bytes(b"x")

    exit_file.write_bytes(b"1\n")
    assert "focused_exit_binding_mismatch" in {
        issue.code for issue in validate_implementation_focused_report(record, tmp_path)
    }


def test_focused_report_builder_derives_all_file_bindings(tmp_path: Path) -> None:
    _initialize_candidate_repository(tmp_path)
    log = tmp_path / "focused/logs/check.log"
    exit_file = tmp_path / "focused/exits/check.exit"
    input_file = tmp_path / "tests/input.py"
    log.parent.mkdir(parents=True)
    exit_file.parent.mkdir(parents=True)
    input_file.parent.mkdir(parents=True)
    log.write_text("passed\n")
    exit_file.write_bytes(b"0\n")
    input_file.write_text("# input\n")
    required = [{
        "role_id": "check",
        "argv": ["pytest", "-q", "tests/input.py"],
        "cwd": ".",
        "environment": {"LC_ALL": "C.UTF-8", "PYTHONHASHSEED": "0"},
    }]
    binding_fixture = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence/implementation_focused_report.v1.json")
    )
    candidate = tmp_path / "source.py"
    candidate.write_bytes(b"x")
    binding_fixture["candidate_binding"]["candidate_paths"][0].update(
        {"size": 1, "sha256": file_sha256(candidate)}
    )
    binding_fixture["candidate_binding"]["candidate_path_set_sha256"] = canonical_sha256(
        binding_fixture["candidate_binding"]["candidate_paths"]
    )
    binding_fixture["candidate_binding"]["evidence_root_exclusion"] = "focused"
    task_contract_binding = deepcopy(binding_fixture["task_contract_binding"])
    task_contract_binding["required_command_set_sha256"] = canonical_sha256(required)
    plan = tmp_path / task_contract_binding["plan_path"]
    plan.write_text("approved plan\n")
    task_contract_binding["plan_sha256"] = file_sha256(plan)
    _git_output(
        tmp_path,
        "add",
        "--",
        plan.relative_to(tmp_path).as_posix(),
        input_file.relative_to(tmp_path).as_posix(),
    )
    _git_output(tmp_path, "commit", "-q", "-m", "bind focused inputs")
    _bind_candidate_to_repository(tmp_path, binding_fixture["candidate_binding"])
    report = build_implementation_focused_report(
        repository_root=tmp_path,
        task_contract_binding=task_contract_binding,
        candidate_binding=binding_fixture["candidate_binding"],
        execution_ledger_binding=_write_focused_test_ledger_binding(tmp_path),
        required_commands=required,
        observations=[{
            "role_id": "check",
            "input_paths": ["tests/input.py"],
            "started_at": "2026-01-01T00:00:00+00:00",
            "finished_at": "2026-01-01T00:00:01+00:00",
            "log_path": "focused/logs/check.log",
            "exit_path": "focused/exits/check.exit",
        }],
    )
    assert report["commands"][0]["input_bindings"] == [
        {"path": "tests/input.py", "sha256": file_sha256(input_file)}
    ]
    assert validate_implementation_focused_report(report, tmp_path) == []


def _focused_builder_inputs(
    tmp_path: Path,
    role_ids: list[str],
    *,
    ledger_generation: int = 1,
) -> dict[str, object]:
    _initialize_candidate_repository(tmp_path)
    fixture = load_json_closed(
        Path(
            "tests/fixtures/retirement_broad_evidence/implementation_focused_report.v1.json"
        )
    )
    candidate = tmp_path / "source.py"
    candidate.write_bytes(b"x")
    fixture["candidate_binding"]["candidate_paths"][0].update(
        {"size": 1, "sha256": file_sha256(candidate)}
    )
    fixture["candidate_binding"]["candidate_path_set_sha256"] = canonical_sha256(
        fixture["candidate_binding"]["candidate_paths"]
    )
    fixture["candidate_binding"]["evidence_root_exclusion"] = "focused"
    required = [
        {
            "role_id": role,
            "argv": ["python", "-m", "compileall", role],
            "cwd": ".",
            "environment": {"LC_ALL": "C.UTF-8", "PYTHONHASHSEED": "0"},
        }
        for role in role_ids
    ]
    task_contract = deepcopy(fixture["task_contract_binding"])
    task_contract["required_command_set_sha256"] = canonical_sha256(required)
    plan = tmp_path / task_contract["plan_path"]
    plan.write_text("approved plan\n")
    task_contract["plan_sha256"] = file_sha256(plan)
    _git_output(tmp_path, "add", "--", plan.relative_to(tmp_path).as_posix())
    _git_output(tmp_path, "commit", "-q", "-m", "bind focused plan")
    _bind_candidate_to_repository(tmp_path, fixture["candidate_binding"])
    observations = []
    for role in reversed(role_ids):
        log = tmp_path / f"focused/logs/{role}.log"
        exit_file = tmp_path / f"focused/exits/{role}.exit"
        log.parent.mkdir(parents=True, exist_ok=True)
        exit_file.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("passed\n")
        exit_file.write_bytes(b"0\n")
        observations.append(
            {
                "role_id": role,
                "input_paths": [],
                "started_at": "2026-01-01T00:00:00+00:00",
                "finished_at": "2026-01-01T00:00:01+00:00",
                "log_path": f"focused/logs/{role}.log",
                "exit_path": f"focused/exits/{role}.exit",
            }
        )
    return {
        "repository_root": tmp_path,
        "task_contract_binding": task_contract,
        "candidate_binding": fixture["candidate_binding"],
        "execution_ledger_binding": _write_focused_test_ledger_binding(
            tmp_path, generation=ledger_generation
        ),
        "required_commands": required,
        "observations": observations,
    }


def test_focused_report_builder_preserves_authoritative_nonlexical_role_order(
    tmp_path: Path,
) -> None:
    inputs = _focused_builder_inputs(
        tmp_path,
        ["collect-bootstrap-focused", "test-bootstrap-focused", "compile-bootstrap"],
    )

    report = build_implementation_focused_report(**inputs)

    assert [row["role_id"] for row in report["commands"]] == [
        "collect-bootstrap-focused",
        "test-bootstrap-focused",
        "compile-bootstrap",
    ]
    assert validate_implementation_focused_report(report, tmp_path) == []


@pytest.mark.parametrize(
    "invalid_field",
    [
        "empty_commands",
        "task_contract_binding",
        "candidate_binding",
        "execution_ledger_binding",
        "input_paths_none",
        "log_path_none",
        "exit_path_none",
    ],
)
def test_focused_report_builder_rejects_validator_invalid_inputs(
    tmp_path: Path, invalid_field: str
) -> None:
    inputs = _focused_builder_inputs(tmp_path, ["check"])
    if invalid_field == "empty_commands":
        inputs["required_commands"] = []
        inputs["observations"] = []
    elif invalid_field.endswith("_none"):
        field = invalid_field.removesuffix("_none")
        inputs["observations"][0][field] = None
    else:
        inputs[invalid_field] = {}

    with pytest.raises(ContractError, match="focused_report_invalid"):
        build_implementation_focused_report(**inputs)


def test_focused_report_builder_rejects_candidate_drift_before_returning(
    tmp_path: Path,
) -> None:
    inputs = _focused_builder_inputs(tmp_path, ["check"])
    (tmp_path / "source.py").write_text("drift after candidate capture\n")

    with pytest.raises(
        ContractError, match="focused_report_invalid:candidate_path_live_mismatch"
    ):
        build_implementation_focused_report(**inputs)


@pytest.mark.parametrize("ledger_role", ["live_path", "request_path", "snapshot_path"])
def test_focused_report_reopens_every_ledger_coordinate(
    tmp_path: Path, ledger_role: str
) -> None:
    inputs = _focused_builder_inputs(tmp_path, ["check"])
    report = build_implementation_focused_report(**inputs)
    bound_path = tmp_path / report["execution_ledger_binding"][ledger_role]
    bound_path.write_bytes(b"{}\n")

    assert broad_evidence.Issue(
        "ledger_generation_invalid",
        "$.execution_ledger_binding",
        (
            "live_generation_unrelated"
            if ledger_role == "live_path"
            else "generation_binding_coordinate_invalid"
        ),
    ) in validate_implementation_focused_report(report, tmp_path)

    with pytest.raises(
        ContractError,
        match="focused_report_invalid:ledger_generation_invalid",
    ):
        build_implementation_focused_report(**inputs)


@pytest.mark.parametrize(
    "defect",
    [
        "request_record_mismatch",
        "arbitrary_snapshot_coordinate",
        "invalid_ancestry",
    ],
)
def test_focused_report_builder_and_validator_require_canonical_ledger_generation(
    tmp_path: Path, defect: str
) -> None:
    generation = 3 if defect == "invalid_ancestry" else 1
    inputs = _focused_builder_inputs(
        tmp_path, ["check"], ledger_generation=generation
    )
    report = build_implementation_focused_report(**inputs)
    invalid = _invalidate_ledger_binding_history(
        tmp_path, inputs["execution_ledger_binding"], defect
    )
    report["execution_ledger_binding"] = invalid
    report["normalized_report_sha256"] = canonical_sha256(
        report, exclude={"normalized_report_sha256"}
    )

    assert "ledger_generation_invalid" in {
        issue.code
        for issue in validate_implementation_focused_report(report, tmp_path)
    }

    inputs["execution_ledger_binding"] = invalid
    with pytest.raises(
        ContractError,
        match="focused_report_invalid:ledger_generation_invalid",
    ):
        build_implementation_focused_report(**inputs)


def test_focused_report_historical_ledger_binding_accepts_canonical_descendant_live(
    tmp_path: Path,
) -> None:
    inputs = _focused_builder_inputs(tmp_path, ["check"])
    report = build_implementation_focused_report(**inputs)

    _advance_bound_ledger(tmp_path, inputs["execution_ledger_binding"])

    assert validate_implementation_focused_report(report, tmp_path) == []
    with pytest.raises(
        ContractError,
        match="focused_report_invalid:ledger_generation_invalid",
    ):
        build_implementation_focused_report(**inputs)


def test_focused_builder_rechecks_strict_current_after_final_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = _focused_builder_inputs(tmp_path, ["check"])
    binding = inputs["execution_ledger_binding"]
    original = broad_evidence.validate_implementation_focused_report
    advanced = False

    def validate_then_advance(
        record: dict[str, object], repository_root: Path, **kwargs: object
    ) -> list[broad_evidence.Issue]:
        nonlocal advanced
        if not advanced:
            advanced = True
            _advance_bound_ledger(tmp_path, binding)
        return original(record, repository_root, **kwargs)

    monkeypatch.setattr(
        broad_evidence,
        "validate_implementation_focused_report",
        validate_then_advance,
    )

    with pytest.raises(
        ContractError,
        match="focused_report_invalid:ledger_generation_invalid",
    ):
        build_implementation_focused_report(**inputs)
    assert advanced is True


def test_focused_builder_and_validator_reject_integer_ledger_generation_mismatch(
    tmp_path: Path,
) -> None:
    inputs = _focused_builder_inputs(tmp_path, ["check"])
    report = build_implementation_focused_report(**inputs)
    invalid = deepcopy(inputs["execution_ledger_binding"])
    invalid["generation"] += 1
    report["execution_ledger_binding"] = invalid
    report["normalized_report_sha256"] = canonical_sha256(
        report, exclude={"normalized_report_sha256"}
    )

    assert broad_evidence.Issue(
        "ledger_generation_invalid",
        "$.execution_ledger_binding",
        "generation_binding_coordinate_invalid",
    ) in validate_implementation_focused_report(report, tmp_path)

    inputs["execution_ledger_binding"] = invalid
    with pytest.raises(
        ContractError,
        match="focused_report_invalid:ledger_generation_invalid",
    ):
        build_implementation_focused_report(**inputs)


@pytest.mark.parametrize("live_defect", ["missing", "tampered", "non_descendant"])
def test_historical_ledger_binding_rejects_invalid_current_live(
    tmp_path: Path, live_defect: str
) -> None:
    inputs = _focused_builder_inputs(tmp_path, ["check"])
    report = build_implementation_focused_report(**inputs)
    binding = inputs["execution_ledger_binding"]
    live = tmp_path / binding["live_path"]
    if live_defect == "missing":
        live.unlink()
    elif live_defect == "tampered":
        live.write_bytes(b"{}\n")
    else:
        other = _write_focused_test_ledger_binding(
            tmp_path, prefix="other/ledger-history", generation=2
        )
        live.write_bytes((tmp_path / other["snapshot_path"]).read_bytes())

    issues = validate_implementation_focused_report(report, tmp_path)

    assert any(
        issue.code == "ledger_generation_invalid"
        and issue.path == "$.execution_ledger_binding"
        for issue in issues
    )


@pytest.mark.parametrize(
    ("boundary", "coordinate"),
    [
        ("after_bound_binding_validation", "bound_request"),
        ("after_bound_binding_validation", "bound_snapshot"),
        ("after_candidate_binding_validation", "candidate_request"),
        ("after_candidate_binding_validation", "candidate_snapshot"),
    ],
)
def test_historical_ledger_binding_rejects_generation_identity_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
    coordinate: str,
) -> None:
    inputs = _focused_builder_inputs(tmp_path, ["check"])
    report = build_implementation_focused_report(**inputs)
    binding = inputs["execution_ledger_binding"]
    _, child = _advance_bound_ledger(tmp_path, binding)
    coordinates = {
        "bound_request": Path(binding["request_path"]),
        "bound_snapshot": Path(binding["snapshot_path"]),
        "candidate_request": child.request_path,
        "candidate_snapshot": child.snapshot_path,
    }
    mutated = False

    def mutate_at_boundary(observed: str) -> None:
        nonlocal mutated
        if observed == boundary and not mutated:
            mutated = True
            (tmp_path / coordinates[coordinate]).write_bytes(b"{}\n")

    monkeypatch.setattr(
        retirement_materialization,
        "_generation_validation_boundary",
        mutate_at_boundary,
    )

    assert broad_evidence.Issue(
        "ledger_generation_invalid",
        "$.execution_ledger_binding",
        "generation_binding_changed",
    ) in validate_implementation_focused_report(report, tmp_path)
    assert mutated is True


@pytest.mark.parametrize(
    ("boundary", "coordinate"),
    [
        ("after_candidate_generation_validation", "request"),
        ("after_candidate_generation_validation", "snapshot"),
        ("before_final_candidate_lineage_check", "request"),
        ("before_final_candidate_lineage_check", "snapshot"),
    ],
)
def test_historical_ledger_binding_rejects_intermediate_ancestry_identity_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
    coordinate: str,
) -> None:
    inputs = _focused_builder_inputs(tmp_path, ["check"])
    report = build_implementation_focused_report(**inputs)
    binding = inputs["execution_ledger_binding"]
    _, intermediate = _advance_bound_ledger(tmp_path, binding)
    _, _current = _advance_bound_ledger(
        tmp_path, _ledger_binding(intermediate)
    )
    target = (
        intermediate.request_path
        if coordinate == "request"
        else intermediate.snapshot_path
    )
    mutated = False

    def mutate_at_boundary(observed: str) -> None:
        nonlocal mutated
        if observed == boundary and not mutated:
            mutated = True
            (tmp_path / target).write_bytes(b"{}\n")

    monkeypatch.setattr(
        retirement_materialization,
        "_generation_validation_boundary",
        mutate_at_boundary,
    )

    assert broad_evidence.Issue(
        "ledger_generation_invalid",
        "$.execution_ledger_binding",
        "generation_binding_changed",
    ) in validate_implementation_focused_report(report, tmp_path)
    assert mutated is True


def test_focused_report_rejects_extra_observed_role(tmp_path: Path) -> None:
    fixture = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence/implementation_focused_report.v1.json")
    )
    fixture["commands"] = [{"role_id": "extra"}]
    fixture["command_count"] = 1
    fixture["normalized_report_sha256"] = canonical_sha256(
        fixture, exclude={"normalized_report_sha256"}
    )
    assert "focused_command_row_invalid" in {
        issue.code for issue in validate_implementation_focused_report(fixture, tmp_path)
    }


def _write_review_subject(tmp_path: Path, subject_path: Path) -> Path:
    if not (tmp_path / ".git").exists():
        _initialize_candidate_repository(tmp_path)
    plan_path, _, receipt = _materialize_first_ledger(tmp_path)
    plan_logical = plan_path.relative_to(tmp_path).as_posix()
    plan_status = _git_output(
        tmp_path, "status", "--porcelain=v1", "--", plan_logical
    )
    if plan_status:
        _git_output(tmp_path, "add", "--", plan_logical)
        _git_output(tmp_path, "commit", "-q", "-m", "bind plan")
    ledger_binding = {
        "live_path": receipt.output_path.as_posix(),
        "byte_sha256": receipt.output_sha256,
        "schema_version": "workflow_retirement_execution_ledger.v1",
        "generation": receipt.generation,
        "request_path": receipt.request_path.as_posix(),
        "request_sha256": receipt.request_sha256,
        "snapshot_path": receipt.snapshot_path.as_posix(),
        "snapshot_sha256": receipt.snapshot_sha256,
    }
    fixture_root = Path("tests/fixtures/retirement_broad_evidence")
    record = load_json_closed(fixture_root / "broad_failure_remediation.v1.json")
    source_path = tmp_path / "source.py"
    source_path.write_bytes(b"x")
    source_row = record["candidate_binding"]["candidate_paths"][0]
    source_row["sha256"] = file_sha256(source_path)
    source_row["size"] = source_path.stat().st_size
    record["candidate_binding"]["candidate_path_set_sha256"] = canonical_sha256(
        record["candidate_binding"]["candidate_paths"]
    )
    _bind_candidate_to_repository(tmp_path, record["candidate_binding"])
    record["production_diff"] = deepcopy(
        record["candidate_binding"]["candidate_paths"]
    )
    baseline = load_json_closed(fixture_root / "broad_known_failure_baseline.v1.json")
    baseline_path = tmp_path / "evidence/known-failure-baseline.json"
    baseline_path.write_text(json.dumps(baseline, sort_keys=True) + "\n")
    task_scope_path = tmp_path / "evidence/task-scope.json"
    task_scope_path.write_text("{}\n")
    focused = load_json_closed(fixture_root / "implementation_focused_report.v1.json")
    focused["candidate_binding"] = record["candidate_binding"]
    focused["execution_ledger_binding"] = ledger_binding
    focused["task_contract_binding"]["plan_sha256"] = file_sha256(tmp_path / "plan.md")
    log_path = tmp_path / "evidence/focused/logs/check.log"
    exit_path = tmp_path / "evidence/focused/exits/check.exit"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    exit_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("passed\n")
    exit_path.write_bytes(b"0\n")
    focused["commands"][0]["log_binding"]["sha256"] = file_sha256(log_path)
    focused["commands"][0]["exit_binding"]["sha256"] = file_sha256(exit_path)
    focused["normalized_report_sha256"] = canonical_sha256(
        focused, exclude={"normalized_report_sha256"}
    )
    focused_path = tmp_path / "evidence/focused/report.json"
    focused_path.write_text(json.dumps(focused, sort_keys=True) + "\n")
    record["execution_ledger_binding"] = ledger_binding
    record["baseline_binding"] = {
        "path": "evidence/known-failure-baseline.json",
        "sha256": file_sha256(baseline_path),
    }
    record["task_scope_binding"] = {
        "path": "evidence/task-scope.json",
        "sha256": file_sha256(task_scope_path),
    }
    record["focused_regression_evidence"] = {
        "path": "evidence/focused/report.json",
        "sha256": file_sha256(focused_path),
    }
    record["normalized_remediation_sha256"] = canonical_sha256(
        record, exclude={"normalized_remediation_sha256"}
    )
    subject = tmp_path / subject_path
    subject.parent.mkdir(parents=True, exist_ok=True)
    subject.write_text(json.dumps(record, sort_keys=True) + "\n")
    return subject


def test_immutable_review_snapshot_survives_live_rereview(tmp_path: Path) -> None:
    subject_path = Path("evidence/failure-remediation.json")
    review_path = Path("evidence/remediation-specification-review.json")
    subject = _write_review_subject(tmp_path, subject_path)
    review = tmp_path / review_path
    record = {
        "schema_version": "review.v1",
        "review_kind": "specification",
        "reviewer": {"identity": "reviewer"},
        "subject": {
            "kind": "broad_failure_remediation",
            "path": subject_path.as_posix(),
            "sha256": file_sha256(subject),
        },
        "result": "approved",
        "issues": [],
        "reviewed_at": "2026-01-01T00:00:00+00:00",
        "claims_not_made": ["Review does not authorize mutation."],
    }
    review.write_text(json.dumps(record, sort_keys=True) + "\n")
    binding = publish_immutable_review(
        repository_root=tmp_path,
        evidence_root=Path("evidence"),
        subject_path=subject_path,
        review_path=review_path,
    )
    immutable = tmp_path / binding["immutable_path"]
    original = immutable.read_bytes()
    review.write_text("later review bytes\n")
    assert immutable.read_bytes() == original


def test_immutable_review_publication_rejects_detached_derived_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    subject_path = Path("evidence/failure-remediation.json")
    review_path = Path("evidence/remediation-specification-review.json")
    _write_review_subject(tmp_path, subject_path)
    review = _write_live_review(
        tmp_path, subject_path=subject_path, review_path=review_path
    )
    review_record = load_json_closed(review)
    review_bytes = review.read_bytes()
    destination = broad_evidence._derived_immutable_review_path(
        Path("evidence"),
        review_record["subject"],
        review_record["review_kind"],
        f"sha256:{hashlib.sha256(review_bytes).hexdigest()}",
    )
    parent = tmp_path / destination.parent
    detached = parent.with_name(f"{parent.name}-detached")
    real_boundary = safe_io._conditional_publish_boundary
    raced = False

    def detach_parent(stage, parent_fd, temporary_name, destination_name):
        nonlocal raced
        if stage == "before_parent_validation" and not raced:
            raced = True
            parent.rename(detached)
            parent.mkdir()
        return real_boundary(stage, parent_fd, temporary_name, destination_name)

    monkeypatch.setattr(safe_io, "_conditional_publish_boundary", detach_parent)

    with pytest.raises(ContractError, match="immutable_review_path_invalid"):
        publish_immutable_review(
            repository_root=tmp_path,
            evidence_root=Path("evidence"),
            subject_path=subject_path,
            review_path=review_path,
        )

    assert not (tmp_path / destination).exists()
    assert not (detached / destination.name).exists()


@pytest.mark.parametrize("changed_input", ["subject", "review"])
def test_immutable_review_publication_rejects_live_input_identity_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    changed_input: str,
) -> None:
    subject_path = Path("evidence/failure-remediation.json")
    review_path = Path("evidence/remediation-specification-review.json")
    subject = _write_review_subject(tmp_path, subject_path)
    review = _write_live_review(
        tmp_path, subject_path=subject_path, review_path=review_path
    )
    review_record = load_json_closed(review)
    review_bytes = review.read_bytes()
    destination = broad_evidence._derived_immutable_review_path(
        Path("evidence"),
        review_record["subject"],
        review_record["review_kind"],
        f"sha256:{hashlib.sha256(review_bytes).hexdigest()}",
    )
    changed = subject if changed_input == "subject" else review
    changed_bytes = changed.read_bytes()
    real_boundary = getattr(
        broad_evidence,
        "_immutable_review_publication_boundary",
        lambda *_args: None,
    )
    raced = False

    def replace_live_input(boundary):
        nonlocal raced
        if boundary == "before_live_input_revalidation" and not raced:
            raced = True
            replacement = changed.with_name(f".{changed.name}.replacement")
            replacement.write_bytes(changed_bytes)
            replacement.replace(changed)
        return real_boundary(boundary)

    monkeypatch.setattr(
        broad_evidence,
        "_immutable_review_publication_boundary",
        replace_live_input,
        raising=False,
    )

    with pytest.raises(ContractError, match="immutable_review_live_input_changed"):
        publish_immutable_review(
            repository_root=tmp_path,
            evidence_root=Path("evidence"),
            subject_path=subject_path,
            review_path=review_path,
        )

    assert not (tmp_path / destination).exists()


def _rewrite_valid_review(review: Path, *, reviewed_at: str) -> None:
    record = load_json_closed(review)
    record["reviewed_at"] = reviewed_at
    review.write_text(json.dumps(record, sort_keys=True) + "\n")


def test_immutable_review_rereview_requires_valid_prior_append_only_binding(
    tmp_path: Path,
) -> None:
    subject_path = Path("evidence/failure-remediation.json")
    review_path = Path("evidence/remediation-specification-review.json")
    subject = _write_review_subject(tmp_path, subject_path)
    review = tmp_path / review_path
    record = {
        "schema_version": "review.v1",
        "review_kind": "specification",
        "reviewer": {"identity": "reviewer"},
        "subject": {
            "kind": "broad_failure_remediation",
            "path": subject_path.as_posix(),
            "sha256": file_sha256(subject),
        },
        "result": "approved",
        "issues": [],
        "reviewed_at": "2026-01-01T00:00:00+00:00",
        "claims_not_made": ["Review does not authorize mutation."],
    }
    review.write_text(json.dumps(record, sort_keys=True) + "\n")
    prior = publish_immutable_review(
        repository_root=tmp_path,
        evidence_root=Path("evidence"),
        subject_path=subject_path,
        review_path=review_path,
    )
    _rewrite_valid_review(review, reviewed_at="2026-01-02T00:00:00+00:00")

    with pytest.raises(ContractError, match="prior_review_binding_required"):
        publish_immutable_review(
            repository_root=tmp_path,
            evidence_root=Path("evidence"),
            subject_path=subject_path,
            review_path=review_path,
        )

    replacement = publish_immutable_review(
        repository_root=tmp_path,
        evidence_root=Path("evidence"),
        subject_path=subject_path,
        review_path=review_path,
        prior_review_binding=prior,
    )
    assert replacement["sha256"] == file_sha256(review)
    assert (tmp_path / prior["immutable_path"]).is_file()


def test_immutable_review_rereview_rejects_missing_prior_snapshot(
    tmp_path: Path,
) -> None:
    subject_path = Path("evidence/failure-remediation.json")
    review_path = Path("evidence/remediation-specification-review.json")
    subject = _write_review_subject(tmp_path, subject_path)
    review = tmp_path / review_path
    record = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence/review.v1.json")
    )
    record["subject"] = {
        "kind": "broad_failure_remediation",
        "path": subject_path.as_posix(),
        "sha256": file_sha256(subject),
    }
    review.write_text(json.dumps(record, sort_keys=True) + "\n")
    prior = publish_immutable_review(
        repository_root=tmp_path,
        evidence_root=Path("evidence"),
        subject_path=subject_path,
        review_path=review_path,
    )
    (tmp_path / prior["immutable_path"]).unlink()
    _rewrite_valid_review(review, reviewed_at="2026-01-02T00:00:00+00:00")

    with pytest.raises(ContractError, match="prior_immutable_review_invalid"):
        publish_immutable_review(
            repository_root=tmp_path,
            evidence_root=Path("evidence"),
            subject_path=subject_path,
            review_path=review_path,
            prior_review_binding=prior,
        )


def _write_live_review(
    tmp_path: Path,
    *,
    subject_path: Path,
    review_path: Path,
    subject_kind: str = "broad_failure_remediation",
) -> Path:
    subject = tmp_path / subject_path
    review = tmp_path / review_path
    review.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "schema_version": "review.v1",
        "review_kind": "specification",
        "reviewer": {"identity": "reviewer"},
        "subject": {
            "kind": subject_kind,
            "path": subject_path.as_posix(),
            "sha256": file_sha256(subject),
        },
        "result": "approved",
        "issues": [],
        "reviewed_at": "2026-01-01T00:00:00+00:00",
        "claims_not_made": ["Review does not authorize mutation."],
    }
    review.write_text(json.dumps(record, sort_keys=True) + "\n")
    return review


def _immutable_review_component(
    *, evidence_root: Path, subject_path: Path, subject: Path, depth: int
) -> Path:
    logical_hash = hashlib.sha256(subject_path.as_posix().encode("utf-8")).hexdigest()
    components = [
        evidence_root / "immutable-reviews",
        evidence_root / "immutable-reviews" / logical_hash,
        evidence_root
        / "immutable-reviews"
        / logical_hash
        / file_sha256(subject).removeprefix("sha256:"),
    ]
    return components[depth]


@pytest.mark.parametrize("depth", [0, 1, 2])
def test_immutable_review_publication_rejects_each_symlinked_intermediate(
    tmp_path: Path, depth: int
) -> None:
    subject_path = Path("evidence/failure-remediation.json")
    review_path = Path("evidence/remediation-specification-review.json")
    subject = _write_review_subject(tmp_path, subject_path)
    _write_live_review(
        tmp_path, subject_path=subject_path, review_path=review_path
    )
    component = _immutable_review_component(
        evidence_root=Path("evidence"),
        subject_path=subject_path,
        subject=subject,
        depth=depth,
    )
    outside = tmp_path / "outside"
    outside.mkdir()
    absolute_component = tmp_path / component
    absolute_component.parent.mkdir(parents=True, exist_ok=True)
    absolute_component.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ContractError, match="immutable_review_path_invalid"):
        publish_immutable_review(
            repository_root=tmp_path,
            evidence_root=Path("evidence"),
            subject_path=subject_path,
            review_path=review_path,
        )

    assert list(outside.iterdir()) == []


@pytest.mark.parametrize("depth", [0, 1, 2])
def test_immutable_review_publication_accepts_each_regular_intermediate(
    tmp_path: Path, depth: int
) -> None:
    subject_path = Path("evidence/failure-remediation.json")
    review_path = Path("evidence/remediation-specification-review.json")
    subject = _write_review_subject(tmp_path, subject_path)
    _write_live_review(
        tmp_path, subject_path=subject_path, review_path=review_path
    )
    component = _immutable_review_component(
        evidence_root=Path("evidence"),
        subject_path=subject_path,
        subject=subject,
        depth=depth,
    )
    (tmp_path / component).mkdir(parents=True)

    binding = publish_immutable_review(
        repository_root=tmp_path,
        evidence_root=Path("evidence"),
        subject_path=subject_path,
        review_path=review_path,
    )

    assert (tmp_path / binding["immutable_path"]).is_file()


@pytest.mark.parametrize("depth", [0, 1, 2])
def test_immutable_review_rereview_rejects_symlinked_prior_history_component(
    tmp_path: Path, depth: int
) -> None:
    subject_path = Path("evidence/failure-remediation.json")
    review_path = Path("evidence/remediation-specification-review.json")
    subject = _write_review_subject(tmp_path, subject_path)
    review = _write_live_review(
        tmp_path, subject_path=subject_path, review_path=review_path
    )
    prior = publish_immutable_review(
        repository_root=tmp_path,
        evidence_root=Path("evidence"),
        subject_path=subject_path,
        review_path=review_path,
    )
    component = tmp_path / _immutable_review_component(
        evidence_root=Path("evidence"),
        subject_path=subject_path,
        subject=subject,
        depth=depth,
    )
    preserved = tmp_path / f"preserved-{depth}"
    component.rename(preserved)
    component.symlink_to(preserved, target_is_directory=True)
    _rewrite_valid_review(review, reviewed_at="2026-01-02T00:00:00+00:00")

    with pytest.raises(ContractError, match="immutable_review_path_invalid"):
        publish_immutable_review(
            repository_root=tmp_path,
            evidence_root=Path("evidence"),
            subject_path=subject_path,
            review_path=review_path,
            prior_review_binding=prior,
        )


def test_immutable_review_publication_rejects_invalid_bound_subject_before_history_io(
    tmp_path: Path,
) -> None:
    subject_path = Path("evidence/failure-remediation.json")
    review_path = Path("evidence/remediation-specification-review.json")
    subject = tmp_path / subject_path
    subject.parent.mkdir(parents=True)
    subject.write_text(
        '{"schema_version":"broad_evidence_bootstrap_subject.v1"}\n'
    )
    _write_live_review(
        tmp_path,
        subject_path=subject_path,
        review_path=review_path,
        subject_kind="broad_evidence_bootstrap",
    )

    with pytest.raises(ContractError, match="review_subject_record_invalid"):
        publish_immutable_review(
            repository_root=tmp_path,
            evidence_root=Path("evidence"),
            subject_path=subject_path,
            review_path=review_path,
        )

    assert not (tmp_path / "evidence/immutable-reviews").exists()


@pytest.mark.parametrize("logical_input", ["subject", "review"])
def test_review_publication_rejects_symlinked_live_input(
    tmp_path: Path, logical_input: str
) -> None:
    subject_path = Path("evidence/failure-remediation.json")
    review_path = Path("evidence/remediation-specification-review.json")
    subject = _write_review_subject(tmp_path, subject_path)
    review = _write_live_review(
        tmp_path, subject_path=subject_path, review_path=review_path
    )
    selected = subject if logical_input == "subject" else review
    preserved = tmp_path / f"outside-{logical_input}.json"
    selected.rename(preserved)
    selected.symlink_to(preserved)

    expected = "review_subject_unreadable" if logical_input == "subject" else "review_unreadable"
    with pytest.raises(ContractError, match=expected):
        publish_immutable_review(
            repository_root=tmp_path,
            evidence_root=Path("evidence"),
            subject_path=subject_path,
            review_path=review_path,
        )

    assert not (tmp_path / "evidence/immutable-reviews").exists()


def test_review_publication_passes_only_exact_lifecycle_manifest_exclusions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    subject_path = Path("evidence/bootstrap-subject.json")
    review_path = Path("evidence/specification-review.json")
    subject = tmp_path / subject_path
    subject.parent.mkdir(parents=True)
    subject.write_text('{"schema_version":"test-only"}\n')
    _write_live_review(
        tmp_path,
        subject_path=subject_path,
        review_path=review_path,
        subject_kind="broad_evidence_bootstrap",
    )
    captured: list[str] = []

    def accept_subject(**kwargs: object) -> list[object]:
        captured.extend(kwargs["permitted_manifest_exclusions"])
        return []

    monkeypatch.setattr(broad_evidence, "validate_review_subject", accept_subject)

    current_binding = broad_evidence.derive_review_binding(
        evidence_root=Path("evidence"),
        review_path=review_path,
        review_bytes=(tmp_path / review_path).read_bytes(),
    )

    publish_immutable_review(
        repository_root=tmp_path,
        evidence_root=Path("evidence"),
        subject_path=subject_path,
        review_path=review_path,
    )

    assert captured == sorted(
        [
            subject_path.as_posix(),
            review_path.as_posix(),
            current_binding["immutable_path"],
        ]
    )


def test_review_publication_exclusions_are_closed_over_existing_review_slots(
    tmp_path: Path,
) -> None:
    subject_path = Path("evidence/bootstrap-subject.json")
    review_path = Path("evidence/specification-review.json")
    quality_path = Path("evidence/quality-review.json")
    subject = tmp_path / subject_path
    subject.parent.mkdir(parents=True, exist_ok=True)
    subject.write_text("{}\n")
    current_bindings: list[dict[str, object]] = []
    for review_kind, path in (
        ("specification", review_path),
        ("code_quality", quality_path),
    ):
        review = {
            "schema_version": "review.v1",
            "review_kind": review_kind,
            "reviewer": {"identity": f"{review_kind}-reviewer"},
            "subject": {
                "kind": "broad_evidence_bootstrap",
                "path": subject_path.as_posix(),
                "sha256": file_sha256(subject),
            },
            "result": "approved",
            "issues": [],
            "reviewed_at": "2026-01-02T00:00:00+00:00",
            "claims_not_made": ["Synthetic current review."],
        }
        target = _write_producer_json(tmp_path, path.as_posix(), review)
        current_bindings.append(
            broad_evidence.derive_review_binding(
                evidence_root=Path("evidence"),
                review_path=path,
                review_bytes=target.read_bytes(),
            )
        )
    historical_review = load_json_closed(tmp_path / review_path)
    historical_review["subject"]["sha256"] = f"sha256:{'1' * 64}"
    historical_review["reviewed_at"] = "2026-01-01T00:00:00+00:00"
    historical_bytes = json.dumps(historical_review, sort_keys=True).encode() + b"\n"
    historical_binding = broad_evidence.derive_review_binding(
        evidence_root=Path("evidence"),
        review_path=review_path,
        review_bytes=historical_bytes,
    )
    target = tmp_path / historical_binding["immutable_path"]
    target.parent.mkdir(parents=True)
    target.write_bytes(historical_bytes)

    assert broad_evidence._publication_manifest_exclusions(
        repository_root=tmp_path,
        evidence_root=Path("evidence"),
        subject_path=subject_path,
        review_path=review_path,
        subject_kind="broad_evidence_bootstrap",
    ) == sorted(
        [
            subject_path.as_posix(),
            review_path.as_posix(),
            quality_path.as_posix(),
            current_bindings[0]["immutable_path"],
            current_bindings[1]["immutable_path"],
        ]
    )

    unexpected = target.with_name("unexpected.json")
    unexpected.write_text("{}\n")
    with pytest.raises(ContractError, match="immutable_review_path_invalid"):
        broad_evidence._validated_immutable_review_bindings(
            tmp_path, Path("evidence")
        )


def test_immutable_review_publication_rejects_subject_kind_schema_mismatch(
    tmp_path: Path,
) -> None:
    subject_path = Path("evidence/failure-remediation.json")
    review_path = Path("evidence/remediation-specification-review.json")
    _write_review_subject(tmp_path, subject_path)
    _write_live_review(
        tmp_path,
        subject_path=subject_path,
        review_path=review_path,
        subject_kind="broad_evidence_bootstrap",
    )

    with pytest.raises(ContractError, match="review_subject_kind_schema_mismatch"):
        publish_immutable_review(
            repository_root=tmp_path,
            evidence_root=Path("evidence"),
            subject_path=subject_path,
            review_path=review_path,
        )


def test_immutable_review_publication_rejects_review_kind_filename_mismatch(
    tmp_path: Path,
) -> None:
    subject_path = Path("evidence/failure-remediation.json")
    review_path = Path("evidence/remediation-quality-review.json")
    _write_review_subject(tmp_path, subject_path)
    _write_live_review(
        tmp_path, subject_path=subject_path, review_path=review_path
    )

    with pytest.raises(ContractError, match="review_live_path_mismatch"):
        publish_immutable_review(
            repository_root=tmp_path,
            evidence_root=Path("evidence"),
            subject_path=subject_path,
            review_path=review_path,
        )


def test_review_binding_bound_validation_reopens_and_derives_immutable_bytes(
    tmp_path: Path,
) -> None:
    subject_path = Path("evidence/failure-remediation.json")
    review_path = Path("evidence/remediation-specification-review.json")
    _write_review_subject(tmp_path, subject_path)
    _write_live_review(
        tmp_path, subject_path=subject_path, review_path=review_path
    )
    binding = publish_immutable_review(
        repository_root=tmp_path,
        evidence_root=Path("evidence"),
        subject_path=subject_path,
        review_path=review_path,
    )

    assert validate_bound_record(binding, tmp_path) == []

    wrong_coordinate = json.loads(json.dumps(binding))
    wrong_coordinate["immutable_path"] = "evidence/immutable-reviews/wrong.json"
    wrong_coordinate["normalized_binding_sha256"] = canonical_sha256(
        wrong_coordinate, exclude={"normalized_binding_sha256"}
    )
    assert "review_binding_immutable_path_mismatch" in {
        issue.code for issue in validate_bound_record(wrong_coordinate, tmp_path)
    }

    immutable = tmp_path / binding["immutable_path"]
    immutable.chmod(0o644)
    immutable.write_text("changed\n")
    assert "review_binding_immutable_unreadable" in {
        issue.code for issue in validate_bound_record(binding, tmp_path)
    }


@pytest.mark.parametrize("depth", [0, 1, 2])
def test_review_binding_bound_validation_rejects_each_symlinked_intermediate(
    tmp_path: Path, depth: int
) -> None:
    subject_path = Path("evidence/failure-remediation.json")
    review_path = Path("evidence/remediation-specification-review.json")
    subject = _write_review_subject(tmp_path, subject_path)
    _write_live_review(
        tmp_path, subject_path=subject_path, review_path=review_path
    )
    binding = publish_immutable_review(
        repository_root=tmp_path,
        evidence_root=Path("evidence"),
        subject_path=subject_path,
        review_path=review_path,
    )
    component = tmp_path / _immutable_review_component(
        evidence_root=Path("evidence"),
        subject_path=subject_path,
        subject=subject,
        depth=depth,
    )
    preserved = tmp_path / f"binding-preserved-{depth}"
    component.rename(preserved)
    component.symlink_to(preserved, target_is_directory=True)

    assert "review_binding_immutable_unreadable" in {
        issue.code for issue in validate_bound_record(binding, tmp_path)
    }


def test_immutable_review_rereview_accepts_prior_under_old_subject_digest(
    tmp_path: Path,
) -> None:
    subject_path = Path("evidence/failure-remediation.json")
    review_path = Path("evidence/remediation-specification-review.json")
    subject = _write_review_subject(tmp_path, subject_path)
    review = _write_live_review(
        tmp_path, subject_path=subject_path, review_path=review_path
    )
    prior = publish_immutable_review(
        repository_root=tmp_path,
        evidence_root=Path("evidence"),
        subject_path=subject_path,
        review_path=review_path,
    )
    prior_path = prior["immutable_path"]
    changed_subject = load_json_closed(subject)
    changed_subject["claims_not_made"] = ["changed but still valid"]
    changed_subject["normalized_remediation_sha256"] = canonical_sha256(
        changed_subject, exclude={"normalized_remediation_sha256"}
    )
    subject.write_text(json.dumps(changed_subject, sort_keys=True) + "\n")
    changed_review = load_json_closed(review)
    changed_review["subject"]["sha256"] = file_sha256(subject)
    changed_review["reviewed_at"] = "2026-01-02T00:00:00+00:00"
    review.write_text(json.dumps(changed_review, sort_keys=True) + "\n")

    with pytest.raises(ContractError, match="prior_review_binding_required"):
        publish_immutable_review(
            repository_root=tmp_path,
            evidence_root=Path("evidence"),
            subject_path=subject_path,
            review_path=review_path,
        )

    replacement = publish_immutable_review(
        repository_root=tmp_path,
        evidence_root=Path("evidence"),
        subject_path=subject_path,
        review_path=review_path,
        prior_review_binding=prior,
    )

    assert replacement["subject"]["sha256"] == file_sha256(subject)
    assert replacement["immutable_path"] != prior_path
    assert (tmp_path / prior_path).is_file()


def _write_pending_materializer_inputs(
    repository: Path,
) -> dict[str, Path]:
    fixture_root = Path("tests/fixtures/retirement_broad_evidence")
    baseline = load_json_closed(fixture_root / "broad_known_failure_baseline.v1.json")
    inputs: dict[str, Path] = {}
    baseline_destination = Path(
        "evidence/implementation-baseline/known-failure-baseline.json"
    )
    baseline_absolute = repository / baseline_destination
    baseline_absolute.parent.mkdir(parents=True, exist_ok=True)
    baseline_absolute.write_text(json.dumps(baseline, sort_keys=True) + "\n")
    inputs["baseline"] = baseline_destination
    baseline_sha = file_sha256(baseline_absolute)
    for role, kind, reviewer, logical_path in (
        (
            "specification_review",
            "specification",
            "spec-reviewer",
            "reviews/implementation-baseline-specification.json",
        ),
        (
            "quality_review",
            "code_quality",
            "quality-reviewer",
            "reviews/implementation-baseline-quality.json",
        ),
    ):
        review = load_json_closed(fixture_root / "review.v1.json")
        review.update(
            {
                "review_kind": kind,
                "reviewer": {"identity": reviewer},
                "result": "approved",
                "subject": {
                    "kind": "implementation_failure_baseline",
                    "path": baseline_destination.as_posix(),
                    "sha256": baseline_sha,
                },
            }
        )
        destination = Path("evidence") / logical_path
        destination_absolute = repository / destination
        destination_absolute.parent.mkdir(parents=True, exist_ok=True)
        destination_absolute.write_text(json.dumps(review, sort_keys=True) + "\n")
        review_bytes = destination_absolute.read_bytes()
        immutable = broad_evidence._derived_immutable_review_path(
            Path("evidence"),
            review["subject"],
            review["review_kind"],
            f"sha256:{hashlib.sha256(review_bytes).hexdigest()}",
        )
        immutable_absolute = repository / immutable
        immutable_absolute.parent.mkdir(parents=True, exist_ok=True)
        immutable_absolute.write_bytes(review_bytes)
        immutable_absolute.chmod(0o444)
        inputs[role] = destination
    return inputs


def test_review_binding_derivation_requires_one_declared_evidence_root() -> None:
    review = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence/review.v1.json")
    )
    review["subject"] = {
        "kind": "implementation_failure_baseline",
        "path": "evidence/implementation-baseline/known-failure-baseline.json",
        "sha256": f"sha256:{'1' * 64}",
    }
    review_bytes = (json.dumps(review, sort_keys=True) + "\n").encode()

    binding = broad_evidence.derive_review_binding(
        evidence_root=Path("evidence"),
        review_path=Path("evidence/reviews/implementation-baseline-specification.json"),
        review_bytes=review_bytes,
    )
    assert Path("evidence") in Path(binding["immutable_path"]).parents
    with pytest.raises(ContractError, match="review_evidence_root_mismatch"):
        broad_evidence.derive_review_binding(
            evidence_root=Path("different-evidence"),
            review_path=Path("evidence/reviews/implementation-baseline-specification.json"),
            review_bytes=review_bytes,
        )
    review["subject"]["path"] = "outside/known-failure-baseline.json"
    with pytest.raises(ContractError, match="review_evidence_root_mismatch"):
        broad_evidence.derive_review_binding(
            evidence_root=Path("evidence"),
            review_path=Path("evidence/reviews/implementation-baseline-specification.json"),
            review_bytes=(json.dumps(review, sort_keys=True) + "\n").encode(),
        )


def test_review_publisher_rejects_cross_root_before_creating_history(
    tmp_path: Path,
) -> None:
    subject_path = Path("evidence/failure-remediation.json")
    subject = _write_review_subject(tmp_path, subject_path)
    review_path = Path("outside/remediation-specification-review.json")
    review = {
        "schema_version": "review.v1",
        "review_kind": "specification",
        "reviewer": {"identity": "reviewer"},
        "reviewed_at": "2026-01-01T00:00:00+00:00",
        "subject": {
            "kind": "broad_failure_remediation",
            "path": subject_path.as_posix(),
            "sha256": file_sha256(subject),
        },
        "result": "approved",
        "issues": [],
        "claims_not_made": ["Synthetic routing test."],
    }
    _write_producer_json(tmp_path, review_path.as_posix(), review)

    with pytest.raises(ContractError, match="review_evidence_root_mismatch"):
        publish_immutable_review(
            repository_root=tmp_path,
            evidence_root=Path("evidence"),
            subject_path=subject_path,
            review_path=review_path,
        )
    assert not (tmp_path / "evidence/immutable-reviews").exists()


def _write_matching_immutable_review(
    repository: Path, review_path: Path
) -> dict[str, object]:
    review_bytes = (repository / review_path).read_bytes()
    binding = broad_evidence.derive_review_binding(
        evidence_root=Path("evidence"),
        review_path=review_path,
        review_bytes=review_bytes,
    )
    immutable = repository / binding["immutable_path"]
    immutable.parent.mkdir(parents=True, exist_ok=True)
    immutable.write_bytes(review_bytes)
    immutable.chmod(0o444)
    return binding


def test_pending_materializer_never_writes_owner_values(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    inputs = _write_pending_materializer_inputs(repository)
    receipt = materialize_pending(
        repository_root=repository,
        evidence_root=Path("evidence"),
        record_kind="broad-failure-baseline-attestation",
        output_path=Path(
            "evidence/attestations/pre-implementation/broad-failure-baseline.json"
        ),
        generation=1,
        input_paths=inputs,
        parameters={
            "prepared_by": {"identity": "mechanical-writer"},
            "prepared_at": "2026-01-01T00:00:00+00:00",
        },
    )
    result = load_json_closed(repository / receipt.output_path)
    assert validate_record(result) == []
    assert result["evidence_status"] == "pending_owner_confirmation"
    assert result["owner"] is None
    assert result["owner_adoption"] is None
    assert not any(
        value for key, value in result["owner_confirmations"].items() if key != "confirmed_at"
    )

    with pytest.raises(MaterializationError, match="parameter_names_mismatch"):
        materialize_pending(
            repository_root=repository,
            evidence_root=Path("evidence"),
            record_kind="broad-failure-baseline-attestation",
            output_path=Path("evidence/other.json"),
            generation=1,
            input_paths=inputs,
            parameters={
                "prepared_by": {"identity": "mechanical-writer"},
                "prepared_at": "2026-01-01T00:00:00+00:00",
                "owner": {"identity": "forbidden"},
            },
        )


@pytest.mark.parametrize(
    "routing_case",
    ["same-root", "cross-root", "baseline-slot", "specification-slot", "quality-slot"],
)
def test_pending_baseline_adapter_requires_one_canonical_evidence_root_chain(
    tmp_path: Path,
    routing_case: str,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    inputs = _write_pending_materializer_inputs(repository)
    evidence_root = Path("evidence")
    if routing_case == "cross-root":
        evidence_root = Path("different-evidence-root")
    elif routing_case == "baseline-slot":
        inputs["baseline"] = Path(
            "evidence/implementation-baseline/wrong-baseline.json"
        )
    elif routing_case == "specification-slot":
        inputs["specification_review"] = Path(
            "evidence/reviews/wrong-specification.json"
        )
    elif routing_case == "quality-slot":
        inputs["quality_review"] = Path("evidence/reviews/wrong-quality.json")
    output = (
        evidence_root
        / "attestations/pre-implementation/broad-failure-baseline.json"
    )
    kwargs = {
        "repository_root": repository,
        "evidence_root": evidence_root,
        "record_kind": "broad-failure-baseline-attestation",
        "output_path": output,
        "generation": 1,
        "input_paths": inputs,
        "parameters": {
            "prepared_by": {"identity": "mechanical-writer"},
            "prepared_at": "2026-01-01T00:00:00+00:00",
        },
    }

    if routing_case == "same-root":
        receipt = materialize_pending(**kwargs)
        assert receipt.output_path == output
        return

    with pytest.raises(MaterializationError, match="output_slot_invalid"):
        materialize_pending(**kwargs)
    assert not (repository / output).exists()
    assert not (repository / evidence_root / "materialization-inputs").exists()
    assert not (repository / evidence_root / "immutable-outputs").exists()


def test_pending_materializer_rejects_missing_immutable_review_before_publication(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    inputs = _write_pending_materializer_inputs(repository)
    specification_path = inputs["specification_review"]
    specification_bytes = (repository / specification_path).read_bytes()
    specification_binding = broad_evidence.derive_review_binding(
        evidence_root=Path("evidence"),
        review_path=specification_path,
        review_bytes=specification_bytes,
    )
    (repository / specification_binding["immutable_path"]).unlink()

    with pytest.raises(MaterializationError, match="review_pair_invalid"):
        materialize_pending(
            repository_root=repository,
            evidence_root=Path("evidence"),
            record_kind="broad-failure-baseline-attestation",
            output_path=Path(
                "evidence/attestations/pre-implementation/broad-failure-baseline.json"
            ),
            generation=1,
            input_paths=inputs,
            parameters={
                "prepared_by": {"identity": "mechanical-writer"},
                "prepared_at": "2026-01-01T00:00:00+00:00",
            },
        )

    assert not (repository / "evidence/materialization-inputs").exists()
    assert not (repository / "evidence/immutable-outputs").exists()
    assert not (
        repository
        / "evidence/attestations/pre-implementation/broad-failure-baseline.json"
    ).exists()


def test_pending_materializer_rejects_missing_canonical_live_review(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    inputs = _write_pending_materializer_inputs(repository)
    (repository / inputs["quality_review"]).unlink()

    with pytest.raises(MaterializationError, match="publication_path_not_regular"):
        materialize_pending(
            repository_root=repository,
            evidence_root=Path("evidence"),
            record_kind="broad-failure-baseline-attestation",
            output_path=Path(
                "evidence/attestations/pre-implementation/broad-failure-baseline.json"
            ),
            generation=1,
            input_paths=inputs,
            parameters={
                "prepared_by": {"identity": "mechanical-writer"},
                "prepared_at": "2026-01-01T00:00:00+00:00",
            },
        )


def test_pending_materializer_rejects_tampered_immutable_review(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    inputs = _write_pending_materializer_inputs(repository)
    quality_path = inputs["quality_review"]
    quality_binding = broad_evidence.derive_review_binding(
        evidence_root=Path("evidence"),
        review_path=quality_path,
        review_bytes=(repository / quality_path).read_bytes(),
    )
    immutable = repository / quality_binding["immutable_path"]
    immutable.chmod(0o644)
    immutable.write_bytes(b"{}\n")

    with pytest.raises(MaterializationError, match="review_pair_invalid"):
        materialize_pending(
            repository_root=repository,
            evidence_root=Path("evidence"),
            record_kind="broad-failure-baseline-attestation",
            output_path=Path(
                "evidence/attestations/pre-implementation/broad-failure-baseline.json"
            ),
            generation=1,
            input_paths=inputs,
            parameters={
                "prepared_by": {"identity": "mechanical-writer"},
                "prepared_at": "2026-01-01T00:00:00+00:00",
            },
        )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda specification, quality: quality.__setitem__(
            "review_kind", "specification"
        ),
        lambda specification, quality: (
            quality.__setitem__("result", "rejected"),
            quality.__setitem__(
                "issues",
                [
                    {
                        "code": "review-rejected",
                        "path": "$",
                        "message": "not approved",
                    }
                ],
            ),
        ),
        lambda specification, quality: quality.__setitem__(
            "reviewer", specification["reviewer"]
        ),
        lambda specification, quality: quality.__setitem__(
            "subject",
            {
                **quality["subject"],
                "sha256": f"sha256:{'f' * 64}",
            },
        ),
    ],
)
def test_pending_materializer_rejects_invalid_canonical_review_pair(
    tmp_path: Path,
    mutation,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    inputs = _write_pending_materializer_inputs(repository)
    specification_path = inputs["specification_review"]
    quality_path = inputs["quality_review"]
    specification = load_json_closed(repository / specification_path)
    quality = load_json_closed(repository / quality_path)
    mutation(specification, quality)
    (repository / quality_path).write_text(json.dumps(quality, sort_keys=True) + "\n")
    _write_matching_immutable_review(repository, quality_path)

    with pytest.raises(MaterializationError, match="review_pair_invalid"):
        materialize_pending(
            repository_root=repository,
            evidence_root=Path("evidence"),
            record_kind="broad-failure-baseline-attestation",
            output_path=Path(
                "evidence/attestations/pre-implementation/broad-failure-baseline.json"
            ),
            generation=1,
            input_paths=inputs,
            parameters={
                "prepared_by": {"identity": "mechanical-writer"},
                "prepared_at": "2026-01-01T00:00:00+00:00",
            },
        )


def test_materialization_rejects_invalid_adapter_output_before_any_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    handoff = repository / "handoff.json"
    handoff.write_text("{}\n")
    adapter = retirement_materialization.ADAPTERS["query"]
    monkeypatch.setitem(
        retirement_materialization.ADAPTERS,
        "query",
        retirement_materialization.Adapter(
            adapter.input_roles,
            adapter.parameter_names,
            lambda *_: {"schema_version": "unregistered.v1"},
            output_path_validator=adapter.output_path_validator,
        ),
    )

    with pytest.raises(MaterializationError, match="adapter_output_invalid"):
        materialize_transaction(
            repository_root=repository,
            evidence_root=Path("evidence"),
            record_kind="query",
            output_path=Path("evidence/query.json"),
            generation=1,
            input_paths={"handoff": Path("handoff.json")},
            parameters={
                "queue_id": "queue",
                "capture_commit": "0" * 40,
            },
        )

    assert not (repository / "evidence").exists()


def test_pending_materialization_rejects_valid_owner_confirmed_adapter_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    inputs = _write_pending_materializer_inputs(repository)
    adapter = retirement_materialization.ADAPTERS[
        "broad-failure-baseline-attestation"
    ]
    confirmed = load_json_closed(
        Path("tests/fixtures/retirement_broad_evidence")
        / "broad_failure_baseline_attestation.confirmed.v1.json"
    )
    assert validate_record(confirmed) == []
    monkeypatch.setitem(
        retirement_materialization.ADAPTERS,
        "broad-failure-baseline-attestation",
        retirement_materialization.Adapter(
            adapter.input_roles,
            adapter.parameter_names,
            lambda *_: confirmed,
            pending_only=True,
            output_path_validator=adapter.output_path_validator,
        ),
    )

    with pytest.raises(
        MaterializationError, match="adapter_output_pending_invariant_invalid"
    ):
        materialize_pending(
            repository_root=repository,
            evidence_root=Path("evidence"),
            record_kind="broad-failure-baseline-attestation",
            output_path=Path(
                "evidence/attestations/pre-implementation/broad-failure-baseline.json"
            ),
            generation=1,
            input_paths=inputs,
            parameters={
                "prepared_by": {"identity": "mechanical-writer"},
                "prepared_at": "2026-01-01T00:00:00+00:00",
            },
        )

    assert not (repository / "evidence/materialization-inputs").exists()
    assert not (repository / "evidence/immutable-outputs").exists()
    assert not (
        repository
        / "evidence/attestations/pre-implementation/broad-failure-baseline.json"
    ).exists()


def test_junit_builder_maps_collected_node_and_normalizes_payload() -> None:
    xml = b'''<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite tests="2" failures="1" errors="0" skipped="0">
  <testcase classname="tests.test_a" name="test_ok" file="tests/test_a.py" />
  <testcase classname="tests.test_a" name="test_bad" file="tests/test_a.py">
    <failure>/tmp/pytest-of-ci.user+gpu/pytest-12/test_bad0/value.json</failure>
  </testcase>
</testsuite></testsuites>'''
    result = parse_junit_outcomes(
        xml,
        collected_node_ids=["tests/test_a.py::test_bad", "tests/test_a.py::test_ok"],
        repository_root=Path("/repo"),
        pytest_session_parent=Path("/tmp/pytest-of-ci.user+gpu"),
    )
    assert result["totals"] == {
        "collected": 2,
        "passed": 1,
        "failed": 1,
        "errors": 0,
        "skipped": 0,
    }
    assert result["failures"][0]["node_id"] == "tests/test_a.py::test_bad"
    assert result["failures"][0]["normalized_payload"] == "<pytest-tmp>/test_bad0/value.json"


def test_junit_builder_fails_closed_on_unmappable_or_duplicate_testcase() -> None:
    xml = b'''<testsuite tests="1" failures="1" errors="0" skipped="0">
      <testcase classname="x" name="same"><failure>bad</failure></testcase>
    </testsuite>'''
    with pytest.raises(ContractError, match="junit_node_id_unmappable"):
        parse_junit_outcomes(
            xml,
            collected_node_ids=["a.py::same", "b.py::same"],
            repository_root=Path("/repo"),
            pytest_session_parent=Path("/tmp/pytest-of-u"),
        )


@pytest.mark.parametrize(
    ("attribute", "value"),
    [
        ("tests", "x"),
        ("tests", "-1"),
        ("tests", " 0"),
        ("failures", "+0"),
        ("errors", "00"),
        ("skipped", "0 "),
    ],
)
def test_junit_builder_rejects_noncanonical_declared_totals(
    attribute: str, value: str
) -> None:
    attributes = {
        "tests": "0",
        "failures": "0",
        "errors": "0",
        "skipped": "0",
    }
    attributes[attribute] = value
    xml = (
        "<testsuite "
        + " ".join(f'{key}="{item}"' for key, item in attributes.items())
        + "/>"
    ).encode()

    with pytest.raises(
        ContractError, match=rf"^junit_declared_total_invalid:{attribute}$"
    ):
        parse_junit_outcomes(
            xml,
            collected_node_ids=[],
            repository_root=Path("/repo"),
            pytest_session_parent=Path("/tmp/pytest-of-u"),
        )


@pytest.mark.parametrize("missing_attribute", ["tests", "failures", "errors", "skipped"])
def test_junit_builder_requires_every_declared_total(
    missing_attribute: str,
) -> None:
    attributes = {
        "tests": "0",
        "failures": "0",
        "errors": "0",
        "skipped": "0",
    }
    del attributes[missing_attribute]
    xml = (
        "<testsuite "
        + " ".join(f'{key}="{item}"' for key, item in attributes.items())
        + "/>"
    ).encode()

    with pytest.raises(
        ContractError,
        match=rf"^junit_declared_total_invalid:{missing_attribute}$",
    ):
        parse_junit_outcomes(
            xml,
            collected_node_ids=[],
            repository_root=Path("/repo"),
            pytest_session_parent=Path("/tmp/pytest-of-u"),
        )


def test_junit_builder_rejects_empty_testsuites_wrapper() -> None:
    with pytest.raises(ContractError, match=r"^junit_suite_partition_invalid$"):
        parse_junit_outcomes(
            b"<testsuites/>",
            collected_node_ids=[],
            repository_root=Path("/repo"),
            pytest_session_parent=Path("/tmp/pytest-of-u"),
        )


def test_junit_builder_translates_decimal_conversion_failure() -> None:
    xml = (
        '<testsuite tests="'
        + "1" * 5000
        + '" failures="0" errors="0" skipped="0"/>'
    ).encode()

    with pytest.raises(
        ContractError, match=r"^junit_declared_total_invalid:tests$"
    ):
        parse_junit_outcomes(
            xml,
            collected_node_ids=[],
            repository_root=Path("/repo"),
            pytest_session_parent=Path("/tmp/pytest-of-u"),
        )


def test_junit_builder_preserves_double_colon_inside_parameter_id() -> None:
    name = "test_value[private/context::entry]"
    xml = f'''<testsuite tests="1" failures="1" errors="0" skipped="0">
      <testcase classname="tests.test_value" name="{name}" file="tests/test_value.py">
        <failure>bad</failure>
      </testcase>
    </testsuite>'''.encode()
    result = parse_junit_outcomes(
        xml,
        collected_node_ids=[f"tests/test_value.py::{name}"],
        repository_root=Path("/repo"),
        pytest_session_parent=Path("/tmp/pytest-of-u"),
    )
    assert result["failures"][0]["node_id"] == f"tests/test_value.py::{name}"


def test_junit_builder_uses_classname_when_file_is_omitted_and_names_repeat() -> None:
    name = "test_same"
    xml = f'''<testsuite tests="2" failures="1" errors="0" skipped="0">
      <testcase classname="tests.test_first" name="{name}"><failure>bad</failure></testcase>
      <testcase classname="tests.test_second" name="{name}" />
    </testsuite>'''.encode()
    result = parse_junit_outcomes(
        xml,
        collected_node_ids=[
            f"tests/test_first.py::{name}",
            f"tests/test_second.py::{name}",
        ],
        repository_root=Path("/repo"),
        pytest_session_parent=Path("/tmp/pytest-of-u"),
    )
    assert result["failures"][0]["node_id"] == f"tests/test_first.py::{name}"


def test_materialization_live_lock_contention_returns_typed_busy(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    plan = repository / "plan.md"
    _write_ledger_plan(plan)
    record = _ledger(Path("plan.md"))
    record["plan_binding"]["sha256"] = f"sha256:{hashlib.sha256(plan.read_bytes()).hexdigest()}"
    record["normalized_ledger_sha256"] = canonical_sha256(record, exclude={"normalized_ledger_sha256"})
    output = Path("evidence/execution-ledger.json")
    key = hashlib.sha256(output.as_posix().encode()).hexdigest()
    lock_path = repository / ".retirement-materialization-locks" / f"{key}.lock"
    lock_path.parent.mkdir()
    with lock_path.open("a+b") as held:
        fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(MaterializationError, match="materialization_busy"):
            materialize_transaction(
                repository_root=repository,
                evidence_root=Path("evidence"),
                record_kind="execution-ledger",
                output_path=output,
                generation=1,
                input_paths={"approved_plan": Path("plan.md")},
                parameters={"record": record},
            )
    assert not (repository / "evidence").exists()


def test_materialization_recovers_exact_request_only_crash_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import orchestrator.retirement.materialization as module

    repository = tmp_path / "repo"
    repository.mkdir()
    plan = repository / "plan.md"
    _write_ledger_plan(plan)
    record = _ledger(Path("plan.md"))
    record["plan_binding"]["sha256"] = f"sha256:{hashlib.sha256(plan.read_bytes()).hexdigest()}"
    record["normalized_ledger_sha256"] = canonical_sha256(record, exclude={"normalized_ledger_sha256"})
    original = module._exclusive_identical
    calls = 0

    def crash_before_snapshot(root: Path, path: Path, data: bytes) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("injected crash")
        original(root, path, data)

    monkeypatch.setattr(module, "_exclusive_identical", crash_before_snapshot)
    kwargs = dict(
        repository_root=repository,
        evidence_root=Path("evidence"),
        record_kind="execution-ledger",
        output_path=Path("evidence/execution-ledger.json"),
        generation=1,
        input_paths={"approved_plan": Path("plan.md")},
        parameters={"record": record},
    )
    with pytest.raises(RuntimeError, match="injected crash"):
        materialize_transaction(**kwargs)
    assert len(list((repository / "evidence/materialization-inputs").rglob("*.json"))) == 1
    assert not list((repository / "evidence/immutable-outputs").rglob("*.json"))
    assert not (repository / "evidence/execution-ledger.json").exists()

    monkeypatch.setattr(module, "_exclusive_identical", original)
    receipt = materialize_transaction(**kwargs)
    assert (repository / receipt.output_path).read_bytes() == (
        repository / receipt.snapshot_path
    ).read_bytes()


_MATERIALIZATION_SUBPROCESS = r"""
import json
import sys
from pathlib import Path

import orchestrator.retirement.materialization as materialization

config = json.loads(Path(sys.argv[1]).read_text())
boundary = sys.argv[2] if len(sys.argv) == 3 else None

if boundary is not None:
    def hold_at_boundary(observed):
        if observed == boundary:
            print(json.dumps({"status": "boundary", "boundary": observed}), flush=True)
            sys.stdin.read(1)

    materialization._materialization_boundary = hold_at_boundary

kwargs = {
    "repository_root": Path(config["repository_root"]),
    "evidence_root": Path("evidence"),
    "record_kind": "execution-ledger",
    "output_path": Path("evidence/execution-ledger.json"),
    "generation": 1,
    "input_paths": {"approved_plan": Path("plan.md")},
    "parameters": {"record": config["record"]},
}
try:
    receipt = materialization.materialize_transaction(**kwargs)
except materialization.MaterializationError as exc:
    print(json.dumps({"status": "error", "code": exc.code}), flush=True)
else:
    print(json.dumps({"status": "success", "receipt": receipt.as_dict()}), flush=True)
"""


def _subprocess_materialization_config(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    repository = tmp_path / "repo"
    repository.mkdir()
    plan = repository / "plan.md"
    _write_ledger_plan(plan)
    record = _ledger(Path("plan.md"))
    record["plan_binding"]["sha256"] = (
        f"sha256:{hashlib.sha256(plan.read_bytes()).hexdigest()}"
    )
    record["normalized_ledger_sha256"] = canonical_sha256(
        record, exclude={"normalized_ledger_sha256"}
    )
    config = tmp_path / "materialization-config.json"
    config.write_text(
        json.dumps({"repository_root": str(repository), "record": record}) + "\n"
    )
    return repository, config, record


def _start_materialization_subprocess(
    config: Path, *, boundary: str | None = None
) -> subprocess.Popen[str]:
    command = [sys.executable, "-c", _MATERIALIZATION_SUBPROCESS, str(config)]
    if boundary is not None:
        command.append(boundary)
    return subprocess.Popen(
        command,
        cwd=Path(__file__).resolve().parents[1],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _bounded_subprocess_readline(
    stream: object, *, timeout_seconds: float = 10.0
) -> str:
    """Read one text line without allowing a partial line to block forever."""

    if timeout_seconds <= 0:
        raise ValueError("subprocess_readiness_timeout_invalid")
    fileno = stream.fileno()
    encoding = getattr(stream, "encoding", None) or "utf-8"
    errors = getattr(stream, "errors", None) or "strict"
    deadline = time.monotonic() + timeout_seconds
    payload = bytearray()
    selector = selectors.DefaultSelector()
    try:
        selector.register(fileno, selectors.EVENT_READ)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not selector.select(remaining):
                raise TimeoutError("subprocess_readiness_timeout")
            chunk = os.read(fileno, 1)
            if not chunk:
                if not payload:
                    raise EOFError("subprocess_readiness_eof")
                return payload.decode(encoding, errors)
            payload.extend(chunk)
            if chunk == b"\n":
                return payload.decode(encoding, errors)
    finally:
        selector.close()


def _terminate_and_reap_subprocess(
    process: subprocess.Popen[str], *, timeout_seconds: float = 2.0
) -> None:
    """Stop a test child, reap it, and close every inherited pipe."""

    try:
        if process.poll() is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
        try:
            process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            if process.poll() is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
            process.wait(timeout=timeout_seconds)
    finally:
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None and not stream.closed:
                stream.close()


def test_subprocess_readiness_timeout_and_cleanup_are_bounded() -> None:
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import sys,time; "
                "sys.stdout.write('partial'); sys.stdout.flush(); time.sleep(60)"
            ),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert child.stdout is not None
        with pytest.raises(TimeoutError, match="subprocess_readiness_timeout"):
            _bounded_subprocess_readline(child.stdout, timeout_seconds=0.05)
        _terminate_and_reap_subprocess(child, timeout_seconds=1.0)
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=2)
        for stream in (child.stdin, child.stdout, child.stderr):
            if stream is not None and not stream.closed:
                stream.close()

    assert child.poll() is not None


@pytest.mark.parametrize(
    ("boundary", "request_count", "snapshot_count"),
    [
        ("after_request_creation", 1, 0),
        ("before_snapshot_publication", 1, 0),
        ("after_snapshot_publication", 1, 1),
        ("before_live_publication", 1, 1),
    ],
)
def test_crashed_subprocess_holder_replays_exact_generation_after_kernel_release(
    tmp_path: Path, boundary: str, request_count: int, snapshot_count: int
) -> None:
    repository, config, record = _subprocess_materialization_config(tmp_path)
    holder: subprocess.Popen[str] | None = None
    contender: subprocess.Popen[str] | None = None
    try:
        holder = _start_materialization_subprocess(config, boundary=boundary)
        assert holder.stdout is not None
        observed = json.loads(_bounded_subprocess_readline(holder.stdout))
        assert observed == {"status": "boundary", "boundary": boundary}

        contender = _start_materialization_subprocess(config)
        contender_stdout, contender_stderr = contender.communicate(timeout=10)
        assert contender.returncode == 0, contender_stderr
        assert json.loads(contender_stdout) == {
            "status": "error",
            "code": "materialization_busy",
        }

        holder.kill()
        holder_stdout, holder_stderr = holder.communicate(timeout=10)
        assert holder.returncode is not None
        assert holder_stdout == ""
        assert holder_stderr == ""
        assert len(
            list(
                (repository / "evidence/materialization-inputs").rglob("*.json")
            )
        ) == request_count
        assert len(
            list((repository / "evidence/immutable-outputs").rglob("*.json"))
        ) == snapshot_count
        assert not (repository / "evidence/execution-ledger.json").exists()
    finally:
        if contender is not None:
            _terminate_and_reap_subprocess(contender)
        if holder is not None:
            _terminate_and_reap_subprocess(holder)

    receipt = materialize_transaction(
        repository_root=repository,
        evidence_root=Path("evidence"),
        record_kind="execution-ledger",
        output_path=Path("evidence/execution-ledger.json"),
        generation=1,
        input_paths={"approved_plan": Path("plan.md")},
        parameters={"record": record},
    )

    assert len(list((repository / "evidence/materialization-inputs").rglob("*.json"))) == 1
    assert len(list((repository / "evidence/immutable-outputs").rglob("*.json"))) == 1
    assert (repository / receipt.output_path).read_bytes() == (
        repository / receipt.snapshot_path
    ).read_bytes()
    assert validate_generation(repository, receipt.request_path, receipt.snapshot_path) == []


def test_replay_after_crashed_holder_rejects_changed_exact_slot_without_alternate(
    tmp_path: Path,
) -> None:
    repository, config, record = _subprocess_materialization_config(tmp_path)
    holder: subprocess.Popen[str] | None = None
    try:
        holder = _start_materialization_subprocess(
            config, boundary="after_request_creation"
        )
        assert holder.stdout is not None
        assert json.loads(_bounded_subprocess_readline(holder.stdout)) == {
            "status": "boundary",
            "boundary": "after_request_creation",
        }
        holder.kill()
        holder.communicate(timeout=10)
    finally:
        if holder is not None:
            _terminate_and_reap_subprocess(holder)

    requests = list((repository / "evidence/materialization-inputs").rglob("*.json"))
    assert len(requests) == 1
    original_path = requests[0]
    original_path.write_text("{}\n")

    with pytest.raises(MaterializationError, match="immutable_slot_conflict"):
        materialize_transaction(
            repository_root=repository,
            evidence_root=Path("evidence"),
            record_kind="execution-ledger",
            output_path=Path("evidence/execution-ledger.json"),
            generation=1,
            input_paths={"approved_plan": Path("plan.md")},
            parameters={"record": record},
        )

    assert list((repository / "evidence/materialization-inputs").rglob("*.json")) == [
        original_path
    ]
    assert not list((repository / "evidence/immutable-outputs").rglob("*.json"))
    assert not (repository / "evidence/execution-ledger.json").exists()


def test_retirement_package_contains_no_queue_path_or_repository_labels() -> None:
    authority = load_json_closed(
        Path("docs/plans/2026-07-13-procedure-first-reuse-inventory.json")
    )["yaml_retirement_handoff"]
    queue = next(
        row for row in authority["queues"] if row["queue_id"] == "delete_non_survivor_estate"
    )
    forbidden = {Path(path).name for path in queue["paths"]}
    forbidden.update(
        {
            "agent-orchestration",
            "agent-orchestration-2",
            "EasySpin",
            "PtychoPINN",
            "ptychopinnpaper2",
        }
    )
    production = "\n".join(
        path.read_text() for path in sorted(Path("orchestrator/retirement").glob("*.py"))
    )
    assert sorted(value for value in forbidden if value in production) == []


def test_retirement_package_contains_no_candidate_namespace_defaults() -> None:
    production = "\n".join(
        path.read_text() for path in sorted(Path("orchestrator/retirement").glob("*.py"))
    )
    assert "delete-non-survivor-estate" not in production
    assert "task-01-bootstrap" not in production


def _write_pytest_wrapper(
    path: Path, *, raw_user: str | None, fail_candidate_parent: bool = False
) -> Path:
    failure_patch = ""
    if fail_candidate_parent:
        failure_patch = """
from pathlib import Path
_original_mkdir = Path.mkdir
def _controlled_mkdir(self, *args, **kwargs):
    if self.name == "pytest-of-ci.user+gpu":
        raise OSError("injected candidate-parent failure")
    return _original_mkdir(self, *args, **kwargs)
Path.mkdir = _controlled_mkdir
"""
    path.write_text(
        f"""#!{sys.executable}
import _pytest.tmpdir as _tmpdir
_tmpdir.get_user = lambda: {raw_user!r}
{failure_patch}
from pytest import console_main
raise SystemExit(console_main())
"""
    )
    path.chmod(0o700)
    return path


@pytest.mark.parametrize(
    "raw_user, fail_candidate_parent, resolution, component",
    [
        ("ci.user+gpu", False, "raw_get_user", "ci.user+gpu"),
        (None, False, "missing_user_unknown", "unknown"),
        ("", False, "missing_user_unknown", "unknown"),
        ("ci.user+gpu", True, "mkdir_fallback_unknown", "unknown"),
    ],
)
def test_pytest_temp_preflight_observes_bound_pytest_automatic_basetemp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    raw_user: str | None,
    fail_candidate_parent: bool,
    resolution: str,
    component: str,
) -> None:
    executable = _write_pytest_wrapper(
        tmp_path / "bound-pytest",
        raw_user=raw_user,
        fail_candidate_parent=fail_candidate_parent,
    )
    temp_root = tmp_path / "automatic-root"
    temp_root.mkdir()
    monkeypatch.setenv("PYTEST_DEBUG_TEMPROOT", str(temp_root))

    record = build_pytest_temp_root_preflight(executable)

    assert record["raw_get_user"] == raw_user
    assert record["root_component_resolution"] == resolution
    assert record["root_component"] == component
    assert Path(record["observed_session_parent"]).name == f"pytest-of-{component}"
    assert Path(record["observed_basetemp"]).name.startswith("pytest-")
    assert validate_record(record) == []


@pytest.mark.parametrize(
    "mutate",
    [
        lambda record: record.__setitem__("pytest_version", "8.4.0"),
        lambda record: record["pytest_executable_binding"].__setitem__(
            "sha256", f"sha256:{'0' * 64}"
        ),
        lambda record: record["tmpdir_module_binding"].__setitem__(
            "sha256", f"sha256:{'0' * 64}"
        ),
        lambda record: record.__setitem__(
            "environment_binding", {"PYTEST_DEBUG_TEMPROOT": "/different-root"}
        ),
        lambda record: record.__setitem__("raw_get_user", "different-user"),
        lambda record: record.__setitem__(
            "root_component_resolution", "mkdir_fallback_unknown"
        ),
        lambda record: record.__setitem__("system_temp_root", "/different-root"),
        lambda record: record.__setitem__(
            "observed_session_parent", "/different-root/pytest-of-user"
        ),
        lambda record: record.__setitem__(
            "observed_basetemp", "/different-root/pytest-of-user/pytest-9"
        ),
    ],
)
def test_pytest_temp_preflight_rejects_redigested_semantic_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutate,
) -> None:
    executable = _write_pytest_wrapper(
        tmp_path / "bound-pytest", raw_user="ci.user+gpu"
    )
    temp_root = tmp_path / "automatic-root"
    temp_root.mkdir()
    monkeypatch.setenv("PYTEST_DEBUG_TEMPROOT", str(temp_root))
    record = build_pytest_temp_root_preflight(executable)

    mutate(record)
    record["normalized_record_sha256"] = canonical_sha256(
        record, exclude={"normalized_record_sha256"}
    )

    assert validate_bound_record(record, tmp_path) != []


def test_pytest_temp_preflight_rejects_non_pytest_executable_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = _write_pytest_wrapper(
        tmp_path / "bound-pytest", raw_user="ci.user+gpu"
    )
    temp_root = tmp_path / "automatic-root"
    temp_root.mkdir()
    monkeypatch.setenv("PYTEST_DEBUG_TEMPROOT", str(temp_root))
    record = build_pytest_temp_root_preflight(executable)
    python_executable = Path(sys.executable).resolve()
    record["pytest_executable_binding"] = {
        "path": str(python_executable),
        "sha256": file_sha256(python_executable),
    }
    record["normalized_record_sha256"] = canonical_sha256(
        record, exclude={"normalized_record_sha256"}
    )

    assert validate_bound_record(record, tmp_path) != []


def test_pytest_temp_preflight_rejects_copied_tmpdir_module_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = _write_pytest_wrapper(
        tmp_path / "bound-pytest", raw_user="ci.user+gpu"
    )
    temp_root = tmp_path / "automatic-root"
    temp_root.mkdir()
    monkeypatch.setenv("PYTEST_DEBUG_TEMPROOT", str(temp_root))
    record = build_pytest_temp_root_preflight(executable)
    copied_module = tmp_path / "copied-tmpdir.py"
    copied_module.write_bytes(Path(record["tmpdir_module_binding"]["path"]).read_bytes())
    record["tmpdir_module_binding"] = {
        "path": str(copied_module),
        "sha256": file_sha256(copied_module),
    }
    record["normalized_record_sha256"] = canonical_sha256(
        record, exclude={"normalized_record_sha256"}
    )

    assert validate_bound_record(record, tmp_path) != []


def test_broad_evidence_module_cli_starts_without_runpy_warning() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "orchestrator.retirement.broad_evidence", "--help"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert "RuntimeWarning" not in completed.stderr


def test_preflight_cli_rejects_absolute_output_before_running_probe() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "orchestrator.retirement.broad_evidence",
            "probe-pytest-temp-root",
            "--pytest-executable",
            "/definitely/not/a/pytest/executable",
            "--out",
            "/tmp/escaped-preflight.json",
        ],
        cwd=Path(__file__).parents[1],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert completed.returncode == 2
    assert "preflight_output_path_invalid" in completed.stderr
    assert "pytest_executable_invalid" not in completed.stderr


@pytest.mark.parametrize("output", [Path("../escape.json"), Path("/tmp/escape.json")])
def test_preflight_writer_rejects_non_repository_relative_output(
    tmp_path: Path, output: Path
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    with pytest.raises(ContractError, match="preflight_output_path_invalid"):
        write_json(repository, output, {"status": "safe"})


@pytest.mark.parametrize("link_final", [False, True])
def test_preflight_writer_rejects_symlink_output_components(
    tmp_path: Path, link_final: bool
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "record.json"
    target.write_text("owner bytes\n")
    if link_final:
        (repository / "record.json").symlink_to(target)
        output = Path("record.json")
    else:
        (repository / "linked").symlink_to(outside, target_is_directory=True)
        output = Path("linked/record.json")
    with pytest.raises(ContractError, match="preflight_output_path_invalid"):
        write_json(repository, output, {"status": "safe"})
    assert target.read_text() == "owner bytes\n"


def test_preflight_writer_restores_final_entry_raced_after_last_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    output = repository / "record.json"
    output.write_text("old bytes\n")
    outside = tmp_path / "outside.json"
    outside.write_text("owner bytes\n")
    real_renameat2 = safe_io._renameat2
    raced = False

    def race_after_capture(parent, old_name, new_name, flags):
        nonlocal raced
        if not raced:
            raced = True
            output.unlink()
            output.symlink_to(outside)
        return real_renameat2(parent, old_name, new_name, flags)

    monkeypatch.setattr(safe_io, "_renameat2", race_after_capture)

    with pytest.raises(ContractError, match="preflight_output_concurrent_mutation"):
        write_json(repository, Path(output.name), {"status": "safe"})

    assert output.is_symlink()
    assert output.resolve() == outside
    assert outside.read_bytes() == b"owner bytes\n"


def test_preflight_writer_rejects_detached_logical_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    evidence = repository / "evidence"
    evidence.mkdir()
    detached = repository / "detached"
    real_boundary = safe_io._conditional_publish_boundary
    raced = False

    def detach_parent(stage, parent, temporary_name, destination_name):
        nonlocal raced
        if stage == "before_parent_validation" and not raced:
            raced = True
            evidence.rename(detached)
            evidence.mkdir()
        return real_boundary(stage, parent, temporary_name, destination_name)

    monkeypatch.setattr(safe_io, "_conditional_publish_boundary", detach_parent)

    with pytest.raises(ContractError, match="preflight_output_path_invalid"):
        write_json(
            repository, Path("evidence/record.json"), {"status": "safe"}
        )

    assert not (evidence / "record.json").exists()
    assert not (detached / "record.json").exists()


def _publish_test_review_pair(
    tmp_path: Path,
    *,
    subject_path: Path,
    specification_reviewer: str = "spec-reviewer",
    quality_reviewer: str = "quality-reviewer",
    quality_subject_path: Path | None = None,
    quality_result: str = "approved",
    specification_reviewed_at: str = "2026-01-01T00:00:00+00:00",
    quality_reviewed_at: str = "2026-01-01T00:00:00+00:00",
) -> tuple[dict[str, object], dict[str, object]]:
    subject = _write_review_subject(tmp_path, subject_path)
    quality_subject = subject
    if quality_subject_path is not None:
        quality_subject = tmp_path / quality_subject_path
        quality_subject.parent.mkdir(parents=True, exist_ok=True)
        # Review subjects carry repository bindings, not their own logical path.
        # Copying preserves one frozen Git/index identity for the mismatch test.
        quality_subject.write_bytes(subject.read_bytes())

    independent_subjects = [subject]
    if quality_subject != subject:
        independent_subjects.append(quality_subject)
    for bound_subject in independent_subjects:
        assert validate_bound_record(
            load_json_closed(bound_subject), tmp_path
        ) == []

    bindings: list[dict[str, object]] = []
    for kind, reviewer, reviewed_at, bound_subject, logical_path in (
        (
            "specification",
            specification_reviewer,
            specification_reviewed_at,
            subject,
            subject_path.with_name("remediation-specification-review.json"),
        ),
        (
            "code_quality",
            quality_reviewer,
            quality_reviewed_at,
            quality_subject,
            subject_path.with_name("remediation-quality-review.json"),
        ),
    ):
        result = quality_result if kind == "code_quality" else "approved"
        review = {
            "schema_version": "review.v1",
            "review_kind": kind,
            "reviewer": {"identity": reviewer},
            "subject": {
                "kind": "broad_failure_remediation",
                "path": bound_subject.relative_to(tmp_path).as_posix(),
                "sha256": file_sha256(bound_subject),
            },
            "result": result,
            "issues": (
                []
                if result == "approved"
                else [
                    {
                        "code": "fixture_rejection",
                        "path": "$.subject",
                        "message": "fixture rejection",
                    }
                ]
            ),
            "reviewed_at": reviewed_at,
            "claims_not_made": ["Review does not authorize mutation."],
        }
        absolute_review = tmp_path / logical_path
        absolute_review.parent.mkdir(parents=True, exist_ok=True)
        absolute_review.write_text(json.dumps(review, sort_keys=True) + "\n")
        bindings.append(
            publish_immutable_review(
                repository_root=tmp_path,
                evidence_root=Path("evidence"),
                subject_path=bound_subject.relative_to(tmp_path),
                review_path=logical_path,
            )
        )
    return bindings[0], bindings[1]


def test_wrong_subject_pair_reuses_one_frozen_subject_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    subject_path = Path("evidence/failure-remediation.json")
    alternate_path = Path("evidence/other/failure-remediation.json")
    original = _write_review_subject
    calls: list[Path] = []
    first_subject: Path | None = None

    def track_setup(repository: Path, logical_path: Path) -> Path:
        nonlocal first_subject
        calls.append(logical_path)
        if first_subject is None:
            first_subject = original(repository, logical_path)
            return first_subject
        alternate = repository / logical_path
        alternate.parent.mkdir(parents=True, exist_ok=True)
        alternate.write_bytes(first_subject.read_bytes())
        return alternate

    monkeypatch.setattr(
        sys.modules[__name__], "_write_review_subject", track_setup
    )

    specification, quality = _publish_test_review_pair(
        tmp_path,
        subject_path=subject_path,
        quality_subject_path=alternate_path,
    )

    for logical_path in (subject_path, alternate_path):
        assert validate_bound_record(
            load_json_closed(tmp_path / logical_path), tmp_path
        ) == []
    assert (tmp_path / subject_path).read_bytes() == (
        tmp_path / alternate_path
    ).read_bytes()
    assert calls == [subject_path]
    assert quality["logical_path"] == subject_path.with_name(
        "remediation-quality-review.json"
    ).as_posix()
    quality_review = load_json_closed(tmp_path / quality["logical_path"])
    assert quality_review["subject"]["path"] == alternate_path.as_posix()
    assert broad_evidence.validate_review_pair(
        specification_binding=specification,
        quality_binding=quality,
        repository_root=tmp_path,
        expected_subject_kind="broad_failure_remediation",
    ) == [
        broad_evidence.Issue(
            "review_pair_subject_mismatch", "$.subject"
        )
    ]


def test_review_pair_validates_complete_immutable_bindings_and_subject(
    tmp_path: Path,
) -> None:
    assert retirement.validate_review_pair is broad_evidence.validate_review_pair
    subject_path = Path("evidence/failure-remediation.json")
    specification, quality = _publish_test_review_pair(
        tmp_path, subject_path=subject_path
    )

    assert broad_evidence.validate_review_pair(
        specification_binding=specification,
        quality_binding=quality,
        repository_root=tmp_path,
        expected_subject_kind="broad_failure_remediation",
        expected_subject_binding={
            "path": subject_path.as_posix(),
            "sha256": file_sha256(tmp_path / subject_path),
        },
    ) == []

    # Historical validation consumes immutable snapshots, not replaceable live bytes.
    (tmp_path / specification["logical_path"]).write_text("replaced live bytes\n")
    assert broad_evidence.validate_review_pair(
        specification_binding=specification,
        quality_binding=quality,
        repository_root=tmp_path,
        expected_subject_kind="broad_failure_remediation",
    ) == []


def test_review_pair_rejects_quality_timestamp_before_specification(
    tmp_path: Path,
) -> None:
    specification, quality = _publish_test_review_pair(
        tmp_path,
        subject_path=Path("evidence/failure-remediation.json"),
        specification_reviewed_at="2026-01-02T00:00:00+00:00",
        quality_reviewed_at="2026-01-01T00:00:00+00:00",
    )

    assert broad_evidence.validate_review_pair(
        specification_binding=specification,
        quality_binding=quality,
        repository_root=tmp_path,
        expected_subject_kind="broad_failure_remediation",
    ) == [
        broad_evidence.Issue(
            "review_pair_timestamp_order_invalid", "$.reviewed_at"
        )
    ]

@pytest.mark.parametrize(
    "variant",
    [
        "rejected",
        "same_reviewer",
        "wrong_subject",
        "wrong_live_name",
        "mutable_live_only",
    ],
)
def test_review_pair_fails_closed_for_incomplete_or_inconsistent_authority(
    tmp_path: Path, variant: str
) -> None:
    subject_path = Path("evidence/failure-remediation.json")
    specification, quality = _publish_test_review_pair(
        tmp_path,
        subject_path=subject_path,
        quality_result="rejected" if variant == "rejected" else "approved",
        quality_reviewer=(
            "spec-reviewer" if variant == "same_reviewer" else "quality-reviewer"
        ),
        quality_subject_path=(
            Path("evidence/other/failure-remediation.json")
            if variant == "wrong_subject"
            else None
        ),
    )
    if variant == "mutable_live_only":
        specification = {
            "path": specification["logical_path"],
            "sha256": specification["sha256"],
        }
    elif variant == "wrong_live_name":
        quality["logical_path"] = "evidence/quality-latest.json"
        quality["normalized_binding_sha256"] = canonical_sha256(
            quality, exclude={"normalized_binding_sha256"}
        )

    issues = broad_evidence.validate_review_pair(
        specification_binding=specification,
        quality_binding=quality,
        repository_root=tmp_path,
        expected_subject_kind="broad_failure_remediation",
    )
    if variant == "wrong_subject":
        assert issues == [
            broad_evidence.Issue(
                "review_pair_subject_mismatch", "$.subject"
            )
        ]
    else:
        assert issues


def test_review_pair_reopens_subject_bytes_no_follow(tmp_path: Path) -> None:
    subject_path = Path("evidence/failure-remediation.json")
    specification, quality = _publish_test_review_pair(
        tmp_path, subject_path=subject_path
    )
    subject = tmp_path / subject_path
    subject.unlink()
    subject.symlink_to(tmp_path / specification["immutable_path"])

    assert broad_evidence.validate_review_pair(
        specification_binding=specification,
        quality_binding=quality,
        repository_root=tmp_path,
        expected_subject_kind="broad_failure_remediation",
    )
