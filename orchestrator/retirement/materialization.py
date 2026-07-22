"""Immutable one-shot materialization transactions.

The storage layer is record-kind neutral.  Small bootstrap adapters define the
closed input and parameter grammar for the only Task-1-owned record kinds.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import secrets
import stat
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping

from .broad_evidence import (
    ContractError,
    FAILURE_BASELINE_ATTESTATION_CLAIMS_NOT_MADE,
    Issue,
    build_initial_execution_ledger,
    canonical_json_bytes,
    canonical_sha256,
    derive_review_binding,
    file_sha256,
    load_json_closed,
    validate_bound_record,
    validate_execution_ledger,
    validate_record,
    validate_review_binding_pair,
    validate_review_pair,
    REVIEW_SUBJECT_SCHEMAS,
    _expected_live_review_name,
    _head_regular_file_bytes,
)
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


GENERATION_MIN = 1
GENERATION_MAX = 99_999_999
GENERATION_FILE_RE = re.compile(r"^[0-9]{8}-[0-9a-f]{64}(?:\.[A-Za-z0-9._-]+)?$")


class MaterializationError(RuntimeError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}:{detail}" if detail else code)


@dataclass(frozen=True)
class MaterializationReceipt:
    request_path: Path
    request_sha256: str
    snapshot_path: Path
    snapshot_sha256: str
    generation: int
    output_path: Path
    output_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "request_path": self.request_path.as_posix(),
            "request_sha256": self.request_sha256,
            "snapshot_path": self.snapshot_path.as_posix(),
            "snapshot_sha256": self.snapshot_sha256,
            "generation": self.generation,
            "output_path": self.output_path.as_posix(),
            "output_sha256": self.output_sha256,
        }


@dataclass(frozen=True)
class InputCapture:
    path: Path
    data: bytes
    binding: Mapping[str, Any]


@dataclass(frozen=True)
class PriorGenerationCapture:
    binding: Mapping[str, Any]
    request_path: Path
    snapshot_path: Path
    request_file: BoundRegularFile
    snapshot_file: BoundRegularFile
    ancestry_captures: tuple[BoundRepositoryRegular, ...]


@dataclass(frozen=True)
class BoundRepositoryRegular:
    path: Path
    file: BoundRegularFile
    parent: BoundLogicalParent


@dataclass(frozen=True)
class OverlayRepositoryRegular:
    """Immutable logical bytes supplied by an already validated snapshot."""

    path: Path
    data: bytes


ResolvedRepositoryRegular = BoundRepositoryRegular | OverlayRepositoryRegular


@dataclass(frozen=True)
class GenerationBindingResolution:
    bound_request: ResolvedRepositoryRegular
    bound_snapshot: ResolvedRepositoryRegular
    current_request: ResolvedRepositoryRegular
    current_snapshot: ResolvedRepositoryRegular
    live: ResolvedRepositoryRegular


@dataclass(frozen=True)
class BoundAncestryResolution:
    matched: bool
    captures: tuple[ResolvedRepositoryRegular, ...]


Builder = Callable[[Path, Mapping[str, InputCapture], Mapping[str, Any]], Any]
OutputValidator = Callable[[Any], list[Any]]
OutputPathValidator = Callable[
    [Path, Path, Mapping[str, Path], Mapping[str, Any]], bool
]


@dataclass(frozen=True)
class Adapter:
    input_roles: frozenset[str]
    parameter_names: frozenset[str]
    builder: Builder
    pending_only: bool = False
    output_validator: OutputValidator = validate_record
    output_path_validator: OutputPathValidator | None = None


@dataclass(frozen=True)
class CompletionHandoffPolicy:
    task_number: int
    reservation_after_completed_steps: int
    subject_kind: str
    parent_directory: str
    task_directory_role: str


COMPLETION_HANDOFF_POLICIES = {
    1: CompletionHandoffPolicy(
        task_number=1,
        reservation_after_completed_steps=2,
        subject_kind="broad_evidence_bootstrap",
        parent_directory="implementation-commits",
        task_directory_role="bootstrap",
    ),
}


def _fixed_output_slot(*suffix: str) -> OutputPathValidator:
    def validate(
        evidence_root: Path,
        output_path: Path,
        _inputs: Mapping[str, Path],
        _parameters: Mapping[str, Any],
    ) -> bool:
        return output_path == evidence_root.joinpath(*suffix)

    return validate


def _baseline_attestation_slot(
    evidence_root: Path,
    output_path: Path,
    input_paths: Mapping[str, Path],
    _parameters: Mapping[str, Any],
) -> bool:
    return (
        output_path
        == evidence_root
        / "attestations/pre-implementation/broad-failure-baseline.json"
        and input_paths
        == {
            "baseline": evidence_root
            / "implementation-baseline/known-failure-baseline.json",
            "specification_review": evidence_root
            / "reviews/implementation-baseline-specification.json",
            "quality_review": evidence_root
            / "reviews/implementation-baseline-quality.json",
        }
    )


def _adapter_output_slot_valid(
    adapter: Adapter,
    evidence_root: Path,
    output_path: Path,
    input_paths: Mapping[str, Path],
    parameters: Mapping[str, Any],
) -> bool:
    return (
        adapter.output_path_validator is not None
        and adapter.output_path_validator(
            evidence_root, output_path, input_paths, parameters
        )
    )


def _validated_relative(path: Path) -> Path:
    text = path.as_posix()
    pure = PurePosixPath(text)
    if (
        path.is_absolute()
        or text in {"", "."}
        or "\x00" in text
        or any(part in {"", ".", ".."} for part in pure.parts)
        or str(pure) != text
    ):
        raise MaterializationError("path_not_repository_relative", text)
    return Path(text)


def _json_output(record: Any) -> bytes:
    return json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n"


def _build_ledger(
    repository_root: Path,
    inputs: Mapping[str, InputCapture],
    parameters: Mapping[str, Any],
) -> Any:
    return _build_ledger_with_future_mode(
        repository_root,
        inputs,
        parameters,
        check_future_absence=True,
    )


def _build_ledger_with_future_mode(
    repository_root: Path,
    inputs: Mapping[str, InputCapture],
    parameters: Mapping[str, Any],
    *,
    check_future_absence: bool,
    bound_file_bytes: Mapping[str, bytes] | None = None,
    require_committed_fallback: bool = False,
) -> Any:
    plan = inputs["approved_plan"]
    plan_path = plan.path
    plan_bytes = plan.data
    record = parameters["record"]
    resolved_bytes = dict(bound_file_bytes or {})
    prior_plan_bytes = resolved_bytes.get(plan_path.as_posix())
    if prior_plan_bytes is not None and prior_plan_bytes != plan_bytes:
        raise MaterializationError("plan_binding_mismatch")
    resolved_bytes[plan_path.as_posix()] = plan_bytes
    issues = validate_bound_record(
        record,
        repository_root=repository_root,
        bound_file_bytes=resolved_bytes,
        require_committed_fallback=require_committed_fallback,
        check_ledger_future_absence=check_future_absence,
    )
    if issues:
        raise MaterializationError("output_contract_invalid", issues[0].code)
    if record["plan_binding"] != {
        "path": plan_path.as_posix(),
        "sha256": f"sha256:{hashlib.sha256(plan_bytes).hexdigest()}",
    }:
        raise MaterializationError("plan_binding_mismatch")
    return record


def _completion_handoff_paths(
    policy: CompletionHandoffPolicy,
    *,
    evidence_root: Path,
) -> tuple[Path, Path, Path]:
    subject = (
        evidence_root
        / policy.parent_directory
        / f"task-{policy.task_number:02d}-{policy.task_directory_role}"
        / "subject.json"
    )
    specification_name = _expected_live_review_name(
        policy.subject_kind, "specification"
    )
    quality_name = _expected_live_review_name(policy.subject_kind, "code_quality")
    if specification_name is None or quality_name is None:
        raise MaterializationError("completion_handoff_policy_invalid")
    return (
        subject,
        subject.with_name(specification_name),
        subject.with_name(quality_name),
    )


def _completion_review_pair_issues(
    repository_root: Path,
    *,
    policy: CompletionHandoffPolicy,
    subject_path: Path,
    specification_path: Path,
    quality_path: Path,
    request_prior_binding: Mapping[str, Any],
    bound_file_bytes: Mapping[str, bytes] | None = None,
    require_committed_fallback: bool = False,
) -> list[Issue]:
    try:
        subject_capture = _capture_resolved_relative_regular(
            repository_root,
            subject_path,
            bound_file_bytes,
            require_committed_fallback,
        )
        specification_capture = _capture_resolved_relative_regular(
            repository_root,
            specification_path,
            bound_file_bytes,
            require_committed_fallback,
        )
        quality_capture = _capture_resolved_relative_regular(
            repository_root,
            quality_path,
            bound_file_bytes,
            require_committed_fallback,
        )
        subject = _load_json_bytes_closed(
            _resolved_regular_data(subject_capture), subject_path
        )
    except (MaterializationError, ContractError, OSError):
        return [Issue("ledger_completion_review_pair_invalid")]
    expected_subject_schema = REVIEW_SUBJECT_SCHEMAS.get(policy.subject_kind)
    if (
        not isinstance(subject, Mapping)
        or subject.get("schema_version") != expected_subject_schema
        or validate_record(subject)
    ):
        return [Issue("ledger_completion_subject_invalid")]
    subject_binding = {
        "path": subject_path.as_posix(),
        "sha256": (
            "sha256:"
            + hashlib.sha256(_resolved_regular_data(subject_capture)).hexdigest()
        ),
    }
    expected_ledger_binding = {
        "live_path": request_prior_binding.get("output_path"),
        "byte_sha256": request_prior_binding.get("snapshot_sha256"),
        "schema_version": "workflow_retirement_execution_ledger.v1",
        "generation": request_prior_binding.get("generation"),
        "request_path": request_prior_binding.get("request_path"),
        "request_sha256": request_prior_binding.get("request_sha256"),
        "snapshot_path": request_prior_binding.get("snapshot_path"),
        "snapshot_sha256": request_prior_binding.get("snapshot_sha256"),
    }
    if subject.get("execution_ledger_binding") != expected_ledger_binding:
        return [Issue("ledger_completion_subject_invalid")]
    evidence_root = Path(request_prior_binding["output_path"]).parent
    try:
        specification_binding = derive_review_binding(
            evidence_root=evidence_root,
            review_path=specification_path,
            review_bytes=_resolved_regular_data(specification_capture),
        )
        quality_binding = derive_review_binding(
            evidence_root=evidence_root,
            review_path=quality_path,
            review_bytes=_resolved_regular_data(quality_capture),
        )
    except ContractError:
        return [Issue("ledger_completion_review_pair_invalid")]
    try:
        pair_issues = validate_review_binding_pair(
            specification_binding=specification_binding,
            quality_binding=quality_binding,
            repository_root=repository_root,
            expected_subject_kind=policy.subject_kind,
            expected_subject_binding=subject_binding,
            bound_file_bytes=bound_file_bytes,
            require_committed_fallback=require_committed_fallback,
        )
    except (ContractError, OSError):
        pair_issues = [Issue("review_pair_binding_invalid")]
    if pair_issues:
        return [Issue("ledger_completion_review_pair_invalid")]

    try:
        live_capture = _capture_resolved_relative_regular(
            repository_root,
            Path(request_prior_binding["output_path"]),
            bound_file_bytes,
            require_committed_fallback,
        )
        prior_snapshot_capture = _capture_resolved_relative_regular(
            repository_root,
            Path(request_prior_binding["snapshot_path"]),
            bound_file_bytes,
            require_committed_fallback,
        )
    except (KeyError, TypeError, MaterializationError, OSError):
        return [Issue("ledger_completion_subject_invalid")]
    prior_snapshot_sha = (
        "sha256:"
        + hashlib.sha256(_resolved_regular_data(prior_snapshot_capture)).hexdigest()
    )
    if prior_snapshot_sha != request_prior_binding.get("snapshot_sha256"):
        return [Issue("ledger_completion_subject_invalid")]
    if _resolved_regular_data(live_capture) == _resolved_regular_data(
        prior_snapshot_capture
    ):
        deep_issues = validate_review_pair(
            specification_binding=specification_binding,
            quality_binding=quality_binding,
            repository_root=repository_root,
            expected_subject_kind=policy.subject_kind,
            expected_subject_binding=subject_binding,
            bound_file_bytes=bound_file_bytes,
            require_committed_fallback=require_committed_fallback,
        )
        if deep_issues:
            return [Issue("ledger_completion_subject_invalid")]
    if any(
        not _resolved_relative_regular_matches(
            repository_root,
            capture,
            bound_file_bytes,
            require_committed_fallback,
        )
        for capture in (
            subject_capture,
            specification_capture,
            quality_capture,
            live_capture,
            prior_snapshot_capture,
        )
    ):
        return [Issue("ledger_completion_review_pair_invalid")]
    return []


def _completion_handoff_issues(
    repository_root: Path,
    *,
    prior_task: Mapping[str, Any],
    transition: Mapping[str, Any],
    request_prior_binding: Mapping[str, Any],
    bound_file_bytes: Mapping[str, bytes] | None = None,
    require_committed_fallback: bool = False,
) -> list[Issue]:
    policy = COMPLETION_HANDOFF_POLICIES.get(transition.get("task_number"))
    if policy is None:
        return []
    completed = prior_task.get("completed_step_count")
    evidence_root = Path(request_prior_binding["output_path"]).parent
    try:
        subject_path, specification_path, quality_path = _completion_handoff_paths(
            policy, evidence_root=evidence_root
        )
    except MaterializationError:
        return [Issue("ledger_completion_policy_invalid")]
    review_paths = sorted(
        [specification_path.as_posix(), quality_path.as_posix()]
    )
    if completed == policy.reservation_after_completed_steps:
        if (
            transition["evidence_bindings"] != []
            or transition["future_bindings"]
            != [{"path": path, "sha256": None} for path in review_paths]
        ):
            return [Issue("ledger_completion_reservation_mismatch")]
    elif completed == policy.reservation_after_completed_steps + 1:
        expected_paths = sorted(
            [
                subject_path.as_posix(),
                specification_path.as_posix(),
                quality_path.as_posix(),
            ]
        )
        if (
            transition["future_bindings"] != []
            or [row["path"] for row in transition["evidence_bindings"]]
            != expected_paths
        ):
            return [Issue("ledger_completion_evidence_mismatch")]
        pair_issues = _completion_review_pair_issues(
            repository_root,
            policy=policy,
            subject_path=subject_path,
            specification_path=specification_path,
            quality_path=quality_path,
            request_prior_binding=request_prior_binding,
            bound_file_bytes=bound_file_bytes,
            require_committed_fallback=require_committed_fallback,
        )
        if pair_issues:
            return pair_issues
    return []


def _execution_ledger_generation_issues(
    record: Mapping[str, Any],
    *,
    repository_root: Path,
    generation: int,
    plan_path: Path,
    plan_bytes: bytes,
    prior_record: Mapping[str, Any] | None,
    request_prior_binding: Mapping[str, Any] | None,
    bound_file_bytes: Mapping[str, bytes] | None = None,
    require_committed_fallback: bool = False,
) -> list[Issue]:
    """Validate one contextual ledger generation against its predecessor."""

    try:
        genesis = build_initial_execution_ledger(
            plan_path=plan_path,
            plan_bytes=plan_bytes,
        )
    except ContractError as exc:
        return [Issue("ledger_plan_invalid", "$.plan_binding", str(exc))]
    if generation == 1:
        if request_prior_binding is not None or prior_record is not None:
            return [Issue("ledger_genesis_prior_unexpected")]
        return [] if record == genesis else [Issue("ledger_genesis_mismatch")]
    if generation < 2 or prior_record is None or request_prior_binding is None:
        return [Issue("ledger_prior_generation_required")]
    prior_issues = validate_execution_ledger(prior_record)
    if prior_issues:
        return [Issue("ledger_prior_record_invalid", message=prior_issues[0].code)]
    expected_plan_coordinates = [
        {
            key: row[key]
            for key in ("task_number", "title", "total_step_count")
        }
        for row in genesis["tasks"]
    ]
    prior_plan_coordinates = [
        {
            key: row[key]
            for key in ("task_number", "title", "total_step_count")
        }
        for row in prior_record["tasks"]
    ]
    if (
        prior_record.get("plan_binding") != genesis["plan_binding"]
        or prior_plan_coordinates != expected_plan_coordinates
        or prior_record.get("task_count") != genesis["task_count"]
        or prior_record.get("claims_not_made") != genesis["claims_not_made"]
    ):
        return [Issue("ledger_prior_authority_drift")]
    transition = record.get("last_transition")
    if not isinstance(transition, Mapping):
        return [Issue("ledger_transition_required", "$.last_transition")]
    if transition.get("prior_generation_binding") != request_prior_binding:
        return [Issue("ledger_transition_prior_mismatch", "$.last_transition")]
    if (
        request_prior_binding.get("generation") != generation - 1
        or not isinstance(request_prior_binding.get("output_path"), str)
    ):
        return [Issue("ledger_transition_prior_mismatch", "$.last_transition")]
    current_task = prior_record.get("current_task")
    if type(current_task) is not int or not 1 <= current_task <= 17:
        return [Issue("ledger_prior_current_task_invalid", "$.current_task")]
    prior_task = prior_record["tasks"][current_task - 1]
    completed = prior_task["completed_step_count"]
    total = prior_task["total_step_count"]
    next_step = completed + 1
    expected_new_status = "complete" if next_step == total else "in_progress"
    if (
        prior_task["status"] != "in_progress"
        or not 1 <= next_step <= total
        or transition.get("task_number") != current_task
        or transition.get("step_number") != next_step
        or transition.get("old_status") != "in_progress"
        or transition.get("new_status") != expected_new_status
    ):
        return [Issue("ledger_transition_coordinate_mismatch", "$.last_transition")]
    prior_evidence = prior_task["evidence_bindings"]
    transition_evidence = transition["evidence_bindings"]
    prior_evidence_paths = {binding["path"] for binding in prior_evidence}
    transition_evidence_paths = {
        binding["path"] for binding in transition_evidence
    }
    if prior_evidence_paths & transition_evidence_paths:
        return [Issue("ledger_transition_evidence_not_new", "$.last_transition")]
    future_paths = {binding["path"] for binding in transition["future_bindings"]}
    all_evidence_paths = {
        binding["path"]
        for task in prior_record["tasks"]
        for binding in task["evidence_bindings"]
    } | transition_evidence_paths
    reserved_paths = {
        request_prior_binding["request_path"],
        request_prior_binding["snapshot_path"],
        request_prior_binding["output_path"],
    }
    if future_paths & (all_evidence_paths | reserved_paths):
        return [Issue("ledger_future_binding_overlap", "$.last_transition.future_bindings")]
    completion_issues = _completion_handoff_issues(
        repository_root,
        prior_task=prior_task,
        transition=transition,
        request_prior_binding=request_prior_binding,
        bound_file_bytes=bound_file_bytes,
        require_committed_fallback=require_committed_fallback,
    )
    if completion_issues:
        return completion_issues
    expected = deepcopy(prior_record)
    expected_task = expected["tasks"][current_task - 1]
    expected_task["completed_step_count"] = next_step
    expected_task["evidence_bindings"] = sorted(
        [*prior_evidence, *transition_evidence], key=lambda binding: binding["path"]
    )
    if expected_new_status == "complete":
        expected_task["status"] = "complete"
        if current_task == 17:
            expected["current_task"] = None
        else:
            expected["tasks"][current_task]["status"] = "in_progress"
            expected["current_task"] = current_task + 1
    expected["last_transition"] = deepcopy(transition)
    expected["normalized_ledger_sha256"] = canonical_sha256(
        expected, exclude={"normalized_ledger_sha256"}
    )
    return [] if record == expected else [Issue("ledger_transition_projection_mismatch")]


def _handoff(data: bytes, path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    document = _load_json_bytes_closed(data, path)
    if not isinstance(document, dict):
        raise MaterializationError("authority_not_object")
    handoff = document.get("yaml_retirement_handoff", document)
    if not isinstance(handoff, dict) or handoff.get("schema_version") != "procedure_first_yaml_retirement_handoff.v1":
        raise MaterializationError("authority_schema_invalid")
    return document, handoff


def _build_query(
    repository_root: Path,
    inputs: Mapping[str, InputCapture],
    parameters: Mapping[str, Any],
) -> Any:
    del repository_root
    authority = inputs["handoff"]
    _, handoff = _handoff(authority.data, authority.path)
    queue_id = parameters["queue_id"]
    rows = [row for row in handoff.get("queues", []) if row.get("queue_id") == queue_id]
    if len(rows) != 1:
        raise MaterializationError("queue_not_unique", str(queue_id))
    paths = rows[0].get("paths")
    if not isinstance(paths, list) or any(not isinstance(path, str) for path in paths):
        raise MaterializationError("queue_paths_invalid")
    sorted_paths = sorted(paths)
    if len(set(sorted_paths)) != len(sorted_paths):
        raise MaterializationError("queue_paths_duplicate")
    encoded = "".join(f"{path}\n" for path in sorted_paths).encode("utf-8")
    authority_path = authority.path
    record: dict[str, Any] = {
        "schema_version": "query.v1",
        "authority": {
            "path": authority_path.as_posix(),
            "sha256": authority.binding["sha256"],
            "schema_version": handoff["schema_version"],
        },
        "queue_id": queue_id,
        "paths": sorted_paths,
        "path_count": len(sorted_paths),
        "path_encoding": "utf8_repository_relative_posix_lf.v1",
        "path_list_sha256": f"sha256:{hashlib.sha256(encoded).hexdigest()}",
        "capture_commit": parameters["capture_commit"],
        "normalized_query_sha256": "",
        "claims_not_made": [
            "This query does not authorize deletion or classify references."
        ],
    }
    record["normalized_query_sha256"] = canonical_sha256(
        record, exclude={"normalized_query_sha256"}
    )
    return record


def _build_pending_baseline_attestation(
    repository_root: Path,
    inputs: Mapping[str, InputCapture],
    parameters: Mapping[str, Any],
) -> Any:
    baseline_input = inputs["baseline"]
    specification_input = inputs["specification_review"]
    quality_input = inputs["quality_review"]
    baseline_path = baseline_input.path
    baseline = _load_json_bytes_closed(baseline_input.data, baseline_path)
    if (
        baseline.get("schema_version") != "broad_known_failure_baseline.v1"
        or validate_record(baseline)
    ):
        raise MaterializationError("baseline_schema_invalid")
    baseline_sha = baseline_input.binding["sha256"]
    review_parent = specification_input.path.parent
    if (
        review_parent.name != "reviews"
        or quality_input.path.parent != review_parent
    ):
        raise MaterializationError("review_pair_invalid", "review_live_paths_invalid")
    evidence_root = review_parent.parent
    try:
        specification_binding = derive_review_binding(
            evidence_root=evidence_root,
            review_path=specification_input.path,
            review_bytes=specification_input.data,
        )
        quality_binding = derive_review_binding(
            evidence_root=evidence_root,
            review_path=quality_input.path,
            review_bytes=quality_input.data,
        )
    except ContractError as exc:
        raise MaterializationError("review_pair_invalid", str(exc)) from exc
    review_issues = validate_review_binding_pair(
        specification_binding=specification_binding,
        quality_binding=quality_binding,
        repository_root=repository_root,
        expected_subject_kind="implementation_failure_baseline",
        expected_subject_binding={
            "path": baseline_path.as_posix(),
            "sha256": baseline_sha,
        },
    )
    if review_issues:
        raise MaterializationError("review_pair_invalid", review_issues[0].code)
    normalization = baseline["failure_normalization"]
    record = {
        "schema_version": "broad_failure_baseline_attestation.v1",
        "evidence_status": "pending_owner_confirmation",
        "baseline_binding": {
            "path": baseline_path.as_posix(),
            "sha256": baseline_sha,
            "schema_version": baseline["schema_version"],
            "candidate_path_set_sha256": baseline["candidate_binding"][
                "candidate_path_set_sha256"
            ],
        },
        "failure_set_binding": {
            "failure_count": len(baseline["failures"]),
            "normalized_failure_set_sha256": baseline[
                "normalized_failure_set_sha256"
            ],
        },
        "normalization_binding": {
            "schema_version": normalization["schema_version"],
            "normalized_contract_sha256": normalization[
                "normalized_contract_sha256"
            ],
        },
        "classification_summary": dict(baseline["classification_summary"]),
        "specification_review_binding": dict(specification_binding),
        "quality_review_binding": dict(quality_binding),
        "owner": None,
        "owner_confirmations": {
            "exact_failure_table_confirmed": False,
            "normalization_contract_confirmed": False,
            "classification_partition_confirmed": False,
            "reviews_confirmed": False,
            "comparison_only_confirmed": False,
            "no_out_of_scope_repair_confirmed": False,
            "confirmed_at": None,
        },
        "prepared_by": parameters["prepared_by"],
        "prepared_at": parameters["prepared_at"],
        "owner_adoption": None,
        "claims_not_made": list(FAILURE_BASELINE_ATTESTATION_CLAIMS_NOT_MADE),
    }
    return record


def _validate_query_output(record: Any) -> list[Any]:
    # Lazy import avoids the source_bindings -> materialization import cycle
    # while keeping the adapter bound to its owning schema registry.
    from .source_bindings import validate_workspace_record_shape

    return list(validate_workspace_record_shape(record))


def _validate_adapter_output(
    record: Any, *, adapter: Adapter, pending: bool
) -> None:
    issues = adapter.output_validator(record)
    if issues:
        raise MaterializationError("adapter_output_invalid", issues[0].code)
    if adapter.pending_only:
        confirmations = record.get("owner_confirmations")
        pending_invalid = (
            not pending
            or record.get("evidence_status") != "pending_owner_confirmation"
            or record.get("owner") is not None
            or record.get("owner_adoption") is not None
            or not isinstance(confirmations, Mapping)
            or any(
                value is not False and value is not None
                for value in confirmations.values()
            )
        )
        if pending_invalid:
            raise MaterializationError("adapter_output_pending_invariant_invalid")


ADAPTERS: dict[str, Adapter] = {
    "execution-ledger": Adapter(
        frozenset({"approved_plan"}),
        frozenset({"record"}),
        _build_ledger,
        output_path_validator=_fixed_output_slot("execution-ledger.json"),
    ),
    "query": Adapter(
        frozenset({"handoff"}),
        frozenset({"queue_id", "capture_commit"}),
        _build_query,
        output_validator=_validate_query_output,
        output_path_validator=_fixed_output_slot("query.json"),
    ),
    "broad-failure-baseline-attestation": Adapter(
        frozenset({"baseline", "specification_review", "quality_review"}),
        frozenset({"prepared_by", "prepared_at"}),
        _build_pending_baseline_attestation,
        pending_only=True,
        output_path_validator=_baseline_attestation_slot,
    ),
}


def _input_binding(
    repository_root: Path,
    role: str,
    path: Path,
    *,
    bound_file_bytes: Mapping[str, bytes] | None = None,
    require_committed_fallback: bool = False,
) -> InputCapture:
    relative = _validated_relative(path)
    if bound_file_bytes is not None and relative.as_posix() in bound_file_bytes:
        data = bound_file_bytes[relative.as_posix()]
        if not isinstance(data, bytes):
            raise MaterializationError(
                "bound_file_bytes_invalid", relative.as_posix()
            )
    else:
        try:
            data = _nofollow_file_bytes(repository_root, relative)
        except FileNotFoundError as exc:
            raise MaterializationError(
                "input_not_regular", relative.as_posix()
            ) from exc
        assert data is not None
        if require_committed_fallback:
            committed = _head_regular_file_bytes(
                repository_root, relative.as_posix()
            )
            if committed is None or data != committed:
                raise MaterializationError(
                    "committed_fallback_mismatch", relative.as_posix()
                )
    try:
        value = _load_json_bytes_closed(data, relative)
        schema = value.get("schema_version") if isinstance(value, dict) else None
    except ContractError:
        schema = None
    binding = {
        "role": role,
        "path": relative.as_posix(),
        "size": len(data),
        "sha256": f"sha256:{hashlib.sha256(data).hexdigest()}",
        "schema_version": schema,
    }
    return InputCapture(path=relative, data=data, binding=binding)


def _request_path(evidence_root: Path, output_path: Path, generation: int, digest: str) -> Path:
    key = hashlib.sha256(output_path.as_posix().encode("utf-8")).hexdigest()
    return evidence_root / "materialization-inputs" / key / (
        f"{generation:08d}-{digest.removeprefix('sha256:')}.json"
    )


def _snapshot_path(
    evidence_root: Path, output_path: Path, generation: int, output_sha: str
) -> Path:
    key = hashlib.sha256(output_path.as_posix().encode("utf-8")).hexdigest()
    suffix = "".join(output_path.suffixes)
    return evidence_root / "immutable-outputs" / key / (
        f"{generation:08d}-{output_sha.removeprefix('sha256:')}{suffix}"
    )


def _evidence_root_from_request_path(request_path: Path) -> Path:
    if (
        len(request_path.parents) < 3
        or request_path.parent.parent.name != "materialization-inputs"
    ):
        raise MaterializationError("request_path_layout_invalid")
    return _validated_relative(request_path.parents[2])


def _open_nofollow_directory(
    repository_root: Path, relative_directory: Path, *, create: bool
) -> int:
    """Open a repository-relative directory without following any component."""
    relative_directory = (
        Path(".")
        if relative_directory.as_posix() == "."
        else _validated_relative(relative_directory)
    )
    descriptor = os.open(repository_root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        if relative_directory.as_posix() == ".":
            return descriptor
        for component in relative_directory.parts:
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
                    raise MaterializationError(
                        "publication_path_symlink", relative_directory.as_posix()
                    ) from exc
            except OSError as exc:
                raise MaterializationError(
                    "publication_path_symlink", relative_directory.as_posix()
                ) from exc
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _nofollow_file_bytes(
    repository_root: Path, relative_path: Path, *, missing_ok: bool = False
) -> bytes | None:
    relative_path = _validated_relative(relative_path)
    try:
        parent = _open_nofollow_directory(
            repository_root, relative_path.parent, create=False
        )
    except FileNotFoundError:
        if missing_ok:
            return None
        raise
    try:
        try:
            captured = capture_regular_file_at(
                parent,
                relative_path.name,
                relative_path.as_posix(),
                missing_ok=missing_ok,
            )
        except AtomicPublishError as exc:
            code = {
                "unstable_capture": "publication_concurrent_mutation",
                "final_slot_not_regular": "publication_path_symlink",
            }.get(exc.code, "publication_path_not_regular")
            raise MaterializationError(code, relative_path.as_posix()) from exc
        return None if captured is None else captured.data
    finally:
        os.close(parent)


def _capture_bound_relative_regular(
    repository_root: Path, relative_path: Path
) -> BoundRepositoryRegular:
    relative_path = _validated_relative(relative_path)
    try:
        parent = _open_nofollow_directory(
            repository_root, relative_path.parent, create=False
        )
        try:
            logical_parent = bind_logical_parent(
                repository_root, relative_path.parent, parent
            )
            captured = capture_regular_file_at(
                parent,
                relative_path.name,
                relative_path.as_posix(),
                missing_ok=False,
            )
        finally:
            os.close(parent)
    except (AtomicPublishError, OSError) as exc:
        raise MaterializationError(
            "publication_path_unreadable", relative_path.as_posix()
        ) from exc
    assert captured is not None
    if not logical_parent_matches(logical_parent):
        raise MaterializationError(
            "publication_path_unreadable", relative_path.as_posix()
        )
    return BoundRepositoryRegular(
        path=relative_path, file=captured, parent=logical_parent
    )


def _capture_resolved_relative_regular(
    repository_root: Path,
    relative_path: Path,
    bound_file_bytes: Mapping[str, bytes] | None,
    require_committed_fallback: bool = False,
) -> ResolvedRepositoryRegular:
    relative_path = _validated_relative(relative_path)
    logical_path = relative_path.as_posix()
    if bound_file_bytes is not None and logical_path in bound_file_bytes:
        data = bound_file_bytes[logical_path]
        if not isinstance(data, bytes):
            raise MaterializationError("bound_file_bytes_invalid", logical_path)
        return OverlayRepositoryRegular(path=relative_path, data=data)
    capture = _capture_bound_relative_regular(repository_root, relative_path)
    if require_committed_fallback:
        committed = _head_regular_file_bytes(repository_root, logical_path)
        if committed is None or capture.file.data != committed:
            raise MaterializationError(
                "committed_fallback_mismatch", logical_path
            )
    return capture


def _resolved_regular_data(capture: ResolvedRepositoryRegular) -> bytes:
    return (
        capture.data
        if isinstance(capture, OverlayRepositoryRegular)
        else capture.file.data
    )


def _resolved_relative_regular_matches(
    repository_root: Path,
    capture: ResolvedRepositoryRegular,
    bound_file_bytes: Mapping[str, bytes] | None,
    require_committed_fallback: bool = False,
) -> bool:
    if isinstance(capture, OverlayRepositoryRegular):
        return (
            bound_file_bytes is not None
            and bound_file_bytes.get(capture.path.as_posix()) == capture.data
        )
    if not _bound_relative_regular_matches(repository_root, capture):
        return False
    if require_committed_fallback:
        return _head_regular_file_bytes(
            repository_root, capture.path.as_posix()
        ) == capture.file.data
    return True


def _capture_relative_regular(
    repository_root: Path, relative_path: Path
) -> BoundRegularFile:
    return _capture_bound_relative_regular(repository_root, relative_path).file


def _bound_relative_regular_matches(
    repository_root: Path, expected: BoundRepositoryRegular
) -> bool:
    if not logical_parent_matches(expected.parent):
        return False
    try:
        current = _capture_bound_relative_regular(repository_root, expected.path)
    except MaterializationError:
        return False
    return (
        current.file == expected.file
        and logical_parent_matches(expected.parent)
    )


def _load_json_bytes_closed(data: bytes, path: Path) -> Any:
    def reject_duplicate(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ContractError(f"duplicate_json_key:{key}")
            result[key] = value
        return result

    try:
        return json.loads(data, object_pairs_hook=reject_duplicate)
    except ContractError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"invalid_json:{path}:{exc}") from exc


def _exclusive_identical(repository_root: Path, relative_path: Path, data: bytes) -> None:
    relative_path = _validated_relative(relative_path)
    parent = _open_nofollow_directory(repository_root, relative_path.parent, create=True)
    temporary_name = f".{relative_path.name}.{secrets.token_hex(12)}"
    cleanup_temporary = True
    descriptor = -1
    try:
        try:
            logical_parent = bind_logical_parent(
                repository_root, relative_path.parent, parent
            )
            existing = capture_regular_file_at(
                parent,
                relative_path.name,
                relative_path.as_posix(),
                missing_ok=True,
            )
            if existing is not None:
                if existing.data != data:
                    raise MaterializationError(
                        "immutable_slot_conflict", relative_path.as_posix()
                    )
                if not logical_parent_matches(logical_parent):
                    raise MaterializationError(
                        "publication_concurrent_mutation", relative_path.as_posix()
                    )
                return
            descriptor = os.open(
                temporary_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=parent,
            )
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.close(descriptor)
            descriptor = -1
            conditional_publish_file_at(
                parent,
                temporary_name,
                relative_path.name,
                None,
                relative_path.as_posix(),
                logical_parent=logical_parent,
            )
        except AtomicPublishError as exc:
            cleanup_temporary = not exc.preserve_temporary
            if exc.code in {"concurrent_mutation", "logical_parent_changed"}:
                raise MaterializationError(
                    "publication_concurrent_mutation", relative_path.as_posix()
                ) from exc
            raise MaterializationError(
                "publication_atomic_failed", relative_path.as_posix()
            ) from exc
        except OSError as exc:
            raise MaterializationError(
                "publication_path_symlink", relative_path.as_posix()
            ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if cleanup_temporary:
            try:
                os.unlink(temporary_name, dir_fd=parent)
            except FileNotFoundError:
                pass
        os.close(parent)


def _atomic_publish(
    repository_root: Path,
    relative_path: Path,
    data: bytes,
    *,
    owned_live: BoundRepositoryRegular | None = None,
) -> BoundRepositoryRegular:
    relative_path = _validated_relative(relative_path)
    parent = _open_nofollow_directory(repository_root, relative_path.parent, create=True)
    try:
        if owned_live is None:
            logical_parent = bind_logical_parent(
                repository_root, relative_path.parent, parent
            )
            expected = capture_regular_file_at(
                parent,
                relative_path.name,
                relative_path.as_posix(),
                missing_ok=True,
            )
        else:
            if owned_live.path != relative_path or not logical_parent_matches(
                owned_live.parent
            ):
                raise AtomicPublishError(
                    "concurrent_mutation", relative_path.as_posix()
                )
            logical_parent = owned_live.parent
            expected = owned_live.file
    except AtomicPublishError as exc:
        os.close(parent)
        code = (
            "publication_concurrent_mutation"
            if exc.code
            in {"unstable_capture", "concurrent_mutation", "logical_parent_changed"}
            else "publication_path_symlink"
        )
        raise MaterializationError(code, relative_path.as_posix()) from exc
    descriptor: int | None = None
    cleanup_temporary = True
    temporary_name = ""
    for _ in range(128):
        temporary_name = f".{relative_path.name}.{secrets.token_hex(12)}"
        try:
            descriptor = os.open(
                temporary_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=parent,
            )
        except FileExistsError:
            continue
        break
    if descriptor is None:
        os.close(parent)
        raise MaterializationError("temporary_slot_exhausted", relative_path.as_posix())
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        published = conditional_publish_file_at(
            parent,
            temporary_name,
            relative_path.name,
            expected,
            relative_path.as_posix(),
            logical_parent=logical_parent,
        )
        return BoundRepositoryRegular(relative_path, published, logical_parent)
    except AtomicPublishError as exc:
        cleanup_temporary = not exc.preserve_temporary
        code = {
            "final_slot_not_regular": "publication_path_symlink",
            "concurrent_mutation": "publication_concurrent_mutation",
            "atomic_rename_unavailable": "publication_atomic_rename_unavailable",
            "atomic_rollback_failed": "publication_atomic_rollback_failed",
            "atomic_recovery_failed": "publication_atomic_recovery_failed",
            "logical_parent_changed": "publication_concurrent_mutation",
        }.get(exc.code, "publication_atomic_failed")
        raise MaterializationError(code, relative_path.as_posix()) from exc
    finally:
        if cleanup_temporary:
            try:
                os.unlink(temporary_name, dir_fd=parent)
            except FileNotFoundError:
                pass
        os.close(parent)


def _generation_slot_names(
    repository_root: Path,
    directory: Path,
    generation: int,
    *,
    create: bool = True,
    bound_file_bytes: Mapping[str, bytes] | None = None,
) -> list[str]:
    names: set[str] = set()
    try:
        descriptor = _open_nofollow_directory(
            repository_root, directory, create=create
        )
    except FileNotFoundError:
        descriptor = None
    if descriptor is not None:
        try:
            names.update(os.listdir(descriptor))
        finally:
            os.close(descriptor)
    if bound_file_bytes is not None:
        names.update(
            Path(path).name
            for path in bound_file_bytes
            if _validated_relative(Path(path)).parent == directory
        )
    prefix = f"{generation:08d}-"
    return sorted(name for name in names if name.startswith(prefix))


def _materialization_boundary(_boundary: str) -> None:
    """No-op probe used to inject process death at lock-held publication boundaries."""


def _prior_binding_boundary(_boundary: str) -> None:
    """No-op probe for validate/use races in prior-generation capture."""


def _generation_validation_boundary(_boundary: str) -> None:
    """No-op probe for final generation identity validation races."""


def _prior_binding(
    repository_root: Path,
    output_path: Path,
    generation: int,
    prior_request: Path | None,
    prior_snapshot: Path | None,
) -> PriorGenerationCapture | None:
    if generation == 1:
        if prior_request is not None or prior_snapshot is not None:
            raise MaterializationError("unexpected_prior_generation")
        return None
    if prior_request is None or prior_snapshot is None:
        raise MaterializationError("prior_generation_required")
    request_path = _validated_relative(prior_request)
    snapshot_path = _validated_relative(prior_snapshot)
    try:
        bound_request = _capture_bound_relative_regular(repository_root, request_path)
        bound_snapshot = _capture_bound_relative_regular(repository_root, snapshot_path)
    except MaterializationError as exc:
        raise MaterializationError("prior_generation_invalid", str(exc)) from exc
    request_capture = bound_request.file
    snapshot_capture = bound_snapshot.file
    ancestor_captures: list[BoundRepositoryRegular] = []
    _prior_binding_boundary("after_prior_capture")
    issues = _validate_generation_captured(
        repository_root,
        request_path,
        snapshot_path,
        request_capture.data,
        snapshot_capture.data,
        _ancestry_captures=ancestor_captures,
    )
    if issues:
        raise MaterializationError("prior_generation_invalid", issues[0].code)
    try:
        if request_capture != _capture_relative_regular(repository_root, request_path):
            raise MaterializationError("prior_request_changed_after_capture")
        if snapshot_capture != _capture_relative_regular(repository_root, snapshot_path):
            raise MaterializationError("prior_snapshot_changed_after_capture")
        request = _load_json_bytes_closed(request_capture.data, request_path)
    except (MaterializationError, ContractError) as exc:
        raise MaterializationError("prior_generation_invalid", str(exc)) from exc
    if request.get("generation") != generation - 1:
        raise MaterializationError("generation_not_contiguous")
    if request.get("output_path") != output_path.as_posix():
        raise MaterializationError("prior_output_mismatch")
    binding = {
        "request_path": request_path.as_posix(),
        "request_sha256": f"sha256:{hashlib.sha256(request_capture.data).hexdigest()}",
        "snapshot_path": snapshot_path.as_posix(),
        "snapshot_sha256": f"sha256:{hashlib.sha256(snapshot_capture.data).hexdigest()}",
        "generation": generation - 1,
        "output_path": output_path.as_posix(),
    }
    capture = PriorGenerationCapture(
        binding=binding,
        request_path=request_path,
        snapshot_path=snapshot_path,
        request_file=request_capture,
        snapshot_file=snapshot_capture,
        ancestry_captures=(
            bound_request,
            bound_snapshot,
            *ancestor_captures,
        ),
    )
    _assert_prior_generation_current(repository_root, capture)
    return capture


def _assert_prior_generation_current(
    repository_root: Path, capture: PriorGenerationCapture
) -> None:
    if any(
        not _bound_relative_regular_matches(repository_root, bound)
        for bound in capture.ancestry_captures
    ):
        raise MaterializationError("prior_generation_invalid", "capture_changed")


def _quarantine_materialized_file(
    repository_root: Path, path: Path, expected_data: bytes
) -> None:
    parent = _open_nofollow_directory(repository_root, path.parent, create=False)
    try:
        logical_parent = bind_logical_parent(repository_root, path.parent, parent)
        captured = capture_regular_file_at(
            parent, path.name, path.as_posix(), missing_ok=False
        )
        if captured is None or captured.data != expected_data:
            raise MaterializationError(
                "materialization_rollback_concurrent_mutation", path.as_posix()
            )
        conditional_quarantine_file_at(
            parent,
            path.name,
            captured,
            path.as_posix(),
            logical_parent=logical_parent,
        )
    except AtomicPublishError as exc:
        raise MaterializationError(
            "materialization_rollback_failed", path.as_posix()
        ) from exc
    finally:
        os.close(parent)


def _rollback_new_generation(
    repository_root: Path,
    *,
    output_path: Path,
    prior_live_bytes: bytes,
    published_live: BoundRepositoryRegular,
    request_path: Path,
    request_data: bytes,
    request_was_absent: bool,
    snapshot_path: Path,
    output_data: bytes,
    snapshot_was_absent: bool,
) -> None:
    try:
        _atomic_publish(
            repository_root,
            output_path,
            prior_live_bytes,
            owned_live=published_live,
        )
    except MaterializationError as exc:
        if exc.code == "publication_concurrent_mutation":
            raise MaterializationError(
                "materialization_rollback_concurrent_mutation",
                output_path.as_posix(),
            ) from exc
        raise MaterializationError(
            "materialization_rollback_failed", output_path.as_posix()
        ) from exc
    if snapshot_was_absent:
        _quarantine_materialized_file(
            repository_root, snapshot_path, output_data
        )
    if request_was_absent:
        _quarantine_materialized_file(
            repository_root, request_path, request_data
        )


def materialize_transaction(
    *,
    repository_root: Path,
    evidence_root: Path,
    record_kind: str,
    output_path: Path,
    generation: int,
    input_paths: Mapping[str, Path],
    parameters: Mapping[str, Any],
    prior_request: Path | None = None,
    prior_snapshot: Path | None = None,
    pending: bool = False,
) -> MaterializationReceipt:
    repository_root = repository_root.resolve(strict=True)
    evidence_root = _validated_relative(evidence_root)
    output_path = _validated_relative(output_path)
    try:
        output_path.relative_to(evidence_root)
    except ValueError as exc:
        raise MaterializationError("output_outside_evidence_root") from exc
    if not GENERATION_MIN <= generation <= GENERATION_MAX:
        raise MaterializationError("generation_out_of_range")
    adapter = ADAPTERS.get(record_kind)
    if adapter is None:
        raise MaterializationError("record_kind_unknown", record_kind)
    if adapter.pending_only != pending:
        raise MaterializationError("producer_mode_invalid", record_kind)
    if frozenset(input_paths) != adapter.input_roles:
        raise MaterializationError("input_roles_mismatch")
    if frozenset(parameters) != adapter.parameter_names:
        raise MaterializationError("parameter_names_mismatch")
    if not _adapter_output_slot_valid(
        adapter, evidence_root, output_path, input_paths, parameters
    ):
        raise MaterializationError("output_slot_invalid", output_path.as_posix())
    key = hashlib.sha256(output_path.as_posix().encode("utf-8")).hexdigest()
    git_dir = repository_root / ".git"
    lock_root = git_dir / "retirement-materialization-locks" if git_dir.is_dir() else repository_root / ".retirement-materialization-locks"
    lock_root.mkdir(parents=True, exist_ok=True)
    lock_path = lock_root / f"{key}.lock"
    with lock_path.open("a+b") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise MaterializationError("materialization_busy", output_path.as_posix()) from exc
        prior_capture = _prior_binding(
            repository_root, output_path, generation, prior_request, prior_snapshot
        )
        prior = (
            None if prior_capture is None else dict(prior_capture.binding)
        )
        captures = [
            _input_binding(repository_root, role, input_paths[role])
            for role in sorted(input_paths)
        ]
        bindings = [dict(capture.binding) for capture in captures]
        captured_inputs = {
            role: capture for role, capture in zip(sorted(input_paths), captures)
        }
        request: dict[str, Any] = {
            "schema_version": "retirement_materialization_request.v1",
            "record_kind": record_kind,
            "output_path": output_path.as_posix(),
            "generation": generation,
            "prior_generation_binding": prior,
            "input_bindings": bindings,
            "parameters": dict(parameters),
            "expected_input_set_sha256": canonical_sha256(bindings),
            "normalized_request_sha256": "",
            "claims_not_made": [
                "This request does not authorize owner action or source mutation."
            ],
        }
        request["normalized_request_sha256"] = canonical_sha256(
            request, exclude={"normalized_request_sha256"}
        )
        request_issues = validate_record(request)
        if request_issues:
            raise MaterializationError(
                "materialization_request_invalid", request_issues[0].code
            )
        request_path = _request_path(
            evidence_root, output_path, generation, request["normalized_request_sha256"]
        )
        record = adapter.builder(repository_root, captured_inputs, parameters)
        _validate_adapter_output(record, adapter=adapter, pending=pending)
        if record_kind == "execution-ledger":
            try:
                prior_record = (
                    None
                    if prior_capture is None
                    else _load_json_bytes_closed(
                        prior_capture.snapshot_file.data,
                        prior_capture.snapshot_path,
                    )
                )
            except ContractError as exc:
                raise MaterializationError(
                    "ledger_generation_invalid", "ledger_prior_record_invalid"
                ) from exc
            if prior_record is not None and not isinstance(prior_record, Mapping):
                raise MaterializationError(
                    "ledger_generation_invalid", "ledger_prior_record_invalid"
                )
            ledger_issues = _execution_ledger_generation_issues(
                record,
                repository_root=repository_root,
                generation=generation,
                plan_path=captured_inputs["approved_plan"].path,
                plan_bytes=captured_inputs["approved_plan"].data,
                prior_record=prior_record,
                request_prior_binding=prior,
            )
            if ledger_issues:
                raise MaterializationError(
                    "ledger_generation_invalid", ledger_issues[0].code
                )
        output_data = _json_output(record)
        output_sha = f"sha256:{hashlib.sha256(output_data).hexdigest()}"
        snapshot_path = _snapshot_path(evidence_root, output_path, generation, output_sha)
        request_data = _json_output(request)
        existing_requests = _generation_slot_names(
            repository_root, request_path.parent, generation
        )
        if existing_requests not in ([], [request_path.name]):
            raise MaterializationError("generation_slot_conflict")
        existing_snapshots = _generation_slot_names(
            repository_root, snapshot_path.parent, generation
        )
        if existing_snapshots not in ([], [snapshot_path.name]):
            raise MaterializationError("generation_slot_conflict")
        request_bytes = _nofollow_file_bytes(
            repository_root, request_path, missing_ok=True
        )
        snapshot_bytes = _nofollow_file_bytes(
            repository_root, snapshot_path, missing_ok=True
        )
        live_bytes = _nofollow_file_bytes(
            repository_root, output_path, missing_ok=True
        )
        if request_bytes is not None and request_bytes != request_data:
            raise MaterializationError("immutable_slot_conflict", request_path.as_posix())
        if snapshot_bytes is not None and snapshot_bytes != output_data:
            raise MaterializationError("immutable_slot_conflict", snapshot_path.as_posix())
        if generation == 1:
            prefix_state_valid = (
                (request_bytes, snapshot_bytes, live_bytes)
                in {
                    (None, None, None),
                    (request_data, None, None),
                    (request_data, output_data, None),
                    (request_data, output_data, output_data),
                }
            )
            if live_bytes is not None and live_bytes != output_data:
                raise MaterializationError("live_output_exists_without_history")
        else:
            assert prior is not None
            assert prior_capture is not None
            prior_live_bytes = prior_capture.snapshot_file.data
            prefix_state_valid = (
                (request_bytes, snapshot_bytes, live_bytes)
                in {
                    (None, None, prior_live_bytes),
                    (request_data, None, prior_live_bytes),
                    (request_data, output_data, prior_live_bytes),
                    (request_data, output_data, output_data),
                }
            )
            if live_bytes not in {prior_live_bytes, output_data}:
                raise MaterializationError("stale_live_output")
        if not prefix_state_valid:
            raise MaterializationError("materialization_nonprefix_state")
        request_was_absent = request_bytes is None
        snapshot_was_absent = snapshot_bytes is None
        if prior_capture is not None:
            _prior_binding_boundary("before_prior_prepublication_check")
            _assert_prior_generation_current(repository_root, prior_capture)
        _exclusive_identical(repository_root, request_path, request_data)
        _materialization_boundary("after_request_creation")
        _materialization_boundary("before_snapshot_publication")
        _exclusive_identical(repository_root, snapshot_path, output_data)
        _materialization_boundary("after_snapshot_publication")
        _materialization_boundary("before_live_publication")
        if record_kind == "execution-ledger":
            _build_ledger(repository_root, captured_inputs, parameters)
        published_live = _atomic_publish(repository_root, output_path, output_data)
        if _nofollow_file_bytes(repository_root, output_path) != output_data:
            raise MaterializationError("live_publication_mismatch")
        if prior_capture is not None:
            _prior_binding_boundary("before_prior_postpublication_check")
            try:
                _assert_prior_generation_current(repository_root, prior_capture)
            except MaterializationError:
                _rollback_new_generation(
                    repository_root,
                    output_path=output_path,
                    prior_live_bytes=prior_capture.snapshot_file.data,
                    published_live=published_live,
                    request_path=request_path,
                    request_data=request_data,
                    request_was_absent=request_was_absent,
                    snapshot_path=snapshot_path,
                    output_data=output_data,
                    snapshot_was_absent=snapshot_was_absent,
                )
                raise
        return MaterializationReceipt(
            request_path=request_path,
            request_sha256=f"sha256:{hashlib.sha256(request_data).hexdigest()}",
            snapshot_path=snapshot_path,
            snapshot_sha256=f"sha256:{hashlib.sha256(output_data).hexdigest()}",
            generation=generation,
            output_path=output_path,
            output_sha256=output_sha,
        )


def materialize_pending(**kwargs: Any) -> MaterializationReceipt:
    kwargs["pending"] = True
    return materialize_transaction(**kwargs)


def _validate_generation_captured(
    repository_root: Path,
    request_path: Path,
    snapshot_path: Path,
    request_bytes: bytes,
    snapshot_bytes: bytes,
    *,
    _validate_ancestors: bool = True,
    _ancestry_captures: list[ResolvedRepositoryRegular] | None = None,
    bound_file_bytes: Mapping[str, bytes] | None = None,
    require_committed_fallback: bool = False,
) -> list[Issue]:
    issues: list[Issue] = []
    try:
        request_path = _validated_relative(request_path)
        snapshot_path = _validated_relative(snapshot_path)
        request = _load_json_bytes_closed(request_bytes, request_path)
    except (MaterializationError, ContractError, OSError) as exc:
        return [Issue("generation_unreadable", "$", str(exc))]
    record_issues = validate_record(request)
    if record_issues:
        issues.extend(record_issues)
        return sorted(set(issues))
    generation = request["generation"]
    if not isinstance(generation, int) or not GENERATION_MIN <= generation <= GENERATION_MAX:
        issues.append(Issue("generation_out_of_range", "$.generation"))
        return sorted(set(issues))
    try:
        evidence_root = _evidence_root_from_request_path(request_path)
    except MaterializationError:
        issues.append(Issue("request_path_mismatch"))
        return sorted(set(issues))
    expected_request = _request_path(
        evidence_root,
        Path(request["output_path"]),
        generation,
        request["normalized_request_sha256"],
    )
    if request_path != expected_request:
        issues.append(Issue("request_path_mismatch"))
    try:
        request_slot = _generation_slot_names(
            repository_root,
            request_path.parent,
            generation,
            create=False,
            bound_file_bytes=bound_file_bytes,
        )
    except (MaterializationError, OSError) as exc:
        return [Issue("generation_unreadable", "$", str(exc))]
    if request_slot != [request_path.name]:
        issues.append(Issue("generation_request_slot_extra"))
    prior = request.get("prior_generation_binding")
    prior_request_path: Path | None = None
    prior_snapshot_path: Path | None = None
    prior_request_bytes: bytes | None = None
    prior_snapshot_bytes: bytes | None = None
    prior_record: Mapping[str, Any] | None = None
    if generation == 1:
        if prior is not None:
            issues.append(Issue("prior_generation_unexpected"))
    else:
        prior_keys = {
            "request_path",
            "request_sha256",
            "snapshot_path",
            "snapshot_sha256",
            "generation",
            "output_path",
        }
        if not isinstance(prior, dict) or set(prior) != prior_keys:
            issues.append(Issue("prior_generation_binding_invalid"))
        else:
            try:
                prior_request_path = _validated_relative(Path(prior["request_path"]))
                prior_snapshot_path = _validated_relative(Path(prior["snapshot_path"]))
                prior_request_capture = _capture_resolved_relative_regular(
                    repository_root,
                    prior_request_path,
                    bound_file_bytes,
                    require_committed_fallback,
                )
                prior_snapshot_capture = _capture_resolved_relative_regular(
                    repository_root,
                    prior_snapshot_path,
                    bound_file_bytes,
                    require_committed_fallback,
                )
                prior_request_bytes = _resolved_regular_data(prior_request_capture)
                prior_snapshot_bytes = _resolved_regular_data(prior_snapshot_capture)
                if _ancestry_captures is not None:
                    _ancestry_captures.extend(
                        (prior_request_capture, prior_snapshot_capture)
                    )
                changed = (
                    prior["generation"] != generation - 1
                    or prior["output_path"] != request["output_path"]
                    or prior_request_bytes is None
                    or prior_snapshot_bytes is None
                    or f"sha256:{hashlib.sha256(prior_request_bytes).hexdigest()}"
                    != prior["request_sha256"]
                    or f"sha256:{hashlib.sha256(prior_snapshot_bytes).hexdigest()}"
                    != prior["snapshot_sha256"]
                )
            except (KeyError, TypeError, MaterializationError, OSError):
                changed = True
            if changed:
                issues.append(Issue("prior_generation_changed"))
            else:
                try:
                    loaded_prior = _load_json_bytes_closed(
                        prior_snapshot_bytes, prior_snapshot_path
                    )
                except (ContractError, TypeError):
                    issues.append(Issue("prior_generation_changed"))
                else:
                    if not isinstance(loaded_prior, Mapping):
                        issues.append(Issue("prior_generation_changed"))
                    else:
                        prior_record = loaded_prior
    adapter = ADAPTERS.get(request.get("record_kind"))
    raw_bindings = request.get("input_bindings")
    if adapter is None:
        issues.append(Issue("generation_record_kind_unknown"))
        return sorted(set(issues))
    if not isinstance(raw_bindings, list) or request.get("expected_input_set_sha256") != canonical_sha256(raw_bindings):
        issues.append(Issue("generation_input_set_invalid"))
        return sorted(set(issues))
    input_paths: dict[str, Path] = {}
    captured_inputs: dict[str, InputCapture] = {}
    observed_bindings: list[dict[str, Any]] = []
    for binding in raw_bindings:
        if not isinstance(binding, dict) or set(binding) != {
            "role", "path", "size", "sha256", "schema_version"
        }:
            issues.append(Issue("generation_input_binding_invalid"))
            continue
        role = binding["role"]
        if not isinstance(role, str) or role in input_paths:
            issues.append(Issue("generation_input_binding_invalid"))
            continue
        try:
            relative = _validated_relative(Path(binding["path"]))
            observed = _input_binding(
                repository_root,
                role,
                relative,
                bound_file_bytes=bound_file_bytes,
                require_committed_fallback=require_committed_fallback,
            )
        except (MaterializationError, TypeError):
            issues.append(Issue("generation_input_changed", str(binding.get("path"))))
            continue
        input_paths[role] = relative
        captured_inputs[role] = observed
        observed_binding = dict(observed.binding)
        observed_bindings.append(observed_binding)
        if observed_binding != binding:
            issues.append(Issue("generation_input_changed", relative.as_posix()))
    if frozenset(input_paths) != adapter.input_roles:
        issues.append(Issue("generation_input_roles_mismatch"))
    output_path = Path(request["output_path"])
    if not _adapter_output_slot_valid(
        adapter,
        evidence_root,
        output_path,
        input_paths,
        request["parameters"],
    ):
        issues.append(Issue("generation_output_slot_invalid", "$.output_path"))
    if issues:
        return sorted(set(issues))
    try:
        snapshot_slot = _generation_slot_names(
            repository_root,
            snapshot_path.parent,
            generation,
            create=False,
            bound_file_bytes=bound_file_bytes,
        )
    except (MaterializationError, OSError):
        snapshot_slot = []
        issues.append(Issue("snapshot_unreadable"))
    if snapshot_slot != [snapshot_path.name]:
        issues.append(Issue("generation_snapshot_slot_extra"))
    snapshot_sha = f"sha256:{hashlib.sha256(snapshot_bytes).hexdigest()}"
    expected_snapshot = _snapshot_path(
        evidence_root, output_path, generation, snapshot_sha
    )
    if snapshot_path != expected_snapshot:
        issues.append(Issue("snapshot_path_mismatch"))
    rebuilt: Any = None
    try:
        rebuilt = (
            _build_ledger_with_future_mode(
                repository_root,
                captured_inputs,
                request["parameters"],
                check_future_absence=False,
                bound_file_bytes=bound_file_bytes,
                require_committed_fallback=require_committed_fallback,
            )
            if request.get("record_kind") == "execution-ledger"
            else adapter.builder(
                repository_root, captured_inputs, request["parameters"]
            )
        )
        _validate_adapter_output(
            rebuilt, adapter=adapter, pending=adapter.pending_only
        )
        expected_output = _json_output(rebuilt)
    except (MaterializationError, ContractError, KeyError, TypeError, OSError):
        issues.append(Issue("snapshot_output_contract_invalid"))
    else:
        if snapshot_bytes != expected_output:
            issues.append(Issue("snapshot_output_mismatch"))
    if request.get("record_kind") == "execution-ledger" and isinstance(
        rebuilt, Mapping
    ):
        ledger_issues = _execution_ledger_generation_issues(
            rebuilt,
            repository_root=repository_root,
            generation=generation,
            plan_path=captured_inputs["approved_plan"].path,
            plan_bytes=captured_inputs["approved_plan"].data,
            prior_record=prior_record,
            request_prior_binding=prior if isinstance(prior, Mapping) else None,
            bound_file_bytes=bound_file_bytes,
            require_committed_fallback=require_committed_fallback,
        )
        issues.extend(ledger_issues)
    if (
        _validate_ancestors
        and not issues
        and generation > 1
        and prior_request_path is not None
        and prior_snapshot_path is not None
        and prior_request_bytes is not None
        and prior_snapshot_bytes is not None
    ):
        ancestor_request_path = prior_request_path
        ancestor_snapshot_path = prior_snapshot_path
        ancestor_request_bytes = prior_request_bytes
        ancestor_snapshot_bytes = prior_snapshot_bytes
        while True:
            ancestor_issues = _validate_generation_captured(
                repository_root,
                ancestor_request_path,
                ancestor_snapshot_path,
                ancestor_request_bytes,
                ancestor_snapshot_bytes,
                _validate_ancestors=False,
                _ancestry_captures=_ancestry_captures,
                bound_file_bytes=bound_file_bytes,
                require_committed_fallback=require_committed_fallback,
            )
            if ancestor_issues:
                issues.append(
                    Issue(
                        "prior_generation_invalid",
                        message=ancestor_issues[0].code,
                    )
                )
                break
            try:
                ancestor_request = _load_json_bytes_closed(
                    ancestor_request_bytes, ancestor_request_path
                )
                if ancestor_request.get("generation") == 1:
                    break
                ancestor_prior = ancestor_request["prior_generation_binding"]
                ancestor_request_path = _validated_relative(
                    Path(ancestor_prior["request_path"])
                )
                ancestor_snapshot_path = _validated_relative(
                    Path(ancestor_prior["snapshot_path"])
                )
                ancestor_request_capture = _capture_resolved_relative_regular(
                    repository_root,
                    ancestor_request_path,
                    bound_file_bytes,
                    require_committed_fallback,
                )
                ancestor_snapshot_capture = _capture_resolved_relative_regular(
                    repository_root,
                    ancestor_snapshot_path,
                    bound_file_bytes,
                    require_committed_fallback,
                )
                ancestor_request_bytes = _resolved_regular_data(
                    ancestor_request_capture
                )
                ancestor_snapshot_bytes = _resolved_regular_data(
                    ancestor_snapshot_capture
                )
                if _ancestry_captures is not None:
                    _ancestry_captures.extend(
                        (ancestor_request_capture, ancestor_snapshot_capture)
                    )
            except (AttributeError, KeyError, TypeError, ContractError, MaterializationError):
                issues.append(Issue("prior_generation_invalid"))
                break
    return sorted(set(issues))


def validate_generation(
    repository_root: Path,
    request_path: Path,
    snapshot_path: Path,
    *,
    bound_file_bytes: Mapping[str, bytes] | None = None,
    require_committed_fallback: bool = False,
) -> list[Issue]:
    try:
        request_path = _validated_relative(request_path)
        snapshot_path = _validated_relative(snapshot_path)
        request_capture = _capture_resolved_relative_regular(
            repository_root,
            request_path,
            bound_file_bytes,
            require_committed_fallback,
        )
    except (MaterializationError, OSError) as exc:
        return [Issue("generation_unreadable", "$", str(exc))]
    try:
        snapshot_capture = _capture_resolved_relative_regular(
            repository_root,
            snapshot_path,
            bound_file_bytes,
            require_committed_fallback,
        )
    except (MaterializationError, OSError) as exc:
        return [Issue("snapshot_unreadable", "$", str(exc))]
    ancestry_captures: list[ResolvedRepositoryRegular] = []
    issues = _validate_generation_captured(
        repository_root,
        request_path,
        snapshot_path,
        _resolved_regular_data(request_capture),
        _resolved_regular_data(snapshot_capture),
        _ancestry_captures=ancestry_captures,
        bound_file_bytes=bound_file_bytes,
        require_committed_fallback=require_committed_fallback,
    )
    _generation_validation_boundary("before_final_identity_check")
    if not _resolved_relative_regular_matches(
        repository_root,
        request_capture,
        bound_file_bytes,
        require_committed_fallback,
    ):
        issues.append(Issue("generation_unreadable", "$", request_path.as_posix()))
    if not _resolved_relative_regular_matches(
        repository_root,
        snapshot_capture,
        bound_file_bytes,
        require_committed_fallback,
    ):
        issues.append(Issue("snapshot_unreadable", "$", snapshot_path.as_posix()))
    if any(
        not _resolved_relative_regular_matches(
            repository_root,
            capture,
            bound_file_bytes,
            require_committed_fallback,
        )
        for capture in ancestry_captures
    ):
        issues.append(Issue("prior_generation_changed"))
    return sorted(set(issues))


def _generation_request_names(
    repository_root: Path,
    directory: Path,
    *,
    bound_file_bytes: Mapping[str, bytes] | None = None,
) -> list[str]:
    names: set[str] = set()
    try:
        descriptor = _open_nofollow_directory(
            repository_root, directory, create=False
        )
    except FileNotFoundError:
        descriptor = None
    if descriptor is not None:
        try:
            names.update(os.listdir(descriptor))
        finally:
            os.close(descriptor)
    if bound_file_bytes is not None:
        names.update(
            Path(path).name
            for path in bound_file_bytes
            if _validated_relative(Path(path)).parent == directory
        )
    ordered = sorted(names)
    if any(GENERATION_FILE_RE.fullmatch(name) is None for name in ordered):
        raise MaterializationError("generation_request_directory_invalid")
    return ordered


def _resolve_request_bound_ancestor(
    repository_root: Path,
    request: Mapping[str, Any],
    *,
    bound: Mapping[str, Any],
    bound_file_bytes: Mapping[str, bytes] | None = None,
    require_committed_fallback: bool = False,
) -> BoundAncestryResolution:
    expected = {
        "request_path": bound["request_path"],
        "request_sha256": bound["request_sha256"],
        "snapshot_path": bound["snapshot_path"],
        "snapshot_sha256": bound["snapshot_sha256"],
        "generation": bound["generation"],
        "output_path": bound["live_path"],
    }
    current = request
    seen: set[str] = set()
    captures: list[ResolvedRepositoryRegular] = []
    while current.get("generation", 0) > bound["generation"]:
        prior = current.get("prior_generation_binding")
        if not isinstance(prior, Mapping):
            raise MaterializationError("generation_binding_changed")
        if dict(prior) == expected:
            return BoundAncestryResolution(True, tuple(captures))
        try:
            prior_request_path = _validated_relative(Path(prior["request_path"]))
            prior_snapshot_path = _validated_relative(
                Path(prior["snapshot_path"])
            )
            if prior_request_path.as_posix() in seen:
                raise MaterializationError("generation_binding_changed")
            seen.add(prior_request_path.as_posix())
            prior_request_capture = _capture_resolved_relative_regular(
                repository_root,
                prior_request_path,
                bound_file_bytes,
                require_committed_fallback,
            )
            prior_snapshot_capture = _capture_resolved_relative_regular(
                repository_root,
                prior_snapshot_path,
                bound_file_bytes,
                require_committed_fallback,
            )
            request_sha = (
                "sha256:"
                + hashlib.sha256(
                    _resolved_regular_data(prior_request_capture)
                ).hexdigest()
            )
            snapshot_sha = (
                "sha256:"
                + hashlib.sha256(
                    _resolved_regular_data(prior_snapshot_capture)
                ).hexdigest()
            )
            if (
                prior.get("request_sha256") != request_sha
                or prior.get("snapshot_sha256") != snapshot_sha
                or prior.get("generation") != current.get("generation") - 1
                or prior.get("output_path") != bound["live_path"]
            ):
                raise MaterializationError("generation_binding_changed")
            current = _load_json_bytes_closed(
                _resolved_regular_data(prior_request_capture), prior_request_path
            )
            if (
                not isinstance(current, Mapping)
                or current.get("record_kind") != "execution-ledger"
                or current.get("generation") != prior.get("generation")
                or current.get("output_path") != bound["live_path"]
            ):
                raise MaterializationError("generation_binding_changed")
            captures.extend((prior_request_capture, prior_snapshot_capture))
        except (KeyError, TypeError, MaterializationError, ContractError, OSError) as exc:
            raise MaterializationError("generation_binding_changed") from exc
    return BoundAncestryResolution(False, tuple(captures))


def _resolve_generation_binding_current(
    repository_root: Path,
    binding: Mapping[str, Any],
    *,
    allow_descendant: bool = True,
    bound_file_bytes: Mapping[str, bytes] | None = None,
    require_committed_fallback: bool = False,
) -> tuple[list[Issue], GenerationBindingResolution | None]:
    """Reopen a bound generation against its current canonical live descendant."""

    try:
        request_path = _validated_relative(Path(binding["request_path"]))
        snapshot_path = _validated_relative(Path(binding["snapshot_path"]))
        live_path = _validated_relative(Path(binding["live_path"]))
        request_capture = _capture_resolved_relative_regular(
            repository_root,
            request_path,
            bound_file_bytes,
            require_committed_fallback,
        )
        snapshot_capture = _capture_resolved_relative_regular(
            repository_root,
            snapshot_path,
            bound_file_bytes,
            require_committed_fallback,
        )
        live_capture = _capture_resolved_relative_regular(
            repository_root,
            live_path,
            bound_file_bytes,
            require_committed_fallback,
        )
    except (KeyError, TypeError, MaterializationError, OSError) as exc:
        return [Issue("live_generation_unreadable", "$", str(exc))], None

    request_bytes = _resolved_regular_data(request_capture)
    snapshot_bytes = _resolved_regular_data(snapshot_capture)
    request_sha = f"sha256:{hashlib.sha256(request_bytes).hexdigest()}"
    snapshot_sha = f"sha256:{hashlib.sha256(snapshot_bytes).hexdigest()}"
    if (
        request_sha != binding.get("request_sha256")
        or snapshot_sha != binding.get("snapshot_sha256")
        or snapshot_sha != binding.get("byte_sha256")
    ):
        return [Issue("generation_binding_coordinate_invalid")], None
    try:
        request = _load_json_bytes_closed(request_bytes, request_path)
    except ContractError as exc:
        return [Issue("generation_binding_coordinate_invalid", message=str(exc))], None
    if (
        not isinstance(request, Mapping)
        or request.get("record_kind") != "execution-ledger"
        or request.get("output_path") != live_path.as_posix()
        or request.get("generation") != binding.get("generation")
    ):
        return [Issue("generation_binding_coordinate_invalid")], None
    bound_issues = validate_generation(
        repository_root,
        request_path,
        snapshot_path,
        bound_file_bytes=bound_file_bytes,
        require_committed_fallback=require_committed_fallback,
    )
    _generation_validation_boundary("after_bound_binding_validation")
    if (
        not _resolved_relative_regular_matches(
            repository_root,
            request_capture,
            bound_file_bytes,
            require_committed_fallback,
        )
        or not _resolved_relative_regular_matches(
            repository_root,
            snapshot_capture,
            bound_file_bytes,
            require_committed_fallback,
        )
    ):
        return [Issue("generation_binding_changed")], None
    if bound_issues:
        return [Issue("bound_generation_invalid", message=bound_issues[0].code)], None
    live_bytes = _resolved_regular_data(live_capture)
    if live_bytes == snapshot_bytes:
        if not _resolved_relative_regular_matches(
            repository_root,
            live_capture,
            bound_file_bytes,
            require_committed_fallback,
        ):
            return [Issue("live_generation_unreadable")], None
        return [], GenerationBindingResolution(
            bound_request=request_capture,
            bound_snapshot=snapshot_capture,
            current_request=request_capture,
            current_snapshot=snapshot_capture,
            live=live_capture,
        )
    if not allow_descendant:
        return [Issue("live_generation_not_bound")], None

    live_sha = f"sha256:{hashlib.sha256(live_bytes).hexdigest()}"
    evidence_root = _evidence_root_from_request_path(request_path)
    candidates: list[
        tuple[
            ResolvedRepositoryRegular,
            ResolvedRepositoryRegular,
            tuple[ResolvedRepositoryRegular, ...],
        ]
    ] = []
    try:
        names = _generation_request_names(
            repository_root,
            request_path.parent,
            bound_file_bytes=bound_file_bytes,
        )
    except (MaterializationError, OSError) as exc:
        return [Issue("live_generation_unreadable", message=str(exc))], None
    for name in names:
        generation = int(name[:8])
        if generation <= binding["generation"]:
            continue
        candidate_request_path = request_path.parent / name
        candidate_snapshot_path = _snapshot_path(
            evidence_root, live_path, generation, live_sha
        )
        try:
            candidate_request_capture = _capture_resolved_relative_regular(
                repository_root,
                candidate_request_path,
                bound_file_bytes,
                require_committed_fallback,
            )
            candidate_snapshot_capture = _capture_resolved_relative_regular(
                repository_root,
                candidate_snapshot_path,
                bound_file_bytes,
                require_committed_fallback,
            )
            candidate_request = _load_json_bytes_closed(
                _resolved_regular_data(candidate_request_capture),
                candidate_request_path,
            )
        except (MaterializationError, ContractError, OSError):
            continue
        candidate_is_valid = (
            _resolved_regular_data(candidate_snapshot_capture) == live_bytes
            and isinstance(candidate_request, Mapping)
            and candidate_request.get("record_kind") == "execution-ledger"
            and candidate_request.get("generation") == generation
            and candidate_request.get("output_path") == live_path.as_posix()
        )
        ancestry = BoundAncestryResolution(False, ())
        if candidate_is_valid:
            candidate_generation_issues = validate_generation(
                repository_root,
                candidate_request_path,
                candidate_snapshot_path,
                bound_file_bytes=bound_file_bytes,
                require_committed_fallback=require_committed_fallback,
            )
            _generation_validation_boundary(
                "after_candidate_generation_validation"
            )
            if not candidate_generation_issues:
                try:
                    ancestry = _resolve_request_bound_ancestor(
                        repository_root,
                        candidate_request,
                        bound=binding,
                        bound_file_bytes=bound_file_bytes,
                        require_committed_fallback=require_committed_fallback,
                    )
                except MaterializationError:
                    return [Issue("generation_binding_changed")], None
                candidate_is_valid = ancestry.matched
            else:
                candidate_is_valid = False
        _generation_validation_boundary("after_candidate_binding_validation")
        candidate_captures = (
            candidate_request_capture,
            candidate_snapshot_capture,
            *ancestry.captures,
        )
        if any(
            not _resolved_relative_regular_matches(
                repository_root,
                capture,
                bound_file_bytes,
                require_committed_fallback,
            )
            for capture in candidate_captures
        ):
            return [Issue("generation_binding_changed")], None
        if not candidate_is_valid:
            continue
        candidates.append(
            (
                candidate_request_capture,
                candidate_snapshot_capture,
                ancestry.captures,
            )
        )
    _generation_validation_boundary("before_final_candidate_lineage_check")
    if any(
        not _resolved_relative_regular_matches(
            repository_root,
            capture,
            bound_file_bytes,
            require_committed_fallback,
        )
        for candidate_request, candidate_snapshot, ancestry_captures in candidates
        for capture in (
            candidate_request,
            candidate_snapshot,
            *ancestry_captures,
        )
    ):
        return [Issue("generation_binding_changed")], None
    if (
        not _resolved_relative_regular_matches(
            repository_root,
            request_capture,
            bound_file_bytes,
            require_committed_fallback,
        )
        or not _resolved_relative_regular_matches(
            repository_root,
            snapshot_capture,
            bound_file_bytes,
            require_committed_fallback,
        )
    ):
        return [Issue("generation_binding_changed")], None
    if len(candidates) != 1:
        code = (
            "live_generation_unrelated"
            if not candidates
            else "live_generation_ambiguous"
        )
        return [Issue(code)], None
    (
        candidate_request_capture,
        candidate_snapshot_capture,
        ancestry_captures,
    ) = candidates[0]
    if any(
        not _resolved_relative_regular_matches(
            repository_root,
            capture,
            bound_file_bytes,
            require_committed_fallback,
        )
        for capture in (
            request_capture,
            snapshot_capture,
            candidate_request_capture,
            candidate_snapshot_capture,
            *ancestry_captures,
        )
    ):
        return [Issue("generation_binding_changed")], None
    if not _resolved_relative_regular_matches(
        repository_root,
        live_capture,
        bound_file_bytes,
        require_committed_fallback,
    ):
        return [Issue("live_generation_unreadable")], None
    return [], GenerationBindingResolution(
        bound_request=request_capture,
        bound_snapshot=snapshot_capture,
        current_request=candidate_request_capture,
        current_snapshot=candidate_snapshot_capture,
        live=live_capture,
    )


def validate_generation_binding_current(
    repository_root: Path,
    binding: Mapping[str, Any],
    *,
    allow_descendant: bool = True,
    bound_file_bytes: Mapping[str, bytes] | None = None,
    require_committed_fallback: bool = False,
) -> list[Issue]:
    """Reopen a generation through live state plus exact logical byte shadows."""

    issues, _resolution = _resolve_generation_binding_current(
        repository_root,
        binding,
        allow_descendant=allow_descendant,
        bound_file_bytes=bound_file_bytes,
        require_committed_fallback=require_committed_fallback,
    )
    return issues


def generation_binding_lineage_file_bindings(
    repository_root: Path,
    binding: Mapping[str, Any],
) -> tuple[list[Issue], list[dict[str, str]], list[dict[str, str]]]:
    """Return bound and later request/snapshot rows from one validated live lineage."""

    issues, resolution = _resolve_generation_binding_current(
        repository_root, binding, allow_descendant=True
    )
    if issues or resolution is None:
        return issues or [Issue("generation_lineage_invalid")], [], []

    captures: list[tuple[int, BoundRepositoryRegular, BoundRepositoryRegular]] = []
    request_capture = resolution.current_request
    snapshot_capture = resolution.current_snapshot
    seen: set[str] = set()
    try:
        while True:
            request = _load_json_bytes_closed(
                request_capture.file.data, request_capture.path
            )
            generation = request.get("generation")
            if (
                type(generation) is not int
                or not GENERATION_MIN <= generation <= GENERATION_MAX
                or request.get("record_kind") != "execution-ledger"
                or request.get("output_path") != binding.get("live_path")
                or request_capture.path.as_posix() in seen
            ):
                raise MaterializationError("generation_lineage_invalid")
            seen.add(request_capture.path.as_posix())
            captures.append((generation, request_capture, snapshot_capture))
            if generation == 1:
                break
            prior = request.get("prior_generation_binding")
            if not isinstance(prior, Mapping):
                raise MaterializationError("generation_lineage_invalid")
            prior_request_path = _validated_relative(Path(prior["request_path"]))
            prior_snapshot_path = _validated_relative(Path(prior["snapshot_path"]))
            prior_request_capture = _capture_bound_relative_regular(
                repository_root, prior_request_path
            )
            prior_snapshot_capture = _capture_bound_relative_regular(
                repository_root, prior_snapshot_path
            )
            if (
                prior.get("generation") != generation - 1
                or prior.get("output_path") != binding.get("live_path")
                or prior.get("request_sha256")
                != "sha256:"
                + hashlib.sha256(prior_request_capture.file.data).hexdigest()
                or prior.get("snapshot_sha256")
                != "sha256:"
                + hashlib.sha256(prior_snapshot_capture.file.data).hexdigest()
            ):
                raise MaterializationError("generation_lineage_invalid")
            request_capture = prior_request_capture
            snapshot_capture = prior_snapshot_capture
    except (KeyError, TypeError, ContractError, MaterializationError, OSError) as exc:
        return [Issue("generation_lineage_invalid", message=str(exc))], [], []

    bound_generation = binding.get("generation")
    bound_matches = [
        (request_capture, snapshot_capture)
        for generation, request_capture, snapshot_capture in captures
        if generation == bound_generation
        and request_capture.path.as_posix() == binding.get("request_path")
        and snapshot_capture.path.as_posix() == binding.get("snapshot_path")
    ]
    if len(bound_matches) != 1:
        return [Issue("generation_lineage_invalid")], [], []

    _generation_validation_boundary("after_lineage_capture")
    if any(
        not _bound_relative_regular_matches(repository_root, request_capture)
        or not _bound_relative_regular_matches(repository_root, snapshot_capture)
        for _generation, request_capture, snapshot_capture in captures
    ):
        return [Issue("generation_binding_changed")], [], []

    def rows(selected: list[tuple[int, BoundRepositoryRegular, BoundRepositoryRegular]]) -> list[dict[str, str]]:
        result = [
            {
                "path": capture.path.as_posix(),
                "sha256": "sha256:" + hashlib.sha256(capture.file.data).hexdigest(),
            }
            for _generation, request_capture, snapshot_capture in selected
            for capture in (request_capture, snapshot_capture)
        ]
        return sorted(result, key=lambda row: row["path"])

    bound = [row for row in captures if row[0] <= bound_generation]
    descendants = [row for row in captures if row[0] > bound_generation]
    return [], rows(bound), rows(descendants)
