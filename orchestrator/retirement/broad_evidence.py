"""Closed, queue-neutral evidence contracts used by retirement programs.

This module intentionally does not execute pytest and never chooses ownership,
review verdicts, or adoption values.  It validates and derives deterministic
records from caller-supplied files and machine observations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .safe_io import (
    AtomicPublishError,
    BoundLogicalParent,
    BoundRegularFile,
    bind_logical_parent,
    capture_regular_file_at,
    conditional_quarantine_file_at,
    conditional_publish_file_at,
    logical_parent_matches,
)


SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
HEX_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

FAILURE_BASELINE_ATTESTATION_CLAIMS_NOT_MADE = (
    "Pending status alone is not owner adoption; this attestation does not "
    "authorize source, store, workflow, run-root, or repository mutation or "
    "out-of-scope remediation.",
)
ANSI_CSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
ASCII_PATH_BOUNDARY = " \t\r\n\f\v\"'([{=:`"
PREFIX_BOUNDARY = frozenset(ASCII_PATH_BOUNDARY)
BROAD_KNOWN_FAILURE_BASELINE_V1_FAILURE_COUNT = 6
BROAD_EVIDENCE_BOOTSTRAP_V1_FAILURE_COUNT = 6


@dataclass(frozen=True)
class Issue:
    code: str
    path: str = "$"
    message: str = ""

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Issue):
            return NotImplemented
        return (self.path, self.code, self.message) < (
            other.path,
            other.code,
            other.message,
        )


class ContractError(ValueError):
    """Raised when bytes cannot be decoded as a closed contract."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def canonical_sha256(value: Any, *, exclude: set[str] | None = None) -> str:
    if exclude:
        if not isinstance(value, Mapping):
            raise TypeError("digest projection must be an object")
        value = {key: item for key, item in value.items() if key not in exclude}
    return f"sha256:{hashlib.sha256(canonical_json_bytes(value)).hexdigest()}"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def parse_exit_bytes(raw: bytes) -> int:
    if not re.fullmatch(rb"(?:0|-[1-9][0-9]*|[1-9][0-9]*)\n", raw):
        raise ContractError("invalid_exit_bytes")
    return int(raw[:-1])


def _reject_duplicate(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"duplicate_json_key:{key}")
        result[key] = value
    return result


def load_json_closed(path: Path) -> Any:
    top_level = head = tree = index_path_result = None
    try:
        return json.loads(path.read_bytes(), object_pairs_hook=_reject_duplicate)
    except ContractError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"invalid_json:{path}:{exc}") from exc


def validate_fixture_manifest(root: Path) -> list[Issue]:
    """Validate the closed manifest and its exact directory contents."""

    manifest_path = root / "manifest.v1.json"
    try:
        manifest = load_json_closed(manifest_path)
    except ContractError as exc:
        return [Issue("fixture_manifest_unreadable", "$", str(exc))]
    expected_keys = {
        "schema_version",
        "fixture_root",
        "rows",
        "fixture_count",
        "normalized_path_set_sha256",
        "normalized_row_set_sha256",
        "claims_not_made",
    }
    if not isinstance(manifest, Mapping) or set(manifest) != expected_keys:
        return [Issue("fixture_manifest_keys_mismatch")]
    if manifest["schema_version"] != "retirement_fixture_manifest.v1":
        return [Issue("fixture_manifest_schema_invalid")]
    if (
        not isinstance(manifest["fixture_root"], str)
        or not manifest["fixture_root"]
        or type(manifest["fixture_count"]) is not int
        or manifest["fixture_count"] < 0
    ):
        return [Issue("fixture_manifest_values_invalid")]
    try:
        observed_root = root.resolve(strict=True).relative_to(
            Path.cwd().resolve(strict=True)
        ).as_posix()
    except (OSError, ValueError):
        observed_root = None
    fixture_root_mismatch = manifest["fixture_root"] != observed_root
    if not _is_nonempty_string_list(manifest["claims_not_made"]):
        return [Issue("fixture_claims_invalid", "$.claims_not_made")]
    rows = manifest["rows"]
    if not isinstance(rows, list):
        return [Issue("fixture_rows_invalid")]
    row_keys = {
        "path",
        "schema_version",
        "lifecycle_role",
        "expected_validation",
        "file_sha256",
    }
    if any(not isinstance(row, Mapping) or set(row) != row_keys for row in rows):
        return [Issue("fixture_row_keys_mismatch")]
    if any(
        not isinstance(row["path"], str)
        or not row["path"]
        or not isinstance(row["schema_version"], str)
        or not row["schema_version"]
        or not isinstance(row["lifecycle_role"], str)
        or not row["lifecycle_role"]
        or row["expected_validation"] not in {"accepted", "rejected"}
        or not _is_sha256(row["file_sha256"])
        for row in rows
    ):
        return [Issue("fixture_row_values_invalid")]
    paths = [row["path"] for row in rows]
    actual_paths = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path != manifest_path
    )
    if paths != sorted(paths) or len(paths) != len(set(paths)) or paths != actual_paths:
        return [Issue("fixture_path_set_mismatch")]
    issues: list[Issue] = []
    if fixture_root_mismatch:
        issues.append(Issue("fixture_root_mismatch", "$.fixture_root"))
    if manifest["fixture_count"] != len(rows):
        issues.append(Issue("fixture_count_mismatch"))
    if manifest["normalized_path_set_sha256"] != canonical_sha256(paths):
        issues.append(Issue("fixture_path_digest_mismatch"))
    if manifest["normalized_row_set_sha256"] != canonical_sha256(rows):
        issues.append(Issue("fixture_row_digest_mismatch"))
    seen_roles: set[tuple[str, str]] = set()
    source_schemas = {
        "workspace_baseline.v1",
        "bootstrap_workspace_baseline.v1",
        "non_target_queue_sources.v1",
        "query.v1",
        "precommit_control.v1",
    }
    for index, row in enumerate(rows):
        coordinate = (row["schema_version"], row["lifecycle_role"])
        if coordinate in seen_roles:
            issues.append(Issue("fixture_lifecycle_role_duplicate", f"$.rows[{index}]"))
        seen_roles.add(coordinate)
        if row["expected_validation"] not in {"accepted", "rejected"}:
            issues.append(Issue("fixture_expected_validation_invalid", f"$.rows[{index}]"))
        path = root / row["path"]
        if path.is_symlink() or not path.is_file():
            issues.append(Issue("fixture_not_regular", f"$.rows[{index}]"))
        elif row["file_sha256"] != file_sha256(path):
            issues.append(Issue("fixture_file_digest_mismatch", f"$.rows[{index}]"))
        else:
            try:
                fixture = load_json_closed(path)
            except ContractError as exc:
                issues.append(
                    Issue("fixture_record_unreadable", f"$.rows[{index}]", str(exc))
                )
                continue
            actual_schema = (
                fixture.get("schema_version")
                if isinstance(fixture, Mapping)
                else None
            )
            if actual_schema != row["schema_version"]:
                issues.append(
                    Issue("fixture_schema_binding_mismatch", f"$.rows[{index}]")
                )
                continue
            if actual_schema in SCHEMA_KEYS:
                validation_issues: Sequence[Any] = validate_record(fixture)
            elif actual_schema in source_schemas:
                from .source_bindings import validate_workspace_record_shape

                validation_issues = validate_workspace_record_shape(fixture)
            else:
                issues.append(
                    Issue("fixture_schema_not_registered", f"$.rows[{index}]")
                )
                continue
            observed_validation = "rejected" if validation_issues else "accepted"
            if row["expected_validation"] != observed_validation:
                issues.append(
                    Issue(
                        "fixture_expected_validation_mismatch",
                        f"$.rows[{index}]",
                        f"expected={row['expected_validation']}; observed={observed_validation}",
                    )
                )
    return sorted(set(issues))


SCHEMA_KEYS: dict[str, frozenset[str]] = {
    "workflow_retirement_execution_ledger.v1": frozenset(
        {
            "schema_version",
            "plan_binding",
            "task_count",
            "tasks",
            "current_task",
            "last_transition",
            "normalized_ledger_sha256",
            "claims_not_made",
        }
    ),
    "retirement_materialization_request.v1": frozenset(
        {
            "schema_version",
            "record_kind",
            "output_path",
            "generation",
            "prior_generation_binding",
            "input_bindings",
            "parameters",
            "expected_input_set_sha256",
            "normalized_request_sha256",
            "claims_not_made",
        }
    ),
    "pytest_temp_root_preflight.v1": frozenset(
        {
            "schema_version",
            "pytest_executable_binding",
            "pytest_version",
            "tmpdir_module_binding",
            "environment_binding",
            "raw_get_user",
            "root_component_resolution",
            "root_component",
            "system_temp_root",
            "observed_session_parent",
            "observed_basetemp",
            "normalized_record_sha256",
            "claims_not_made",
        }
    ),
    "broad_failure_payload_normalization.v1": frozenset(
        {
            "schema_version",
            "repository_root",
            "pytest_temp_root_preflight_binding",
            "pytest_version",
            "system_temp_root",
            "pytest_root_component",
            "pytest_session_parent",
            "pytest_temp_prefix_rule",
            "ordered_transforms",
            "normalized_contract_sha256",
        }
    ),
    "implementation_focused_report.v1": frozenset(
        {
            "schema_version",
            "task_contract_binding",
            "candidate_binding",
            "execution_ledger_binding",
            "required_commands",
            "commands",
            "command_count",
            "command_set_sha256",
            "outcome",
            "normalized_report_sha256",
            "claims_not_made",
        }
    ),
    "implementation_verification_subject.v1": frozenset(
        {
            "schema_version",
            "task_contract_binding",
            "candidate_binding",
            "execution_ledger_binding",
            "focused_report_binding",
            "broad_outcome_binding",
            "candidate_path_manifest",
            "normalized_subject_sha256",
            "claims_not_made",
        }
    ),
    "broad_evidence_bootstrap_subject.v1": frozenset(
        {
            "schema_version",
            "task_contract_binding",
            "bootstrap_workspace_baseline_binding",
            "candidate_binding",
            "execution_ledger_binding",
            "focused_report_binding",
            "collection_binding",
            "raw_broad_bindings",
            "observed_totals",
            "observed_failed_node_ids",
            "candidate_path_manifest",
            "normalized_subject_sha256",
            "claims_not_made",
        }
    ),
    "broad_outcome.v1": frozenset(
        {
            "schema_version",
            "candidate_binding",
            "execution_ledger_binding",
            "collection",
            "command",
            "environment",
            "collected_node_ids",
            "rs_log",
            "exit_result",
            "junit_report",
            "pytest_temp_root_preflight",
            "failure_normalization",
            "outcomes",
            "run_root_snapshots",
            "known_failure_baseline_binding",
            "approved_remediation_bindings",
            "approved_skip_change_bindings",
            "baseline_comparison",
            "normalized_outcome_sha256",
            "claims_not_made",
        }
    ),
    "broad_known_failure_baseline.v1": frozenset(
        {
            "schema_version",
            "execution_ledger_binding",
            "candidate_binding",
            "collection_binding",
            "broad_outcome_binding",
            "pytest_exit",
            "totals",
            "failures",
            "failure_normalization",
            "normalized_failure_set_sha256",
            "classification_summary",
            "claims_not_made",
        }
    ),
    "broad_failure_remediation.v1": frozenset(
        {
            "schema_version",
            "execution_ledger_binding",
            "candidate_binding",
            "task_scope_binding",
            "baseline_binding",
            "removed_failure_rows",
            "production_diff",
            "focused_regression_evidence",
            "normalized_remediation_sha256",
            "claims_not_made",
        }
    ),
    "broad_skip_change.v1": frozenset(
        {
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
    ),
    "broad_failure_baseline_attestation.v1": frozenset(
        {
            "schema_version",
            "evidence_status",
            "baseline_binding",
            "failure_set_binding",
            "normalization_binding",
            "classification_summary",
            "specification_review_binding",
            "quality_review_binding",
            "owner",
            "owner_confirmations",
            "prepared_by",
            "prepared_at",
            "owner_adoption",
            "claims_not_made",
        }
    ),
    "review.v1": frozenset(
        {
            "schema_version",
            "review_kind",
            "reviewer",
            "reviewed_at",
            "subject",
            "result",
            "issues",
            "claims_not_made",
        }
    ),
    "review_binding.v1": frozenset(
        {
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
    ),
}


DIGEST_FIELDS: dict[str, str | None] = {
    "workflow_retirement_execution_ledger.v1": "normalized_ledger_sha256",
    "retirement_materialization_request.v1": "normalized_request_sha256",
    "pytest_temp_root_preflight.v1": "normalized_record_sha256",
    "broad_failure_payload_normalization.v1": "normalized_contract_sha256",
    "implementation_focused_report.v1": "normalized_report_sha256",
    "implementation_verification_subject.v1": "normalized_subject_sha256",
    "broad_evidence_bootstrap_subject.v1": "normalized_subject_sha256",
    "broad_outcome.v1": "normalized_outcome_sha256",
    "broad_known_failure_baseline.v1": None,
    "broad_failure_remediation.v1": "normalized_remediation_sha256",
    "broad_skip_change.v1": "normalized_skip_change_sha256",
    "broad_failure_baseline_attestation.v1": None,
    "review.v1": None,
    "review_binding.v1": "normalized_binding_sha256",
}


def _keys_issue(record: Mapping[str, Any], schema: str) -> list[Issue]:
    expected = SCHEMA_KEYS[schema]
    actual = frozenset(record)
    if actual == expected:
        return []
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    return [Issue("record_keys_mismatch", "$", f"missing={missing}; extra={extra}")]


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None


def _is_relative_logical_path(value: Any) -> bool:
    if (
        not isinstance(value, str)
        or value in {"", "."}
        or "\x00" in value
        or "\\" in value
    ):
        return False
    path = Path(value)
    return not path.is_absolute() and path.as_posix() == value and ".." not in path.parts


def _is_file_binding(value: Any, *, sized: bool = False) -> bool:
    keys = {"path", "sha256", "size"} if sized else {"path", "sha256"}
    if not isinstance(value, Mapping) or set(value) != keys:
        return False
    if not _is_relative_logical_path(value.get("path")) or not _is_sha256(
        value.get("sha256")
    ):
        return False
    return not sized or (
        type(value.get("size")) is int and value["size"] >= 0
    )


MATERIALIZATION_REQUEST_CONTRACTS: dict[str, dict[str, Any]] = {
    "execution-ledger": {
        "input_roles": frozenset({"approved_plan"}),
        "parameter_keys": frozenset({"record"}),
        "output_suffix": ("execution-ledger.json",),
    },
    "query": {
        "input_roles": frozenset({"handoff"}),
        "parameter_keys": frozenset({"queue_id", "capture_commit"}),
        "output_suffix": ("query.json",),
    },
    "broad-failure-baseline-attestation": {
        "input_roles": frozenset(
            {"baseline", "specification_review", "quality_review"}
        ),
        "parameter_keys": frozenset({"prepared_by", "prepared_at"}),
        "output_suffix": (
            "attestations",
            "pre-implementation",
            "broad-failure-baseline.json",
        ),
    },
}


def _is_candidate_path_row(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and set(value) == {"path", "sha256", "size", "state"}
        and _is_file_binding(
            {key: value[key] for key in ("path", "sha256", "size")}, sized=True
        )
        and isinstance(value["state"], str)
        and value["state"] in {"added", "modified", "deleted"}
    )


def _is_candidate_binding(value: Any) -> bool:
    keys = {
        "head",
        "head_tree",
        "index_sha256",
        "evidence_root_exclusion",
        "candidate_paths",
        "candidate_path_set_sha256",
    }
    if not isinstance(value, Mapping) or set(value) != keys:
        return False
    rows = value["candidate_paths"]
    if (
        not isinstance(value["head"], str)
        or re.fullmatch(r"[0-9a-f]{40}", value["head"]) is None
        or not isinstance(value["head_tree"], str)
        or re.fullmatch(r"[0-9a-f]{40}", value["head_tree"]) is None
        or not _is_sha256(value["index_sha256"])
        or not _is_relative_logical_path(value["evidence_root_exclusion"])
        or not isinstance(rows, list)
        or not rows
        or any(not _is_candidate_path_row(row) for row in rows)
    ):
        return False
    paths = [row["path"] for row in rows]
    return paths == sorted(set(paths)) and value["candidate_path_set_sha256"] == canonical_sha256(rows)


def _is_task_contract_binding(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and set(value)
        == {"plan_path", "plan_sha256", "task_number", "required_command_set_sha256"}
        and _is_relative_logical_path(value["plan_path"])
        and _is_sha256(value["plan_sha256"])
        and type(value["task_number"]) is int
        and 1 <= value["task_number"] <= 17
        and _is_sha256(value["required_command_set_sha256"])
    )


def _is_ledger_binding(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and set(value)
        == {
            "live_path",
            "byte_sha256",
            "schema_version",
            "generation",
            "request_path",
            "request_sha256",
            "snapshot_path",
            "snapshot_sha256",
        }
        and value["schema_version"] == "workflow_retirement_execution_ledger.v1"
        and type(value["generation"]) is int
        and value["generation"] > 0
        and all(
            _is_relative_logical_path(value[field])
            for field in ("live_path", "request_path", "snapshot_path")
        )
        and all(
            _is_sha256(value[field])
            for field in (
                "byte_sha256",
                "request_sha256",
                "snapshot_sha256",
            )
        )
        and value["byte_sha256"] == value["snapshot_sha256"]
    )


def _is_focused_report_binding(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and set(value) == {"path", "sha256", "normalized_report_sha256"}
        and _is_relative_logical_path(value["path"])
        and _is_sha256(value["sha256"])
        and _is_sha256(value["normalized_report_sha256"])
    )


def _is_environment(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and set(value) == {"LC_ALL", "PYTHONHASHSEED", "PYTEST_DEBUG_TEMPROOT"}
        and value["LC_ALL"] == "C.UTF-8"
        and value["PYTHONHASHSEED"] == "0"
        and (value["PYTEST_DEBUG_TEMPROOT"] is None or isinstance(value["PYTEST_DEBUG_TEMPROOT"], str))
    )


def _is_command(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and set(value) == {"argv", "cwd"}
        and isinstance(value["argv"], list)
        and bool(value["argv"])
        and all(isinstance(arg, str) and arg for arg in value["argv"])
        and value["cwd"] == "."
    )


def _is_collection(value: Any) -> bool:
    keys = {
        "argv",
        "cwd",
        "environment",
        "log_binding",
        "exit_binding",
        "parsed_exit",
        "node_ids_binding",
        "node_id_count",
        "node_id_list_sha256",
    }
    return (
        isinstance(value, Mapping)
        and set(value) == keys
        and _is_command({"argv": value["argv"], "cwd": value["cwd"]})
        and _is_environment(value["environment"])
        and _is_file_binding(value["log_binding"], sized=True)
        and _is_file_binding(value["exit_binding"], sized=True)
        and type(value["parsed_exit"]) is int
        and value["parsed_exit"] == 0
        and _is_file_binding(value["node_ids_binding"], sized=True)
        and type(value["node_id_count"]) is int
        and value["node_id_count"] >= 0
        and _is_sha256(value["node_id_list_sha256"])
    )


def _is_sorted_unique_strings(value: Any, *, nonempty: bool = False) -> bool:
    return (
        isinstance(value, list)
        and (not nonempty or bool(value))
        and all(isinstance(item, str) and bool(item) for item in value)
        and value == sorted(set(value))
    )


def _is_nonempty_string_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and bool(item) for item in value)
    )


def _is_totals(value: Any) -> bool:
    keys = {"collected", "passed", "failed", "errors", "skipped"}
    return (
        isinstance(value, Mapping)
        and set(value) == keys
        and all(type(value[key]) is int and value[key] >= 0 for key in keys)
        and value["collected"]
        == sum(value[key] for key in ("passed", "failed", "errors", "skipped"))
    )


def _is_classified_failure_row(value: Any) -> bool:
    keys = {
        "node_id",
        "outcome_kind",
        "failure_payload_sha256",
        "ownership_class",
        "ownership_basis",
        "authorized_remediation_scope",
    }
    if (
        not isinstance(value, Mapping)
        or set(value) != keys
        or not isinstance(value["node_id"], str)
        or not value["node_id"]
        or not isinstance(value["outcome_kind"], str)
        or value["outcome_kind"] not in {"failure", "error"}
        or not _is_sha256(value["failure_payload_sha256"])
        or not isinstance(value["ownership_class"], str)
        or value["ownership_class"] not in {"queue_owned", "external"}
        or not _is_sorted_unique_strings(value["ownership_basis"], nonempty=True)
        or any(
            not _is_relative_logical_path(path) for path in value["ownership_basis"]
        )
        or not _is_sorted_unique_strings(value["authorized_remediation_scope"])
        or any(
            not _is_relative_logical_path(path)
            for path in value["authorized_remediation_scope"]
        )
    ):
        return False
    return (
        bool(value["authorized_remediation_scope"])
        if value["ownership_class"] == "queue_owned"
        else value["authorized_remediation_scope"] == []
    )


def _is_focused_environment(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and set(value) == {"LC_ALL", "PYTHONHASHSEED"}
        and value["LC_ALL"] == "C.UTF-8"
        and value["PYTHONHASHSEED"] == "0"
    )


def _is_focused_required_command(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and set(value) == {"role_id", "argv", "cwd", "environment"}
        and isinstance(value["role_id"], str)
        and re.fullmatch(r"[a-z0-9][a-z0-9-]*", value["role_id"]) is not None
        and isinstance(value["argv"], list)
        and bool(value["argv"])
        and all(isinstance(arg, str) and bool(arg) for arg in value["argv"])
        and value["cwd"] == "."
        and _is_focused_environment(value["environment"])
    )


def _is_focused_observed_command(value: Any) -> bool:
    observed_keys = {
        "role_id",
        "argv",
        "cwd",
        "environment",
        "input_bindings",
        "started_at",
        "finished_at",
        "log_binding",
        "exit_binding",
        "parsed_exit",
        "outcome",
    }
    return (
        isinstance(value, Mapping)
        and set(value) == observed_keys
        and _is_focused_required_command(
            {key: value[key] for key in ("role_id", "argv", "cwd", "environment")}
        )
        and isinstance(value["input_bindings"], list)
        and all(_is_file_binding(binding) for binding in value["input_bindings"])
        and isinstance(value["started_at"], str)
        and isinstance(value["finished_at"], str)
        and _is_file_binding(value["log_binding"])
        and _is_file_binding(value["exit_binding"])
        and type(value["parsed_exit"]) is int
        and value["parsed_exit"] == 0
        and value["outcome"] == "passed"
    )


def _validate_focused_report_nested(record: Mapping[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    for field, validator in (
        ("task_contract_binding", _is_task_contract_binding),
        ("candidate_binding", _is_candidate_binding),
        ("execution_ledger_binding", _is_ledger_binding),
    ):
        if not validator(record[field]):
            issues.append(Issue("nested_binding_invalid", f"$.{field}"))
    required = record["required_commands"]
    commands = record["commands"]
    if not isinstance(required, list) or not isinstance(commands, list):
        issues.append(Issue("focused_commands_invalid"))
        return issues
    if not required or not commands:
        issues.append(Issue("focused_commands_empty"))
    required_valid = isinstance(required, list) and all(
        _is_focused_required_command(row) for row in required
    )
    commands_valid = isinstance(commands, list) and all(
        _is_focused_observed_command(row) for row in commands
    )
    if not required_valid:
        issues.append(Issue("focused_required_row_invalid"))
    if not commands_valid:
        issues.append(Issue("focused_command_row_invalid"))
    if (
        type(record["command_count"]) is not int
        or record["command_count"] < 0
        or record["command_count"] != len(required)
        or len(commands) != len(required)
    ):
        issues.append(Issue("focused_command_count_mismatch"))
    if required_valid and commands_valid:
        required_keys = {"role_id", "argv", "cwd", "environment"}
        required_roles = [row["role_id"] for row in required]
        command_roles = [row["role_id"] for row in commands]
        if (
            required_roles != command_roles
            and sorted(required_roles) == sorted(command_roles)
        ):
            issues.append(Issue("focused_role_order_mismatch"))
        elif any(
            {key: command[key] for key in required_keys} != dict(required_row)
            for required_row, command in zip(required, commands)
        ):
            issues.append(Issue("focused_command_contract_mismatch"))
    if record["command_set_sha256"] != canonical_sha256(required):
        issues.append(Issue("focused_command_set_digest_mismatch"))
    task = record["task_contract_binding"]
    if (
        _is_task_contract_binding(task)
        and record["command_set_sha256"] != task["required_command_set_sha256"]
    ):
        issues.append(Issue("focused_task_command_set_mismatch"))
    if record["outcome"] != "passed":
        issues.append(Issue("focused_outcome_invalid"))
    return issues


def _validate_known_failure_baseline(record: Mapping[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    for field, validator in (
        ("execution_ledger_binding", _is_ledger_binding),
        ("candidate_binding", _is_candidate_binding),
        ("collection_binding", _is_collection),
        ("broad_outcome_binding", _is_file_binding),
    ):
        if not validator(record[field]):
            issues.append(Issue("nested_binding_invalid", f"$.{field}"))
    pytest_exit = record["pytest_exit"]
    if (
        not isinstance(pytest_exit, Mapping)
        or set(pytest_exit) != {"binding", "parsed_exit"}
        or not _is_file_binding(pytest_exit.get("binding"))
        or type(pytest_exit.get("parsed_exit")) is not int
    ):
        issues.append(Issue("baseline_pytest_exit_invalid", "$.pytest_exit"))
    totals = record["totals"]
    if not _is_totals(totals):
        issues.append(Issue("baseline_totals_invalid", "$.totals"))
    failures = record["failures"]
    if (
        not isinstance(failures, list)
        or not failures
        or any(not _is_classified_failure_row(row) for row in failures)
        or [row["node_id"] for row in failures] != sorted(
            {row["node_id"] for row in failures}
        )
    ):
        issues.append(Issue("baseline_failures_invalid", "$.failures"))
    elif len(failures) != BROAD_KNOWN_FAILURE_BASELINE_V1_FAILURE_COUNT:
        issues.append(Issue("baseline_failure_count_invalid", "$.failures"))
    elif _is_totals(totals) and len(failures) != totals["failed"] + totals["errors"]:
        issues.append(Issue("baseline_failure_count_mismatch", "$.failures"))
    if record["normalized_failure_set_sha256"] != canonical_sha256(failures):
        issues.append(Issue("baseline_failure_set_digest_mismatch"))
    normalization = record["failure_normalization"]
    if (
        not isinstance(normalization, Mapping)
        or normalization.get("schema_version")
        != "broad_failure_payload_normalization.v1"
        or validate_record(normalization)
    ):
        issues.append(Issue("baseline_normalization_invalid"))
    summary = record["classification_summary"]
    expected_summary = None
    if isinstance(failures, list) and all(
        _is_classified_failure_row(row) for row in failures
    ):
        expected_summary = {
            "queue_owned": sum(
                row["ownership_class"] == "queue_owned" for row in failures
            ),
            "external": sum(row["ownership_class"] == "external" for row in failures),
        }
    if (
        not isinstance(summary, Mapping)
        or set(summary) != {"queue_owned", "external"}
        or any(type(summary[key]) is not int or summary[key] < 0 for key in summary)
        or (expected_summary is not None and dict(summary) != expected_summary)
    ):
        issues.append(Issue("baseline_classification_summary_invalid"))
    if _is_totals(totals) and isinstance(pytest_exit, Mapping):
        expected_exit = 1 if totals["failed"] + totals["errors"] else 0
        if pytest_exit.get("parsed_exit") != expected_exit:
            issues.append(Issue("baseline_pytest_exit_semantics_invalid"))
    return issues


def _validate_failure_remediation(record: Mapping[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    for field, validator in (
        ("execution_ledger_binding", _is_ledger_binding),
        ("candidate_binding", _is_candidate_binding),
        ("task_scope_binding", _is_file_binding),
        ("baseline_binding", _is_file_binding),
        ("focused_regression_evidence", _is_file_binding),
    ):
        if not validator(record[field]):
            issues.append(Issue("nested_binding_invalid", f"$.{field}"))
    removed = record["removed_failure_rows"]
    if (
        not isinstance(removed, list)
        or not removed
        or any(
            not _is_classified_failure_row(row)
            or row["ownership_class"] != "queue_owned"
            for row in removed
        )
        or [row["node_id"] for row in removed]
        != sorted({row["node_id"] for row in removed})
    ):
        issues.append(Issue("remediation_failure_rows_invalid"))
    production = record["production_diff"]
    candidate = record["candidate_binding"]
    if (
        not isinstance(production, list)
        or not production
        or any(not _is_candidate_path_row(row) for row in production)
        or [row["path"] for row in production]
        != sorted({row["path"] for row in production})
        or (
            _is_candidate_binding(candidate)
            and any(row not in candidate["candidate_paths"] for row in production)
        )
    ):
        issues.append(Issue("remediation_production_diff_invalid"))
    return issues


def _is_predecessor_skip_set_binding(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and set(value) == {"path", "sha256", "skip_node_ids", "skip_set_sha256"}
        and _is_file_binding({"path": value["path"], "sha256": value["sha256"]})
        and _is_sorted_unique_strings(value["skip_node_ids"])
        and value["skip_set_sha256"] == canonical_sha256(value["skip_node_ids"])
    )


def _validate_skip_change(record: Mapping[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    for field, validator in (
        ("execution_ledger_binding", _is_ledger_binding),
        ("candidate_binding", _is_candidate_binding),
        ("predecessor_skip_set_binding", _is_predecessor_skip_set_binding),
        ("focused_regression_evidence", _is_file_binding),
    ):
        if not validator(record[field]):
            issues.append(Issue("nested_binding_invalid", f"$.{field}"))
    added = record["added_skip_node_ids"]
    removed = record["removed_skip_node_ids"]
    if (
        not _is_sorted_unique_strings(added)
        or not _is_sorted_unique_strings(removed)
        or (not added and not removed)
        or set(added) & set(removed)
    ):
        issues.append(Issue("skip_delta_partition_invalid"))
    authorized = record["authorized_diff"]
    candidate = record["candidate_binding"]
    if (
        not isinstance(authorized, list)
        or not authorized
        or any(not _is_candidate_path_row(row) for row in authorized)
        or [row["path"] for row in authorized]
        != sorted({row["path"] for row in authorized})
        or (
            _is_candidate_binding(candidate)
            and any(row not in candidate["candidate_paths"] for row in authorized)
        )
    ):
        issues.append(Issue("skip_authorized_diff_invalid"))
    predecessor = record["predecessor_skip_set_binding"]
    if _is_predecessor_skip_set_binding(predecessor) and _is_sorted_unique_strings(
        added
    ) and _is_sorted_unique_strings(removed):
        prior = set(predecessor["skip_node_ids"])
        if set(added) & prior or not set(removed) <= prior:
            issues.append(Issue("skip_delta_partition_invalid"))
        expected = sorted((prior - set(removed)) | set(added))
        if record["resulting_skip_set_sha256"] != canonical_sha256(expected):
            issues.append(Issue("skip_result_digest_mismatch"))
    elif not _is_sha256(record["resulting_skip_set_sha256"]):
        issues.append(Issue("skip_result_digest_mismatch"))
    return issues


def _inline_subject_evidence_bindings(
    record: Mapping[str, Any],
) -> tuple[dict[str, tuple[str, int | None]], bool]:
    """Return every evidence binding visible without reopening another record."""

    rows: list[tuple[str, str, int | None]] = []
    ledger = record.get("execution_ledger_binding")
    if _is_ledger_binding(ledger):
        rows.extend(
            (
                (ledger["live_path"], ledger["byte_sha256"], None),
                (ledger["request_path"], ledger["request_sha256"], None),
                (ledger["snapshot_path"], ledger["snapshot_sha256"], None),
            )
        )
    focused = record.get("focused_report_binding")
    if _is_focused_report_binding(focused):
        rows.append((focused["path"], focused["sha256"], None))
    if record.get("schema_version") == "implementation_verification_subject.v1":
        broad = record.get("broad_outcome_binding")
        if _is_file_binding(broad):
            rows.append((broad["path"], broad["sha256"], None))
    elif record.get("schema_version") == "broad_evidence_bootstrap_subject.v1":
        baseline = record.get("bootstrap_workspace_baseline_binding")
        if isinstance(baseline, Mapping) and _is_file_binding(
            {"path": baseline.get("path"), "sha256": baseline.get("sha256")}
        ):
            rows.append((baseline["path"], baseline["sha256"], None))
        raw_bindings = record.get("raw_broad_bindings")
        if isinstance(raw_bindings, list):
            for raw in raw_bindings:
                if isinstance(raw, Mapping) and _is_file_binding(
                    {
                        "path": raw.get("path"),
                        "sha256": raw.get("sha256"),
                        "size": raw.get("size"),
                    },
                    sized=True,
                ):
                    rows.append((raw["path"], raw["sha256"], raw["size"]))
    result: dict[str, tuple[str, int | None]] = {}
    valid = True
    for path, digest, size in rows:
        prior = result.get(path)
        if prior is not None and (
            prior[0] != digest
            or (prior[1] is not None and size is not None and prior[1] != size)
        ):
            valid = False
            continue
        result[path] = (
            digest,
            prior[1] if prior is not None and prior[1] is not None else size,
        )
    return result, valid


def _validate_subject_nested(record: Mapping[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    validators = {
        "task_contract_binding": _is_task_contract_binding,
        "candidate_binding": _is_candidate_binding,
        "execution_ledger_binding": _is_ledger_binding,
        "focused_report_binding": _is_focused_report_binding,
    }
    for field, validator in validators.items():
        if not validator(record[field]):
            issues.append(Issue("nested_binding_invalid", f"$.{field}"))
    if record["schema_version"] == "implementation_verification_subject.v1":
        if not _is_file_binding(record["broad_outcome_binding"]):
            issues.append(Issue("nested_binding_invalid", "$.broad_outcome_binding"))
    else:
        baseline = record["bootstrap_workspace_baseline_binding"]
        baseline_keys = {
            "path", "sha256", "head", "index_sha256", "index_file_sha256",
            "index_entries_file_sha256", "status_file_sha256", "archive_sha256",
            "index_entry_count", "index_entry_set_sha256", "dirty_entry_count",
            "dirty_entry_set_sha256", "dirty_path_set_sha256", "normalized_baseline_sha256",
        }
        if (
            not isinstance(baseline, Mapping)
            or set(baseline) != baseline_keys
            or not _is_relative_logical_path(baseline.get("path"))
            or not isinstance(baseline.get("head"), str)
            or re.fullmatch(r"[0-9a-f]{40}", baseline["head"]) is None
            or any(
                not _is_sha256(baseline.get(field))
                for field in baseline_keys - {"path", "head", "index_entry_count", "dirty_entry_count"}
            )
            or type(baseline.get("index_entry_count")) is not int
            or type(baseline.get("dirty_entry_count")) is not int
        ):
            issues.append(
                Issue(
                    "nested_binding_invalid",
                    "$.bootstrap_workspace_baseline_binding",
                )
            )
        if not _is_collection(record["collection_binding"]):
            issues.append(Issue("nested_binding_invalid", "$.collection_binding"))
        raw = record["raw_broad_bindings"]
        required_raw_roles = {
            "collection-log",
            "collection-exit",
            "collected-node-ids",
            "pytest-temp-root-preflight",
            "broad-rs-log",
            "broad-exit",
            "broad-junit",
        }
        raw_valid = (
            isinstance(raw, list)
            and bool(raw)
            and not any(
                not isinstance(row, Mapping)
                or set(row) != {"role_id", "path", "sha256", "size"}
                or not isinstance(row["role_id"], str)
                or not row["role_id"]
                or not _is_file_binding(
                    {key: row[key] for key in ("path", "sha256", "size")},
                    sized=True,
                )
                for row in raw
            )
        )
        if not raw_valid:
            issues.append(Issue("nested_binding_invalid", "$.raw_broad_bindings"))
        elif {row["role_id"] for row in raw} != required_raw_roles or len(raw) != len(
            required_raw_roles
        ):
            issues.append(Issue("raw_broad_role_partition_invalid"))
        totals = record["observed_totals"]
        total_keys = {"collected", "passed", "failed", "errors", "skipped"}
        totals_valid = (
            isinstance(totals, Mapping)
            and set(totals) == total_keys
            and all(type(totals[key]) is int and totals[key] >= 0 for key in total_keys)
            and totals["collected"]
            == sum(totals[key] for key in ("passed", "failed", "errors", "skipped"))
        )
        if not totals_valid:
            issues.append(Issue("observed_totals_invalid", "$.observed_totals"))
        failed = record["observed_failed_node_ids"]
        failed_valid = (
            isinstance(failed, list)
            and all(isinstance(node, str) and bool(node) for node in failed)
            and failed == sorted(set(failed))
            and totals_valid
            and len(failed) == totals["failed"] + totals["errors"]
        )
        if not failed_valid:
            issues.append(
                Issue("observed_failure_partition_invalid", "$.observed_failed_node_ids")
            )
        elif len(failed) != BROAD_EVIDENCE_BOOTSTRAP_V1_FAILURE_COUNT:
            issues.append(
                Issue("observed_failure_count_invalid", "$.observed_failed_node_ids")
            )
        collection_valid = _is_collection(record["collection_binding"])
        if collection_valid and totals_valid:
            if record["collection_binding"]["node_id_count"] != totals["collected"]:
                issues.append(Issue("collection_observed_count_mismatch"))
            if raw_valid:
                by_role = {row.get("role_id"): row for row in raw}
                for role, field in (
                    ("collection-log", "log_binding"),
                    ("collection-exit", "exit_binding"),
                    ("collected-node-ids", "node_ids_binding"),
                ):
                    row = by_role.get(role)
                    bound = record["collection_binding"][field]
                    if (
                        not isinstance(row, Mapping)
                        or row.get("path") != bound["path"]
                        or row.get("sha256") != bound["sha256"]
                    ):
                        issues.append(Issue("collection_raw_binding_mismatch", f"$.{role}"))
    manifest = record["candidate_path_manifest"]
    if (
        not isinstance(manifest, list)
        or not manifest
        or any(not _is_candidate_path_row(row) for row in manifest)
        or [row["path"] for row in manifest] != sorted({row["path"] for row in manifest})
    ):
        issues.append(Issue("candidate_manifest_invalid", "$.candidate_path_manifest"))
    candidate = record["candidate_binding"]
    if _is_candidate_binding(candidate) and isinstance(manifest, list) and all(
        _is_candidate_path_row(row) for row in manifest
    ):
        evidence, evidence_valid = _inline_subject_evidence_bindings(record)
        actual = {row["path"]: row for row in manifest}
        candidate_rows = {row["path"]: row for row in candidate["candidate_paths"]}
        if any(path in candidate_rows for path in evidence):
            evidence_valid = False
        if [actual.get(path) for path in sorted(candidate_rows)] != [
            candidate_rows[path] for path in sorted(candidate_rows)
        ]:
            issues.append(
                Issue(
                    "candidate_manifest_projection_mismatch",
                    "$.candidate_path_manifest",
                )
            )
        expected_paths = set(candidate_rows) | set(evidence)
        exclusion = candidate["evidence_root_exclusion"]
        prefix = exclusion + "/"
        unexplained = set(actual) - expected_paths
        unexplained_outside_evidence = {
            path
            for path in unexplained
            if path != exclusion and not path.startswith(prefix)
        }
        if unexplained_outside_evidence:
            issues.append(
                Issue(
                    "candidate_manifest_projection_mismatch",
                    "$.candidate_path_manifest",
                )
            )
        evidence_rows_valid = expected_paths <= set(actual) and all(
            path == exclusion or path.startswith(prefix) for path in unexplained
        )
        for path, (digest, size) in evidence.items():
            row = actual.get(path)
            if (
                row is None
                or row.get("sha256") != digest
                or row.get("state") != "added"
                or (size is not None and row.get("size") != size)
            ):
                evidence_rows_valid = False
        if not evidence_valid or not evidence_rows_valid:
            issues.append(
                Issue(
                    "candidate_manifest_evidence_projection_mismatch",
                    "$.candidate_path_manifest",
                )
            )
    return issues


def _is_run_root_snapshot(value: Any) -> bool:
    keys = {
        "root_path",
        "root_path_sha256",
        "scope_basis",
        "before_snapshot_sha256",
        "after_snapshot_sha256",
    }
    if not isinstance(value, Mapping) or set(value) != keys:
        return False
    root_path = value["root_path"]
    if not isinstance(root_path, str):
        return False
    path = Path(root_path)
    return (
        path.is_absolute()
        and path.as_posix() == root_path
        and "." not in path.parts
        and ".." not in path.parts
        and value["root_path_sha256"] == canonical_sha256(root_path)
        and isinstance(value["scope_basis"], str)
        and value["scope_basis"] in {"planning_candidate", "owner_supported"}
        and _is_sha256(value["before_snapshot_sha256"])
        and _is_sha256(value["after_snapshot_sha256"])
    )


def _is_reviewed_record_binding(value: Any) -> bool:
    keys = {"record", "specification_review", "quality_review"}
    return (
        isinstance(value, Mapping)
        and set(value) == keys
        and _is_file_binding(value["record"])
        and _is_complete_review_binding(value["specification_review"])
        and _is_complete_review_binding(value["quality_review"])
        and len(
            {
                value["record"]["path"],
                value["specification_review"]["logical_path"],
                value["quality_review"]["logical_path"],
            }
        )
        == len(keys)
    )


def _is_known_failure_baseline_binding(value: Any) -> bool:
    keys = {
        "outcome",
        "record",
        "specification_review",
        "quality_review",
        "owner_attestation",
    }
    return (
        isinstance(value, Mapping)
        and set(value) == keys
        and all(
            _is_file_binding(value[field])
            for field in {"outcome", "record", "owner_attestation"}
        )
        and _is_complete_review_binding(value["specification_review"])
        and _is_complete_review_binding(value["quality_review"])
        and len(
            {
                value["outcome"]["path"],
                value["record"]["path"],
                value["owner_attestation"]["path"],
                value["specification_review"]["logical_path"],
                value["quality_review"]["logical_path"],
            }
        )
        == len(keys)
    )


def _is_reviewed_binding_prefix(value: Any) -> bool:
    if not isinstance(value, list) or any(
        not _is_reviewed_record_binding(row) for row in value
    ):
        return False
    paths = [row["record"]["path"] for row in value]
    return paths == sorted(set(paths))


def _validate_broad_baseline_comparison(
    record: Mapping[str, Any], outcomes: Any
) -> list[Issue]:
    comparison = record["baseline_comparison"]
    keys = {
        "normalization_contract_sha256",
        "baseline_failure_set_sha256",
        "approved_remediation_set_sha256",
        "observed_failure_set_sha256",
        "removed_failure_node_ids",
        "predecessor_skip_set_sha256",
        "approved_skip_change_set_sha256",
        "observed_skip_set_sha256",
    }
    if (
        not isinstance(comparison, Mapping)
        or set(comparison) != keys
        or any(
            not _is_sha256(comparison[field])
            for field in keys - {"removed_failure_node_ids"}
        )
        or not _is_sorted_unique_strings(comparison.get("removed_failure_node_ids"))
    ):
        return [Issue("baseline_comparison_invalid", "$.baseline_comparison")]
    if not isinstance(outcomes, Mapping):
        return []
    observed_failure_rows = []
    failures = outcomes.get("failures")
    if isinstance(failures, list) and all(isinstance(row, Mapping) for row in failures):
        observed_failure_rows = [
            {
                "node_id": row.get("node_id"),
                "outcome_kind": row.get("outcome_kind"),
                "failure_payload_sha256": row.get("failure_payload_sha256"),
            }
            for row in failures
        ]
    skipped = outcomes.get("skipped_node_ids")
    normalization = record["failure_normalization"]
    normalization_digest = (
        normalization.get("normalized_contract_sha256")
        if isinstance(normalization, Mapping)
        else None
    )
    expected = {
        "normalization_contract_sha256": normalization_digest,
        "approved_remediation_set_sha256": canonical_sha256(
            record["approved_remediation_bindings"]
        ),
        "observed_failure_set_sha256": canonical_sha256(observed_failure_rows),
        "approved_skip_change_set_sha256": canonical_sha256(
            record["approved_skip_change_bindings"]
        ),
        "observed_skip_set_sha256": canonical_sha256(skipped),
    }
    if any(comparison[field] != value for field, value in expected.items()):
        return [Issue("baseline_comparison_mismatch", "$.baseline_comparison")]
    removed = comparison["removed_failure_node_ids"]
    outcome = outcomes.get("outcome")
    remediations = record["approved_remediation_bindings"]
    if (
        (outcome == "known_failures_matched" and (removed or remediations))
        or (outcome == "approved_failure_subset" and (not removed or not remediations))
    ):
        return [Issue("baseline_comparison_mismatch", "$.baseline_comparison")]
    return []


def _validate_broad_outcome_nested(record: Mapping[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    if not _is_candidate_binding(record["candidate_binding"]):
        issues.append(Issue("nested_binding_invalid", "$.candidate_binding"))
    if not _is_ledger_binding(record["execution_ledger_binding"]):
        issues.append(Issue("nested_binding_invalid", "$.execution_ledger_binding"))
    for field in ("rs_log", "junit_report", "pytest_temp_root_preflight"):
        if not _is_file_binding(record[field]):
            issues.append(Issue("nested_binding_invalid", f"$.{field}"))
    collection = record["collection"]
    if not _is_collection(collection):
        issues.append(Issue("nested_binding_invalid", "$.collection"))
    if not _is_command(record["command"]):
        issues.append(Issue("nested_record_invalid", "$.command"))
    if not _is_environment(record["environment"]):
        issues.append(Issue("nested_record_invalid", "$.environment"))
    if (
        _is_collection(collection)
        and _is_environment(record["environment"])
        and collection["environment"] != record["environment"]
    ):
        issues.append(Issue("broad_environment_mismatch", "$.environment"))
    exit_result = record["exit_result"]
    if (
        not isinstance(exit_result, Mapping)
        or set(exit_result) != {"binding", "parsed_exit"}
        or not _is_file_binding(exit_result.get("binding"))
        or type(exit_result.get("parsed_exit")) is not int
    ):
        issues.append(Issue("nested_binding_invalid", "$.exit_result"))
    normalization = record["failure_normalization"]
    if (
        not isinstance(normalization, Mapping)
        or normalization.get("schema_version") != "broad_failure_payload_normalization.v1"
        or validate_record(normalization)
    ):
        issues.append(Issue("nested_record_invalid", "$.failure_normalization"))
    if isinstance(normalization, Mapping) and normalization.get(
        "pytest_temp_root_preflight_binding"
    ) != record["pytest_temp_root_preflight"]:
        issues.append(Issue("preflight_binding_mismatch", "$.failure_normalization"))
    snapshots = record["run_root_snapshots"]
    if (
        not isinstance(snapshots, list)
        or not snapshots
        or any(not _is_run_root_snapshot(row) for row in snapshots)
        or [row["root_path"] for row in snapshots]
        != sorted({row["root_path"] for row in snapshots})
        or len({row["scope_basis"] for row in snapshots}) != 1
    ):
        issues.append(Issue("run_root_snapshots_invalid", "$.run_root_snapshots"))
    elif any(
        row["before_snapshot_sha256"] != row["after_snapshot_sha256"]
        for row in snapshots
    ):
        issues.append(Issue("run_root_snapshot_changed", "$.run_root_snapshots"))
    baseline_binding = record["known_failure_baseline_binding"]
    if baseline_binding is not None and not _is_known_failure_baseline_binding(
        baseline_binding
    ):
        issues.append(
            Issue("baseline_binding_invalid", "$.known_failure_baseline_binding")
        )
    remediations = record["approved_remediation_bindings"]
    if not _is_reviewed_binding_prefix(remediations):
        issues.append(
            Issue("remediation_bindings_invalid", "$.approved_remediation_bindings")
        )
    skip_changes = record["approved_skip_change_bindings"]
    if not _is_reviewed_binding_prefix(skip_changes):
        issues.append(
            Issue("skip_change_bindings_invalid", "$.approved_skip_change_bindings")
        )
    outcomes = record["outcomes"]
    outcome_keys = {"outcome", "totals", "failures", "skipped_node_ids"}
    if not isinstance(outcomes, Mapping) or set(outcomes) != outcome_keys:
        issues.append(Issue("nested_record_invalid", "$.outcomes"))
    else:
        totals = outcomes["totals"]
        failures = outcomes["failures"]
        skipped = outcomes["skipped_node_ids"]
        collected = record["collected_node_ids"]
        outcome_partition_valid = (
            isinstance(outcomes["outcome"], str)
            and outcomes["outcome"]
            in {"baseline_candidate", "known_failures_matched", "approved_failure_subset"}
            and _is_totals(totals)
            and _is_sorted_unique_strings(collected)
            and _is_sorted_unique_strings(skipped)
            and isinstance(failures, list)
        )
        if not outcome_partition_valid:
            issues.append(Issue("outcome_partition_invalid", "$.outcomes"))
        else:
            failure_nodes: list[str] = []
            for row in failures:
                if (
                    not isinstance(row, Mapping)
                    or set(row) != {"node_id", "outcome_kind", "failure_payload_sha256", "normalized_payload"}
                    or not isinstance(row.get("outcome_kind"), str)
                    or row.get("outcome_kind") not in {"failure", "error"}
                    or not _is_sha256(row.get("failure_payload_sha256"))
                    or not isinstance(row.get("normalized_payload"), str)
                    or not isinstance(row.get("node_id"), str)
                ):
                    issues.append(Issue("failure_row_invalid", "$.outcomes.failures"))
                    break
                failure_nodes.append(row["node_id"])
            if (
                failure_nodes != sorted(set(failure_nodes))
                or not set(failure_nodes + skipped) <= set(collected)
                or set(failure_nodes) & set(skipped)
                or len(failure_nodes) != totals["failed"] + totals["errors"]
                or len(skipped) != totals["skipped"]
                or len(collected) != totals["collected"]
                or (_is_collection(collection) and collection["node_id_count"] != len(collected))
            ):
                issues.append(Issue("outcome_partition_mismatch", "$.outcomes"))
            expected_pytest_exit = (
                1 if totals["failed"] + totals["errors"] > 0 else 0
            )
            if (
                isinstance(exit_result, Mapping)
                and exit_result.get("parsed_exit") != expected_pytest_exit
            ):
                issues.append(
                    Issue("broad_exit_semantics_invalid", "$.exit_result.parsed_exit")
                )
        lifecycle = outcomes.get("outcome")
        comparison = record["baseline_comparison"]
        if lifecycle == "baseline_candidate":
            if (
                baseline_binding is not None
                or remediations != []
                or skip_changes != []
                or comparison is not None
            ):
                issues.append(Issue("broad_lifecycle_invalid"))
        else:
            if baseline_binding is None or comparison is None:
                issues.append(Issue("broad_lifecycle_invalid"))
            else:
                issues.extend(_validate_broad_baseline_comparison(record, outcomes))
    return issues


REVIEW_SUBJECT_KINDS = frozenset(
    {
        "broad_evidence_bootstrap",
        "implementation_failure_baseline",
        "implementation_candidate",
        "broad_failure_remediation",
        "broad_skip_change",
        "category_input",
        "batch_assignment",
        "broad_baseline",
        "batch_eligibility",
        "root_scope_pending",
        "root_scope_confirmed",
        "initial_root_bindings_pending",
        "initial_root_bindings_confirmed",
        "batch_owner_pending",
        "batch_owner_confirmed",
        "batch_post_edit",
        "batch_repair",
        "batch_closure",
        "final_closeout",
    }
)

REVIEW_SUBJECT_SCHEMAS = {
    "broad_evidence_bootstrap": "broad_evidence_bootstrap_subject.v1",
    "implementation_failure_baseline": "broad_known_failure_baseline.v1",
    "implementation_candidate": "implementation_verification_subject.v1",
    "broad_failure_remediation": "broad_failure_remediation.v1",
    "broad_skip_change": "broad_skip_change.v1",
    "broad_baseline": "broad_outcome.v1",
}


def validate_review_subject(
    *,
    subject_kind: str,
    record: Any,
    repository_root: Path,
    subject_path: Path | str | None = None,
    permitted_manifest_exclusions: Sequence[str] = (),
) -> list[Issue]:
    expected = REVIEW_SUBJECT_SCHEMAS.get(subject_kind)
    if expected is None:
        return [Issue("review_subject_kind_not_registered", "$.subject.kind")]
    if not isinstance(record, Mapping) or record.get("schema_version") != expected:
        return [Issue("review_subject_schema_mismatch", "$.subject.kind")]
    return validate_bound_record(
        record,
        repository_root,
        review_subject_path=(
            Path(subject_path).as_posix() if subject_path is not None else None
        ),
        permitted_manifest_exclusions=permitted_manifest_exclusions,
    )


def _is_review_subject(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    if set(value) not in (
        {"kind", "path", "sha256"},
        {"kind", "path", "sha256", "commit", "tree"},
    ):
        return False
    if (
        not isinstance(value["kind"], str)
        or value["kind"] not in REVIEW_SUBJECT_KINDS
        or not _is_relative_logical_path(value["path"])
        or not _is_sha256(value["sha256"])
    ):
        return False
    if "commit" in value:
        return (
            isinstance(value["commit"], str)
            and re.fullmatch(r"[0-9a-f]{40}", value["commit"]) is not None
            and isinstance(value["tree"], str)
            and re.fullmatch(r"[0-9a-f]{40}", value["tree"]) is not None
        )
    return True


def _validate_review(record: Mapping[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    if not isinstance(record["review_kind"], str) or record["review_kind"] not in {
        "specification",
        "code_quality",
    }:
        issues.append(Issue("review_kind_invalid", "$.review_kind"))
    if (
        not isinstance(record["reviewer"], Mapping)
        or set(record["reviewer"]) != {"identity"}
        or not isinstance(record["reviewer"]["identity"], str)
        or not record["reviewer"]["identity"]
    ):
        issues.append(Issue("reviewer_invalid", "$.reviewer"))
    try:
        reviewed = datetime.fromisoformat(record["reviewed_at"])
        if reviewed.tzinfo is None:
            raise ValueError
    except (TypeError, ValueError):
        issues.append(Issue("reviewed_at_invalid", "$.reviewed_at"))
    if not _is_review_subject(record["subject"]):
        issues.append(Issue("review_subject_invalid", "$.subject"))
    typed_issues = record["issues"]
    if not isinstance(typed_issues, list) or any(
        not isinstance(issue, Mapping)
        or set(issue) != {"code", "path", "message"}
        or not isinstance(issue["code"], str)
        or not issue["code"]
        or not isinstance(issue["path"], str)
        or not isinstance(issue["message"], str)
        for issue in typed_issues if isinstance(typed_issues, list)
    ):
        issues.append(Issue("review_issues_invalid", "$.issues"))
    if record["result"] == "approved":
        if typed_issues != []:
            issues.append(Issue("approved_review_has_issues", "$.issues"))
    elif record["result"] == "rejected":
        if not isinstance(typed_issues, list) or not typed_issues:
            issues.append(Issue("rejected_review_missing_issues", "$.issues"))
    else:
        issues.append(Issue("review_result_invalid", "$.result"))
    if (
        not isinstance(record["claims_not_made"], list)
        or not record["claims_not_made"]
        or any(
            not isinstance(claim, str) or not claim
            for claim in record["claims_not_made"]
        )
    ):
        issues.append(Issue("review_claims_invalid", "$.claims_not_made"))
    return issues


def _validate_review_binding(record: Mapping[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    if (
        not _is_relative_logical_path(record["logical_path"])
        or not _is_relative_logical_path(record["immutable_path"])
        or not _is_sha256(record["sha256"])
        or not isinstance(record["review_kind"], str)
        or record["review_kind"] not in {"specification", "code_quality"}
        or not _is_review_subject(record["subject"])
        or not isinstance(record["result"], str)
        or record["result"] not in {"approved", "rejected"}
    ):
        issues.append(Issue("review_binding_coordinates_invalid"))
    if (
        not isinstance(record["reviewer"], Mapping)
        or set(record["reviewer"]) != {"identity"}
        or not isinstance(record["reviewer"].get("identity"), str)
        or not record["reviewer"].get("identity")
    ):
        issues.append(Issue("review_binding_reviewer_invalid", "$.reviewer"))
    try:
        reviewed = datetime.fromisoformat(record["reviewed_at"])
        if reviewed.tzinfo is None:
            raise ValueError
    except (TypeError, ValueError):
        issues.append(Issue("review_binding_timestamp_invalid", "$.reviewed_at"))
    if (
        not isinstance(record["claims_not_made"], list)
        or not record["claims_not_made"]
    ):
        issues.append(Issue("review_binding_claims_invalid", "$.claims_not_made"))
    return issues


def _is_complete_review_binding(value: Any) -> bool:
    """Return whether ``value`` is one complete closed review binding.

    This predicate intentionally performs only in-memory schema validation.
    Historical consumers must additionally call :func:`validate_review_pair`
    so both immutable review snapshots and their shared subject are reopened.
    """

    return (
        isinstance(value, Mapping)
        and value.get("schema_version") == "review_binding.v1"
        and not validate_record(value)
    )


def _validate_materialization_request(record: Mapping[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    kind = record["record_kind"]
    contract = MATERIALIZATION_REQUEST_CONTRACTS.get(kind) if isinstance(kind, str) else None
    if contract is None:
        issues.append(Issue("request_record_kind_invalid", "$.record_kind"))

    output = record["output_path"]
    if not _is_relative_logical_path(output):
        issues.append(Issue("request_output_path_invalid", "$.output_path"))
    elif contract is not None:
        suffix = contract["output_suffix"]
        if tuple(Path(output).parts[-len(suffix) :]) != suffix:
            issues.append(Issue("request_output_slot_invalid", "$.output_path"))

    generation = record["generation"]
    if type(generation) is not int or not 1 <= generation <= 99_999_999:
        issues.append(Issue("request_generation_invalid", "$.generation"))

    bindings = record["input_bindings"]
    roles: list[str] = []
    bindings_valid = isinstance(bindings, list)
    if bindings_valid:
        for index, binding in enumerate(bindings):
            if (
                not isinstance(binding, Mapping)
                or set(binding)
                != {"role", "path", "size", "sha256", "schema_version"}
                or not isinstance(binding.get("role"), str)
                or not binding.get("role")
                or not _is_relative_logical_path(binding.get("path"))
                or type(binding.get("size")) is not int
                or binding.get("size", -1) < 0
                or not _is_sha256(binding.get("sha256"))
                or (
                    binding.get("schema_version") is not None
                    and (
                        not isinstance(binding.get("schema_version"), str)
                        or not binding.get("schema_version")
                    )
                )
            ):
                bindings_valid = False
                issues.append(
                    Issue("request_input_binding_invalid", f"$.input_bindings[{index}]")
                )
                continue
            roles.append(binding["role"])
        if roles != sorted(set(roles)):
            bindings_valid = False
            issues.append(Issue("request_input_bindings_invalid", "$.input_bindings"))
        if contract is not None and frozenset(roles) != contract["input_roles"]:
            bindings_valid = False
            issues.append(Issue("request_input_roles_invalid", "$.input_bindings"))
    else:
        issues.append(Issue("request_input_bindings_invalid", "$.input_bindings"))
    if (
        not isinstance(record["expected_input_set_sha256"], str)
        or not _is_sha256(record["expected_input_set_sha256"])
        or not isinstance(bindings, list)
        or record["expected_input_set_sha256"] != canonical_sha256(bindings)
    ):
        issues.append(
            Issue("request_input_set_digest_mismatch", "$.expected_input_set_sha256")
        )

    parameters = record["parameters"]
    if not isinstance(parameters, Mapping):
        issues.append(Issue("request_parameters_invalid", "$.parameters"))
    elif contract is not None and frozenset(parameters) != contract["parameter_keys"]:
        issues.append(Issue("request_parameters_invalid", "$.parameters"))
    elif kind == "execution-ledger":
        nested_record = parameters.get("record")
        nested_issues = (
            validate_record(nested_record)
            if isinstance(nested_record, Mapping)
            and nested_record.get("schema_version")
            == "workflow_retirement_execution_ledger.v1"
            else [Issue("schema_version_mismatch")]
        )
        if nested_issues:
            issues.append(
                Issue(
                    "request_parameter_record_invalid",
                    "$.parameters.record",
                    nested_issues[0].code,
                )
            )
    elif kind == "query" and (
        not isinstance(parameters.get("queue_id"), str)
        or not parameters["queue_id"]
        or not isinstance(parameters.get("capture_commit"), str)
        or re.fullmatch(r"[0-9a-f]{40}", parameters["capture_commit"]) is None
    ):
        issues.append(Issue("request_parameters_invalid", "$.parameters"))
    elif kind == "broad-failure-baseline-attestation" and (
        not isinstance(parameters.get("prepared_by"), Mapping)
        or set(parameters["prepared_by"]) != {"identity"}
        or not isinstance(parameters["prepared_by"].get("identity"), str)
        or not parameters["prepared_by"].get("identity")
        or _aware_timestamp(parameters.get("prepared_at")) is None
    ):
        issues.append(Issue("request_parameters_invalid", "$.parameters"))

    prior = record["prior_generation_binding"]
    if type(generation) is int and generation == 1:
        if prior is not None:
            issues.append(Issue("request_prior_generation_invalid", "$.prior_generation_binding"))
    elif type(generation) is int and generation > 1:
        prior_keys = {
            "request_path",
            "request_sha256",
            "snapshot_path",
            "snapshot_sha256",
            "generation",
            "output_path",
        }
        if (
            not isinstance(prior, Mapping)
            or set(prior) != prior_keys
            or not _is_relative_logical_path(prior.get("request_path"))
            or not _is_relative_logical_path(prior.get("snapshot_path"))
            or not _is_sha256(prior.get("request_sha256"))
            or not _is_sha256(prior.get("snapshot_sha256"))
            or type(prior.get("generation")) is not int
            or prior.get("generation") != generation - 1
            or prior.get("output_path") != output
        ):
            issues.append(Issue("request_prior_generation_invalid", "$.prior_generation_binding"))
    return issues


def _aware_timestamp(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo is not None else None


def _validate_failure_baseline_attestation(
    record: Mapping[str, Any]
) -> list[Issue]:
    issues: list[Issue] = []
    if record["claims_not_made"] != list(
        FAILURE_BASELINE_ATTESTATION_CLAIMS_NOT_MADE
    ):
        issues.append(
            Issue(
                "attestation_claims_not_made_invalid",
                "$.claims_not_made",
            )
        )
    baseline = record["baseline_binding"]
    if (
        not isinstance(baseline, Mapping)
        or set(baseline)
        != {
            "path",
            "sha256",
            "schema_version",
            "candidate_path_set_sha256",
        }
        or not _is_file_binding(
            {"path": baseline.get("path"), "sha256": baseline.get("sha256")}
        )
        or baseline.get("schema_version") != "broad_known_failure_baseline.v1"
        or not _is_sha256(baseline.get("candidate_path_set_sha256"))
    ):
        issues.append(
            Issue("attestation_baseline_binding_invalid", "$.baseline_binding")
        )
    failure_set = record["failure_set_binding"]
    if (
        not isinstance(failure_set, Mapping)
        or set(failure_set)
        != {"failure_count", "normalized_failure_set_sha256"}
        or type(failure_set.get("failure_count")) is not int
        or failure_set.get("failure_count", -1) < 0
        or not _is_sha256(failure_set.get("normalized_failure_set_sha256"))
    ):
        issues.append(
            Issue(
                "attestation_failure_set_binding_invalid",
                "$.failure_set_binding",
            )
        )
    normalization = record["normalization_binding"]
    if (
        not isinstance(normalization, Mapping)
        or set(normalization)
        != {"schema_version", "normalized_contract_sha256"}
        or normalization.get("schema_version")
        != "broad_failure_payload_normalization.v1"
        or not _is_sha256(normalization.get("normalized_contract_sha256"))
    ):
        issues.append(
            Issue(
                "attestation_normalization_binding_invalid",
                "$.normalization_binding",
            )
        )
    classification = record["classification_summary"]
    if (
        not isinstance(classification, Mapping)
        or set(classification) != {"queue_owned", "external"}
        or any(type(classification.get(key)) is not int for key in classification)
        or any(classification[key] < 0 for key in classification)
        or (
            isinstance(failure_set, Mapping)
            and type(failure_set.get("failure_count")) is int
            and sum(classification.values()) != failure_set["failure_count"]
        )
    ):
        issues.append(
            Issue(
                "attestation_classification_summary_invalid",
                "$.classification_summary",
            )
        )
    specification = record["specification_review_binding"]
    quality = record["quality_review_binding"]
    expected_subject = (
        {
            "kind": "implementation_failure_baseline",
            "path": baseline["path"],
            "sha256": baseline["sha256"],
        }
        if isinstance(baseline, Mapping)
        and isinstance(baseline.get("path"), str)
        and isinstance(baseline.get("sha256"), str)
        else None
    )
    if (
        not _is_complete_review_binding(specification)
        or not _is_complete_review_binding(quality)
        or specification.get("review_kind") != "specification"
        or quality.get("review_kind") != "code_quality"
        or specification.get("result") != "approved"
        or quality.get("result") != "approved"
        or specification.get("subject") != expected_subject
        or quality.get("subject") != expected_subject
        or specification.get("reviewer") == quality.get("reviewer")
    ):
        issues.append(
            Issue("attestation_review_binding_invalid", "$.specification_review_binding")
        )
    if isinstance(specification, Mapping) and isinstance(quality, Mapping):
        specification_reviewed = _aware_timestamp(specification.get("reviewed_at"))
        quality_reviewed = _aware_timestamp(quality.get("reviewed_at"))
        if (
            specification_reviewed is not None
            and quality_reviewed is not None
            and specification_reviewed > quality_reviewed
        ):
            issues.append(
                Issue(
                    "review_pair_timestamp_order_invalid",
                    "$.quality_review_binding.reviewed_at",
                )
            )
    prepared_by = record["prepared_by"]
    if (
        not isinstance(prepared_by, Mapping)
        or set(prepared_by) != {"identity"}
        or not isinstance(prepared_by.get("identity"), str)
        or not prepared_by.get("identity")
    ):
        issues.append(
            Issue("attestation_prepared_identity_invalid", "$.prepared_by")
        )
    prepared_at = _aware_timestamp(record["prepared_at"])
    if prepared_at is None:
        issues.append(Issue("attestation_prepared_at_invalid", "$.prepared_at"))
    review_times = [
        _aware_timestamp(binding.get("reviewed_at"))
        for binding in (specification, quality)
        if isinstance(binding, Mapping)
    ]
    if prepared_at is not None and any(
        value is not None and value > prepared_at for value in review_times
    ):
        issues.append(Issue("attestation_timestamp_order_invalid"))

    confirmation_keys = {
        "exact_failure_table_confirmed",
        "normalization_contract_confirmed",
        "classification_partition_confirmed",
        "reviews_confirmed",
        "comparison_only_confirmed",
        "no_out_of_scope_repair_confirmed",
        "confirmed_at",
    }
    confirmations = record["owner_confirmations"]
    if not isinstance(confirmations, Mapping) or set(confirmations) != confirmation_keys:
        issues.append(Issue("owner_confirmation_keys_mismatch"))
        return issues
    status = record["evidence_status"]
    if status == "pending_owner_confirmation":
        if record["owner"] is not None or record["owner_adoption"] is not None:
            issues.append(Issue("pending_owner_fields_nonnull"))
        if confirmations["confirmed_at"] is not None or any(
            confirmations[key] is not False
            for key in confirmation_keys - {"confirmed_at"}
        ):
            issues.append(Issue("pending_confirmation_affirmative"))
        return issues
    if status != "owner_confirmed":
        issues.append(Issue("evidence_status_invalid"))
        return issues

    owner = record["owner"]
    if (
        not isinstance(owner, Mapping)
        or set(owner) != {"identity", "role"}
        or any(not isinstance(owner.get(key), str) or not owner.get(key) for key in owner)
    ):
        issues.append(Issue("attestation_owner_invalid", "$.owner"))
    adoption = record["owner_adoption"]
    owner_identity = owner.get("identity") if isinstance(owner, Mapping) else None
    if (
        not isinstance(adoption, Mapping)
        or set(adoption) != {"identity", "statement", "adopted_at"}
        or adoption.get("identity") != owner_identity
        or not isinstance(adoption.get("statement"), str)
        or not adoption.get("statement")
    ):
        issues.append(
            Issue("attestation_owner_adoption_invalid", "$.owner_adoption")
        )
    if any(
        confirmations[key] is not True
        for key in confirmation_keys - {"confirmed_at"}
    ):
        issues.append(Issue("confirmed_confirmation_incomplete"))
    confirmed_at = _aware_timestamp(confirmations["confirmed_at"])
    if confirmed_at is None:
        issues.append(
            Issue(
                "attestation_confirmation_timestamp_invalid",
                "$.owner_confirmations.confirmed_at",
            )
        )
    adopted_at = (
        _aware_timestamp(adoption.get("adopted_at"))
        if isinstance(adoption, Mapping)
        else None
    )
    if adopted_at is None:
        issues.append(
            Issue(
                "attestation_adoption_timestamp_invalid",
                "$.owner_adoption.adopted_at",
            )
        )
    if (
        prepared_at is not None
        and confirmed_at is not None
        and adopted_at is not None
        and (
            prepared_at > confirmed_at
            or confirmed_at > adopted_at
        )
    ):
        issues.append(Issue("attestation_timestamp_order_invalid"))
    return issues


def validate_record(record: Any) -> list[Issue]:
    if not isinstance(record, Mapping):
        return [Issue("record_not_object")]
    schema = record.get("schema_version")
    if not isinstance(schema, str) or schema not in SCHEMA_KEYS:
        return [Issue("unknown_schema", "$.schema_version", repr(schema))]
    issues = _keys_issue(record, schema)
    if issues:
        return issues
    digest_field = DIGEST_FIELDS[schema]
    if digest_field is not None:
        value = record.get(digest_field)
        if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
            issues.append(Issue("normalized_digest_invalid", f"$.{digest_field}"))
        elif value != canonical_sha256(record, exclude={digest_field}):
            issues.append(Issue("normalized_digest_mismatch", f"$.{digest_field}"))
    if "claims_not_made" in SCHEMA_KEYS[schema] and not _is_nonempty_string_list(
        record["claims_not_made"]
    ):
        issues.append(Issue("claims_not_made_invalid", "$.claims_not_made"))
    if schema == "workflow_retirement_execution_ledger.v1":
        issues.extend(validate_execution_ledger(record, check_base=False))
    elif schema == "retirement_materialization_request.v1":
        issues.extend(_validate_materialization_request(record))
    elif schema in {
        "implementation_verification_subject.v1",
        "broad_evidence_bootstrap_subject.v1",
    }:
        issues.extend(_validate_subject_nested(record))
    elif schema == "review_binding.v1":
        issues.extend(_validate_review_binding(record))
    elif schema == "broad_outcome.v1":
        issues.extend(_validate_broad_outcome_nested(record))
    elif schema == "implementation_focused_report.v1":
        issues.extend(_validate_focused_report_nested(record))
    elif schema == "broad_known_failure_baseline.v1":
        issues.extend(_validate_known_failure_baseline(record))
    elif schema == "broad_failure_remediation.v1":
        issues.extend(_validate_failure_remediation(record))
    elif schema == "broad_skip_change.v1":
        issues.extend(_validate_skip_change(record))
    elif schema == "pytest_temp_root_preflight.v1":
        issues.extend(_validate_pytest_temp_root_preflight(record))
    elif schema == "broad_failure_payload_normalization.v1":
        issues.extend(_validate_failure_payload_normalization(record))
    elif schema == "review.v1":
        issues.extend(_validate_review(record))
    elif schema == "review_binding.v1":
        issues.extend(_validate_review_binding(record))
    elif schema == "broad_failure_baseline_attestation.v1":
        issues.extend(_validate_failure_baseline_attestation(record))
    return sorted(set(issues))


def _bound_path(repository_root: Path, logical_path: Any) -> Path | None:
    if not _is_relative_logical_path(logical_path):
        return None
    return repository_root / logical_path


def _read_repository_file_no_follow(
    repository_root: Path, logical_path: Any
) -> bytes | None:
    if not _is_relative_logical_path(logical_path):
        return None
    components = Path(logical_path).parts
    descriptor: int | None = None
    try:
        descriptor = os.open(
            repository_root,
            os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0),
        )
        for component in components[:-1]:
            child = os.open(
                component,
                os.O_RDONLY
                | os.O_DIRECTORY
                | os.O_NOFOLLOW
                | getattr(os, "O_CLOEXEC", 0),
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = child
        opened = os.open(
            components[-1],
            os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
            dir_fd=descriptor,
        )
        try:
            before = os.fstat(opened)
            if not stat.S_ISREG(before.st_mode):
                return None
            chunks: list[bytes] = []
            while True:
                chunk = os.read(opened, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            after = os.fstat(opened)
            if (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            ) != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            ):
                return None
            return b"".join(chunks)
        finally:
            os.close(opened)
    except OSError:
        return None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _repository_path_absent_no_follow(
    repository_root: Path, logical_path: Any
) -> bool:
    if not _is_relative_logical_path(logical_path):
        return False
    components = Path(logical_path).parts
    descriptor: int | None = None
    traversed: list[str] = []
    try:
        descriptor = os.open(
            repository_root,
            os.O_RDONLY
            | os.O_DIRECTORY
            | os.O_NOFOLLOW
            | getattr(os, "O_CLOEXEC", 0),
        )
        for component in components[:-1]:
            relative_parent = Path(*traversed) if traversed else Path(".")
            try:
                parent_binding = bind_logical_parent(
                    repository_root, relative_parent, descriptor
                )
            except AtomicPublishError:
                return False
            try:
                child = os.open(
                    component,
                    os.O_RDONLY
                    | os.O_DIRECTORY
                    | os.O_NOFOLLOW
                    | getattr(os, "O_CLOEXEC", 0),
                    dir_fd=descriptor,
                )
            except FileNotFoundError:
                return _repository_absence_still_bound(
                    repository_root,
                    tuple(traversed),
                    descriptor,
                    parent_binding,
                    component,
                    str(logical_path),
                )
            os.close(descriptor)
            descriptor = child
            traversed.append(component)
        relative_parent = Path(*traversed) if traversed else Path(".")
        try:
            parent_binding = bind_logical_parent(
                repository_root, relative_parent, descriptor
            )
        except AtomicPublishError:
            return False
        try:
            os.stat(components[-1], dir_fd=descriptor, follow_symlinks=False)
        except FileNotFoundError:
            return _repository_absence_still_bound(
                repository_root,
                tuple(traversed),
                descriptor,
                parent_binding,
                components[-1],
                str(logical_path),
            )
        return False
    except OSError:
        return False
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _repository_absence_boundary(
    _stage: str, _parent_fd: int, _logical_path: str
) -> None:
    """No-op deterministic boundary for repository-absence races."""


def _repository_absence_still_bound(
    repository_root: Path,
    parent_parts: tuple[str, ...],
    parent_fd: int,
    binding: BoundLogicalParent,
    absent_name: str,
    logical_path: str,
) -> bool:
    _repository_absence_boundary(
        "after_absence_observation", parent_fd, logical_path
    )
    if not logical_parent_matches(binding):
        return False
    reopened: int | None = None
    try:
        reopened = os.open(
            repository_root,
            os.O_RDONLY
            | os.O_DIRECTORY
            | os.O_NOFOLLOW
            | getattr(os, "O_CLOEXEC", 0),
        )
        for component in parent_parts:
            child = os.open(
                component,
                os.O_RDONLY
                | os.O_DIRECTORY
                | os.O_NOFOLLOW
                | getattr(os, "O_CLOEXEC", 0),
                dir_fd=reopened,
            )
            os.close(reopened)
            reopened = child
        reopened_metadata = os.fstat(reopened)
        if (
            reopened_metadata.st_dev != binding.device
            or reopened_metadata.st_ino != binding.inode
        ):
            return False
        try:
            os.stat(absent_name, dir_fd=reopened, follow_symlinks=False)
        except FileNotFoundError:
            return logical_parent_matches(binding)
        return False
    except OSError:
        return False
    finally:
        if reopened is not None:
            os.close(reopened)


def _candidate_binding_live_issues(
    record: Mapping[str, Any],
    repository_root: Path,
    *,
    permitted_ambient_paths: Sequence[str] = (),
) -> list[Issue]:
    candidate = record.get("candidate_binding")
    if not _is_candidate_binding(candidate):
        return []
    issues: list[Issue] = []
    try:
        top_level = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=repository_root,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository_root,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        tree = subprocess.run(
            ["git", "rev-parse", "HEAD^{tree}"],
            cwd=repository_root,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        index_path_result = subprocess.run(
            ["git", "rev-parse", "--git-path", "index"],
            cwd=repository_root,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        raw_top_level = top_level.stdout.decode("utf-8").strip()
        raw_index_path = index_path_result.stdout.decode("utf-8").strip()
        if not raw_index_path:
            raise ValueError("git index path missing")
        index_path = Path(raw_index_path)
        if index_path.is_absolute():
            index_logical = index_path.relative_to(repository_root).as_posix()
        else:
            index_logical = index_path.as_posix()
        index_bytes = _read_repository_file_no_follow(repository_root, index_logical)
    except (OSError, UnicodeError, ValueError):
        index_bytes = None
        raw_top_level = ""
    if (
        top_level is None
        or head is None
        or tree is None
        or index_path_result is None
        or top_level.returncode != 0
        or head.returncode != 0
        or tree.returncode != 0
        or index_path_result.returncode != 0
        or Path(raw_top_level) != repository_root
        or head.stdout.decode("ascii", "replace").strip() != candidate["head"]
        or tree.stdout.decode("ascii", "replace").strip() != candidate["head_tree"]
        or index_bytes is None
        or f"sha256:{hashlib.sha256(index_bytes).hexdigest()}"
        != candidate["index_sha256"]
    ):
        issues.append(Issue("candidate_git_identity_mismatch", "$.candidate_binding"))
    if any(
        command is None
        for command in (top_level, head, tree, index_path_result)
    ):
        return issues

    exclusion = Path(candidate["evidence_root_exclusion"])
    ambient = list(permitted_ambient_paths)
    if (
        ambient != sorted(set(ambient))
        or any(not _is_relative_logical_path(path) for path in ambient)
        or any(Path(path) == exclusion or exclusion in Path(path).parents for path in ambient)
    ):
        issues.append(Issue("candidate_ambient_path_set_invalid"))
        ambient = []
    full_status = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        cwd=repository_root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    observed_paths: set[str] = set()
    fields = full_status.stdout.removesuffix(b"\0").split(b"\0") if full_status.stdout else []
    cursor = 0
    status_valid = full_status.returncode == 0
    while status_valid and cursor < len(fields):
        field = fields[cursor]
        if len(field) < 4 or field[2:3] != b" ":
            status_valid = False
            break
        try:
            path = field[3:].decode("utf-8")
        except UnicodeError:
            status_valid = False
            break
        if not _is_relative_logical_path(path):
            status_valid = False
            break
        observed_paths.add(path)
        status_code = field[:2]
        cursor += 1
        if b"R" in status_code or b"C" in status_code:
            if cursor >= len(fields):
                status_valid = False
                break
            try:
                source_path = fields[cursor].decode("utf-8")
            except UnicodeError:
                status_valid = False
                break
            if not _is_relative_logical_path(source_path):
                status_valid = False
                break
            observed_paths.add(source_path)
            cursor += 1
    if not status_valid:
        issues.append(Issue("candidate_git_status_invalid", "$.candidate_binding"))
    else:
        nonexcluded = {
            path
            for path in observed_paths
            if Path(path) != exclusion and exclusion not in Path(path).parents
        }
        ambient_set = set(ambient)
        declared = {row["path"] for row in candidate["candidate_paths"]}
        if not ambient_set <= nonexcluded:
            issues.append(Issue("candidate_ambient_path_set_invalid"))
        if declared != nonexcluded - ambient_set:
            issues.append(Issue("candidate_path_set_live_mismatch", "$.candidate_binding.candidate_paths"))
    for index, row in enumerate(candidate["candidate_paths"]):
        path = row["path"]
        logical = Path(path)
        if logical == exclusion or exclusion in logical.parents:
            issues.append(
                Issue(
                    "candidate_evidence_exclusion_overlap",
                    f"$.candidate_binding.candidate_paths[{index}]",
                )
            )
            continue
        head_entry = subprocess.run(
            ["git", "ls-tree", "-z", candidate["head"], "--", path],
            cwd=repository_root,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        status = subprocess.run(
            [
                "git",
                "status",
                "--porcelain=v1",
                "-z",
                "--untracked-files=all",
                "--",
                path,
            ],
            cwd=repository_root,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        status_rows = status.stdout.removesuffix(b"\0").split(b"\0") if status.stdout else []
        try:
            status_path = status_rows[0][3:].decode("utf-8") if len(status_rows) == 1 else ""
        except UnicodeError:
            status_path = ""
        if (
            status.returncode != 0
            or len(status_rows) != 1
            or len(status_rows[0]) < 4
            or status_rows[0][2:3] != b" "
            or status_path != path
        ):
            issues.append(
                Issue(
                    "candidate_path_git_state_mismatch",
                    f"$.candidate_binding.candidate_paths[{index}]",
                )
            )
        head_bytes: bytes | None = None
        head_exists = False
        if head_entry.returncode == 0 and head_entry.stdout:
            rows = head_entry.stdout.removesuffix(b"\0").split(b"\0")
            if len(rows) == 1:
                try:
                    coordinates, raw_path = rows[0].split(b"\t", 1)
                    _mode, object_type, oid = coordinates.decode("ascii").split(" ")
                    decoded_path = raw_path.decode("utf-8")
                except (ValueError, UnicodeError):
                    decoded_path = ""
                    object_type = ""
                    oid = ""
                if decoded_path == path and object_type == "blob":
                    blob = subprocess.run(
                        ["git", "cat-file", "blob", oid],
                        cwd=repository_root,
                        check=False,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                    if blob.returncode == 0:
                        head_exists = True
                        head_bytes = blob.stdout
        data = _read_repository_file_no_follow(repository_root, path)
        if row["state"] == "deleted":
            if (
                not _repository_path_absent_no_follow(repository_root, path)
                or not head_exists
                or head_bytes is None
                or len(head_bytes) != row["size"]
                or f"sha256:{hashlib.sha256(head_bytes).hexdigest()}" != row["sha256"]
            ):
                issues.append(
                    Issue("candidate_path_git_state_mismatch", f"$.candidate_binding.candidate_paths[{index}]")
                )
            continue
        if (
            data is None
            or len(data) != row["size"]
            or f"sha256:{hashlib.sha256(data).hexdigest()}" != row["sha256"]
        ):
            issues.append(
                    Issue("candidate_path_live_mismatch", f"$.candidate_binding.candidate_paths[{index}]")
                )
            continue
        state_matches = (
            not head_exists
            if row["state"] == "added"
            else head_exists and head_bytes is not None and data != head_bytes
        )
        if not state_matches:
            issues.append(
                Issue(
                    "candidate_path_git_state_mismatch",
                    f"$.candidate_binding.candidate_paths[{index}]",
                )
            )
    return issues


def _check_bound_file(
    binding: Mapping[str, Any], repository_root: Path, path: str
) -> tuple[list[Issue], Mapping[str, Any] | None]:
    issues: list[Issue] = []
    if not _is_file_binding(binding):
        return [Issue("nested_binding_invalid", path)], None
    data = _read_repository_file_no_follow(repository_root, binding["path"])
    if data is None or f"sha256:{hashlib.sha256(data).hexdigest()}" != binding["sha256"]:
        return [Issue("bound_file_unreadable", path)], None
    try:
        value = json.loads(data, object_pairs_hook=_reject_duplicate)
    except (ContractError, json.JSONDecodeError, UnicodeDecodeError):
        value = None
    return issues, value if isinstance(value, Mapping) else None


def _reopen_bound_record(
    binding: Any,
    repository_root: Path,
    *,
    expected_schema: str,
    path: str,
    deep: bool,
) -> list[Issue]:
    issues, value = _check_bound_file(
        binding if isinstance(binding, Mapping) else {}, repository_root, path
    )
    if issues:
        return issues
    if (
        value is None
        or value.get("schema_version") != expected_schema
        or validate_record(value)
        or (deep and validate_bound_record(value, repository_root))
    ):
        return [Issue("bound_record_invalid", path)]
    return []


def _read_bound_bytes(
    binding: Mapping[str, Any], repository_root: Path, path: str
) -> tuple[list[Issue], bytes | None]:
    if not (_is_file_binding(binding) or _is_file_binding(binding, sized=True)):
        return [Issue("nested_binding_invalid", path)], None
    data = _read_repository_file_no_follow(repository_root, binding["path"])
    if (
        data is None
        or f"sha256:{hashlib.sha256(data).hexdigest()}" != binding["sha256"]
        or ("size" in binding and len(data) != binding["size"])
    ):
        return [Issue("bound_file_unreadable", path)], None
    return [], data


def _bound_subject_manifest_issues(
    record: Mapping[str, Any],
    repository_root: Path,
    *,
    focused: Mapping[str, Any] | None,
    broad: Mapping[str, Any] | None,
    review_subject_path: str | None = None,
    permitted_manifest_exclusions: Sequence[str] = (),
) -> list[Issue]:
    evidence, valid = _inline_subject_evidence_bindings(record)
    additions: list[Mapping[str, Any]] = []
    if record.get("schema_version") == "broad_evidence_bootstrap_subject.v1":
        candidate = record.get("candidate_binding")
        evidence_root = (
            Path(candidate["evidence_root_exclusion"])
            if isinstance(candidate, Mapping)
            and _is_relative_logical_path(candidate.get("evidence_root_exclusion"))
            else None
        )
        subject_kind = "broad_evidence_bootstrap"
        inferred_coordinates: set[tuple[str, str]] = set()
        if review_subject_path is None and evidence_root is not None:
            history_prefix = (evidence_root / "immutable-reviews").as_posix() + "/"
            for row in record.get("candidate_path_manifest", []):
                if (
                    not isinstance(row, Mapping)
                    or not _is_candidate_path_row(row)
                    or not row["path"].startswith(history_prefix)
                ):
                    continue
                data = _read_repository_file_no_follow(
                    repository_root, row["path"]
                )
                if data is None:
                    continue
                try:
                    review = _decode_live_record(
                        data, error="immutable_review_path_invalid"
                    )
                except ContractError:
                    continue
                subject = review.get("subject")
                if isinstance(subject, Mapping):
                    path = subject.get("path")
                    kind = subject.get("kind")
                    if isinstance(path, str) and isinstance(kind, str):
                        inferred_coordinates.add((path, kind))
            if len(inferred_coordinates) == 1:
                review_subject_path, subject_kind = next(
                    iter(inferred_coordinates)
                )
            elif inferred_coordinates:
                valid = False
        if evidence_root is None:
            valid = False
        elif review_subject_path is not None:
            try:
                immutable_history = _review_lifecycle_bindings(
                    _validated_immutable_review_bindings(
                        repository_root, evidence_root
                    ),
                    subject_path=Path(review_subject_path),
                    subject_kind=subject_kind,
                )
            except ContractError:
                valid = False
            else:
                manifest_paths = {
                    row["path"]
                    for row in record.get("candidate_path_manifest", [])
                    if isinstance(row, Mapping) and _is_candidate_path_row(row)
                }
                exclusions = set(permitted_manifest_exclusions)
                additions.extend(
                    binding
                    for binding in immutable_history
                    if binding["immutable_path"] in manifest_paths
                    or binding["immutable_path"] not in exclusions
                )
    ledger = record.get("execution_ledger_binding")
    if _is_ledger_binding(ledger):
        from .materialization import generation_binding_lineage_file_bindings

        lineage_issues, bound_lineage, _descendant_lineage = (
            generation_binding_lineage_file_bindings(repository_root, ledger)
        )
        if lineage_issues:
            valid = False
        else:
            additions.extend(bound_lineage)
    if focused is not None:
        focused_binding = record.get("focused_report_binding", {})
        focused_base = (
            Path(focused_binding.get("path", "")).parent.parent
            if isinstance(focused_binding, Mapping)
            else Path(".")
        )
        for command in focused.get("commands", []):
            if isinstance(command, Mapping):
                additions.extend(
                    {
                        **binding,
                        "path": (focused_base / binding["path"]).as_posix(),
                    }
                    for binding in (
                        command.get("log_binding"),
                        command.get("exit_binding"),
                    )
                    if isinstance(binding, Mapping)
                    and isinstance(binding.get("path"), str)
                )
    if broad is not None:
        additions.extend(
            binding
            for binding in (
                broad.get("rs_log"),
                broad.get("junit_report"),
                broad.get("pytest_temp_root_preflight"),
            )
            if isinstance(binding, Mapping)
        )
        collection = broad.get("collection")
        if isinstance(collection, Mapping):
            additions.extend(
                binding
                for binding in (
                    collection.get("log_binding"),
                    collection.get("exit_binding"),
                    collection.get("node_ids_binding"),
                )
                if isinstance(binding, Mapping)
            )
        exit_result = broad.get("exit_result")
        if isinstance(exit_result, Mapping) and isinstance(
            exit_result.get("binding"), Mapping
        ):
            additions.append(exit_result["binding"])
        baseline = broad.get("known_failure_baseline_binding")
        if isinstance(baseline, Mapping):
            additions.extend(
                baseline[field]
                for field in (
                    "outcome",
                    "record",
                    "specification_review",
                    "quality_review",
                    "owner_attestation",
                )
                if isinstance(baseline.get(field), Mapping)
            )
        for prefix_field in (
            "approved_remediation_bindings",
            "approved_skip_change_bindings",
        ):
            for reviewed in broad.get(prefix_field, []):
                if isinstance(reviewed, Mapping):
                    additions.extend(
                        reviewed[field]
                        for field in (
                            "record",
                            "specification_review",
                            "quality_review",
                        )
                        if isinstance(reviewed.get(field), Mapping)
                    )
    for binding in additions:
        if _is_complete_review_binding(binding):
            binding = {
                "path": binding["immutable_path"],
                "sha256": binding["sha256"],
            }
        if not (_is_file_binding(binding) or _is_file_binding(binding, sized=True)):
            valid = False
            continue
        path = binding["path"]
        coordinate = (binding["sha256"], binding.get("size"))
        prior = evidence.get(path)
        if prior is not None and (
            prior[0] != coordinate[0]
            or (
                prior[1] is not None
                and coordinate[1] is not None
                and prior[1] != coordinate[1]
            )
        ):
            valid = False
            continue
        evidence[path] = (
            coordinate[0],
            prior[1] if prior is not None and prior[1] is not None else coordinate[1],
        )
    manifest = record.get("candidate_path_manifest", [])
    actual = {
        row["path"]: row
        for row in manifest
        if isinstance(row, Mapping) and _is_candidate_path_row(row)
    }
    candidate = record.get("candidate_binding", {})
    candidate_paths = {
        row["path"]
        for row in candidate.get("candidate_paths", [])
        if _is_candidate_path_row(row)
    } if isinstance(candidate, Mapping) else set()
    if set(actual) != candidate_paths | set(evidence):
        valid = False
    for path, (digest, declared_size) in evidence.items():
        row = actual.get(path)
        data = _subject_manifest_row_bytes(record, repository_root, path, digest)
        observed_size = len(data) if data is not None else None
        if (
            row is None
            or row.get("sha256") != digest
            or row.get("state") != "added"
            or observed_size is None
            or row.get("size") != observed_size
            or (declared_size is not None and declared_size != observed_size)
        ):
            valid = False
    return [] if valid else [Issue("candidate_manifest_evidence_projection_mismatch")]


def _subject_manifest_row_bytes(
    record: Mapping[str, Any],
    repository_root: Path,
    path: str,
    digest: str,
) -> bytes | None:
    """Read a manifest row, reopening historical mutable live bytes by snapshot."""

    ledger = record.get("execution_ledger_binding")
    if (
        _is_ledger_binding(ledger)
        and path == ledger["live_path"]
        and digest == ledger["byte_sha256"]
    ):
        snapshot = _read_repository_file_no_follow(
            repository_root, ledger["snapshot_path"]
        )
        if (
            snapshot is None
            or f"sha256:{hashlib.sha256(snapshot).hexdigest()}"
            != ledger["snapshot_sha256"]
        ):
            return None
        return snapshot
    return _read_repository_file_no_follow(repository_root, path)


def _reopen_ledger_binding(
    binding: Any,
    repository_root: Path,
    path: str,
    *,
    allow_descendant: bool = True,
) -> list[Issue]:
    if not _is_ledger_binding(binding):
        return [Issue("nested_binding_invalid", path)]
    # Imported lazily because materialization owns generation semantics and
    # imports this module for the underlying record contracts.
    from .materialization import validate_generation_binding_current

    generation_issues = validate_generation_binding_current(
        repository_root, binding, allow_descendant=allow_descendant
    )
    return (
        []
        if not generation_issues
        else [
            Issue(
                "ledger_generation_invalid",
                path,
                generation_issues[0].code,
            )
        ]
    )


def _reopen_json_binding(
    binding: Any,
    repository_root: Path,
    path: str,
    *,
    expected_schema: str | None = None,
) -> tuple[list[Issue], Mapping[str, Any] | None]:
    issues, value = _check_bound_file(binding, repository_root, path)
    if value is None:
        if not issues:
            issues.append(Issue("bound_record_invalid", path))
        return issues, None
    if expected_schema is not None and (
        value.get("schema_version") != expected_schema or validate_record(value)
    ):
        issues.append(Issue("bound_record_invalid", path))
        return issues, None
    return issues, value


def _validate_bound_failure_baseline_attestation(
    record: Mapping[str, Any], repository_root: Path
) -> list[Issue]:
    issues: list[Issue] = []
    baseline_binding = record.get("baseline_binding", {})
    baseline_issues, baseline = _reopen_json_binding(
        {
            "path": baseline_binding.get("path"),
            "sha256": baseline_binding.get("sha256"),
        }
        if isinstance(baseline_binding, Mapping)
        else {},
        repository_root,
        "$.baseline_binding",
        expected_schema="broad_known_failure_baseline.v1",
    )
    issues.extend(baseline_issues)
    if baseline is not None:
        candidate = baseline.get("candidate_binding", {})
        normalization = baseline.get("failure_normalization", {})
        failure_binding = record.get("failure_set_binding", {})
        normalization_binding = record.get("normalization_binding", {})
        expected_matches = (
            isinstance(candidate, Mapping)
            and isinstance(failure_binding, Mapping)
            and isinstance(normalization, Mapping)
            and isinstance(normalization_binding, Mapping)
            and baseline_binding.get("candidate_path_set_sha256")
            == candidate.get("candidate_path_set_sha256")
            and failure_binding.get("failure_count")
            == len(baseline.get("failures", []))
            and failure_binding.get("normalized_failure_set_sha256")
            == baseline.get("normalized_failure_set_sha256")
            and normalization_binding.get("schema_version")
            == normalization.get("schema_version")
            and normalization_binding.get("normalized_contract_sha256")
            == normalization.get("normalized_contract_sha256")
            and record.get("classification_summary")
            == baseline.get("classification_summary")
        )
        if not expected_matches:
            issues.append(Issue("attestation_baseline_record_mismatch"))
    issues.extend(
        validate_review_pair(
            specification_binding=record.get("specification_review_binding"),
            quality_binding=record.get("quality_review_binding"),
            repository_root=repository_root,
            expected_subject_kind="implementation_failure_baseline",
            expected_subject_binding={
                "path": baseline_binding.get("path"),
                "sha256": baseline_binding.get("sha256"),
            }
            if isinstance(baseline_binding, Mapping)
            else None,
        )
    )
    return issues


def validate_bound_record(
    record: Any,
    repository_root: Path,
    *,
    permitted_manifest_exclusions: Sequence[str] = (),
    review_subject_path: str | None = None,
    bound_file_bytes: Mapping[str, bytes] | None = None,
    check_ledger_future_absence: bool = True,
) -> list[Issue]:
    """Validate nested bytes and same-candidate relationships for review subjects.

    ``validate_record`` closes the in-memory shape. This companion validator is
    required before review publication because subject relationships depend on
    immutable files that cannot be proved from digests alone.
    """

    issues = list(validate_record(record))
    exclusions = list(permitted_manifest_exclusions)
    if (
        exclusions != sorted(set(exclusions))
        or any(not _is_relative_logical_path(path) for path in exclusions)
    ):
        issues.append(Issue("manifest_exclusion_invalid"))
        exclusions = []
    if not isinstance(record, Mapping):
        return sorted(set(issues))
    schema = record.get("schema_version")
    immutable_review_ambient_paths: list[str] = []
    if schema == "broad_evidence_bootstrap_subject.v1":
        candidate = record.get("candidate_binding")
        evidence_root = (
            Path(candidate["evidence_root_exclusion"])
            if isinstance(candidate, Mapping)
            and _is_relative_logical_path(candidate.get("evidence_root_exclusion"))
            else None
        )
        if evidence_root is not None:
            try:
                immutable_review_ambient_paths = [
                    binding["immutable_path"]
                    for binding in _validated_immutable_review_bindings(
                        repository_root.resolve(), evidence_root
                    )
                ]
            except ContractError:
                issues.append(Issue("immutable_review_path_invalid"))
    if issues and schema in {
        "broad_known_failure_baseline.v1",
        "broad_failure_remediation.v1",
        "broad_skip_change.v1",
    }:
        return sorted(set(issues))
    root = repository_root.resolve()
    immutable_bound_bytes = dict(bound_file_bytes or {})
    candidate_ambient_paths: list[str] = []
    if schema == "broad_evidence_bootstrap_subject.v1":
        baseline_binding = record.get("bootstrap_workspace_baseline_binding")
        _baseline_issues, baseline_record = _check_bound_file(
            {
                "path": baseline_binding.get("path"),
                "sha256": baseline_binding.get("sha256"),
            }
            if isinstance(baseline_binding, Mapping)
            else {},
            root,
            "$.bootstrap_workspace_baseline_binding",
        )
        if baseline_record is not None:
            from .source_bindings import validate_workspace_record_shape

            if not validate_workspace_record_shape(baseline_record):
                candidate_ambient_paths = sorted(
                    {
                        path
                        for row in baseline_record.get("status_rows", [])
                        if isinstance(row, Mapping)
                        for path in row.get("path_operands", [])
                        if isinstance(path, str)
                    }
                )
    issues.extend(
        _candidate_binding_live_issues(
            record,
            root,
            permitted_ambient_paths=candidate_ambient_paths,
        )
    )
    if schema == "workflow_retirement_execution_ledger.v1":
        plan_binding = record.get("plan_binding", {})
        plan_logical_path = (
            plan_binding.get("path") if isinstance(plan_binding, Mapping) else None
        )
        plan_bytes = (
            immutable_bound_bytes[plan_logical_path]
            if isinstance(plan_logical_path, str)
            and plan_logical_path in immutable_bound_bytes
            else _read_repository_file_no_follow(root, plan_logical_path)
        )
        if (
            plan_bytes is None
            or not isinstance(plan_binding, Mapping)
            or f"sha256:{hashlib.sha256(plan_bytes).hexdigest()}"
            != plan_binding.get("sha256")
        ):
            issues.append(Issue("ledger_plan_binding_unreadable", "$.plan_binding"))
        else:
            try:
                derived = build_initial_execution_ledger(
                    plan_path=Path(plan_binding["path"]), plan_bytes=plan_bytes
                )
            except ContractError:
                issues.append(Issue("ledger_plan_binding_invalid", "$.plan_binding"))
            else:
                expected = [
                    {
                        key: row[key]
                        for key in ("task_number", "title", "total_step_count")
                    }
                    for row in derived["tasks"]
                ]
                observed = [
                    {
                        key: row.get(key)
                        for key in ("task_number", "title", "total_step_count")
                    }
                    for row in record.get("tasks", [])
                    if isinstance(row, Mapping)
                ]
                if observed != expected:
                    issues.append(Issue("ledger_plan_task_mismatch", "$.tasks"))
        for task_index, task in enumerate(record.get("tasks", [])):
            if not isinstance(task, Mapping):
                continue
            for binding_index, binding in enumerate(task.get("evidence_bindings", [])):
                bound_issues, _ = _read_bound_bytes(
                    binding,
                    root,
                    f"$.tasks[{task_index}].evidence_bindings[{binding_index}]",
                )
                issues.extend(bound_issues)
        transition = record.get("last_transition")
        if _is_ledger_transition(transition):
            for index, binding in enumerate(transition["evidence_bindings"]):
                bound_issues, _ = _read_bound_bytes(
                    binding,
                    root,
                    f"$.last_transition.evidence_bindings[{index}]",
                )
                issues.extend(bound_issues)
            if check_ledger_future_absence and any(
                not _repository_path_absent_no_follow(root, binding["path"])
                for binding in transition["future_bindings"]
            ):
                issues.append(
                    Issue(
                        "ledger_future_binding_already_exists",
                        "$.last_transition.future_bindings",
                    )
                )
            prior = transition["prior_generation_binding"]
            for role, path_field, digest_field in (
                ("request", "request_path", "request_sha256"),
                ("snapshot", "snapshot_path", "snapshot_sha256"),
            ):
                bound_issues, _ = _read_bound_bytes(
                    {"path": prior[path_field], "sha256": prior[digest_field]},
                    root,
                    f"$.last_transition.prior_generation_binding.{role}",
                )
                issues.extend(bound_issues)
    elif schema == "review_binding.v1":
        immutable = Path(record.get("immutable_path", ""))
        parts = immutable.parts
        try:
            marker = parts.index("immutable-reviews")
        except ValueError:
            marker = -1
        if marker <= 0:
            issues.append(Issue("review_binding_immutable_path_mismatch"))
        else:
            evidence_root = Path(*parts[:marker])
            logical_path = Path(record.get("logical_path", ""))
            subject_path = Path(record.get("subject", {}).get("path", ""))
            if not (
                _review_path_within_root(logical_path, evidence_root)
                and _review_path_within_root(subject_path, evidence_root)
            ):
                issues.append(Issue("review_binding_evidence_root_mismatch"))
            try:
                expected = _derived_immutable_review_path(
                    evidence_root,
                    record.get("subject", {}),
                    record.get("review_kind", ""),
                    record.get("sha256", ""),
                )
            except (KeyError, TypeError, AttributeError):
                expected = None
            if immutable != expected:
                issues.append(Issue("review_binding_immutable_path_mismatch"))
            else:
                try:
                    directory = _open_review_directory(
                        root, immutable.parent, create=False
                    )
                    try:
                        data = _review_file_bytes(directory, immutable.name)
                    finally:
                        os.close(directory)
                    review = _decode_review_bytes(data)
                except (ContractError, FileNotFoundError):
                    issues.append(Issue("review_binding_immutable_unreadable"))
                else:
                    observed_sha = f"sha256:{hashlib.sha256(data).hexdigest()}"
                    if (
                        observed_sha != record.get("sha256")
                        or validate_record(review)
                        or review.get("review_kind") != record.get("review_kind")
                        or review.get("reviewer") != record.get("reviewer")
                        or review.get("reviewed_at") != record.get("reviewed_at")
                        or review.get("result") != record.get("result")
                        or review.get("subject") != record.get("subject")
                    ):
                        issues.append(Issue("review_binding_immutable_unreadable"))
    elif schema == "broad_failure_baseline_attestation.v1":
        issues.extend(_validate_bound_failure_baseline_attestation(record, root))
    elif schema == "pytest_temp_root_preflight.v1":
        for field in ("pytest_executable_binding", "tmpdir_module_binding"):
            binding = record.get(field)
            if not isinstance(binding, Mapping) or set(binding) != {"path", "sha256"}:
                issues.append(Issue("nested_binding_invalid", f"$.{field}"))
                continue
            path = Path(binding["path"])
            try:
                resolved = path.resolve(strict=True)
            except (OSError, RuntimeError):
                issues.append(Issue("file_binding_unreadable", f"$.{field}"))
                continue
            if (
                not path.is_absolute()
                or resolved != path
                or not path.is_file()
                or not _is_sha256(binding["sha256"])
                or file_sha256(path) != binding["sha256"]
            ):
                issues.append(Issue("file_binding_unreadable", f"$.{field}"))
        executable_binding = record.get("pytest_executable_binding")
        if isinstance(executable_binding, Mapping) and isinstance(
            executable_binding.get("path"), str
        ):
            executable = Path(executable_binding["path"])
            if not os.access(executable, os.X_OK):
                issues.append(
                    Issue("pytest_executable_not_executable", "$.pytest_executable_binding")
                )
            else:
                try:
                    version = subprocess.run(
                        [str(executable), "--version"],
                        cwd=Path.cwd(),
                        env=os.environ.copy(),
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        check=False,
                        timeout=30,
                    )
                except (OSError, subprocess.SubprocessError):
                    version = None
                if (
                    version is None
                    or version.returncode != 0
                    or version.stdout.strip() != "pytest 8.4.1"
                ):
                    issues.append(
                        Issue("pytest_executable_version_mismatch", "$.pytest_executable_binding")
                    )
        module_binding = record.get("tmpdir_module_binding")
        if isinstance(module_binding, Mapping):
            import _pytest.tmpdir as tmpdir_module

            if module_binding.get("path") != str(Path(tmpdir_module.__file__).resolve()):
                issues.append(
                    Issue("tmpdir_module_path_mismatch", "$.tmpdir_module_binding")
                )
    elif schema == "broad_failure_payload_normalization.v1":
        binding = record.get("pytest_temp_root_preflight_binding")
        preflight_issues, preflight = _check_bound_file(
            binding if isinstance(binding, Mapping) else {},
            root,
            "$.pytest_temp_root_preflight_binding",
        )
        issues.extend(preflight_issues)
        observed_preflight = preflight
        if preflight is not None and (
            preflight.get("schema_version") != "pytest_temp_root_preflight.v1"
            or validate_record(preflight)
            or validate_bound_record(preflight, root)
        ):
            issues.append(
                Issue(
                    "bound_record_invalid",
                    "$.pytest_temp_root_preflight_binding",
                )
            )
            preflight = None
        if record.get("repository_root") != root.as_posix():
            issues.append(Issue("normalization_repository_root_mismatch", "$.repository_root"))
        if observed_preflight is not None and any(
            record.get(field) != observed_preflight.get(preflight_field)
            for field, preflight_field in (
                ("pytest_version", "pytest_version"),
                ("system_temp_root", "system_temp_root"),
                ("pytest_root_component", "root_component"),
                ("pytest_session_parent", "observed_session_parent"),
            )
        ):
            issues.append(Issue("normalization_preflight_mismatch"))
    elif schema == "broad_outcome.v1":
        raw: dict[str, bytes | None] = {}
        bindings: list[tuple[str, Any]] = [
            ("rs_log", record.get("rs_log")),
            ("junit_report", record.get("junit_report")),
            ("pytest_temp_root_preflight", record.get("pytest_temp_root_preflight")),
        ]
        collection = record.get("collection")
        if isinstance(collection, Mapping):
            bindings.extend(
                (f"collection.{field}", collection.get(field))
                for field in ("log_binding", "exit_binding")
            )
            if "node_ids_binding" in collection:
                bindings.append(
                    ("collection.node_ids_binding", collection["node_ids_binding"])
                )
        exit_result = record.get("exit_result")
        if isinstance(exit_result, Mapping):
            bindings.append(("exit_result.binding", exit_result.get("binding")))
        for role, binding in bindings:
            if isinstance(binding, Mapping):
                bound_issues, data = _read_bound_bytes(binding, root, f"$.{role}")
                issues.extend(bound_issues)
                raw[role] = data
            else:
                issues.append(Issue("nested_binding_invalid", f"$.{role}"))
        ledger = record.get("execution_ledger_binding")
        issues.extend(
            _reopen_ledger_binding(
                ledger,
                root,
                "$.execution_ledger_binding",
            )
        )
        baseline_authority = record.get("known_failure_baseline_binding")
        if isinstance(baseline_authority, Mapping):
            for field, expected_schema, deep in (
                ("outcome", "broad_outcome.v1", True),
                ("record", "broad_known_failure_baseline.v1", True),
                (
                    "owner_attestation",
                    "broad_failure_baseline_attestation.v1",
                    False,
                ),
            ):
                issues.extend(
                    _reopen_bound_record(
                        baseline_authority.get(field),
                        root,
                        expected_schema=expected_schema,
                        path=f"$.known_failure_baseline_binding.{field}",
                        deep=deep,
                    )
                )
            issues.extend(
                validate_review_pair(
                    specification_binding=baseline_authority.get(
                        "specification_review"
                    ),
                    quality_binding=baseline_authority.get("quality_review"),
                    repository_root=root,
                    expected_subject_kind="implementation_failure_baseline",
                    expected_subject_binding=baseline_authority.get("record"),
                )
            )
        for prefix_field, expected_schema in (
            ("approved_remediation_bindings", "broad_failure_remediation.v1"),
            ("approved_skip_change_bindings", "broad_skip_change.v1"),
        ):
            for index, reviewed in enumerate(record.get(prefix_field, [])):
                if not isinstance(reviewed, Mapping):
                    continue
                issues.extend(
                    _reopen_bound_record(
                        reviewed.get("record"),
                        root,
                        expected_schema=expected_schema,
                        path=f"$.{prefix_field}[{index}].record",
                        deep=True,
                    )
                )
                subject_kind = (
                    "broad_failure_remediation"
                    if prefix_field == "approved_remediation_bindings"
                    else "broad_skip_change"
                )
                issues.extend(
                    validate_review_pair(
                        specification_binding=reviewed.get("specification_review"),
                        quality_binding=reviewed.get("quality_review"),
                        repository_root=root,
                        expected_subject_kind=subject_kind,
                        expected_subject_binding=reviewed.get("record"),
                    )
                )
        collection_exit = raw.get("collection.exit_binding")
        broad_exit = raw.get("exit_result.binding")
        if collection_exit is not None:
            try:
                parsed = parse_exit_bytes(collection_exit)
            except ContractError:
                issues.append(Issue("collection_exit_invalid", "$.collection.exit_binding"))
            else:
                if parsed != collection.get("parsed_exit"):
                    issues.append(Issue("collection_exit_mismatch", "$.collection.parsed_exit"))
        if broad_exit is not None:
            try:
                parsed = parse_exit_bytes(broad_exit)
            except ContractError:
                issues.append(Issue("broad_exit_invalid", "$.exit_result.binding"))
            else:
                if parsed != exit_result.get("parsed_exit"):
                    issues.append(Issue("broad_exit_mismatch", "$.exit_result.parsed_exit"))
        node_bytes = raw.get("collection.node_ids_binding")
        observed_nodes: list[str] | None = None
        if node_bytes is not None:
            try:
                text_value = node_bytes.decode("utf-8")
            except UnicodeDecodeError:
                issues.append(Issue("collected_node_bytes_invalid"))
            else:
                observed_nodes = text_value.splitlines()
                if node_bytes != b"" and not node_bytes.endswith(b"\n"):
                    issues.append(Issue("collected_node_bytes_invalid"))
                if observed_nodes != record.get("collected_node_ids"):
                    issues.append(Issue("collected_node_binding_mismatch"))
                if canonical_sha256(observed_nodes) != collection.get("node_id_list_sha256"):
                    issues.append(Issue("collected_node_digest_mismatch"))
        collect_log = raw.get("collection.log_binding")
        if collect_log is not None and observed_nodes is not None:
            try:
                log_nodes = sorted(
                    line
                    for line in collect_log.decode("utf-8").splitlines()
                    if "::" in line and not line.startswith(("=", " "))
                )
            except UnicodeDecodeError:
                issues.append(Issue("collection_log_invalid"))
            else:
                if log_nodes != observed_nodes:
                    issues.append(Issue("collection_log_node_mismatch"))
        preflight_bytes = raw.get("pytest_temp_root_preflight")
        if preflight_bytes is not None:
            try:
                preflight = json.loads(preflight_bytes, object_pairs_hook=_reject_duplicate)
            except (json.JSONDecodeError, UnicodeDecodeError, ContractError):
                issues.append(Issue("preflight_record_invalid"))
            else:
                if validate_record(preflight) or validate_bound_record(preflight, root):
                    issues.append(Issue("preflight_record_invalid"))
                expected_preflight_environment = {
                    "PYTEST_DEBUG_TEMPROOT": record.get("environment", {}).get(
                        "PYTEST_DEBUG_TEMPROOT"
                    )
                    if isinstance(record.get("environment"), Mapping)
                    else None
                }
                if preflight.get("environment_binding") != expected_preflight_environment:
                    issues.append(Issue("preflight_environment_mismatch"))
                normalization = record.get("failure_normalization", {})
                if not isinstance(normalization, Mapping) or (
                    normalization.get("repository_root") != root.as_posix()
                    or any(
                        normalization.get(field) != preflight.get(preflight_field)
                        for field, preflight_field in (
                            ("pytest_version", "pytest_version"),
                            ("system_temp_root", "system_temp_root"),
                            ("pytest_root_component", "root_component"),
                            ("pytest_session_parent", "observed_session_parent"),
                        )
                    )
                ):
                    issues.append(Issue("normalization_preflight_mismatch"))
        junit = raw.get("junit_report")
        if junit is not None and observed_nodes is not None:
            normalization = record.get("failure_normalization", {})
            try:
                parsed_outcomes = parse_junit_outcomes(
                    junit,
                    collected_node_ids=observed_nodes,
                    repository_root=Path(normalization["repository_root"]),
                    pytest_session_parent=Path(normalization["pytest_session_parent"]),
                )
            except (ContractError, KeyError, TypeError):
                issues.append(Issue("junit_outcome_invalid"))
            else:
                expected = record.get("outcomes", {})
                if (
                    parsed_outcomes.get("totals") != expected.get("totals")
                    or parsed_outcomes.get("failures") != expected.get("failures")
                    or parsed_outcomes.get("skipped_node_ids") != expected.get("skipped_node_ids")
                ):
                    issues.append(Issue("junit_outcome_mismatch"))
        rs_log = raw.get("rs_log")
        if rs_log is not None:
            try:
                rs_text = rs_log.decode("utf-8")
            except UnicodeDecodeError:
                issues.append(Issue("rs_log_invalid"))
            else:
                totals = record.get("outcomes", {}).get("totals", {})
                try:
                    _validate_pytest_terminal_summary(rs_text, totals)
                except ContractError:
                    issues.append(Issue("rs_log_outcome_mismatch"))
        if isinstance(baseline_authority, Mapping):
            try:
                expected_comparison, expected_lifecycle = (
                    derive_broad_baseline_comparison(
                        repository_root=root,
                        known_failure_baseline_binding=baseline_authority,
                        approved_remediation_bindings=record.get(
                            "approved_remediation_bindings", []
                        ),
                        approved_skip_change_bindings=record.get(
                            "approved_skip_change_bindings", []
                        ),
                        failure_normalization=record.get(
                            "failure_normalization", {}
                        ),
                        observed_failures=record.get("outcomes", {}).get(
                            "failures", []
                        ),
                        observed_skipped_node_ids=record.get("outcomes", {}).get(
                            "skipped_node_ids", []
                        ),
                    )
                )
            except (ContractError, KeyError, TypeError) as exc:
                issues.append(
                    Issue("baseline_authority_recomputation_failed", message=str(exc))
                )
            else:
                if record.get("baseline_comparison") != expected_comparison:
                    issues.append(Issue("baseline_comparison_authority_mismatch"))
                if record.get("outcomes", {}).get("outcome") != expected_lifecycle:
                    issues.append(Issue("broad_lifecycle_authority_mismatch"))
    elif schema == "broad_known_failure_baseline.v1":
        broad_binding_for_directory = record.get("broad_outcome_binding", {})
        broad_logical_path = Path(
            broad_binding_for_directory.get("path", "")
            if isinstance(broad_binding_for_directory, Mapping)
            else ""
        )
        baseline_directory_valid = (
            broad_logical_path.name == "outcome.json"
            and broad_logical_path.parent.name == "implementation-baseline"
            and broad_logical_path.parent.parent != Path(".")
        )
        if not baseline_directory_valid:
            issues.append(Issue("baseline_outcome_path_invalid"))
        issues.extend(
            _reopen_ledger_binding(
                record.get("execution_ledger_binding"),
                root,
                "$.execution_ledger_binding",
            )
        )
        collection = record.get("collection_binding", {})
        collection_raw: dict[str, bytes | None] = {}
        if isinstance(collection, Mapping):
            for field in ("log_binding", "exit_binding", "node_ids_binding"):
                raw_issues, data = _read_bound_bytes(
                    collection.get(field, {}), root, f"$.collection_binding.{field}"
                )
                issues.extend(raw_issues)
                collection_raw[field] = data
        collection_exit = collection_raw.get("exit_binding")
        if collection_exit is not None:
            try:
                parsed_collection_exit = parse_exit_bytes(collection_exit)
            except ContractError:
                issues.append(Issue("collection_exit_invalid", "$.collection_binding"))
            else:
                if parsed_collection_exit != 0 or parsed_collection_exit != collection.get(
                    "parsed_exit"
                ):
                    issues.append(
                        Issue("collection_exit_mismatch", "$.collection_binding")
                    )
        node_bytes = collection_raw.get("node_ids_binding")
        if node_bytes is not None:
            try:
                node_text = node_bytes.decode("utf-8")
            except UnicodeDecodeError:
                issues.append(Issue("collected_node_bytes_invalid", "$.collection_binding"))
            else:
                nodes = node_text.splitlines()
                if (
                    (node_bytes and not node_bytes.endswith(b"\n"))
                    or nodes != sorted(set(nodes))
                    or len(nodes) != collection.get("node_id_count")
                    or canonical_sha256(nodes) != collection.get("node_id_list_sha256")
                ):
                    issues.append(
                        Issue("collected_node_binding_mismatch", "$.collection_binding")
                    )
        broad_issues, broad = _reopen_json_binding(
            record.get("broad_outcome_binding"),
            root,
            "$.broad_outcome_binding",
            expected_schema="broad_outcome.v1",
        )
        issues.extend(broad_issues)
        if broad is not None:
            if baseline_directory_valid:
                issues.extend(
                    _broad_directory_issues(broad, broad_logical_path.parent)
                )
            if validate_bound_record(broad, root):
                issues.append(Issue("bound_record_invalid", "$.broad_outcome_binding"))
            for field, code in (
                ("candidate_binding", "baseline_candidate_mismatch"),
                ("execution_ledger_binding", "baseline_ledger_mismatch"),
            ):
                if broad.get(field) != record.get(field):
                    issues.append(Issue(code, f"$.{field}"))
            if broad.get("collection") != collection:
                issues.append(Issue("baseline_collection_mismatch", "$.collection_binding"))
            broad_outcomes = broad.get("outcomes", {})
            if isinstance(broad_outcomes, Mapping):
                broad_failures = broad_outcomes.get("failures", [])
                baseline_signatures = [
                    {
                        key: row[key]
                        for key in ("node_id", "outcome_kind", "failure_payload_sha256")
                    }
                    for row in record.get("failures", [])
                    if isinstance(row, Mapping)
                    and all(
                        key in row
                        for key in (
                            "node_id",
                            "outcome_kind",
                            "failure_payload_sha256",
                        )
                    )
                ]
                broad_signatures = [
                    {
                        key: row[key]
                        for key in ("node_id", "outcome_kind", "failure_payload_sha256")
                    }
                    for row in broad_failures
                    if isinstance(row, Mapping)
                    and all(
                        key in row
                        for key in (
                            "node_id",
                            "outcome_kind",
                            "failure_payload_sha256",
                        )
                    )
                ]
                if (
                    broad_outcomes.get("outcome") != "baseline_candidate"
                    or broad_outcomes.get("totals") != record.get("totals")
                    or broad_signatures != baseline_signatures
                ):
                    issues.append(Issue("baseline_broad_outcome_mismatch"))
            if broad.get("failure_normalization") != record.get(
                "failure_normalization"
            ):
                issues.append(Issue("baseline_normalization_mismatch"))
        exit_binding = record.get("pytest_exit", {})
        raw_exit_issues, raw_exit = _read_bound_bytes(
            exit_binding.get("binding", {})
            if isinstance(exit_binding, Mapping)
            else {},
            root,
            "$.pytest_exit.binding",
        )
        issues.extend(raw_exit_issues)
        if raw_exit is not None:
            try:
                parsed_exit = parse_exit_bytes(raw_exit)
            except ContractError:
                issues.append(Issue("baseline_pytest_exit_invalid", "$.pytest_exit"))
            else:
                if parsed_exit != exit_binding.get("parsed_exit"):
                    issues.append(Issue("baseline_pytest_exit_mismatch", "$.pytest_exit"))
    elif schema == "broad_failure_remediation.v1":
        issues.extend(
            _reopen_ledger_binding(
                record.get("execution_ledger_binding"),
                root,
                "$.execution_ledger_binding",
            )
        )
        baseline_issues, baseline = _reopen_json_binding(
            record.get("baseline_binding"),
            root,
            "$.baseline_binding",
            expected_schema="broad_known_failure_baseline.v1",
        )
        issues.extend(baseline_issues)
        if baseline is not None:
            baseline_rows = {
                row["node_id"]: row
                for row in baseline.get("failures", [])
                if isinstance(row, Mapping) and isinstance(row.get("node_id"), str)
            }
            for row in record.get("removed_failure_rows", []):
                if (
                    isinstance(row, Mapping)
                    and baseline_rows.get(row.get("node_id")) != row
                ):
                    issues.append(Issue("remediation_baseline_row_mismatch"))
        for field in ("task_scope_binding",):
            raw_issues, _ = _read_bound_bytes(
                record.get(field, {}), root, f"$.{field}"
            )
            issues.extend(raw_issues)
        focused_issues, focused = _reopen_json_binding(
            record.get("focused_regression_evidence"),
            root,
            "$.focused_regression_evidence",
            expected_schema="implementation_focused_report.v1",
        )
        issues.extend(focused_issues)
        if focused is not None:
            focused_path = record["focused_regression_evidence"]["path"]
            if validate_implementation_focused_report(
                focused,
                root,
                evidence_directory=Path(focused_path).parent.parent,
            ):
                issues.append(
                    Issue("bound_record_invalid", "$.focused_regression_evidence")
                )
            if focused.get("candidate_binding") != record.get("candidate_binding"):
                issues.append(Issue("remediation_candidate_mismatch"))
            if focused.get("execution_ledger_binding") != record.get(
                "execution_ledger_binding"
            ):
                issues.append(Issue("remediation_ledger_mismatch"))
        production_paths = {
            row["path"]
            for row in record.get("production_diff", [])
            if isinstance(row, Mapping) and isinstance(row.get("path"), str)
        }
        for row in record.get("removed_failure_rows", []):
            if isinstance(row, Mapping) and not production_paths.intersection(
                row.get("authorized_remediation_scope", [])
                if isinstance(row.get("authorized_remediation_scope"), list)
                else []
            ):
                issues.append(Issue("remediation_scope_mismatch"))
    elif schema == "broad_skip_change.v1":
        issues.extend(
            _reopen_ledger_binding(
                record.get("execution_ledger_binding"),
                root,
                "$.execution_ledger_binding",
            )
        )
        predecessor = record.get("predecessor_skip_set_binding", {})
        predecessor_issues, predecessor_bytes = _read_bound_bytes(
            {"path": predecessor.get("path"), "sha256": predecessor.get("sha256")}
            if isinstance(predecessor, Mapping)
            else {},
            root,
            "$.predecessor_skip_set_binding",
        )
        issues.extend(predecessor_issues)
        if predecessor_bytes is not None:
            try:
                predecessor_record = json.loads(
                    predecessor_bytes, object_pairs_hook=_reject_duplicate
                )
            except (json.JSONDecodeError, UnicodeDecodeError, ContractError):
                issues.append(
                    Issue("skip_predecessor_record_invalid", "$.predecessor_skip_set_binding")
                )
            else:
                observed_skip_ids: Any = None
                if (
                    isinstance(predecessor_record, Mapping)
                    and predecessor_record.get("schema_version") == "broad_outcome.v1"
                ):
                    if validate_bound_record(predecessor_record, root):
                        issues.append(
                            Issue(
                                "bound_record_invalid",
                                "$.predecessor_skip_set_binding",
                            )
                        )
                    observed_skip_ids = predecessor_record.get("outcomes", {}).get(
                        "skipped_node_ids"
                    )
                elif isinstance(predecessor_record, Mapping):
                    observed_skip_ids = predecessor_record.get("skip_node_ids")
                if observed_skip_ids != predecessor.get("skip_node_ids"):
                    issues.append(
                        Issue("skip_predecessor_binding_mismatch", "$.predecessor_skip_set_binding")
                    )
        focused_issues, focused = _reopen_json_binding(
            record.get("focused_regression_evidence"),
            root,
            "$.focused_regression_evidence",
            expected_schema="implementation_focused_report.v1",
        )
        issues.extend(focused_issues)
        if focused is not None:
            focused_path = record["focused_regression_evidence"]["path"]
            if validate_implementation_focused_report(
                focused,
                root,
                evidence_directory=Path(focused_path).parent.parent,
            ):
                issues.append(
                    Issue("bound_record_invalid", "$.focused_regression_evidence")
                )
            if focused.get("candidate_binding") != record.get("candidate_binding"):
                issues.append(Issue("skip_candidate_mismatch"))
            if focused.get("execution_ledger_binding") != record.get(
                "execution_ledger_binding"
            ):
                issues.append(Issue("skip_ledger_mismatch"))
    elif schema == "implementation_verification_subject.v1":
        issues.extend(_ledger_task_join_issues(record, root))
        focused_binding = record.get("focused_report_binding", {})
        focused_issues, focused = _check_bound_file(
            {
                "path": focused_binding.get("path"),
                "sha256": focused_binding.get("sha256"),
            }
            if isinstance(focused_binding, Mapping)
            else {},
            root,
            "$.focused_report_binding",
        )
        broad_issues, broad = _check_bound_file(
            record.get("broad_outcome_binding", {}), root, "$.broad_outcome_binding"
        )
        issues.extend(focused_issues)
        issues.extend(broad_issues)
        for name, related in (("focused", focused), ("broad", broad)):
            if related is None:
                continue
            related_issues = (
                validate_implementation_focused_report(
                    related,
                    root,
                    evidence_directory=Path(focused_binding["path"]).parent.parent,
                )
                if name == "focused"
                else validate_bound_record(related, root)
            )
            if related_issues:
                issues.append(Issue("bound_record_invalid", f"$.{name}"))
            if related.get("candidate_binding") != record.get("candidate_binding"):
                issues.append(Issue("subject_candidate_mismatch", f"$.{name}"))
            if related.get("execution_ledger_binding") != record.get(
                "execution_ledger_binding"
            ):
                issues.append(Issue("subject_ledger_mismatch", f"$.{name}"))
        if focused is not None and focused.get("normalized_report_sha256") != focused_binding.get(
            "normalized_report_sha256"
        ):
            issues.append(Issue("focused_report_normalized_digest_mismatch"))
        if focused is not None and focused.get("task_contract_binding") != record.get(
            "task_contract_binding"
        ):
            issues.append(Issue("subject_task_contract_mismatch", "$.focused"))
        issues.extend(
            _bound_subject_manifest_issues(
                record,
                root,
                focused=focused,
                broad=broad,
                review_subject_path=review_subject_path,
                permitted_manifest_exclusions=exclusions,
            )
        )
        if isinstance(focused_binding, Mapping):
            try:
                subject_directory = _subject_evidence_directory(
                    focused_path=focused_binding.get("path", ""),
                    sibling_path=record.get("broad_outcome_binding", {}).get(
                        "path", ""
                    ),
                    sibling_name="outcome.json",
                )
            except (ContractError, AttributeError):
                issues.append(Issue("subject_evidence_directory_mismatch"))
            else:
                if broad is not None:
                    issues.extend(_broad_directory_issues(broad, subject_directory))
    elif schema == "broad_evidence_bootstrap_subject.v1":
        issues.extend(_ledger_task_join_issues(record, root))
        focused_binding = record.get("focused_report_binding", {})
        focused_issues, focused = _check_bound_file(
            {
                "path": focused_binding.get("path"),
                "sha256": focused_binding.get("sha256"),
            }
            if isinstance(focused_binding, Mapping)
            else {},
            root,
            "$.focused_report_binding",
        )
        issues.extend(focused_issues)
        if focused is not None:
            if validate_implementation_focused_report(
                focused,
                root,
                evidence_directory=Path(focused_binding["path"]).parent.parent,
                permitted_ambient_paths=candidate_ambient_paths,
            ):
                issues.append(Issue("bound_record_invalid", "$.focused"))
            for field, code in (
                ("candidate_binding", "subject_candidate_mismatch"),
                ("execution_ledger_binding", "subject_ledger_mismatch"),
                ("task_contract_binding", "subject_task_contract_mismatch"),
            ):
                if focused.get(field) != record.get(field):
                    issues.append(Issue(code, "$.focused"))
            if focused.get("normalized_report_sha256") != focused_binding.get(
                "normalized_report_sha256"
            ):
                issues.append(Issue("focused_report_normalized_digest_mismatch"))
        baseline = record.get("bootstrap_workspace_baseline_binding")
        if isinstance(baseline, Mapping) and {"path", "sha256"} <= set(baseline):
            baseline_issues, baseline_record = _check_bound_file(
                {"path": baseline["path"], "sha256": baseline["sha256"]},
                root,
                "$.bootstrap_workspace_baseline_binding",
            )
            issues.extend(baseline_issues)
            if (
                baseline_record is None
                or baseline_record.get("schema_version")
                != "bootstrap_workspace_baseline.v1"
            ):
                issues.append(Issue("bootstrap_baseline_record_invalid"))
            else:
                capture = baseline_record.get("bootstrap_capture_bindings", {})
                expected = {
                    "head": baseline_record.get("head"),
                    "index_sha256": baseline_record.get("index_sha256"),
                    "index_file_sha256": capture.get("index_file_sha256"),
                    "index_entries_file_sha256": capture.get(
                        "index_entries_file_sha256"
                    ),
                    "status_file_sha256": capture.get("status_file_sha256"),
                    "archive_sha256": capture.get("archive_sha256"),
                    "index_entry_count": baseline_record.get("index_entry_count"),
                    "index_entry_set_sha256": baseline_record.get(
                        "index_entry_set_sha256"
                    ),
                    "dirty_entry_count": baseline_record.get("dirty_entry_count"),
                    "dirty_entry_set_sha256": baseline_record.get(
                        "dirty_entry_set_sha256"
                    ),
                    "dirty_path_set_sha256": baseline_record.get(
                        "dirty_path_set_sha256"
                    ),
                    "normalized_baseline_sha256": baseline_record.get(
                        "normalized_baseline_sha256"
                    ),
                }
                if any(baseline.get(key) != value for key, value in expected.items()):
                    issues.append(Issue("bootstrap_baseline_binding_mismatch"))
                else:
                    from .source_bindings import validate_bootstrap_workspace

                    allowed = sorted(
                        row["path"]
                        for row in record.get("candidate_path_manifest", [])
                        if _is_candidate_path_row(row)
                    )
                    allowed = sorted(
                        set(allowed)
                        | set(exclusions)
                        | set(immutable_review_ambient_paths)
                    )
                    ledger = record.get("execution_ledger_binding")
                    if _is_ledger_binding(ledger):
                        from .materialization import (
                            generation_binding_lineage_file_bindings,
                        )

                        lineage_issues, _bound_lineage, descendant_lineage = (
                            generation_binding_lineage_file_bindings(root, ledger)
                        )
                        if lineage_issues:
                            issues.append(
                                Issue(
                                    "bootstrap_baseline_workspace_invalid",
                                    message=lineage_issues[0].code,
                                )
                            )
                        else:
                            allowed = sorted(
                                set(allowed)
                                | {row["path"] for row in descendant_lineage}
                            )
                    live_issues = validate_bootstrap_workspace(
                        root, baseline_record, allowed
                    )
                    if live_issues:
                        issues.append(
                            Issue(
                                "bootstrap_baseline_workspace_invalid",
                                message=live_issues[0].code,
                            )
                        )
        raw_by_role: dict[str, bytes | None] = {}
        for index, row in enumerate(record.get("raw_broad_bindings", [])):
            if isinstance(row, Mapping) and {"path", "sha256"} <= set(row):
                raw_issues, data = _read_bound_bytes(
                    {
                        "path": row.get("path"),
                        "sha256": row.get("sha256"),
                        "size": row.get("size"),
                    },
                    root,
                    f"$.raw_broad_bindings[{index}]",
                )
                issues.extend(raw_issues)
                if isinstance(row.get("role_id"), str):
                    raw_by_role[row["role_id"]] = data
        baseline_binding_for_directory = record.get(
            "bootstrap_workspace_baseline_binding", {}
        )
        try:
            bootstrap_directory = _subject_evidence_directory(
                focused_path=focused_binding.get("path", "")
                if isinstance(focused_binding, Mapping)
                else "",
                sibling_path=baseline_binding_for_directory.get("path", "")
                if isinstance(baseline_binding_for_directory, Mapping)
                else "",
                sibling_name="bootstrap-workspace-baseline.json",
            )
        except (ContractError, AttributeError):
            issues.append(Issue("subject_evidence_directory_mismatch"))
        else:
            raw_paths = {
                row.get("role_id"): row.get("path")
                for row in record.get("raw_broad_bindings", [])
                if isinstance(row, Mapping)
            }
            if any(
                raw_paths.get(role)
                != (bootstrap_directory / filename).as_posix()
                for role, filename in _BROAD_ROLE_FILENAMES.items()
            ):
                issues.append(Issue("subject_evidence_directory_mismatch"))
        collection = record.get("collection_binding", {})
        collection_exit = raw_by_role.get("collection-exit")
        if collection_exit is not None:
            try:
                parsed_collection_exit = parse_exit_bytes(collection_exit)
            except ContractError:
                issues.append(Issue("collection_exit_invalid", "$.raw_broad_bindings"))
            else:
                if parsed_collection_exit != collection.get("parsed_exit") or parsed_collection_exit != 0:
                    issues.append(Issue("collection_exit_mismatch", "$.collection_binding.parsed_exit"))
        node_bytes = raw_by_role.get("collected-node-ids")
        observed_nodes: list[str] | None = None
        if node_bytes is not None:
            try:
                node_text = node_bytes.decode("utf-8")
            except UnicodeDecodeError:
                issues.append(Issue("collected_node_bytes_invalid"))
            else:
                observed_nodes = node_text.splitlines()
                if node_bytes and not node_bytes.endswith(b"\n"):
                    issues.append(Issue("collected_node_bytes_invalid"))
                if observed_nodes != sorted(set(observed_nodes)):
                    issues.append(Issue("collected_node_partition_invalid"))
                if len(observed_nodes) != collection.get("node_id_count"):
                    issues.append(Issue("collected_node_count_mismatch"))
                if canonical_sha256(observed_nodes) != collection.get("node_id_list_sha256"):
                    issues.append(Issue("collected_node_digest_mismatch"))
        collection_log = raw_by_role.get("collection-log")
        if collection_log is not None and observed_nodes is not None:
            try:
                log_nodes = sorted(
                    line
                    for line in collection_log.decode("utf-8").splitlines()
                    if "::" in line and not line.startswith(("=", " "))
                )
            except UnicodeDecodeError:
                issues.append(Issue("collection_log_invalid"))
            else:
                if log_nodes != observed_nodes:
                    issues.append(Issue("collection_log_node_mismatch"))
        preflight: Mapping[str, Any] | None = None
        preflight_bytes = raw_by_role.get("pytest-temp-root-preflight")
        if preflight_bytes is not None:
            try:
                candidate_preflight = json.loads(
                    preflight_bytes, object_pairs_hook=_reject_duplicate
                )
            except (json.JSONDecodeError, UnicodeDecodeError, ContractError):
                issues.append(Issue("preflight_record_invalid"))
            else:
                if (
                    not isinstance(candidate_preflight, Mapping)
                    or validate_record(candidate_preflight)
                    or validate_bound_record(candidate_preflight, root)
                ):
                    issues.append(Issue("preflight_record_invalid"))
                else:
                    preflight = candidate_preflight
                    expected_preflight_environment = {
                        "PYTEST_DEBUG_TEMPROOT": collection.get(
                            "environment", {}
                        ).get("PYTEST_DEBUG_TEMPROOT")
                        if isinstance(collection.get("environment"), Mapping)
                        else None
                    }
                    if (
                        preflight.get("environment_binding")
                        != expected_preflight_environment
                    ):
                        issues.append(Issue("preflight_environment_mismatch"))
        junit_bytes = raw_by_role.get("broad-junit")
        parsed_outcomes: Mapping[str, Any] | None = None
        if junit_bytes is not None:
            try:
                ET.fromstring(junit_bytes)
            except ET.ParseError:
                issues.append(Issue("junit_outcome_invalid"))
        if junit_bytes is not None and observed_nodes is not None and preflight is not None:
            try:
                parsed_outcomes = parse_junit_outcomes(
                    junit_bytes,
                    collected_node_ids=observed_nodes,
                    repository_root=root,
                    pytest_session_parent=Path(preflight["observed_session_parent"]),
                )
            except (ContractError, KeyError, TypeError):
                issues.append(Issue("junit_outcome_invalid"))
            else:
                totals = record.get("observed_totals")
                failed_ids = record.get("observed_failed_node_ids")
                parsed_ids = [row["node_id"] for row in parsed_outcomes["failures"]]
                if parsed_outcomes["totals"] != totals or parsed_ids != failed_ids:
                    issues.append(Issue("junit_outcome_mismatch"))
        broad_exit = raw_by_role.get("broad-exit")
        if broad_exit is not None:
            try:
                parsed_broad_exit = parse_exit_bytes(broad_exit)
            except ContractError:
                issues.append(Issue("broad_exit_invalid"))
            else:
                totals = record.get("observed_totals", {})
                expected_exit = 1 if totals.get("failed", 0) + totals.get("errors", 0) else 0
                if parsed_broad_exit != expected_exit:
                    issues.append(Issue("broad_exit_mismatch"))
        rs_log = raw_by_role.get("broad-rs-log")
        if rs_log is not None:
            try:
                rs_text = rs_log.decode("utf-8")
            except UnicodeDecodeError:
                issues.append(Issue("rs_log_invalid"))
            else:
                totals = record.get("observed_totals", {})
                try:
                    _validate_pytest_terminal_summary(rs_text, totals)
                except ContractError:
                    issues.append(Issue("rs_log_outcome_mismatch"))
        issues.extend(
            _bound_subject_manifest_issues(
                record,
                root,
                focused=focused,
                broad=None,
                review_subject_path=review_subject_path,
                permitted_manifest_exclusions=exclusions,
            )
        )
    if schema in {
        "implementation_verification_subject.v1",
        "broad_evidence_bootstrap_subject.v1",
    }:
        for index, row in enumerate(record.get("candidate_path_manifest", [])):
            if not isinstance(row, Mapping) or not _is_candidate_path_row(row):
                continue
            data = _subject_manifest_row_bytes(
                record, root, row["path"], row["sha256"]
            )
            deleted = row["state"] == "deleted"
            if (
                (deleted and not _repository_path_absent_no_follow(root, row["path"]))
                or (
                    not deleted
                    and (
                        data is None
                        or len(data) != row["size"]
                        or f"sha256:{hashlib.sha256(data).hexdigest()}"
                        != row["sha256"]
                    )
                )
            ):
                issues.append(
                    Issue("bound_file_unreadable", f"$.candidate_path_manifest[{index}]")
                )
    return sorted(set(issues))


def validate_review_binding_pair(
    *,
    specification_binding: Any,
    quality_binding: Any,
    repository_root: Path,
    expected_subject_kind: str | None = None,
    expected_subject_binding: Mapping[str, Any] | None = None,
) -> list[Issue]:
    """Validate immutable review bytes, roles, paths, and subject coordinates."""

    issues: list[Issue] = []
    bindings = (
        ("specification", specification_binding),
        ("code_quality", quality_binding),
    )
    for expected_kind, binding in bindings:
        path = (
            "$.specification_review_binding"
            if expected_kind == "specification"
            else "$.quality_review_binding"
        )
        if not _is_complete_review_binding(binding):
            issues.append(Issue("review_pair_binding_invalid", path))
            continue
        if validate_bound_record(binding, repository_root):
            issues.append(Issue("review_pair_binding_invalid", path))
        if binding.get("review_kind") != expected_kind:
            issues.append(Issue("review_pair_kind_mismatch", path))
        if binding.get("result") != "approved":
            issues.append(Issue("review_pair_not_approved", path))

    if issues or not all(isinstance(binding, Mapping) for _, binding in bindings):
        return sorted(set(issues))

    specification = specification_binding
    quality = quality_binding
    specification_time = _aware_timestamp(specification.get("reviewed_at"))
    quality_time = _aware_timestamp(quality.get("reviewed_at"))
    if (
        specification_time is None
        or quality_time is None
        or specification_time > quality_time
    ):
        issues.append(Issue("review_pair_timestamp_order_invalid", "$.reviewed_at"))
    specification_subject = specification["subject"]
    quality_subject = quality["subject"]
    if specification_subject != quality_subject:
        issues.append(Issue("review_pair_subject_mismatch", "$.subject"))
    subject_kind = specification_subject.get("kind")
    if expected_subject_kind is not None and subject_kind != expected_subject_kind:
        issues.append(Issue("review_pair_subject_kind_mismatch", "$.subject.kind"))

    if expected_subject_binding is not None:
        expected_coordinates = {
            "path": specification_subject.get("path"),
            "sha256": specification_subject.get("sha256"),
        }
        if (
            not _is_file_binding(expected_subject_binding)
            or expected_coordinates != dict(expected_subject_binding)
        ):
            issues.append(Issue("review_pair_subject_binding_mismatch", "$.subject"))

    expected_specification_name = _expected_live_review_name(
        subject_kind, "specification"
    )
    expected_quality_name = _expected_live_review_name(subject_kind, "code_quality")
    specification_path = Path(specification["logical_path"])
    quality_path = Path(quality["logical_path"])
    if (
        expected_specification_name is None
        or expected_quality_name is None
        or specification_path.name != expected_specification_name
        or quality_path.name != expected_quality_name
        or specification_path.parent != quality_path.parent
        or specification_path == quality_path
    ):
        issues.append(Issue("review_pair_live_paths_invalid", "$.logical_path"))

    if specification["reviewer"]["identity"] == quality["reviewer"]["identity"]:
        issues.append(Issue("review_pair_reviewer_not_distinct", "$.reviewer"))

    return sorted(set(issues))


def validate_review_pair(
    *,
    specification_binding: Any,
    quality_binding: Any,
    repository_root: Path,
    expected_subject_kind: str | None = None,
    expected_subject_binding: Mapping[str, Any] | None = None,
) -> list[Issue]:
    """Validate a complete pair and reopen its shared subject contract."""

    issues = validate_review_binding_pair(
        specification_binding=specification_binding,
        quality_binding=quality_binding,
        repository_root=repository_root,
        expected_subject_kind=expected_subject_kind,
        expected_subject_binding=expected_subject_binding,
    )
    if issues:
        return issues
    specification_subject = specification_binding["subject"]
    subject_kind = specification_subject["kind"]
    subject_binding = {
        "path": specification_subject["path"],
        "sha256": specification_subject["sha256"],
    }
    subject_issues, subject_record = _check_bound_file(
        subject_binding, repository_root.resolve(), "$.subject"
    )
    if subject_issues or subject_record is None:
        issues.append(Issue("review_pair_subject_unreadable", "$.subject"))
    elif validate_review_subject(
        subject_kind=subject_kind,
        record=subject_record,
        repository_root=repository_root,
        subject_path=specification_subject["path"],
        permitted_manifest_exclusions=sorted(
            {
                specification_subject["path"],
                specification_binding["logical_path"],
                specification_binding["immutable_path"],
                quality_binding["logical_path"],
                quality_binding["immutable_path"],
            }
        ),
    ):
        issues.append(Issue("review_pair_subject_invalid", "$.subject"))
    return sorted(set(issues))


def validate_execution_ledger(
    record: Mapping[str, Any], *, check_base: bool = True
) -> list[Issue]:
    issues: list[Issue] = []
    if check_base:
        if record.get("schema_version") != "workflow_retirement_execution_ledger.v1":
            return [Issue("schema_version_mismatch", "$.schema_version")]
        issues.extend(_keys_issue(record, "workflow_retirement_execution_ledger.v1"))
        if issues:
            return issues
        expected_digest = canonical_sha256(record, exclude={"normalized_ledger_sha256"})
        if record.get("normalized_ledger_sha256") != expected_digest:
            issues.append(Issue("normalized_digest_mismatch", "$.normalized_ledger_sha256"))
    if not _is_file_binding(record.get("plan_binding")):
        issues.append(Issue("ledger_plan_binding_invalid", "$.plan_binding"))
    tasks = record.get("tasks")
    if (
        type(record.get("task_count")) is not int
        or record["task_count"] != 17
        or not isinstance(tasks, list)
        or len(tasks) != 17
    ):
        issues.append(Issue("ledger_task_count_invalid", "$.tasks"))
        return sorted(set(issues))
    task_keys = {
        "task_number",
        "title",
        "status",
        "completed_step_count",
        "total_step_count",
        "evidence_bindings",
    }
    expected_numbers = list(range(1, 18))
    numbers = [row.get("task_number") for row in tasks if isinstance(row, Mapping)]
    if numbers != expected_numbers:
        issues.append(Issue("ledger_task_numbers_invalid", "$.tasks"))
    in_progress: list[int] = []
    for index, row in enumerate(tasks):
        path = f"$.tasks[{index}]"
        if not isinstance(row, Mapping) or set(row) != task_keys:
            issues.append(Issue("ledger_task_keys_invalid", path))
            continue
        if (
            type(row["task_number"]) is not int
            or not isinstance(row["title"], str)
            or not row["title"]
        ):
            issues.append(Issue("ledger_task_identity_invalid", path))
        if not isinstance(row["status"], str) or row["status"] not in {
            "pending",
            "in_progress",
            "complete",
        }:
            issues.append(Issue("ledger_task_status_invalid", f"{path}.status"))
        if row["status"] == "in_progress":
            in_progress.append(row["task_number"])
        if type(row["completed_step_count"]) is not int or type(
            row["total_step_count"]
        ) is not int:
            issues.append(Issue("ledger_step_count_invalid", path))
        elif not 0 <= row["completed_step_count"] <= row["total_step_count"]:
            issues.append(Issue("ledger_step_count_invalid", path))
        evidence = row["evidence_bindings"]
        if (
            not isinstance(evidence, list)
            or any(not _is_file_binding(binding) for binding in evidence)
            or [binding["path"] for binding in evidence]
            != sorted({binding["path"] for binding in evidence})
        ):
            issues.append(Issue("ledger_evidence_bindings_invalid", f"{path}.evidence_bindings"))
    current = record.get("current_task")
    if current is None:
        if in_progress:
            issues.append(Issue("ledger_current_task_mismatch", "$.current_task"))
    elif type(current) is not int or in_progress != [current]:
        issues.append(Issue("ledger_current_task_mismatch", "$.current_task"))
    statuses = [row.get("status") for row in tasks if isinstance(row, Mapping)]
    if len(statuses) == 17:
        before_task_one = statuses == ["pending"] * 17
        complete_count = 0
        while complete_count < 17 and statuses[complete_count] == "complete":
            complete_count += 1
        expected_statuses = (
            ["pending"] * 17
            if before_task_one
            else ["complete"] * 17
            if complete_count == 17
            else ["complete"] * complete_count
            + ["in_progress"]
            + ["pending"] * (16 - complete_count)
        )
        if statuses != expected_statuses:
            issues.append(Issue("ledger_status_sequence_invalid", "$.tasks"))
        for row in tasks:
            if not isinstance(row, Mapping):
                continue
            status = row.get("status")
            completed = row.get("completed_step_count")
            total = row.get("total_step_count")
            if type(completed) is int and type(total) is int and (
                (status == "complete" and completed != total)
                or (status == "pending" and completed != 0)
                or (status == "in_progress" and not 0 <= completed < total)
            ):
                issues.append(Issue("ledger_step_status_mismatch", "$.tasks"))
                break
        expected_current = (
            None
            if before_task_one or complete_count == 17
            else complete_count + 1
        )
        if (
            (current is not None and type(current) is not int)
            or current != expected_current
        ):
            issues.append(Issue("ledger_current_task_mismatch", "$.current_task"))
    transition = record.get("last_transition")
    if transition is not None and not _is_ledger_transition(transition):
        issues.append(Issue("ledger_transition_invalid", "$.last_transition"))
    return sorted(set(issues))


def _is_ledger_transition(value: Any) -> bool:
    keys = {
        "prior_generation_binding",
        "task_number",
        "step_number",
        "old_status",
        "new_status",
        "prepared_at",
        "evidence_bindings",
        "future_bindings",
    }
    if not isinstance(value, Mapping) or set(value) != keys:
        return False
    prior = value["prior_generation_binding"]
    prior_keys = {
        "request_path",
        "request_sha256",
        "snapshot_path",
        "snapshot_sha256",
        "generation",
        "output_path",
    }
    evidence = value["evidence_bindings"]
    future = value["future_bindings"]
    return (
        isinstance(prior, Mapping)
        and set(prior) == prior_keys
        and _is_relative_logical_path(prior.get("request_path"))
        and _is_relative_logical_path(prior.get("snapshot_path"))
        and _is_relative_logical_path(prior.get("output_path"))
        and _is_sha256(prior.get("request_sha256"))
        and _is_sha256(prior.get("snapshot_sha256"))
        and type(prior.get("generation")) is int
        and prior["generation"] >= 1
        and type(value["task_number"]) is int
        and 1 <= value["task_number"] <= 17
        and type(value["step_number"]) is int
        and value["step_number"] >= 1
        and isinstance(value["old_status"], str)
        and value["old_status"] in {"pending", "in_progress", "complete"}
        and isinstance(value["new_status"], str)
        and value["new_status"] in {"pending", "in_progress", "complete"}
        and _aware_timestamp(value["prepared_at"]) is not None
        and isinstance(evidence, list)
        and all(_is_file_binding(binding) for binding in evidence)
        and [binding["path"] for binding in evidence]
        == sorted({binding["path"] for binding in evidence})
        and isinstance(future, list)
        and all(
            isinstance(binding, Mapping)
            and set(binding) == {"path", "sha256"}
            and _is_relative_logical_path(binding.get("path"))
            and binding.get("sha256") is None
            for binding in future
        )
        and [binding["path"] for binding in future]
        == sorted({binding["path"] for binding in future})
    )


def build_initial_execution_ledger(*, plan_path: Path, plan_bytes: bytes) -> dict[str, Any]:
    """Derive generation one of the ledger from an immutable Markdown plan."""

    try:
        text = plan_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError("plan_not_utf8") from exc
    headings = list(re.finditer(r"^### Task ([0-9]+): (.+)$", text, re.MULTILINE))
    if [int(match.group(1)) for match in headings] != list(range(1, 18)):
        raise ContractError("plan_task_partition_invalid")
    tasks: list[dict[str, Any]] = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        section = text[heading.end() : end]
        steps = [
            int(value)
            for value in re.findall(r"^- \[ \] \*\*Step ([0-9]+):", section, re.MULTILINE)
        ]
        if not steps or steps != list(range(1, len(steps) + 1)):
            raise ContractError("plan_step_partition_invalid")
        number = int(heading.group(1))
        tasks.append(
            {
                "task_number": number,
                "title": heading.group(2),
                "status": "in_progress" if number == 1 else "pending",
                "completed_step_count": 0,
                "total_step_count": len(steps),
                "evidence_bindings": [],
            }
        )
    record: dict[str, Any] = {
        "schema_version": "workflow_retirement_execution_ledger.v1",
        "plan_binding": {
            "path": plan_path.as_posix(),
            "sha256": f"sha256:{hashlib.sha256(plan_bytes).hexdigest()}",
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


def _replace_prefix_at_boundaries(text: str, prefix: str, replacement: str) -> str:
    if not prefix:
        return text
    result: list[str] = []
    cursor = 0
    while True:
        found = text.find(prefix, cursor)
        if found < 0:
            result.append(text[cursor:])
            break
        before_ok = found == 0 or text[found - 1] in PREFIX_BOUNDARY
        end = found + len(prefix)
        after_ok = end == len(text) or text[end] == "/"
        if before_ok and after_ok:
            result.append(text[cursor:found])
            result.append(replacement)
            cursor = end + (1 if end < len(text) and text[end] == "/" else 0)
        else:
            result.append(text[cursor : found + 1])
            cursor = found + 1
    return "".join(result)


def normalize_failure_payload(
    payload: str, *, repository_root: Path, pytest_session_parent: Path
) -> str:
    normalized = ANSI_CSI_RE.sub("", payload.replace("\r\n", "\n"))
    repository_prefix = str(repository_root)
    normalized = _replace_prefix_at_boundaries(normalized, repository_prefix, "<repo>/")
    session = re.escape(str(pytest_session_parent))
    pattern = re.compile(
        rf"(?P<prefix>^|[{re.escape(ASCII_PATH_BOUNDARY)}])"
        rf"(?P<run>{session}/pytest-[0-9]+)(?=/|$)"
    )
    normalized = pattern.sub(lambda match: match.group("prefix") + "<pytest-tmp>", normalized)
    return normalized


def failure_signature(
    *, testcase_identity: str, outcome_kind: str, payload: str, repository_root: Path,
    pytest_session_parent: Path
) -> str:
    if outcome_kind not in {"failure", "error"}:
        raise ContractError("outcome_kind_invalid")
    stable = normalize_failure_payload(
        payload,
        repository_root=repository_root,
        pytest_session_parent=pytest_session_parent,
    )
    return canonical_sha256([testcase_identity, outcome_kind, stable])


def _junit_nonnegative_decimal(suite: ET.Element, attribute: str) -> int:
    raw = suite.get(attribute)
    if raw is None:
        raise ContractError(f"junit_declared_total_invalid:{attribute}")
    if re.fullmatch(r"(?:0|[1-9][0-9]*)", raw) is None:
        raise ContractError(f"junit_declared_total_invalid:{attribute}")
    try:
        return int(raw)
    except ValueError as exc:
        raise ContractError(
            f"junit_declared_total_invalid:{attribute}"
        ) from exc


def parse_junit_outcomes(
    xml_bytes: bytes,
    *,
    collected_node_ids: Sequence[str],
    repository_root: Path,
    pytest_session_parent: Path,
) -> dict[str, Any]:
    """Map one pytest JUnit report onto the exact collected node partition."""

    if list(collected_node_ids) != sorted(set(collected_node_ids)):
        raise ContractError("collected_node_partition_invalid")
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise ContractError("junit_xml_invalid") from exc
    if root.tag not in {"testsuite", "testsuites"}:
        raise ContractError("junit_root_invalid")
    cases = list(root.iter("testcase"))
    failures: list[dict[str, Any]] = []
    skipped: list[str] = []
    mapped: set[str] = set()
    failed_count = 0
    error_count = 0
    skipped_count = 0
    for case in cases:
        name = case.get("name")
        file_name = case.get("file")
        if not name:
            raise ContractError("junit_testcase_identity_invalid")
        if file_name:
            prefix = f"{file_name}::"
            candidates = []
            for node in collected_node_ids:
                if not node.startswith(prefix):
                    continue
                suffix = node[len(prefix) :]
                if suffix == name or suffix.endswith(f"::{name}"):
                    candidates.append(node)
        else:
            classname = case.get("classname")
            candidates = []
            for node in collected_node_ids:
                path, separator, suffix = node.partition("::")
                if not separator or not (suffix == name or suffix.endswith(f"::{name}")):
                    continue
                module_name = path[:-3].replace("/", ".") if path.endswith(".py") else path.replace("/", ".")
                if classname and not (
                    classname == module_name or classname.startswith(f"{module_name}.")
                ):
                    continue
                candidates.append(node)
        if len(candidates) != 1:
            raise ContractError(f"junit_node_id_unmappable:{name}")
        node_id = candidates[0]
        if node_id in mapped:
            raise ContractError(f"junit_node_id_duplicate:{node_id}")
        mapped.add(node_id)
        failure_elements = case.findall("failure")
        error_elements = case.findall("error")
        skipped_elements = case.findall("skipped")
        if sum(bool(elements) for elements in (failure_elements, error_elements, skipped_elements)) > 1:
            raise ContractError(f"junit_outcome_ambiguous:{node_id}")
        if failure_elements or error_elements:
            kind = "failure" if failure_elements else "error"
            element = (failure_elements or error_elements)[0]
            payload = "".join(element.itertext())
            normalized = normalize_failure_payload(
                payload,
                repository_root=repository_root,
                pytest_session_parent=pytest_session_parent,
            )
            failures.append(
                {
                    "node_id": node_id,
                    "outcome_kind": kind,
                    "failure_payload_sha256": canonical_sha256(
                        [node_id, kind, normalized]
                    ),
                    "normalized_payload": normalized,
                }
            )
            if kind == "failure":
                failed_count += 1
            else:
                error_count += 1
        elif skipped_elements:
            skipped.append(node_id)
            skipped_count += 1
    if mapped != set(collected_node_ids):
        raise ContractError("junit_collected_partition_mismatch")
    totals = {
        "collected": len(cases),
        "passed": len(cases) - failed_count - error_count - skipped_count,
        "failed": failed_count,
        "errors": error_count,
        "skipped": skipped_count,
    }
    suites = [root] if root.tag == "testsuite" else [
        suite for suite in root.iter("testsuite") if not suite.findall("testsuite")
    ]
    if not suites:
        raise ContractError("junit_suite_partition_invalid")
    declared = {
        "collected": sum(_junit_nonnegative_decimal(suite, "tests") for suite in suites),
        "failed": sum(_junit_nonnegative_decimal(suite, "failures") for suite in suites),
        "errors": sum(_junit_nonnegative_decimal(suite, "errors") for suite in suites),
        "skipped": sum(_junit_nonnegative_decimal(suite, "skipped") for suite in suites),
    }
    if any(declared[key] != totals[key] for key in ("collected", "failed", "errors", "skipped")):
        raise ContractError("junit_totals_disagree")
    return {"totals": totals, "failures": sorted(failures, key=lambda row: row["node_id"]), "skipped_node_ids": sorted(skipped)}


def compare_failure_sets(
    *,
    baseline_rows: Sequence[Mapping[str, Any]],
    observed_rows: Sequence[Mapping[str, Any]],
    remediated_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Compare a candidate failure table to a frozen owner baseline.

    A removed row is admissible only when the exact baseline row is queue-owned
    and appears in the already-reviewed remediation prefix.
    """

    def indexed(rows: Sequence[Mapping[str, Any]], lane: str) -> dict[str, Mapping[str, Any]]:
        result: dict[str, Mapping[str, Any]] = {}
        for row in rows:
            node = row.get("node_id")
            if not isinstance(node, str) or not node or node in result:
                raise ContractError(f"{lane}_failure_partition_invalid")
            if row.get("outcome_kind") not in {"failure", "error"}:
                raise ContractError(f"{lane}_failure_partition_invalid")
            digest = row.get("failure_payload_sha256")
            if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
                raise ContractError(f"{lane}_failure_partition_invalid")
            result[node] = row
        return result

    baseline = indexed(baseline_rows, "baseline")
    observed = indexed(observed_rows, "observed")
    remediated = indexed(remediated_rows, "remediation")
    for node, row in observed.items():
        expected = baseline.get(node)
        if expected is None or canonical_json_bytes(expected) != canonical_json_bytes(row):
            raise ContractError(f"unapproved_failure_observed:{node}")
    removed_nodes = sorted(set(baseline) - set(observed))
    if set(remediated) != set(removed_nodes):
        raise ContractError("remediation_set_mismatch")
    for node in removed_nodes:
        baseline_row = baseline[node]
        if baseline_row.get("ownership_class") != "queue_owned":
            raise ContractError(f"external_failure_removed:{node}")
        if canonical_json_bytes(remediated[node]) != canonical_json_bytes(baseline_row):
            raise ContractError(f"remediation_row_mismatch:{node}")
    outcome = "approved_failure_subset" if removed_nodes else "known_failures_matched"
    return {
        "outcome": outcome,
        "observed_failure_count": len(observed),
        "removed_failure_node_ids": removed_nodes,
        "normalized_observed_failure_set_sha256": canonical_sha256(
            [observed[node] for node in sorted(observed)]
        ),
    }


def apply_skip_change(
    predecessor_node_ids: Sequence[str], change: Mapping[str, Any]
) -> list[str]:
    issues = validate_record(change)
    if issues or change.get("schema_version") != "broad_skip_change.v1":
        raise ContractError("skip_change_invalid")
    predecessor = list(predecessor_node_ids)
    added = change["added_skip_node_ids"]
    removed = change["removed_skip_node_ids"]
    for lane, values in (
        ("predecessor", predecessor),
        ("added", added),
        ("removed", removed),
    ):
        if not isinstance(values, list) or values != sorted(set(values)) or any(
            not isinstance(value, str) or not value for value in values
        ):
            raise ContractError(f"skip_{lane}_partition_invalid")
    bound_predecessor = change["predecessor_skip_set_binding"]["skip_node_ids"]
    if predecessor != bound_predecessor:
        raise ContractError("skip_predecessor_binding_mismatch")
    if set(added) & set(predecessor) or not set(removed) <= set(predecessor) or set(added) & set(removed):
        raise ContractError("skip_delta_partition_invalid")
    expected = sorted((set(predecessor) - set(removed)) | set(added))
    if change["resulting_skip_set_sha256"] != canonical_sha256(expected):
        raise ContractError("skip_result_digest_mismatch")
    return expected


def _builder_file_capture(
    repository_root: Path, logical_path: Path | str, *, role: str
) -> tuple[str, bytes]:
    path = Path(logical_path).as_posix()
    data = _read_repository_file_no_follow(repository_root, path)
    if data is None:
        raise ContractError(f"{role}_unreadable")
    return path, data


def _builder_binding(path: str, data: bytes, *, sized: bool = False) -> dict[str, Any]:
    binding: dict[str, Any] = {
        "path": path,
        "sha256": f"sha256:{hashlib.sha256(data).hexdigest()}",
    }
    if sized:
        binding["size"] = len(data)
    return binding


def _builder_json(data: bytes, *, role: str) -> Mapping[str, Any]:
    try:
        value = json.loads(data, object_pairs_hook=_reject_duplicate)
    except (ContractError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ContractError(f"{role}_invalid") from exc
    if not isinstance(value, Mapping):
        raise ContractError(f"{role}_invalid")
    return value


def _raise_builder_issues(prefix: str, issues: Sequence[Issue]) -> None:
    if issues:
        issue = sorted(set(issues))[0]
        raise ContractError(f"{prefix}:{issue.code}:{issue.path}")


_PYTEST_TERMINAL_SUMMARY_RE = re.compile(
    r"^(?:"
    r"=+ (?P<banner_body>.+?) in [0-9]+(?:\.[0-9]+)?s"
    r"(?: \([0-9]+:[0-5][0-9]:[0-5][0-9]\))? =+"
    r"|"
    r"(?P<bare_body>[^=].*?) in [0-9]+(?:\.[0-9]+)?s"
    r"(?: \([0-9]+:[0-5][0-9]:[0-5][0-9]\))?"
    r")$",
    re.MULTILINE,
)
_PYTEST_TERMINAL_SUMMARY_CLAUSE_RE = re.compile(
    r"(?P<count>[0-9]+) "
    r"(?P<label>passed|failed|errors?|skipped|warnings?|deselected|xfailed|xpassed)"
)


def _validate_pytest_terminal_summary(
    raw_log: str, totals: Mapping[str, Any]
) -> None:
    """Validate pytest's final totals line without treating it as identity data."""

    total_keys = ("collected", "passed", "failed", "errors", "skipped")
    if (
        not raw_log.strip()
        or not isinstance(totals, Mapping)
        or any(type(totals.get(key)) is not int or totals[key] < 0 for key in total_keys)
    ):
        raise ContractError("rs_log_outcome_mismatch")
    matches = list(_PYTEST_TERMINAL_SUMMARY_RE.finditer(raw_log))
    if len(matches) != 1 or raw_log[matches[0].end() :].strip():
        raise ContractError("rs_log_outcome_mismatch")

    body = matches[0].group("banner_body") or matches[0].group(
        "bare_body"
    )
    expected = {
        key: totals[key]
        for key in ("passed", "failed", "errors", "skipped")
        if totals[key]
    }
    if body == "no tests ran":
        if totals["collected"] != 0 or expected:
            raise ContractError("rs_log_outcome_mismatch")
        return
    if totals["collected"] == 0:
        raise ContractError("rs_log_outcome_mismatch")

    parsed: dict[str, int] = {}
    for clause in body.split(", "):
        match = _PYTEST_TERMINAL_SUMMARY_CLAUSE_RE.fullmatch(clause)
        if match is None:
            raise ContractError("rs_log_outcome_mismatch")
        raw_label = match.group("label")
        label = {
            "error": "errors",
            "warning": "warnings",
        }.get(raw_label, raw_label)
        if label in parsed:
            raise ContractError("rs_log_outcome_mismatch")
        parsed[label] = int(match.group("count"))
    observed = {
        key: parsed[key]
        for key in ("passed", "failed", "errors", "skipped")
        if key in parsed
    }
    if observed != expected:
        raise ContractError("rs_log_outcome_mismatch")


def _validate_builder_authorities(
    *,
    repository_root: Path,
    candidate_binding: Mapping[str, Any],
    execution_ledger_binding: Mapping[str, Any],
    permitted_ambient_paths: Sequence[str] = (),
) -> None:
    if not _is_candidate_binding(candidate_binding):
        raise ContractError("candidate_binding_invalid")
    _raise_builder_issues(
        "candidate_binding_invalid",
        _candidate_binding_live_issues(
            {"candidate_binding": candidate_binding},
            repository_root,
            permitted_ambient_paths=permitted_ambient_paths,
        ),
    )
    _raise_builder_issues(
        "execution_ledger_binding_invalid",
        _reopen_ledger_binding(
            execution_ledger_binding,
            repository_root,
            "$.execution_ledger_binding",
            allow_descendant=False,
        ),
    )


def _derive_collection_and_outcomes(
    *,
    repository_root: Path,
    collection_argv: Sequence[str],
    broad_environment: Mapping[str, Any],
    collection_log_path: Path | str,
    collection_exit_path: Path | str,
    collected_node_ids_path: Path | str,
    rs_log_path: Path | str,
    broad_exit_path: Path | str,
    junit_path: Path | str,
    pytest_temp_root_preflight_path: Path | str,
) -> tuple[dict[str, Any], dict[str, tuple[str, bytes]], Mapping[str, Any], dict[str, Any]]:
    captures = {
        role: _builder_file_capture(repository_root, path, role=role)
        for role, path in (
            ("collection_log", collection_log_path),
            ("collection_exit", collection_exit_path),
            ("collected_node_ids", collected_node_ids_path),
            ("rs_log", rs_log_path),
            ("broad_exit", broad_exit_path),
            ("junit", junit_path),
            ("preflight", pytest_temp_root_preflight_path),
        )
    }
    if not _is_environment(broad_environment):
        raise ContractError("broad_environment_invalid")
    collection_exit = parse_exit_bytes(captures["collection_exit"][1])
    if collection_exit != 0:
        raise ContractError("collection_exit_nonzero")
    try:
        node_text = captures["collected_node_ids"][1].decode("utf-8")
        collect_text = captures["collection_log"][1].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError("collection_bytes_invalid") from exc
    if captures["collected_node_ids"][1] and not captures["collected_node_ids"][1].endswith(b"\n"):
        raise ContractError("collected_node_bytes_invalid")
    nodes = node_text.splitlines()
    if nodes != sorted(set(nodes)):
        raise ContractError("collected_node_partition_invalid")
    log_nodes = sorted(
        line
        for line in collect_text.splitlines()
        if "::" in line and not line.startswith(("=", " "))
    )
    if log_nodes != nodes:
        raise ContractError("collection_log_node_mismatch")
    preflight = _builder_json(captures["preflight"][1], role="preflight_record")
    if preflight.get("schema_version") != "pytest_temp_root_preflight.v1":
        raise ContractError("preflight_record_invalid")
    _raise_builder_issues("preflight_record_invalid", validate_record(preflight))
    _raise_builder_issues(
        "preflight_record_invalid", validate_bound_record(preflight, repository_root)
    )
    if preflight.get("environment_binding") != {
        "PYTEST_DEBUG_TEMPROOT": broad_environment["PYTEST_DEBUG_TEMPROOT"]
    }:
        raise ContractError("preflight_environment_mismatch")
    outcomes = parse_junit_outcomes(
        captures["junit"][1],
        collected_node_ids=nodes,
        repository_root=repository_root,
        pytest_session_parent=Path(preflight["observed_session_parent"]),
    )
    broad_exit = parse_exit_bytes(captures["broad_exit"][1])
    expected_exit = 1 if outcomes["totals"]["failed"] + outcomes["totals"]["errors"] else 0
    if broad_exit != expected_exit:
        raise ContractError("broad_exit_semantics_invalid")
    try:
        rs_text = captures["rs_log"][1].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ContractError("rs_log_invalid") from exc
    _validate_pytest_terminal_summary(rs_text, outcomes["totals"])
    collection = {
        "argv": list(collection_argv),
        "cwd": ".",
        "environment": dict(broad_environment),
        "log_binding": _builder_binding(*captures["collection_log"], sized=True),
        "exit_binding": _builder_binding(*captures["collection_exit"], sized=True),
        "parsed_exit": collection_exit,
        "node_ids_binding": _builder_binding(*captures["collected_node_ids"], sized=True),
        "node_id_count": len(nodes),
        "node_id_list_sha256": canonical_sha256(nodes),
    }
    if not _is_collection(collection):
        raise ContractError("collection_contract_invalid")
    return collection, captures, preflight, {**outcomes, "collected_node_ids": nodes}


def _derive_failure_normalization(
    *, repository_root: Path, preflight: Mapping[str, Any], preflight_binding: Mapping[str, Any]
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "schema_version": "broad_failure_payload_normalization.v1",
        "repository_root": repository_root.as_posix(),
        "system_temp_root": preflight["system_temp_root"],
        "pytest_session_parent": preflight["observed_session_parent"],
        "pytest_root_component": preflight["root_component"],
        "pytest_version": preflight["pytest_version"],
        "pytest_temp_root_preflight_binding": dict(preflight_binding),
        "ordered_transforms": [
            "crlf_to_lf.v1",
            "strip_ansi_csi.v1",
            "repository_prefix.v1",
            "pytest_managed_run_prefix.v1",
        ],
        "pytest_temp_prefix_rule": "exact_pytest_managed_run_prefix.v1",
        "normalized_contract_sha256": "",
    }
    record["normalized_contract_sha256"] = canonical_sha256(
        record, exclude={"normalized_contract_sha256"}
    )
    _raise_builder_issues("failure_normalization_invalid", validate_record(record))
    return record


def _load_authority_record(
    *,
    repository_root: Path,
    binding: Mapping[str, Any],
    schema_version: str,
    role: str,
) -> Mapping[str, Any]:
    issues, record = _reopen_json_binding(
        binding, repository_root, f"$.{role}", expected_schema=schema_version
    )
    _raise_builder_issues(f"{role}_invalid", issues)
    if record is None:
        raise ContractError(f"{role}_invalid")
    if schema_version == "broad_outcome.v1" and record.get("outcomes", {}).get(
        "outcome"
    ) != "baseline_candidate":
        raise ContractError(f"{role}_not_baseline_candidate")
    _raise_builder_issues(
        f"{role}_invalid", validate_bound_record(record, repository_root)
    )
    return record


def derive_broad_baseline_comparison(
    *,
    repository_root: Path,
    known_failure_baseline_binding: Mapping[str, Any],
    approved_remediation_bindings: Sequence[Mapping[str, Any]],
    approved_skip_change_bindings: Sequence[Mapping[str, Any]],
    failure_normalization: Mapping[str, Any],
    observed_failures: Sequence[Mapping[str, Any]],
    observed_skipped_node_ids: Sequence[str],
) -> tuple[dict[str, Any], str]:
    """Reopen reviewed authority and derive the complete later-run comparison."""

    root = repository_root.resolve(strict=True)
    if not _is_known_failure_baseline_binding(known_failure_baseline_binding):
        raise ContractError("known_failure_baseline_binding_invalid")
    if not _is_reviewed_binding_prefix(list(approved_remediation_bindings)):
        raise ContractError("approved_remediation_prefix_invalid")
    if not _is_reviewed_binding_prefix(list(approved_skip_change_bindings)):
        raise ContractError("approved_skip_change_prefix_invalid")
    baseline_outcome = _load_authority_record(
        repository_root=root,
        binding=known_failure_baseline_binding["outcome"],
        schema_version="broad_outcome.v1",
        role="known_failure_baseline_binding.outcome",
    )
    baseline = _load_authority_record(
        repository_root=root,
        binding=known_failure_baseline_binding["record"],
        schema_version="broad_known_failure_baseline.v1",
        role="known_failure_baseline_binding.record",
    )
    attestation = _load_authority_record(
        repository_root=root,
        binding=known_failure_baseline_binding["owner_attestation"],
        schema_version="broad_failure_baseline_attestation.v1",
        role="known_failure_baseline_binding.owner_attestation",
    )
    _raise_builder_issues(
        "known_failure_baseline_reviews_invalid",
        validate_review_pair(
            specification_binding=known_failure_baseline_binding[
                "specification_review"
            ],
            quality_binding=known_failure_baseline_binding["quality_review"],
            repository_root=root,
            expected_subject_kind="implementation_failure_baseline",
            expected_subject_binding=known_failure_baseline_binding["record"],
        ),
    )
    if (
        baseline.get("broad_outcome_binding")
        != known_failure_baseline_binding["outcome"]
        or attestation.get("baseline_binding", {}).get("path")
        != known_failure_baseline_binding["record"]["path"]
        or attestation.get("baseline_binding", {}).get("sha256")
        != known_failure_baseline_binding["record"]["sha256"]
    ):
        raise ContractError("known_failure_baseline_graph_mismatch")
    if baseline_outcome.get("failure_normalization") != failure_normalization or baseline.get(
        "failure_normalization"
    ) != failure_normalization:
        raise ContractError("baseline_normalization_mismatch")

    baseline_rows = {
        row["node_id"]: row for row in baseline["failures"]
    }
    removed_rows: dict[str, Mapping[str, Any]] = {}
    for index, reviewed in enumerate(approved_remediation_bindings):
        record = _load_authority_record(
            repository_root=root,
            binding=reviewed["record"],
            schema_version="broad_failure_remediation.v1",
            role=f"approved_remediation_bindings[{index}].record",
        )
        _raise_builder_issues(
            "approved_remediation_reviews_invalid",
            validate_review_pair(
                specification_binding=reviewed["specification_review"],
                quality_binding=reviewed["quality_review"],
                repository_root=root,
                expected_subject_kind="broad_failure_remediation",
                expected_subject_binding=reviewed["record"],
            ),
        )
        if record.get("baseline_binding") != known_failure_baseline_binding["record"]:
            raise ContractError("remediation_baseline_binding_mismatch")
        for row in record["removed_failure_rows"]:
            node = row["node_id"]
            if node in removed_rows:
                raise ContractError("remediation_failure_duplicate")
            if row.get("ownership_class") != "queue_owned" or baseline_rows.get(node) != row:
                raise ContractError("remediation_failure_not_baseline_owned")
            removed_rows[node] = row

    observed_signatures = [
        {
            key: row[key]
            for key in ("node_id", "outcome_kind", "failure_payload_sha256")
        }
        for row in observed_failures
    ]
    if [row["node_id"] for row in observed_signatures] != sorted(
        {row["node_id"] for row in observed_signatures}
    ):
        raise ContractError("observed_failure_partition_invalid")
    expected_signatures = [
        {
            key: row[key]
            for key in ("node_id", "outcome_kind", "failure_payload_sha256")
        }
        for node, row in sorted(baseline_rows.items())
        if node not in removed_rows
    ]
    if observed_signatures != expected_signatures:
        raise ContractError("observed_failure_authority_mismatch")

    baseline_skips = list(baseline_outcome["outcomes"]["skipped_node_ids"])
    current_skips = baseline_skips
    for index, reviewed in enumerate(approved_skip_change_bindings):
        record = _load_authority_record(
            repository_root=root,
            binding=reviewed["record"],
            schema_version="broad_skip_change.v1",
            role=f"approved_skip_change_bindings[{index}].record",
        )
        _raise_builder_issues(
            "approved_skip_change_reviews_invalid",
            validate_review_pair(
                specification_binding=reviewed["specification_review"],
                quality_binding=reviewed["quality_review"],
                repository_root=root,
                expected_subject_kind="broad_skip_change",
                expected_subject_binding=reviewed["record"],
            ),
        )
        predecessor = record["predecessor_skip_set_binding"]
        if (
            predecessor["skip_node_ids"] != current_skips
            or predecessor["skip_set_sha256"] != canonical_sha256(current_skips)
        ):
            raise ContractError("skip_predecessor_authority_mismatch")
        current_skips = apply_skip_change(current_skips, record)
    if list(observed_skipped_node_ids) != current_skips:
        raise ContractError("observed_skip_authority_mismatch")

    comparison = {
        "normalization_contract_sha256": failure_normalization[
            "normalized_contract_sha256"
        ],
        "baseline_failure_set_sha256": baseline["normalized_failure_set_sha256"],
        "approved_remediation_set_sha256": canonical_sha256(
            list(approved_remediation_bindings)
        ),
        "observed_failure_set_sha256": canonical_sha256(observed_signatures),
        "removed_failure_node_ids": sorted(removed_rows),
        "predecessor_skip_set_sha256": canonical_sha256(baseline_skips),
        "approved_skip_change_set_sha256": canonical_sha256(
            list(approved_skip_change_bindings)
        ),
        "observed_skip_set_sha256": canonical_sha256(current_skips),
    }
    lifecycle = "approved_failure_subset" if removed_rows else "known_failures_matched"
    return comparison, lifecycle


def build_broad_outcome(
    *,
    repository_root: Path,
    candidate_binding: Mapping[str, Any],
    execution_ledger_binding: Mapping[str, Any],
    collection_argv: Sequence[str],
    broad_argv: Sequence[str],
    environment: Mapping[str, Any],
    collection_log_path: Path | str,
    collection_exit_path: Path | str,
    collected_node_ids_path: Path | str,
    rs_log_path: Path | str,
    broad_exit_path: Path | str,
    junit_path: Path | str,
    pytest_temp_root_preflight_path: Path | str,
    run_root_snapshots: Sequence[Mapping[str, Any]],
    known_failure_baseline_binding: Mapping[str, Any] | None = None,
    approved_remediation_bindings: Sequence[Mapping[str, Any]] = (),
    approved_skip_change_bindings: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build a broad result only from durable raw output and closed authorities."""

    root = repository_root.resolve(strict=True)
    broad_paths = {
        "collection-log": Path(collection_log_path),
        "collection-exit": Path(collection_exit_path),
        "collected-node-ids": Path(collected_node_ids_path),
        "pytest-temp-root-preflight": Path(pytest_temp_root_preflight_path),
        "broad-rs-log": Path(rs_log_path),
        "broad-exit": Path(broad_exit_path),
        "broad-junit": Path(junit_path),
    }
    broad_directories = {path.parent for path in broad_paths.values()}
    if (
        len(broad_directories) != 1
        or any(
            path.name != _BROAD_ROLE_FILENAMES[role]
            for role, path in broad_paths.items()
        )
    ):
        raise ContractError("broad_evidence_directory_mismatch")
    _validate_builder_authorities(
        repository_root=root,
        candidate_binding=candidate_binding,
        execution_ledger_binding=execution_ledger_binding,
    )
    collection, captures, preflight, parsed = _derive_collection_and_outcomes(
        repository_root=root,
        collection_argv=collection_argv,
        broad_environment=environment,
        collection_log_path=collection_log_path,
        collection_exit_path=collection_exit_path,
        collected_node_ids_path=collected_node_ids_path,
        rs_log_path=rs_log_path,
        broad_exit_path=broad_exit_path,
        junit_path=junit_path,
        pytest_temp_root_preflight_path=pytest_temp_root_preflight_path,
    )
    preflight_binding = _builder_binding(*captures["preflight"])
    normalization = _derive_failure_normalization(
        repository_root=root, preflight=preflight, preflight_binding=preflight_binding
    )
    if known_failure_baseline_binding is None:
        if approved_remediation_bindings or approved_skip_change_bindings:
            raise ContractError("broad_lifecycle_invalid")
        baseline_comparison = None
        lifecycle = "baseline_candidate"
    else:
        baseline_comparison, lifecycle = derive_broad_baseline_comparison(
            repository_root=root,
            known_failure_baseline_binding=known_failure_baseline_binding,
            approved_remediation_bindings=approved_remediation_bindings,
            approved_skip_change_bindings=approved_skip_change_bindings,
            failure_normalization=normalization,
            observed_failures=parsed["failures"],
            observed_skipped_node_ids=parsed["skipped_node_ids"],
        )
    record: dict[str, Any] = {
        "schema_version": "broad_outcome.v1",
        "candidate_binding": dict(candidate_binding),
        "execution_ledger_binding": dict(execution_ledger_binding),
        "collection": collection,
        "command": {"argv": list(broad_argv), "cwd": "."},
        "environment": dict(environment),
        "collected_node_ids": parsed["collected_node_ids"],
        "rs_log": _builder_binding(*captures["rs_log"]),
        "exit_result": {
            "binding": _builder_binding(*captures["broad_exit"]),
            "parsed_exit": parse_exit_bytes(captures["broad_exit"][1]),
        },
        "junit_report": _builder_binding(*captures["junit"]),
        "pytest_temp_root_preflight": preflight_binding,
        "failure_normalization": normalization,
        "outcomes": {
            "outcome": lifecycle,
            "totals": parsed["totals"],
            "failures": parsed["failures"],
            "skipped_node_ids": parsed["skipped_node_ids"],
        },
        "run_root_snapshots": [dict(row) for row in run_root_snapshots],
        "known_failure_baseline_binding": (
            dict(known_failure_baseline_binding)
            if known_failure_baseline_binding is not None
            else None
        ),
        "approved_remediation_bindings": [dict(row) for row in approved_remediation_bindings],
        "approved_skip_change_bindings": [dict(row) for row in approved_skip_change_bindings],
        "baseline_comparison": baseline_comparison,
        "normalized_outcome_sha256": "",
        "claims_not_made": [
            "This machine-derived outcome does not classify failure ownership or authorize remediation."
        ],
    }
    record["normalized_outcome_sha256"] = canonical_sha256(
        record, exclude={"normalized_outcome_sha256"}
    )
    _raise_builder_issues("broad_outcome_invalid", validate_record(record))
    _raise_builder_issues("broad_outcome_invalid", validate_bound_record(record, root))
    _raise_builder_issues(
        "broad_outcome_invalid",
        _reopen_ledger_binding(
            execution_ledger_binding,
            root,
            "$.execution_ledger_binding",
            allow_descendant=False,
        ),
    )
    return record


def build_broad_known_failure_baseline(
    *,
    repository_root: Path,
    broad_outcome_path: Path | str,
    ownership_classifications: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Join an exact ownership partition to a validated baseline-candidate outcome."""

    root = repository_root.resolve(strict=True)
    logical_outcome = Path(broad_outcome_path)
    if (
        logical_outcome.name != "outcome.json"
        or logical_outcome.parent.name != "implementation-baseline"
        or logical_outcome.parent.parent == Path(".")
    ):
        raise ContractError("baseline_outcome_path_invalid")
    outcome_path, outcome_bytes = _builder_file_capture(
        root, broad_outcome_path, role="broad_outcome"
    )
    outcome = _builder_json(outcome_bytes, role="broad_outcome")
    if outcome.get("schema_version") != "broad_outcome.v1":
        raise ContractError("broad_outcome_invalid")
    _raise_builder_issues("broad_outcome_invalid", validate_bound_record(outcome, root))
    _raise_builder_issues(
        "baseline_outcome_path_invalid",
        _broad_directory_issues(outcome, logical_outcome.parent),
    )
    if outcome.get("outcomes", {}).get("outcome") != "baseline_candidate":
        raise ContractError("broad_outcome_not_baseline_candidate")
    classifications: dict[str, Mapping[str, Any]] = {}
    expected_keys = {
        "node_id", "ownership_class", "ownership_basis", "authorized_remediation_scope"
    }
    for row in ownership_classifications:
        if not isinstance(row, Mapping) or set(row) != expected_keys:
            raise ContractError("ownership_classification_invalid")
        node = row.get("node_id")
        if not isinstance(node, str) or not node or node in classifications:
            raise ContractError("ownership_classification_partition_invalid")
        classifications[node] = row
    observed = outcome["outcomes"]["failures"]
    if set(classifications) != {row["node_id"] for row in observed}:
        raise ContractError("ownership_classification_partition_invalid")
    failures = []
    for observed_row in observed:
        classification = classifications[observed_row["node_id"]]
        row = {
            **{key: observed_row[key] for key in ("node_id", "outcome_kind", "failure_payload_sha256")},
            **{key: classification[key] for key in expected_keys - {"node_id"}},
        }
        if not _is_classified_failure_row(row):
            raise ContractError("ownership_classification_invalid")
        failures.append(row)
    failures.sort(key=lambda row: row["node_id"])
    record = {
        "schema_version": "broad_known_failure_baseline.v1",
        "execution_ledger_binding": dict(outcome["execution_ledger_binding"]),
        "candidate_binding": dict(outcome["candidate_binding"]),
        "collection_binding": dict(outcome["collection"]),
        "broad_outcome_binding": _builder_binding(outcome_path, outcome_bytes),
        "pytest_exit": dict(outcome["exit_result"]),
        "totals": dict(outcome["outcomes"]["totals"]),
        "failures": failures,
        "failure_normalization": dict(outcome["failure_normalization"]),
        "normalized_failure_set_sha256": canonical_sha256(failures),
        "classification_summary": {
            "queue_owned": sum(row["ownership_class"] == "queue_owned" for row in failures),
            "external": sum(row["ownership_class"] == "external" for row in failures),
        },
        "claims_not_made": [
            "This classification record does not authorize remediation or broaden candidate scope."
        ],
    }
    _raise_builder_issues("broad_failure_baseline_invalid", validate_record(record))
    _raise_builder_issues("broad_failure_baseline_invalid", validate_bound_record(record, root))
    return record


def _subject_manifest(
    *,
    repository_root: Path,
    candidate_binding: Mapping[str, Any],
    evidence_bindings: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    candidate_rows = {
        row["path"]: dict(row) for row in candidate_binding["candidate_paths"]
    }
    evidence: dict[str, tuple[str, int]] = {}
    for binding in evidence_bindings:
        if _is_complete_review_binding(binding):
            path = binding["immutable_path"]
            digest = binding["sha256"]
            declared_size = None
        elif (
            isinstance(binding, Mapping)
            and _is_relative_logical_path(binding.get("path"))
            and _is_sha256(binding.get("sha256"))
            and (
                "size" not in binding
                or type(binding.get("size")) is int
                and binding["size"] >= 0
            )
        ):
            path = binding["path"]
            digest = binding["sha256"]
            declared_size = binding.get("size")
        else:
            raise ContractError("subject_evidence_binding_invalid")
        if path in candidate_rows:
            raise ContractError("subject_candidate_evidence_overlap")
        data = _read_repository_file_no_follow(repository_root, path)
        if data is None:
            raise ContractError(f"subject_evidence_unreadable:{path}")
        coordinate = (f"sha256:{hashlib.sha256(data).hexdigest()}", len(data))
        if coordinate[0] != digest or (
            declared_size is not None and declared_size != coordinate[1]
        ):
            raise ContractError(f"subject_evidence_binding_mismatch:{path}")
        prior = evidence.get(path)
        if prior is not None and prior != coordinate:
            raise ContractError(f"subject_evidence_binding_conflict:{path}")
        evidence[path] = coordinate
    rows = list(candidate_rows.values())
    rows.extend(
        {
            "path": path,
            "sha256": coordinate[0],
            "size": coordinate[1],
            "state": "added",
        }
        for path, coordinate in evidence.items()
    )
    return sorted(rows, key=lambda row: row["path"])


def _ledger_evidence_bindings(
    repository_root: Path, binding: Mapping[str, Any]
) -> list[dict[str, Any]]:
    from .materialization import generation_binding_lineage_file_bindings

    issues, bound_lineage, _descendant_lineage = (
        generation_binding_lineage_file_bindings(repository_root, binding)
    )
    if issues:
        raise ContractError(f"ledger_generation_lineage_invalid:{issues[0].code}")
    return [
        {"path": binding["live_path"], "sha256": binding["byte_sha256"]},
        *bound_lineage,
    ]


def _focused_evidence_bindings(
    focused: Mapping[str, Any], focused_path: str
) -> list[dict[str, Any]]:
    base = Path(focused_path).parent.parent
    result: list[dict[str, Any]] = []
    for command in focused["commands"]:
        for field in ("log_binding", "exit_binding"):
            binding = command[field]
            result.append(
                {
                    "path": (base / binding["path"]).as_posix(),
                    "sha256": binding["sha256"],
                }
            )
    return result


def _broad_evidence_bindings(broad: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    result: list[Mapping[str, Any]] = [
        broad["rs_log"],
        broad["junit_report"],
        broad["pytest_temp_root_preflight"],
        broad["exit_result"]["binding"],
        broad["collection"]["log_binding"],
        broad["collection"]["exit_binding"],
        broad["collection"]["node_ids_binding"],
    ]
    baseline = broad.get("known_failure_baseline_binding")
    if isinstance(baseline, Mapping):
        result.extend(baseline[field] for field in (
            "outcome", "record", "specification_review", "quality_review", "owner_attestation"
        ))
    for field in ("approved_remediation_bindings", "approved_skip_change_bindings"):
        for reviewed in broad.get(field, []):
            result.extend(
                reviewed[name]
                for name in ("record", "specification_review", "quality_review")
            )
    return result


def _validate_task_contract(
    *, repository_root: Path, task_contract_binding: Mapping[str, Any]
) -> None:
    if not _is_task_contract_binding(task_contract_binding):
        raise ContractError("task_contract_binding_invalid")
    data = _read_repository_file_no_follow(
        repository_root, task_contract_binding["plan_path"]
    )
    if data is None or f"sha256:{hashlib.sha256(data).hexdigest()}" != task_contract_binding["plan_sha256"]:
        raise ContractError("task_contract_plan_mismatch")


_BROAD_ROLE_FILENAMES = {
    "collection-log": "collect.log",
    "collection-exit": "collect.exit",
    "collected-node-ids": "collected-node-ids.txt",
    "pytest-temp-root-preflight": "pytest-temp-root-preflight.json",
    "broad-rs-log": "pytest-rs.log",
    "broad-exit": "pytest.exit",
    "broad-junit": "pytest.junit.xml",
}


def _subject_evidence_directory(
    *, focused_path: str, sibling_path: str, sibling_name: str
) -> Path:
    focused = Path(focused_path)
    if focused.parts[-2:] != ("focused", "report.json"):
        raise ContractError("focused_report_path_invalid")
    directory = focused.parent.parent
    if Path(sibling_path) != directory / sibling_name:
        raise ContractError("subject_evidence_directory_mismatch")
    return directory


def _broad_directory_issues(
    broad: Mapping[str, Any], directory: Path
) -> list[Issue]:
    expected = {
        "collection.log_binding": directory / "collect.log",
        "collection.exit_binding": directory / "collect.exit",
        "collection.node_ids_binding": directory / "collected-node-ids.txt",
        "rs_log": directory / "pytest-rs.log",
        "exit_result.binding": directory / "pytest.exit",
        "junit_report": directory / "pytest.junit.xml",
        "pytest_temp_root_preflight": directory / "pytest-temp-root-preflight.json",
    }
    collection = broad.get("collection", {})
    exit_result = broad.get("exit_result", {})
    observed = {
        "collection.log_binding": collection.get("log_binding", {}),
        "collection.exit_binding": collection.get("exit_binding", {}),
        "collection.node_ids_binding": collection.get("node_ids_binding", {}),
        "rs_log": broad.get("rs_log", {}),
        "exit_result.binding": exit_result.get("binding", {}),
        "junit_report": broad.get("junit_report", {}),
        "pytest_temp_root_preflight": broad.get("pytest_temp_root_preflight", {}),
    }
    return [
        Issue("subject_evidence_directory_mismatch", f"$.broad.{role}")
        for role, expected_path in expected.items()
        if not isinstance(observed[role], Mapping)
        or observed[role].get("path") != expected_path.as_posix()
    ]


def _ledger_task_join_issues(
    record: Mapping[str, Any], repository_root: Path
) -> list[Issue]:
    task = record.get("task_contract_binding", {})
    ledger = record.get("execution_ledger_binding", {})
    if not _is_task_contract_binding(task) or not _is_ledger_binding(ledger):
        return []
    issues = _reopen_ledger_binding(ledger, repository_root, "$.execution_ledger_binding")
    if issues:
        return issues
    snapshot_bytes = _read_repository_file_no_follow(
        repository_root, ledger["snapshot_path"]
    )
    if snapshot_bytes is None:
        return [Issue("subject_ledger_task_join_invalid")]
    try:
        bound_generation = json.loads(
            snapshot_bytes, object_pairs_hook=_reject_duplicate
        )
    except (ContractError, json.JSONDecodeError, UnicodeDecodeError):
        return [Issue("subject_ledger_task_join_invalid")]
    current = (
        bound_generation.get("current_task")
        if isinstance(bound_generation, Mapping)
        else None
    )
    rows = (
        bound_generation.get("tasks", [])
        if isinstance(bound_generation, Mapping)
        else []
    )
    matching = [
        row
        for row in rows
        if isinstance(row, Mapping) and row.get("task_number") == current
    ]
    if (
        current != task["task_number"]
        or len(matching) != 1
        or matching[0].get("status") != "in_progress"
    ):
        return [Issue("subject_ledger_task_join_mismatch")]
    return []


def build_broad_evidence_bootstrap_subject(
    *,
    repository_root: Path,
    subject_path: Path | str,
    task_contract_binding: Mapping[str, Any],
    candidate_binding: Mapping[str, Any],
    execution_ledger_binding: Mapping[str, Any],
    bootstrap_workspace_baseline_path: Path | str,
    focused_report_path: Path | str,
    collection_argv: Sequence[str],
    environment: Mapping[str, Any],
    collection_log_path: Path | str,
    collection_exit_path: Path | str,
    collected_node_ids_path: Path | str,
    rs_log_path: Path | str,
    broad_exit_path: Path | str,
    junit_path: Path | str,
    pytest_temp_root_preflight_path: Path | str,
) -> dict[str, Any]:
    """Build the first broad-evidence review subject from the seven raw files."""

    root = repository_root.resolve(strict=True)
    logical_subject_path = _review_relative_path(Path(subject_path))
    evidence_root = Path(candidate_binding.get("evidence_root_exclusion", ""))
    if not _review_path_within_root(logical_subject_path, evidence_root):
        raise ContractError("review_evidence_root_mismatch")
    _validate_task_contract(
        repository_root=root, task_contract_binding=task_contract_binding
    )
    bootstrap_directory = _subject_evidence_directory(
        focused_path=Path(focused_report_path).as_posix(),
        sibling_path=Path(bootstrap_workspace_baseline_path).as_posix(),
        sibling_name="bootstrap-workspace-baseline.json",
    )
    observed_raw_paths = {
        "collection-log": Path(collection_log_path),
        "collection-exit": Path(collection_exit_path),
        "collected-node-ids": Path(collected_node_ids_path),
        "pytest-temp-root-preflight": Path(pytest_temp_root_preflight_path),
        "broad-rs-log": Path(rs_log_path),
        "broad-exit": Path(broad_exit_path),
        "broad-junit": Path(junit_path),
    }
    if any(
        path != bootstrap_directory / _BROAD_ROLE_FILENAMES[role]
        for role, path in observed_raw_paths.items()
    ):
        raise ContractError("bootstrap_evidence_directory_mismatch")
    baseline_path, baseline_bytes = _builder_file_capture(
        root, bootstrap_workspace_baseline_path, role="bootstrap_workspace_baseline"
    )
    baseline = _builder_json(baseline_bytes, role="bootstrap_workspace_baseline")
    if baseline.get("schema_version") != "bootstrap_workspace_baseline.v1":
        raise ContractError("bootstrap_workspace_baseline_invalid")
    ambient_paths = sorted(
        {
            path
            for row in baseline.get("status_rows", [])
            if isinstance(row, Mapping)
            for path in row.get("path_operands", [])
            if isinstance(path, str)
        }
    )
    _validate_builder_authorities(
        repository_root=root,
        candidate_binding=candidate_binding,
        execution_ledger_binding=execution_ledger_binding,
        permitted_ambient_paths=ambient_paths,
    )
    _raise_builder_issues(
        "subject_ledger_task_join_invalid",
        _ledger_task_join_issues(
            {
                "task_contract_binding": task_contract_binding,
                "execution_ledger_binding": execution_ledger_binding,
            },
            root,
        ),
    )
    focused_path, focused_bytes = _builder_file_capture(
        root, focused_report_path, role="focused_report"
    )
    focused = _builder_json(focused_bytes, role="focused_report")
    if focused.get("schema_version") != "implementation_focused_report.v1":
        raise ContractError("focused_report_invalid")
    _raise_builder_issues(
        "focused_report_invalid",
        validate_implementation_focused_report(
            focused,
            root,
            evidence_directory=Path(focused_path).parent.parent,
            permitted_ambient_paths=ambient_paths,
        ),
    )
    for field, expected in (
        ("task_contract_binding", task_contract_binding),
        ("candidate_binding", candidate_binding),
        ("execution_ledger_binding", execution_ledger_binding),
    ):
        if focused.get(field) != expected:
            raise ContractError(f"focused_{field}_mismatch")
    collection, captures, _preflight, parsed = _derive_collection_and_outcomes(
        repository_root=root,
        collection_argv=collection_argv,
        broad_environment=environment,
        collection_log_path=collection_log_path,
        collection_exit_path=collection_exit_path,
        collected_node_ids_path=collected_node_ids_path,
        rs_log_path=rs_log_path,
        broad_exit_path=broad_exit_path,
        junit_path=junit_path,
        pytest_temp_root_preflight_path=pytest_temp_root_preflight_path,
    )
    capture = baseline.get("bootstrap_capture_bindings", {})
    baseline_binding = {
        "path": baseline_path,
        "sha256": f"sha256:{hashlib.sha256(baseline_bytes).hexdigest()}",
        "head": baseline.get("head"),
        "index_sha256": baseline.get("index_sha256"),
        "index_file_sha256": capture.get("index_file_sha256"),
        "index_entries_file_sha256": capture.get("index_entries_file_sha256"),
        "status_file_sha256": capture.get("status_file_sha256"),
        "archive_sha256": capture.get("archive_sha256"),
        "index_entry_count": baseline.get("index_entry_count"),
        "index_entry_set_sha256": baseline.get("index_entry_set_sha256"),
        "dirty_entry_count": baseline.get("dirty_entry_count"),
        "dirty_entry_set_sha256": baseline.get("dirty_entry_set_sha256"),
        "dirty_path_set_sha256": baseline.get("dirty_path_set_sha256"),
        "normalized_baseline_sha256": baseline.get("normalized_baseline_sha256"),
    }
    role_by_capture = {
        "collection_log": "collection-log",
        "collection_exit": "collection-exit",
        "collected_node_ids": "collected-node-ids",
        "preflight": "pytest-temp-root-preflight",
        "rs_log": "broad-rs-log",
        "broad_exit": "broad-exit",
        "junit": "broad-junit",
    }
    raw_bindings = sorted(
        [
            {
                "role_id": role_by_capture[key],
                **_builder_binding(*value, sized=True),
            }
            for key, value in captures.items()
        ],
        key=lambda row: row["role_id"],
    )
    focused_binding = {
        **_builder_binding(focused_path, focused_bytes),
        "normalized_report_sha256": focused["normalized_report_sha256"],
    }
    evidence_bindings: list[Mapping[str, Any]] = [
        baseline_binding,
        focused_binding,
        *raw_bindings,
        *_ledger_evidence_bindings(root, execution_ledger_binding),
        *_focused_evidence_bindings(focused, focused_path),
        *_review_lifecycle_bindings(
            _validated_immutable_review_bindings(root, evidence_root),
            subject_path=logical_subject_path,
            subject_kind="broad_evidence_bootstrap",
        ),
    ]
    record: dict[str, Any] = {
        "schema_version": "broad_evidence_bootstrap_subject.v1",
        "task_contract_binding": dict(task_contract_binding),
        "bootstrap_workspace_baseline_binding": baseline_binding,
        "candidate_binding": dict(candidate_binding),
        "execution_ledger_binding": dict(execution_ledger_binding),
        "focused_report_binding": focused_binding,
        "collection_binding": collection,
        "raw_broad_bindings": raw_bindings,
        "observed_totals": dict(parsed["totals"]),
        "observed_failed_node_ids": [row["node_id"] for row in parsed["failures"]],
        "candidate_path_manifest": _subject_manifest(
            repository_root=root,
            candidate_binding=candidate_binding,
            evidence_bindings=evidence_bindings,
        ),
        "normalized_subject_sha256": "",
        "claims_not_made": [
            "This bootstrap subject records observed failures without classifying or accepting them."
        ],
    }
    record["normalized_subject_sha256"] = canonical_sha256(
        record, exclude={"normalized_subject_sha256"}
    )
    _raise_builder_issues("bootstrap_subject_invalid", validate_record(record))
    _raise_builder_issues(
        "bootstrap_subject_invalid",
        validate_bound_record(
            record,
            root,
            review_subject_path=logical_subject_path.as_posix(),
        ),
    )
    return record


def build_implementation_verification_subject(
    *,
    repository_root: Path,
    task_contract_binding: Mapping[str, Any],
    candidate_binding: Mapping[str, Any],
    execution_ledger_binding: Mapping[str, Any],
    focused_report_path: Path | str,
    broad_outcome_path: Path | str,
) -> dict[str, Any]:
    """Build the exact recursive review projection for one implementation candidate."""

    root = repository_root.resolve(strict=True)
    _validate_task_contract(
        repository_root=root, task_contract_binding=task_contract_binding
    )
    evidence_directory = _subject_evidence_directory(
        focused_path=Path(focused_report_path).as_posix(),
        sibling_path=Path(broad_outcome_path).as_posix(),
        sibling_name="outcome.json",
    )
    _validate_builder_authorities(
        repository_root=root,
        candidate_binding=candidate_binding,
        execution_ledger_binding=execution_ledger_binding,
    )
    _raise_builder_issues(
        "subject_ledger_task_join_invalid",
        _ledger_task_join_issues(
            {
                "task_contract_binding": task_contract_binding,
                "execution_ledger_binding": execution_ledger_binding,
            },
            root,
        ),
    )
    focused_path, focused_bytes = _builder_file_capture(root, focused_report_path, role="focused_report")
    broad_path, broad_bytes = _builder_file_capture(root, broad_outcome_path, role="broad_outcome")
    focused = _builder_json(focused_bytes, role="focused_report")
    broad = _builder_json(broad_bytes, role="broad_outcome")
    _raise_builder_issues(
        "focused_report_invalid",
        validate_implementation_focused_report(
            focused, root, evidence_directory=Path(focused_path).parent.parent
        ),
    )
    _raise_builder_issues("broad_outcome_invalid", validate_bound_record(broad, root))
    _raise_builder_issues(
        "subject_evidence_directory_invalid",
        _broad_directory_issues(broad, evidence_directory),
    )
    for name, related in (("focused", focused), ("broad", broad)):
        for field, expected in (
            ("candidate_binding", candidate_binding),
            ("execution_ledger_binding", execution_ledger_binding),
        ):
            if related.get(field) != expected:
                raise ContractError(f"{name}_{field}_mismatch")
    if focused.get("task_contract_binding") != task_contract_binding:
        raise ContractError("focused_task_contract_binding_mismatch")
    focused_binding = {
        **_builder_binding(focused_path, focused_bytes),
        "normalized_report_sha256": focused["normalized_report_sha256"],
    }
    broad_binding = _builder_binding(broad_path, broad_bytes)
    evidence_bindings: list[Mapping[str, Any]] = [
        focused_binding,
        broad_binding,
        *_ledger_evidence_bindings(root, execution_ledger_binding),
        *_focused_evidence_bindings(focused, focused_path),
        *_broad_evidence_bindings(broad),
    ]
    record: dict[str, Any] = {
        "schema_version": "implementation_verification_subject.v1",
        "task_contract_binding": dict(task_contract_binding),
        "candidate_binding": dict(candidate_binding),
        "execution_ledger_binding": dict(execution_ledger_binding),
        "focused_report_binding": focused_binding,
        "broad_outcome_binding": broad_binding,
        "candidate_path_manifest": _subject_manifest(
            repository_root=root,
            candidate_binding=candidate_binding,
            evidence_bindings=evidence_bindings,
        ),
        "normalized_subject_sha256": "",
        "claims_not_made": [
            "This review subject does not itself approve the implementation candidate."
        ],
    }
    record["normalized_subject_sha256"] = canonical_sha256(
        record, exclude={"normalized_subject_sha256"}
    )
    _raise_builder_issues("implementation_subject_invalid", validate_record(record))
    _raise_builder_issues("implementation_subject_invalid", validate_bound_record(record, root))
    return record


def validate_implementation_focused_report(
    record: Mapping[str, Any],
    repository_root: Path,
    *,
    evidence_directory: Path = Path("."),
    permitted_ambient_paths: Sequence[str] = (),
) -> list[Issue]:
    issues = validate_record(record)
    if issues:
        return issues
    if record.get("schema_version") != "implementation_focused_report.v1":
        return [Issue("schema_version_mismatch")]
    issues.extend(
        _candidate_binding_live_issues(
            record,
            repository_root.resolve(),
            permitted_ambient_paths=permitted_ambient_paths,
        )
    )
    issues.extend(
        _reopen_ledger_binding(
            record["execution_ledger_binding"],
            repository_root.resolve(),
            "$.execution_ledger_binding",
        )
    )
    task_contract = record["task_contract_binding"]
    plan_bytes = _read_repository_file_no_follow(
        repository_root, task_contract["plan_path"]
    )
    if plan_bytes is None or (
        f"sha256:{hashlib.sha256(plan_bytes).hexdigest()}"
        != task_contract["plan_sha256"]
    ):
        issues.append(
            Issue("focused_plan_binding_mismatch", "$.task_contract_binding")
        )
    required_rows = record["required_commands"]
    command_rows = record["commands"]
    if not isinstance(required_rows, list) or not isinstance(command_rows, list):
        return [Issue("focused_commands_invalid")]
    required_keys = {"role_id", "argv", "cwd", "environment"}
    command_keys = required_keys | {
        "input_bindings",
        "started_at",
        "finished_at",
        "log_binding",
        "exit_binding",
        "parsed_exit",
        "outcome",
    }
    required: dict[str, Mapping[str, Any]] = {}
    observed: dict[str, Mapping[str, Any]] = {}
    for row in required_rows:
        if not isinstance(row, Mapping) or set(row) != required_keys:
            issues.append(Issue("focused_required_row_invalid"))
            continue
        role = row.get("role_id")
        if not isinstance(role, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", role) or role in required:
            issues.append(Issue("focused_role_invalid"))
            continue
        required[role] = row
    for row in command_rows:
        if not isinstance(row, Mapping) or set(row) != command_keys:
            issues.append(Issue("focused_command_row_invalid"))
            if isinstance(row, Mapping) and isinstance(row.get("role_id"), str):
                observed[row["role_id"]] = row
            continue
        role = row["role_id"]
        if not isinstance(role, str) or role in observed:
            issues.append(Issue("focused_role_invalid"))
            continue
        observed[role] = row
    if set(required) != set(observed):
        issues.append(Issue("focused_role_set_mismatch"))
        return sorted(set(issues))
    if [row.get("role_id") for row in required_rows] != [
        row.get("role_id") for row in command_rows
    ]:
        issues.append(Issue("focused_role_order_mismatch"))
    if (
        type(record["command_count"]) is not int
        or record["command_count"] < 0
        or record["command_count"] != len(required_rows)
    ):
        issues.append(Issue("focused_command_count_mismatch"))
    if record["command_set_sha256"] != canonical_sha256(required_rows):
        issues.append(Issue("focused_command_set_digest_mismatch"))
    if record["outcome"] != "passed":
        issues.append(Issue("focused_outcome_invalid"))
    for role in sorted(required):
        expected = required[role]
        command = observed[role]
        if {key: command[key] for key in required_keys} != dict(expected):
            issues.append(Issue("focused_command_contract_mismatch", f"$.commands.{role}"))
        if command["outcome"] != "passed" or command["parsed_exit"] != 0:
            issues.append(Issue("focused_command_failed", f"$.commands.{role}"))
        try:
            started = datetime.fromisoformat(command["started_at"])
            finished = datetime.fromisoformat(command["finished_at"])
            if started.tzinfo is None or finished.tzinfo is None or finished < started:
                raise ValueError
        except (TypeError, ValueError):
            issues.append(Issue("focused_timestamp_invalid", f"$.commands.{role}"))
        for lane, expected_path in (
            ("log_binding", f"focused/logs/{role}.log"),
            ("exit_binding", f"focused/exits/{role}.exit"),
        ):
            binding = command[lane]
            if not isinstance(binding, Mapping) or set(binding) != {"path", "sha256"} or binding.get("path") != expected_path:
                issues.append(Issue(f"focused_{lane}_invalid", f"$.commands.{role}"))
                continue
            logical_path = (evidence_directory / expected_path).as_posix()
            data = _read_repository_file_no_follow(repository_root, logical_path)
            if data is None or f"sha256:{hashlib.sha256(data).hexdigest()}" != binding["sha256"]:
                issues.append(Issue(f"focused_{lane}_mismatch", f"$.commands.{role}"))
            elif lane == "exit_binding":
                try:
                    parsed = parse_exit_bytes(data)
                except ContractError:
                    issues.append(Issue("focused_exit_bytes_invalid", f"$.commands.{role}"))
                else:
                    if parsed != command["parsed_exit"]:
                        issues.append(Issue("focused_exit_value_mismatch", f"$.commands.{role}"))
        inputs = command["input_bindings"]
        if not isinstance(inputs, list):
            issues.append(Issue("focused_input_bindings_invalid", f"$.commands.{role}"))
        else:
            input_paths: list[str] = []
            for binding in inputs:
                if not isinstance(binding, Mapping) or set(binding) != {"path", "sha256"}:
                    issues.append(Issue("focused_input_binding_invalid", f"$.commands.{role}"))
                    continue
                input_paths.append(binding["path"])
                data = _read_repository_file_no_follow(
                    repository_root, binding["path"]
                )
                if data is None or f"sha256:{hashlib.sha256(data).hexdigest()}" != binding["sha256"]:
                    issues.append(Issue("focused_input_binding_mismatch", binding["path"]))
            if input_paths != sorted(set(input_paths)):
                issues.append(Issue("focused_input_binding_order_invalid", f"$.commands.{role}"))
    return sorted(set(issues))


def build_implementation_focused_report(
    *,
    repository_root: Path,
    task_contract_binding: Mapping[str, Any],
    candidate_binding: Mapping[str, Any],
    execution_ledger_binding: Mapping[str, Any],
    required_commands: Sequence[Mapping[str, Any]],
    observations: Sequence[Mapping[str, Any]],
    evidence_directory: Path = Path("."),
    permitted_ambient_paths: Sequence[str] = (),
) -> dict[str, Any]:
    if (
        not _is_task_contract_binding(task_contract_binding)
        or not _is_candidate_binding(candidate_binding)
        or not _is_ledger_binding(execution_ledger_binding)
        or not required_commands
        or any(not _is_focused_required_command(row) for row in required_commands)
    ):
        raise ContractError("focused_report_invalid:authoritative_input_invalid")
    _raise_builder_issues(
        "focused_report_invalid",
        _reopen_ledger_binding(
            execution_ledger_binding,
            repository_root,
            "$.execution_ledger_binding",
            allow_descendant=False,
        ),
    )
    required_by_role = {
        row["role_id"]: dict(row) for row in required_commands
    }
    if len(required_by_role) != len(required_commands):
        raise ContractError("focused_report_invalid:focused_required_partition_invalid")
    if not observations or any(not isinstance(row, Mapping) for row in observations):
        raise ContractError("focused_report_invalid:focused_observation_partition_invalid")
    observation_keys = {
        "role_id",
        "input_paths",
        "started_at",
        "finished_at",
        "log_path",
        "exit_path",
    }
    if any(
        set(row) != observation_keys
        or not isinstance(row.get("role_id"), str)
        or not row["role_id"]
        or not isinstance(row.get("input_paths"), list)
        or any(not isinstance(path, str) for path in row["input_paths"])
        or not isinstance(row.get("started_at"), str)
        or not isinstance(row.get("finished_at"), str)
        or not isinstance(row.get("log_path"), str)
        or not isinstance(row.get("exit_path"), str)
        for row in observations
    ):
        raise ContractError("focused_report_invalid:focused_observation_shape_invalid")
    observed_by_role = {
        row["role_id"]: row for row in observations
        if isinstance(row, Mapping) and isinstance(row.get("role_id"), str)
    }
    if len(observed_by_role) != len(observations) or set(observed_by_role) != set(required_by_role):
        raise ContractError("focused_report_invalid:focused_observation_partition_invalid")
    commands: list[dict[str, Any]] = []
    for required_row in required_commands:
        role = required_row["role_id"]
        required = required_by_role[role]
        observed = observed_by_role[role]
        log_path = Path(observed["log_path"])
        exit_path = Path(observed["exit_path"])
        if log_path.as_posix() != f"focused/logs/{role}.log" or exit_path.as_posix() != f"focused/exits/{role}.exit":
            raise ContractError("focused_observation_path_invalid")
        logical_log = (evidence_directory / log_path).as_posix()
        logical_exit = (evidence_directory / exit_path).as_posix()
        input_paths = list(observed["input_paths"])
        if input_paths != sorted(set(input_paths)):
            raise ContractError("focused_input_partition_invalid")
        inputs = []
        for raw_path in input_paths:
            path = Path(raw_path)
            if path.is_absolute() or ".." in path.parts:
                raise ContractError("focused_input_path_invalid")
            data = _read_repository_file_no_follow(repository_root, path.as_posix())
            if data is None:
                raise ContractError("focused_input_unreadable")
            inputs.append(
                {
                    "path": path.as_posix(),
                    "sha256": f"sha256:{hashlib.sha256(data).hexdigest()}",
                }
            )
        log_bytes = _read_repository_file_no_follow(repository_root, logical_log)
        exit_bytes = _read_repository_file_no_follow(repository_root, logical_exit)
        if log_bytes is None or exit_bytes is None:
            raise ContractError("focused_output_unreadable")
        parsed_exit = parse_exit_bytes(exit_bytes)
        command = {
            **required,
            "input_bindings": inputs,
            "started_at": observed["started_at"],
            "finished_at": observed["finished_at"],
            "log_binding": {
                "path": log_path.as_posix(),
                "sha256": f"sha256:{hashlib.sha256(log_bytes).hexdigest()}",
            },
            "exit_binding": {
                "path": exit_path.as_posix(),
                "sha256": f"sha256:{hashlib.sha256(exit_bytes).hexdigest()}",
            },
            "parsed_exit": parsed_exit,
            "outcome": "passed" if parsed_exit == 0 else "failed",
        }
        commands.append(command)
    record: dict[str, Any] = {
        "schema_version": "implementation_focused_report.v1",
        "task_contract_binding": dict(task_contract_binding),
        "candidate_binding": dict(candidate_binding),
        "execution_ledger_binding": dict(execution_ledger_binding),
        "required_commands": [dict(row) for row in required_commands],
        "commands": commands,
        "command_count": len(commands),
        "command_set_sha256": canonical_sha256(list(required_commands)),
        "outcome": "passed" if all(row["parsed_exit"] == 0 for row in commands) else "failed",
        "normalized_report_sha256": "",
        "claims_not_made": ["Focused verification does not claim a broad outcome or owner authorization."],
    }
    record["normalized_report_sha256"] = canonical_sha256(
        record, exclude={"normalized_report_sha256"}
    )
    _raise_builder_issues("focused_report_invalid", validate_record(record))
    _raise_builder_issues(
        "focused_report_invalid",
        validate_implementation_focused_report(
            record,
            repository_root,
            evidence_directory=evidence_directory,
            permitted_ambient_paths=permitted_ambient_paths,
        ),
    )
    _raise_builder_issues(
        "focused_report_invalid",
        _reopen_ledger_binding(
            execution_ledger_binding,
            repository_root,
            "$.execution_ledger_binding",
            allow_descendant=False,
        ),
    )
    return record


def _review_relative_path(path: Path) -> Path:
    text = path.as_posix()
    if (
        path.is_absolute()
        or text in {"", "."}
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ContractError("immutable_review_path_invalid")
    return Path(text)


def _open_review_directory(
    repository_root: Path, relative: Path, *, create: bool
) -> int:
    relative = _review_relative_path(relative)
    descriptor = os.open(repository_root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in relative.parts:
            try:
                child = os.open(
                    component,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=descriptor,
                )
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(component, dir_fd=descriptor)
                except FileExistsError:
                    pass
                try:
                    child = os.open(
                        component,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                        dir_fd=descriptor,
                    )
                except OSError as exc:
                    raise ContractError("immutable_review_path_invalid") from exc
            except OSError as exc:
                raise ContractError("immutable_review_path_invalid") from exc
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _review_file_bytes(directory_fd: int, name: str) -> bytes:
    try:
        captured = capture_regular_file_at(
            directory_fd, name, name, missing_ok=False
        )
    except AtomicPublishError as exc:
        raise ContractError("immutable_review_path_invalid") from exc
    assert captured is not None
    return captured.data


@dataclass(frozen=True)
class _BoundReviewLiveFile:
    path: Path
    file: BoundRegularFile
    parent: BoundLogicalParent


@dataclass(frozen=True)
class _ImmutableReviewPublication:
    file: BoundRegularFile
    parent: BoundLogicalParent
    created: bool


def _capture_review_live_file(
    repository_root: Path, path: Path, *, error: str
) -> _BoundReviewLiveFile:
    try:
        parent_fd = _open_review_directory(
            repository_root, path.parent, create=False
        )
        try:
            logical_parent = bind_logical_parent(
                repository_root, path.parent, parent_fd
            )
            captured = capture_regular_file_at(
                parent_fd, path.name, path.as_posix(), missing_ok=False
            )
        finally:
            os.close(parent_fd)
    except (AtomicPublishError, OSError) as exc:
        raise ContractError(error) from exc
    assert captured is not None
    if not logical_parent_matches(logical_parent):
        raise ContractError(error)
    return _BoundReviewLiveFile(path, captured, logical_parent)


def _review_live_file_matches(
    repository_root: Path, expected: _BoundReviewLiveFile
) -> bool:
    if not logical_parent_matches(expected.parent):
        return False
    try:
        current = _capture_review_live_file(
            repository_root,
            expected.path,
            error="immutable_review_live_input_changed",
        )
    except ContractError:
        return False
    return current.file == expected.file and logical_parent_matches(expected.parent)


def _immutable_review_publication_boundary(_boundary: str) -> None:
    """No-op deterministic boundary for live-input publication races."""


def _publish_immutable_review_bytes(
    repository_root: Path,
    destination: Path,
    history_fd: int,
    data: bytes,
) -> _ImmutableReviewPublication:
    logical_parent = bind_logical_parent(
        repository_root, destination.parent, history_fd
    )
    try:
        existing = capture_regular_file_at(
            history_fd,
            destination.name,
            destination.as_posix(),
            missing_ok=True,
        )
    except AtomicPublishError as exc:
        raise ContractError("immutable_review_path_invalid") from exc
    if existing is not None:
        if existing.data != data:
            raise ContractError("immutable_review_overwrite")
        if not logical_parent_matches(logical_parent):
            raise ContractError("immutable_review_path_invalid")
        return _ImmutableReviewPublication(existing, logical_parent, False)

    temporary_name = (
        f".{destination.name}.{os.getpid()}."
        f"{hashlib.sha256(os.urandom(32)).hexdigest()}.tmp"
    )
    descriptor = -1
    cleanup_temporary = True
    try:
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o444,
            dir_fd=history_fd,
        )
        offset = 0
        while offset < len(data):
            offset += os.write(descriptor, data[offset:])
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        conditional_publish_file_at(
            history_fd,
            temporary_name,
            destination.name,
            None,
            destination.as_posix(),
            logical_parent=logical_parent,
        )
        published = capture_regular_file_at(
            history_fd,
            destination.name,
            destination.as_posix(),
            missing_ok=False,
        )
        assert published is not None
        if not logical_parent_matches(logical_parent):
            raise AtomicPublishError(
                "logical_parent_changed", destination.as_posix()
            )
        return _ImmutableReviewPublication(published, logical_parent, True)
    except AtomicPublishError as exc:
        cleanup_temporary = not exc.preserve_temporary
        raise ContractError("immutable_review_path_invalid") from exc
    except OSError as exc:
        raise ContractError("immutable_review_path_invalid") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if cleanup_temporary:
            try:
                os.unlink(temporary_name, dir_fd=history_fd)
            except FileNotFoundError:
                pass


def _derived_immutable_review_path(
    evidence_root: Path, subject: Mapping[str, Any], review_kind: str, review_sha: str
) -> Path:
    logical_hash = hashlib.sha256(subject["path"].encode("utf-8")).hexdigest()
    return (
        evidence_root
        / "immutable-reviews"
        / logical_hash
        / subject["sha256"].removeprefix("sha256:")
        / f"{review_kind}-{review_sha.removeprefix('sha256:')}.json"
    )


def _review_path_within_root(path: Path, evidence_root: Path) -> bool:
    return path != evidence_root and evidence_root in path.parents


def derive_review_binding(
    *, evidence_root: Path, review_path: Path, review_bytes: bytes
) -> dict[str, Any]:
    """Derive one complete immutable binding from exact captured review bytes."""

    evidence_root = _review_relative_path(evidence_root)
    review_path = _review_relative_path(review_path)
    if not _review_path_within_root(review_path, evidence_root):
        raise ContractError("review_evidence_root_mismatch")
    review = _decode_live_record(review_bytes, error="review_unreadable")
    if review.get("schema_version") != "review.v1":
        raise ContractError("review_schema_invalid")
    issues = validate_record(review)
    if issues:
        raise ContractError(f"review_invalid:{issues[0].code}")
    subject_path = Path(review["subject"]["path"])
    if not _review_path_within_root(subject_path, evidence_root):
        raise ContractError("review_evidence_root_mismatch")
    review_sha = f"sha256:{hashlib.sha256(review_bytes).hexdigest()}"
    immutable_path = _derived_immutable_review_path(
        evidence_root, review["subject"], review["review_kind"], review_sha
    )
    if not _review_path_within_root(immutable_path, evidence_root):
        raise ContractError("review_evidence_root_mismatch")
    binding: dict[str, Any] = {
        "schema_version": "review_binding.v1",
        "logical_path": review_path.as_posix(),
        "immutable_path": immutable_path.as_posix(),
        "sha256": review_sha,
        "review_kind": review["review_kind"],
        "reviewer": review["reviewer"],
        "reviewed_at": review["reviewed_at"],
        "result": review["result"],
        "subject": review["subject"],
        "normalized_binding_sha256": "",
        "claims_not_made": [
            "This binding preserves review bytes and does not authorize mutation."
        ],
    }
    binding["normalized_binding_sha256"] = canonical_sha256(
        binding, exclude={"normalized_binding_sha256"}
    )
    return binding


def _expected_live_review_name(subject_kind: str, review_kind: str) -> str | None:
    lane = "specification" if review_kind == "specification" else "quality"
    if subject_kind in {"broad_evidence_bootstrap", "implementation_candidate"}:
        return f"{lane}-review.json"
    if subject_kind == "implementation_failure_baseline":
        return f"implementation-baseline-{lane}.json"
    if subject_kind == "broad_failure_remediation":
        return f"remediation-{lane}-review.json"
    if subject_kind == "broad_skip_change":
        return f"skip-change-{lane}-review.json"
    return None


def _validated_immutable_review_bindings(
    repository_root: Path,
    evidence_root: Path,
) -> list[dict[str, Any]]:
    """Enumerate and close every immutable review under one evidence root."""

    evidence_root = _review_relative_path(evidence_root)
    root = evidence_root / "immutable-reviews"
    try:
        root_fd = _open_review_directory(repository_root, root, create=False)
    except FileNotFoundError:
        return []
    bindings: list[dict[str, Any]] = []
    try:
        for logical_hash in sorted(os.listdir(root_fd)):
            if HEX_SHA256_RE.fullmatch(logical_hash) is None:
                raise ContractError("immutable_review_path_invalid")
            try:
                logical_fd = os.open(
                    logical_hash,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=root_fd,
                )
            except OSError as exc:
                raise ContractError("immutable_review_path_invalid") from exc
            try:
                for subject_hash in sorted(os.listdir(logical_fd)):
                    if HEX_SHA256_RE.fullmatch(subject_hash) is None:
                        raise ContractError("immutable_review_path_invalid")
                    try:
                        subject_fd = os.open(
                            subject_hash,
                            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=logical_fd,
                        )
                    except OSError as exc:
                        raise ContractError("immutable_review_path_invalid") from exc
                    try:
                        for name in sorted(os.listdir(subject_fd)):
                            if re.fullmatch(
                                r"(?:specification|code_quality)-[0-9a-f]{64}\.json",
                                name,
                            ) is None:
                                raise ContractError("immutable_review_path_invalid")
                            review_bytes = _review_file_bytes(subject_fd, name)
                            try:
                                review = _decode_live_record(
                                    review_bytes,
                                    error="immutable_review_path_invalid",
                                )
                                if validate_record(review):
                                    raise ContractError(
                                        "immutable_review_path_invalid"
                                    )
                                expected_name = _expected_live_review_name(
                                    review["subject"]["kind"],
                                    review["review_kind"],
                                )
                                if expected_name is None:
                                    raise ContractError(
                                        "immutable_review_path_invalid"
                                    )
                                logical_path = Path(
                                    review["subject"]["path"]
                                ).with_name(expected_name)
                                binding = derive_review_binding(
                                    evidence_root=evidence_root,
                                    review_path=logical_path,
                                    review_bytes=review_bytes,
                                )
                            except (KeyError, TypeError, ValueError, ContractError) as exc:
                                raise ContractError(
                                    "immutable_review_path_invalid"
                                ) from exc
                            observed_path = (
                                root / logical_hash / subject_hash / name
                            )
                            if (
                                binding["immutable_path"]
                                != observed_path.as_posix()
                                or validate_bound_record(
                                    binding, repository_root
                                )
                            ):
                                raise ContractError(
                                    "immutable_review_path_invalid"
                                )
                            bindings.append(binding)
                    finally:
                        os.close(subject_fd)
            finally:
                os.close(logical_fd)
    finally:
        os.close(root_fd)
    return sorted(bindings, key=lambda binding: binding["immutable_path"])


def _review_lifecycle_bindings(
    bindings: Sequence[Mapping[str, Any]],
    *,
    subject_path: Path,
    subject_kind: str,
) -> list[Mapping[str, Any]]:
    """Select the two deterministic live review slots for one subject path."""

    subject_path = _review_relative_path(subject_path)
    expected_live_paths = {
        (subject_path.parent / name).as_posix()
        for review_kind in ("specification", "code_quality")
        if (name := _expected_live_review_name(subject_kind, review_kind))
        is not None
    }
    if len(expected_live_paths) != 2:
        raise ContractError("immutable_review_path_invalid")
    matching: list[Mapping[str, Any]] = []
    for binding in bindings:
        subject = binding.get("subject", {})
        if subject.get("path") != subject_path.as_posix():
            continue
        if (
            subject.get("kind") != subject_kind
            or binding.get("logical_path") not in expected_live_paths
        ):
            raise ContractError("immutable_review_path_invalid")
        matching.append(binding)
    return sorted(matching, key=lambda binding: binding["immutable_path"])


def _publication_manifest_exclusions(
    *,
    repository_root: Path,
    evidence_root: Path,
    subject_path: Path,
    review_path: Path,
    subject_kind: str,
) -> list[str]:
    _validated_immutable_review_bindings(repository_root, evidence_root)
    subject_bytes = _read_repository_file_no_follow(
        repository_root, subject_path.as_posix()
    )
    if subject_bytes is None:
        raise ContractError("review_subject_unreadable")
    subject_sha = f"sha256:{hashlib.sha256(subject_bytes).hexdigest()}"
    current_review_bytes = _read_repository_file_no_follow(
        repository_root, review_path.as_posix()
    )
    if current_review_bytes is None:
        raise ContractError("review_unreadable")
    try:
        current_binding = derive_review_binding(
            evidence_root=evidence_root,
            review_path=review_path,
            review_bytes=current_review_bytes,
        )
    except ContractError as exc:
        raise ContractError("review_unreadable") from exc
    paths = {
        subject_path.as_posix(),
        review_path.as_posix(),
        current_binding["immutable_path"],
    }
    for review_kind in ("specification", "code_quality"):
        name = _expected_live_review_name(subject_kind, review_kind)
        if name is None:
            continue
        sibling = subject_path.parent / name
        review_bytes = _read_repository_file_no_follow(
            repository_root, sibling.as_posix()
        )
        if sibling == review_path or review_bytes is None:
            continue
        try:
            binding = derive_review_binding(
                evidence_root=evidence_root,
                review_path=sibling,
                review_bytes=review_bytes,
            )
        except ContractError as exc:
            raise ContractError("review_unreadable") from exc
        if (
            binding["review_kind"] != review_kind
            or binding["subject"]
            != {
                "kind": subject_kind,
                "path": subject_path.as_posix(),
                "sha256": subject_sha,
            }
        ):
            raise ContractError("review_subject_binding_mismatch")
        immutable_bytes = _read_repository_file_no_follow(
            repository_root, binding["immutable_path"]
        )
        if immutable_bytes is not None and validate_bound_record(
            binding, repository_root
        ):
            raise ContractError("immutable_review_path_invalid")
        paths.update({sibling.as_posix(), binding["immutable_path"]})
    return sorted(paths)


def _decode_review_bytes(data: bytes) -> Mapping[str, Any]:
    try:
        value = json.loads(data, object_pairs_hook=_reject_duplicate)
    except (json.JSONDecodeError, UnicodeDecodeError, ContractError) as exc:
        raise ContractError("prior_immutable_review_invalid") from exc
    if not isinstance(value, Mapping):
        raise ContractError("prior_immutable_review_invalid")
    return value


def _decode_live_record(data: bytes | None, *, error: str) -> Mapping[str, Any]:
    if data is None:
        raise ContractError(error)
    try:
        value = json.loads(data, object_pairs_hook=_reject_duplicate)
    except (json.JSONDecodeError, UnicodeDecodeError, ContractError) as exc:
        raise ContractError(error) from exc
    if not isinstance(value, Mapping):
        raise ContractError(error)
    return value


def publish_immutable_review(
    *, repository_root: Path, evidence_root: Path, subject_path: Path,
    review_path: Path, prior_review_binding: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    repository_root = repository_root.resolve(strict=True)
    evidence_root = _review_relative_path(evidence_root)
    subject_path = _review_relative_path(subject_path)
    review_path = _review_relative_path(review_path)
    if not (
        _review_path_within_root(subject_path, evidence_root)
        and _review_path_within_root(review_path, evidence_root)
    ):
        raise ContractError("review_evidence_root_mismatch")
    subject_capture = _capture_review_live_file(
        repository_root, subject_path, error="review_subject_unreadable"
    )
    review_capture = _capture_review_live_file(
        repository_root, review_path, error="review_unreadable"
    )
    subject_bytes = subject_capture.file.data
    review_bytes = review_capture.file.data
    subject = _decode_live_record(subject_bytes, error="review_subject_unreadable")
    review = _decode_live_record(review_bytes, error="review_unreadable")
    issues = validate_record(review)
    if issues:
        raise ContractError(f"review_invalid:{issues[0].code}")
    assert subject_bytes is not None and review_bytes is not None
    subject_sha = f"sha256:{hashlib.sha256(subject_bytes).hexdigest()}"
    derived_binding = derive_review_binding(
        evidence_root=evidence_root,
        review_path=review_path,
        review_bytes=review_bytes,
    )
    review_sha = derived_binding["sha256"]
    binding = review.get("subject")
    if (
        not isinstance(binding, Mapping)
        or binding.get("path") != subject_path.as_posix()
        or binding.get("sha256") != subject_sha
    ):
        raise ContractError("review_subject_binding_mismatch")
    manifest_exclusions = _publication_manifest_exclusions(
        repository_root=repository_root,
        evidence_root=evidence_root,
        subject_path=subject_path,
        review_path=review_path,
        subject_kind=binding["kind"],
    )
    subject_kind_issues = validate_review_subject(
        subject_kind=binding["kind"],
        record=subject,
        repository_root=repository_root,
        subject_path=subject_path,
        permitted_manifest_exclusions=manifest_exclusions,
    )
    if subject_kind_issues:
        prefix = (
            "review_subject_kind_schema_mismatch"
            if subject_kind_issues[0].code
            in {"review_subject_kind_not_registered", "review_subject_schema_mismatch"}
            else "review_subject_record_invalid"
        )
        raise ContractError(
            f"{prefix}:{subject_kind_issues[0].code}"
        )
    expected_name = _expected_live_review_name(binding["kind"], review["review_kind"])
    if expected_name is None or review_path.name != expected_name:
        raise ContractError("review_live_path_mismatch")
    destination = Path(derived_binding["immutable_path"])
    history_fd = _open_review_directory(
        repository_root, destination.parent, create=True
    )
    try:
        prefix = f"{review['review_kind']}-"
        existing_names = sorted(name for name in os.listdir(history_fd) if name.startswith(prefix))
        for name in existing_names:
            _review_file_bytes(history_fd, name)
        current_already_preserved = destination.name in existing_names
        prior_history_exists = any(name != destination.name for name in existing_names)
        logical_fd = _open_review_directory(
            repository_root, destination.parent.parent, create=False
        )
        try:
            for subject_coordinate in os.listdir(logical_fd):
                if HEX_SHA256_RE.fullmatch(subject_coordinate) is None:
                    raise ContractError("immutable_review_path_invalid")
                try:
                    subject_fd = os.open(
                        subject_coordinate,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                        dir_fd=logical_fd,
                    )
                except OSError as exc:
                    raise ContractError("immutable_review_path_invalid") from exc
                try:
                    for name in os.listdir(subject_fd):
                        if not name.startswith(prefix):
                            continue
                        _review_file_bytes(subject_fd, name)
                        if (
                            subject_coordinate != destination.parent.name
                            or name != destination.name
                        ):
                            prior_history_exists = True
                finally:
                    os.close(subject_fd)
        finally:
            os.close(logical_fd)
        if prior_history_exists and prior_review_binding is None:
            raise ContractError("prior_review_binding_required")
        if prior_review_binding is not None:
            prior_issues = validate_bound_record(prior_review_binding, repository_root)
            if prior_issues:
                raise ContractError(
                    f"prior_immutable_review_invalid:{prior_issues[0].code}"
                )
            if (
                prior_review_binding.get("logical_path") != review_path.as_posix()
                or prior_review_binding.get("review_kind") != review["review_kind"]
            ):
                raise ContractError("prior_immutable_review_invalid")
        elif not current_already_preserved and existing_names:
            raise ContractError("prior_review_binding_required")
        publication = _publish_immutable_review_bytes(
            repository_root, destination, history_fd, review_bytes
        )
        _immutable_review_publication_boundary(
            "before_live_input_revalidation"
        )
        if not (
            _review_live_file_matches(repository_root, subject_capture)
            and _review_live_file_matches(repository_root, review_capture)
        ):
            if publication.created:
                try:
                    conditional_quarantine_file_at(
                        history_fd,
                        destination.name,
                        publication.file,
                        destination.as_posix(),
                        logical_parent=publication.parent,
                    )
                except AtomicPublishError as exc:
                    raise ContractError(
                        "immutable_review_live_input_cleanup_failed"
                    ) from exc
            raise ContractError("immutable_review_live_input_changed")
    finally:
        os.close(history_fd)
    return derived_binding


def _absolute_file_binding_shape_issues(value: Any, *, path: str) -> list[Issue]:
    if not isinstance(value, Mapping) or set(value) != {"path", "sha256"}:
        return [Issue("file_binding_invalid", path)]
    raw_path = value["path"]
    digest = value["sha256"]
    if (
        not isinstance(raw_path, str)
        or not Path(raw_path).is_absolute()
        or not isinstance(digest, str)
        or SHA256_RE.fullmatch(digest) is None
    ):
        return [Issue("file_binding_invalid", path)]
    return []


def _canonical_absolute_path(value: Any) -> Path | None:
    if not isinstance(value, str):
        return None
    path = Path(value)
    if not path.is_absolute() or path != path.resolve():
        return None
    return path


def _validate_failure_payload_normalization(
    record: Mapping[str, Any],
) -> list[Issue]:
    issues: list[Issue] = []
    repository_root = _canonical_absolute_path(record["repository_root"])
    if repository_root is None:
        issues.append(
            Issue("normalization_repository_root_invalid", "$.repository_root")
        )
    system_root = _canonical_absolute_path(record["system_temp_root"])
    if system_root is None:
        issues.append(
            Issue("normalization_system_temp_root_invalid", "$.system_temp_root")
        )
    session_parent = _canonical_absolute_path(record["pytest_session_parent"])
    if session_parent is None:
        issues.append(
            Issue("normalization_session_parent_invalid", "$.pytest_session_parent")
        )
    if not _is_file_binding(record["pytest_temp_root_preflight_binding"]):
        issues.append(
            Issue(
                "normalization_preflight_binding_invalid",
                "$.pytest_temp_root_preflight_binding",
            )
        )
    if record["pytest_version"] != "8.4.1":
        issues.append(
            Issue("normalization_pytest_version_invalid", "$.pytest_version")
        )
    component = record["pytest_root_component"]
    if (
        not isinstance(component, str)
        or not component
        or component in {".", ".."}
        or "\x00" in component
        or "/" in component
        or "\\" in component
    ):
        issues.append(
            Issue("normalization_root_component_invalid", "$.pytest_root_component")
        )
        component = None
    if (
        system_root is not None
        and session_parent is not None
        and component is not None
        and session_parent != system_root / f"pytest-of-{component}"
    ):
        issues.append(
            Issue("normalization_session_parent_mismatch", "$.pytest_session_parent")
        )
    if record["ordered_transforms"] != [
        "crlf_to_lf.v1",
        "strip_ansi_csi.v1",
        "repository_prefix.v1",
        "pytest_managed_run_prefix.v1",
    ]:
        issues.append(
            Issue("normalization_transforms_invalid", "$.ordered_transforms")
        )
    if record["pytest_temp_prefix_rule"] != "exact_pytest_managed_run_prefix.v1":
        issues.append(
            Issue("normalization_rule_invalid", "$.pytest_temp_prefix_rule")
        )
    return issues


def _validate_pytest_temp_root_preflight(record: Mapping[str, Any]) -> list[Issue]:
    issues = _absolute_file_binding_shape_issues(
        record["pytest_executable_binding"], path="$.pytest_executable_binding"
    )
    issues.extend(
        _absolute_file_binding_shape_issues(
            record["tmpdir_module_binding"], path="$.tmpdir_module_binding"
        )
    )
    if record["pytest_version"] != "8.4.1":
        issues.append(Issue("pytest_version_mismatch", "$.pytest_version"))

    environment = record["environment_binding"]
    if not isinstance(environment, Mapping) or set(environment) != {
        "PYTEST_DEBUG_TEMPROOT"
    }:
        issues.append(Issue("pytest_environment_binding_invalid", "$.environment_binding"))
        environment_root: str | None = None
    else:
        environment_root = environment["PYTEST_DEBUG_TEMPROOT"]
        if environment_root is not None and not isinstance(environment_root, str):
            issues.append(
                Issue("pytest_environment_value_invalid", "$.environment_binding.PYTEST_DEBUG_TEMPROOT")
            )
            environment_root = None

    expected_system_root = Path(
        environment_root or tempfile.gettempdir()
    ).resolve()
    system_root = _canonical_absolute_path(record["system_temp_root"])
    if system_root is None or system_root != expected_system_root:
        issues.append(Issue("pytest_system_temp_root_mismatch", "$.system_temp_root"))

    raw_user = record["raw_get_user"]
    if raw_user is not None and not isinstance(raw_user, str):
        issues.append(Issue("pytest_raw_get_user_invalid", "$.raw_get_user"))
        raw_user = None
    resolution = record["root_component_resolution"]
    component = record["root_component"]
    expected_resolution: str | None
    expected_component: str | None
    if raw_user:
        if resolution == "raw_get_user":
            expected_resolution, expected_component = "raw_get_user", raw_user
        elif resolution == "mkdir_fallback_unknown":
            expected_resolution, expected_component = "mkdir_fallback_unknown", "unknown"
        else:
            expected_resolution, expected_component = None, None
    else:
        expected_resolution, expected_component = "missing_user_unknown", "unknown"
    if resolution != expected_resolution:
        issues.append(Issue("pytest_root_resolution_mismatch", "$.root_component_resolution"))
    if component != expected_component:
        issues.append(Issue("pytest_root_component_mismatch", "$.root_component"))

    session_parent = _canonical_absolute_path(record["observed_session_parent"])
    if system_root is None or not isinstance(component, str):
        expected_parent = None
    else:
        expected_parent = system_root / f"pytest-of-{component}"
    if session_parent is None or session_parent != expected_parent:
        issues.append(Issue("pytest_session_parent_mismatch", "$.observed_session_parent"))

    observed_basetemp = _canonical_absolute_path(record["observed_basetemp"])
    if (
        observed_basetemp is None
        or session_parent is None
        or observed_basetemp.parent != session_parent
        or re.fullmatch(r"pytest-[0-9]+", observed_basetemp.name) is None
    ):
        issues.append(Issue("pytest_observed_basetemp_invalid", "$.observed_basetemp"))

    claims = record["claims_not_made"]
    if not isinstance(claims, list) or not claims or any(
        not isinstance(claim, str) or not claim for claim in claims
    ):
        issues.append(Issue("pytest_preflight_claims_invalid", "$.claims_not_made"))
    return sorted(set(issues))


def _observe_pytest_automatic_basetemp(pytest_executable: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="retirement-pytest-preflight-") as directory:
        probe_root = Path(directory)
        observation_path = probe_root / "observation.json"
        probe_path = probe_root / "test_runtime_probe.py"
        probe_path.write_text(
            """from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

import _pytest.tmpdir as tmpdir_module
import pytest


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def test_observe_automatic_basetemp(tmp_path_factory, request) -> None:
    assert request.config.option.basetemp is None
    captured = []
    original_get_user = tmpdir_module.get_user

    def capture_get_user():
        value = original_get_user()
        captured.append(value)
        return value

    tmpdir_module.get_user = capture_get_user
    try:
        observed = tmp_path_factory.getbasetemp()
    finally:
        tmpdir_module.get_user = original_get_user
    assert len(captured) == 1
    module_path = Path(tmpdir_module.__file__).resolve()
    system_root = Path(
        os.environ.get("PYTEST_DEBUG_TEMPROOT") or tempfile.gettempdir()
    ).resolve()
    result = {
        "environment_value": os.environ.get("PYTEST_DEBUG_TEMPROOT"),
        "pytest_version": pytest.__version__,
        "raw_get_user": captured[0],
        "system_temp_root": str(system_root),
        "tmpdir_module_path": str(module_path),
        "tmpdir_module_sha256": _sha256(module_path),
        "observed_basetemp": str(observed.resolve()),
    }
    Path(OBSERVATION_PATH).write_text(
        json.dumps(result, sort_keys=True, separators=(",", ":"))
    )
""".replace("OBSERVATION_PATH", repr(str(observation_path)))
        )
        completed = subprocess.run(
            [str(pytest_executable), "-q", "-p", "no:cacheprovider", str(probe_path)],
            cwd=Path.cwd(),
            env=os.environ.copy(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise ContractError(
                "pytest_temp_root_probe_failed:"
                f"exit={completed.returncode}:stdout={completed.stdout[-1000:]!r}:"
                f"stderr={completed.stderr[-1000:]!r}"
            )
        try:
            observation = load_json_closed(observation_path)
        except ContractError as exc:
            raise ContractError("pytest_temp_root_observation_unreadable") from exc
        expected_keys = {
            "environment_value",
            "pytest_version",
            "raw_get_user",
            "system_temp_root",
            "tmpdir_module_path",
            "tmpdir_module_sha256",
            "observed_basetemp",
        }
        if not isinstance(observation, Mapping) or set(observation) != expected_keys:
            raise ContractError("pytest_temp_root_observation_invalid")
        if (
            not isinstance(observation["pytest_version"], str)
            or not isinstance(observation["tmpdir_module_path"], str)
            or not isinstance(observation["tmpdir_module_sha256"], str)
            or SHA256_RE.fullmatch(observation["tmpdir_module_sha256"]) is None
            or not isinstance(observation["system_temp_root"], str)
            or not isinstance(observation["observed_basetemp"], str)
            or observation["environment_value"] is not None
            and not isinstance(observation["environment_value"], str)
            or observation["raw_get_user"] is not None
            and not isinstance(observation["raw_get_user"], str)
        ):
            raise ContractError("pytest_temp_root_observation_invalid")
        return dict(observation)


def build_pytest_temp_root_preflight(pytest_executable: Path) -> dict[str, Any]:
    executable = pytest_executable.resolve(strict=True)
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise ContractError("pytest_executable_invalid")
    observation = _observe_pytest_automatic_basetemp(executable)
    if observation["pytest_version"] != "8.4.1":
        raise ContractError(f"pytest_version_mismatch:{observation['pytest_version']}")

    system_temp_root = Path(observation["system_temp_root"])
    observed = Path(observation["observed_basetemp"])
    parent = observed.parent
    raw_user = observation["raw_get_user"]
    initial_component = raw_user if raw_user else "unknown"
    initial_parent = system_temp_root / f"pytest-of-{initial_component}"
    fallback_parent = system_temp_root / "pytest-of-unknown"
    if parent == initial_parent:
        component = initial_component
        resolution = "raw_get_user" if raw_user else "missing_user_unknown"
    elif raw_user and parent == fallback_parent:
        component = "unknown"
        resolution = "mkdir_fallback_unknown"
    else:
        raise ContractError("pytest_temp_root_parent_disagrees_with_runtime")

    module_path = Path(observation["tmpdir_module_path"])
    if file_sha256(module_path) != observation["tmpdir_module_sha256"]:
        raise ContractError("pytest_tmpdir_module_changed_during_probe")
    record: dict[str, Any] = {
        "schema_version": "pytest_temp_root_preflight.v1",
        "pytest_executable_binding": {
            "path": str(executable),
            "sha256": file_sha256(executable),
        },
        "pytest_version": observation["pytest_version"],
        "tmpdir_module_binding": {
            "path": str(module_path),
            "sha256": observation["tmpdir_module_sha256"],
        },
        "environment_binding": {
            "PYTEST_DEBUG_TEMPROOT": observation["environment_value"]
        },
        "raw_get_user": raw_user,
        "root_component_resolution": resolution,
        "root_component": component,
        "system_temp_root": str(system_temp_root),
        "observed_session_parent": str(parent),
        "observed_basetemp": str(observed),
        "normalized_record_sha256": "",
        "claims_not_made": ["This probe does not execute the broad test suite."],
    }
    record["normalized_record_sha256"] = canonical_sha256(
        record, exclude={"normalized_record_sha256"}
    )
    semantic_issues = _validate_pytest_temp_root_preflight(record)
    if semantic_issues:
        raise ContractError(f"pytest_temp_root_record_invalid:{semantic_issues[0].code}")
    return record


def _validate_preflight_output_path(repository_root: Path, path: Path) -> Path:
    try:
        relative = _review_relative_path(path)
        descriptor = os.open(
            repository_root,
            os.O_RDONLY
            | os.O_DIRECTORY
            | os.O_NOFOLLOW
            | getattr(os, "O_CLOEXEC", 0),
        )
        try:
            for component in relative.parts[:-1]:
                try:
                    child = os.open(
                        component,
                        os.O_RDONLY
                        | os.O_DIRECTORY
                        | os.O_NOFOLLOW
                        | getattr(os, "O_CLOEXEC", 0),
                        dir_fd=descriptor,
                    )
                except FileNotFoundError:
                    return relative
                os.close(descriptor)
                descriptor = child
            try:
                existing = os.stat(
                    relative.name, dir_fd=descriptor, follow_symlinks=False
                )
            except FileNotFoundError:
                existing = None
            if existing is not None and not stat.S_ISREG(existing.st_mode):
                raise ContractError("preflight_output_path_invalid")
        finally:
            os.close(descriptor)
        return relative
    except (OSError, ContractError) as exc:
        raise ContractError("preflight_output_path_invalid") from exc


def write_json(repository_root: Path, path: Path, record: Any) -> None:
    relative = _validate_preflight_output_path(repository_root, path)
    try:
        if relative.parent == Path("."):
            parent = os.open(
                repository_root,
                os.O_RDONLY
                | os.O_DIRECTORY
                | os.O_NOFOLLOW
                | getattr(os, "O_CLOEXEC", 0),
            )
        else:
            parent = _open_review_directory(
                repository_root, relative.parent, create=True
            )
    except (OSError, ContractError) as exc:
        raise ContractError("preflight_output_path_invalid") from exc
    data = json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n"
    name = relative.name
    temporary_name = f".{name}.{os.getpid()}.{hashlib.sha256(os.urandom(32)).hexdigest()}.tmp"
    descriptor = -1
    cleanup_temporary = True
    try:
        logical_parent = bind_logical_parent(
            repository_root, relative.parent, parent
        )
        try:
            current = capture_regular_file_at(
                parent, name, relative.as_posix(), missing_ok=True
            )
        except AtomicPublishError as exc:
            raise ContractError("preflight_output_path_invalid") from exc
        if current is not None and not stat.S_ISREG(current.mode):
            raise ContractError("preflight_output_path_invalid")
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | os.O_NOFOLLOW
            | getattr(os, "O_CLOEXEC", 0),
            0o644,
            dir_fd=parent,
        )
        offset = 0
        while offset < len(data):
            offset += os.write(descriptor, data[offset:])
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        conditional_publish_file_at(
            parent,
            temporary_name,
            name,
            current,
            relative.as_posix(),
            logical_parent=logical_parent,
        )
    except AtomicPublishError as exc:
        cleanup_temporary = not exc.preserve_temporary
        if exc.code == "concurrent_mutation":
            raise ContractError("preflight_output_concurrent_mutation") from exc
        raise ContractError("preflight_output_path_invalid") from exc
    except ContractError:
        raise
    except OSError as exc:
        raise ContractError("preflight_output_path_invalid") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if cleanup_temporary:
            try:
                os.unlink(temporary_name, dir_fd=parent)
            except FileNotFoundError:
                pass
        os.close(parent)


def _current_repository_root() -> Path:
    current = Path.cwd().resolve()
    completed = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=current,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if completed.returncode != 0:
        raise ContractError("repository_root_unavailable")
    root = Path(completed.stdout.strip()).resolve()
    if root != current:
        raise ContractError("repository_root_mismatch")
    return root


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    probe = commands.add_parser("probe-pytest-temp-root")
    probe.add_argument("--pytest-executable", type=Path, required=True)
    probe.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        repository_root = _current_repository_root()
        _validate_preflight_output_path(repository_root, args.out)
        record = build_pytest_temp_root_preflight(args.pytest_executable)
        write_json(repository_root, args.out, record)
    except ContractError as exc:
        print(json.dumps({"status": "rejected", "code": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
