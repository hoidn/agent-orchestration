"""Pure, read-only projection of persisted provider judgment authorities."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from orchestrator.contracts.output_contract import (
    OutputContractError,
    validate_contract_value,
)
from orchestrator.dashboard.compiled_workflow import (
    PersistedCompiledWorkflowError,
    load_persisted_compiled_workflow_surface,
    traverse_persisted_compiled_workflow_call_frames,
)
from orchestrator.workflow.prompt_attempt_result_binding import (
    PROMPT_ATTEMPT_RESULT_BINDING_DEBUG_KEY,
    PromptAttemptResultBindingError,
    validate_prompt_attempt_result_binding,
)
from orchestrator.workflow.prompt_context_report import (
    PROMPT_CONTEXT_REPORT_SCHEMA,
    _comparison,
    _identity_projection,
    _load_publication,
)
from orchestrator.workflow.prompt_identity import (
    PROMPT_ATTEMPT_IDENTITY_VERSION,
    ROLE_CLASSIFICATIONS,
    ROLE_ORDER,
    canonical_json_bytes,
    canonical_sha256,
)
from orchestrator.workflow.persisted_surface import (
    PersistedSurfaceStep,
    PersistedWorkflowSurfaceNode,
    canonical_persisted_surface_bytes,
    persisted_surface_sha256,
)
from orchestrator.workflow.provider_attempts import (
    ProviderAttemptScope,
    validate_provider_attempt_allocations,
)
from orchestrator.workflow.surface_ast import SurfaceStepKind


JUDGMENT_VIEWS_SCHEMA = "workflow_judgment_views.v1"
JUDGMENT_INSPECTION_SCHEMA = "workflow_judgment_inspection.v1"
JUDGMENT_MATRIX_SCHEMA = "workflow_judgment_matrix.v1"
JUDGMENT_DISAGREEMENT_SCHEMA = "workflow_judgment_disagreement.v1"
JUDGMENT_ITERATION_SERIES_SCHEMA = (
    "workflow_judgment_iteration_series.v1"
)
JUDGMENT_RESULT_BINDING_MISSING = "judgment_result_binding_missing"
JUDGMENT_RESULT_BINDING_INVALID = "judgment_result_binding_invalid"
JUDGMENT_RESULT_BINDING_AMBIGUOUS = (
    "judgment_result_binding_ambiguous"
)
JUDGMENT_RESULT_SCOPE_MISMATCH = "judgment_result_scope_mismatch"
JUDGMENT_RESULT_ATTEMPT_MISMATCH = "judgment_result_attempt_mismatch"
JUDGMENT_RESULT_EVIDENCE_INVALID = "judgment_result_evidence_invalid"
JUDGMENT_RESULT_CONTRACT_MISMATCH = "judgment_result_contract_mismatch"
JUDGMENT_RESULT_VALUE_MISMATCH = "judgment_result_value_mismatch"
JUDGMENT_RESULT_COORDINATE_INVALID = "judgment_result_coordinate_invalid"
JUDGMENT_VIEW_GROUP_INVALID = "judgment_view_group_invalid"

_UNAVAILABLE_REASONS = frozenset(
    {
        JUDGMENT_RESULT_BINDING_MISSING,
        JUDGMENT_RESULT_BINDING_INVALID,
        JUDGMENT_RESULT_BINDING_AMBIGUOUS,
        JUDGMENT_RESULT_SCOPE_MISMATCH,
        JUDGMENT_RESULT_ATTEMPT_MISMATCH,
        JUDGMENT_RESULT_EVIDENCE_INVALID,
        JUDGMENT_RESULT_CONTRACT_MISMATCH,
        JUDGMENT_RESULT_VALUE_MISMATCH,
        JUDGMENT_RESULT_COORDINATE_INVALID,
        JUDGMENT_VIEW_GROUP_INVALID,
    }
)
_Q3_COMPARISON_UNAVAILABLE_REASONS = frozenset(
    {
        "no_predecessor",
        "current_record_missing",
        "current_record_invalid",
        "previous_record_invalid",
        "legacy_snapshot_only",
        "provider_policy_unresolved",
        "prompt_identity_composition_mismatch",
        "identity_version_mismatch",
    }
)
_Q3_ROLE_CLASSIFICATION_ORDER = tuple(
    ROLE_CLASSIFICATIONS[role] for role in ROLE_ORDER
)
_Q3_SINGLE_CLASSIFICATIONS = frozenset(
    {"actual_delivery_drift", "prompt_context_unchanged"}
)


class JudgmentResultContractError(ValueError):
    """A persisted result contract or its runtime coordinate fails closed."""

    def __init__(self, code: str, message: str) -> None:
        if code not in {
            JUDGMENT_RESULT_CONTRACT_MISMATCH,
            JUDGMENT_RESULT_COORDINATE_INVALID,
        }:
            raise ValueError("judgment result contract error code is invalid")
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class ResolvedPersistedResultContract:
    """One exact compiler-persisted result contract at a runtime coordinate."""

    workflow_name: str
    persisted_step_id: str
    contract_kind: str
    declared_shape: str
    contract: Mapping[str, Any]
    contract_sha256: str


def empty_judgment_views() -> dict[str, Any]:
    """Return the stable additive projection for an ineligible or empty run."""

    return {
        "schema_version": JUDGMENT_VIEWS_SCHEMA,
        "judgments": [],
        "matrices": [],
        "disagreements": [],
        "iteration_series": [],
    }


def project_judgment_views(
    state: Mapping[str, Any],
    run_root: str | Path,
    *,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    """Project Q4 judgment views from persisted authorities without mutation."""

    if not isinstance(state, Mapping):
        raise TypeError("persisted run state must be a mapping")
    allocations, ambiguous_publications = (
        _validated_allocations_with_ambiguity(
            state.get("provider_attempt_allocations", {})
        )
    )
    if not allocations:
        return empty_judgment_views()
    candidate_allocations = [
        (scope_key, allocation)
        for scope_key, allocation in allocations.items()
        if isinstance(
            allocation.get(
                "prompt_fragment_identity_schema_version"
            ),
            str,
        )
    ]
    if not candidate_allocations:
        return empty_judgment_views()

    root = Path(run_root)
    workspace = _workspace(
        workspace_root
        if workspace_root is not None
        else _workspace_from_run_root(root)
    )
    root_identity = _root_workflow_identity(state)
    judgments: list[dict[str, Any]] = []
    series: list[dict[str, Any]] = []

    for scope_key, allocation in candidate_allocations:
        scope = ProviderAttemptScope.from_dict(allocation["scope"])
        if scope.key != scope_key:
            raise ValueError("allocator scope identity is invalid")
        attempts = _project_scope_attempts(
            state=state,
            run_root=root,
            scope=scope,
            allocation=allocation,
        )
        evidence_eligible = any(
            _attempt_is_eligible_snapshot(attempt)
            for attempt in attempts
        )
        try:
            reached_state = _reached_state(state, scope)
            result, result_problem = _committed_result(
                reached_state,
                scope,
            )
        except (TypeError, ValueError):
            if evidence_eligible:
                judgments.append(
                    _unavailable_judgment(
                        _coordinate(root_identity, scope),
                        JUDGMENT_RESULT_COORDINATE_INVALID,
                    )
                )
            continue
        locator_present = _result_has_locator(result)
        if not evidence_eligible and not locator_present:
            continue

        coordinate = _coordinate(root_identity, scope)
        if result_problem is not None:
            judgments.append(
                _unavailable_judgment(coordinate, result_problem)
            )
            continue
        if result is None:
            try:
                resolve_persisted_result_contract(
                    workspace_root=workspace,
                    state=state,
                    scope=scope,
                )
            except JudgmentResultContractError:
                continue
            series.append(
                _iteration_series(
                    scope=scope,
                    coordinate=coordinate,
                    attempts=attempts,
                    committed_result_status="not_bound",
                )
            )
            continue

        missing_locator = not locator_present
        if scope_key in ambiguous_publications:
            try:
                resolve_persisted_result_contract(
                    workspace_root=workspace,
                    state=state,
                    scope=scope,
                )
            except JudgmentResultContractError as exc:
                judgments.append(
                    _unavailable_judgment(coordinate, exc.code)
                )
            else:
                judgments.append(
                    _unavailable_judgment(
                        coordinate,
                        JUDGMENT_RESULT_BINDING_AMBIGUOUS,
                    )
                )
            continue
        try:
            resolved = resolve_persisted_result_contract(
                workspace_root=workspace,
                state=state,
                scope=scope,
            )
            bound_attempt = _validated_bound_attempt(
                result=result,
                scope=scope,
                allocation=allocation,
                attempts=attempts,
            )
            value = _rehydrate_result_value(
                result=result,
                resolved=resolved,
                workspace=workspace,
            )
            judgment = _available_judgment(
                coordinate=coordinate,
                resolved=resolved,
                value=value,
                attempt=bound_attempt,
                attempts=attempts,
            )
        except JudgmentResultContractError as exc:
            judgments.append(
                _unavailable_judgment(coordinate, exc.code)
            )
            if missing_locator:
                series.append(
                    _iteration_series(
                        scope=scope,
                        coordinate=coordinate,
                        attempts=attempts,
                        committed_result_status="unknown_pre_q4",
                    )
                )
            continue
        except PromptAttemptResultBindingError as exc:
            judgments.append(
                _unavailable_judgment(coordinate, exc.code)
            )
            if exc.code == JUDGMENT_RESULT_BINDING_MISSING:
                series.append(
                    _iteration_series(
                        scope=scope,
                        coordinate=coordinate,
                        attempts=attempts,
                        committed_result_status="unknown_pre_q4",
                    )
                )
            continue
        except (OutputContractError, TypeError, ValueError):
            judgments.append(
                _unavailable_judgment(
                    coordinate,
                    JUDGMENT_RESULT_VALUE_MISMATCH,
                )
            )
            continue

        judgments.append(judgment)
        series.append(
            _iteration_series(
                scope=scope,
                coordinate=coordinate,
                attempts=attempts,
                committed_result_status="bound",
                bound_ordinal=bound_attempt.ordinal,
            )
        )

    judgments = _normalize_group_ambiguities(judgments)
    judgments.sort(key=_judgment_sort_key)
    matrices, disagreements = _project_group_views(judgments)
    series.sort(
        key=lambda row: (
            *_coordinate_sort_key(row["coordinate"]),
            row["scope_sha256"].encode("utf-8"),
        )
    )
    candidate = {
        "schema_version": JUDGMENT_VIEWS_SCHEMA,
        "judgments": judgments,
        "matrices": matrices,
        "disagreements": disagreements,
        "iteration_series": series,
    }
    return validate_judgment_views_projection(candidate)


def _validated_allocations_with_ambiguity(
    value: Any,
) -> tuple[dict[str, Any], frozenset[str]]:
    """Preserve per-result duplicate-publication refusal before normalization."""

    if not isinstance(value, Mapping):
        raise ValueError("provider attempt allocations must be an object")
    sanitized: dict[Any, Any] = {}
    ambiguous: set[str] = set()
    for scope_key, raw_entry in value.items():
        if not isinstance(raw_entry, Mapping):
            sanitized[scope_key] = raw_entry
            continue
        raw_events = raw_entry.get("events")
        if not isinstance(raw_events, list):
            sanitized[scope_key] = raw_entry
            continue
        seen_publications: set[int] = set()
        events: list[Any] = []
        for event in raw_events:
            ordinal = (
                event.get("ordinal")
                if isinstance(event, Mapping)
                and event.get("event") == "evidence_published"
                else None
            )
            if (
                isinstance(ordinal, int)
                and not isinstance(ordinal, bool)
                and ordinal in seen_publications
            ):
                if isinstance(scope_key, str):
                    ambiguous.add(scope_key)
                continue
            if isinstance(ordinal, int) and not isinstance(ordinal, bool):
                seen_publications.add(ordinal)
            events.append(event)
        if isinstance(scope_key, str) and scope_key in ambiguous:
            entry = dict(raw_entry)
            entry["events"] = events
            sanitized[scope_key] = entry
        else:
            sanitized[scope_key] = raw_entry
    return (
        validate_provider_attempt_allocations(sanitized),
        frozenset(ambiguous),
    )


def _project_scope_attempts(
    *,
    state: Mapping[str, Any],
    run_root: Path,
    scope: ProviderAttemptScope,
    allocation: Mapping[str, Any],
) -> tuple[Any, ...]:
    publications: dict[int, Mapping[str, Any] | None] = {}
    for ordinal in range(1, allocation["last_allocated_ordinal"] + 1):
        matches = [
            event
            for event in allocation["events"]
            if event["event"] == "evidence_published"
            and event["ordinal"] == ordinal
        ]
        publications[ordinal] = matches[0] if len(matches) == 1 else None
    authority = allocation.get(
        "prompt_fragment_identity_schema_version"
    )
    return tuple(
        _load_publication(
            state=state,
            root=run_root,
            scope=scope,
            ordinal=ordinal,
            event=publications[ordinal],
            authority=authority,
            report_schema=PROMPT_CONTEXT_REPORT_SCHEMA,
        )
        for ordinal in range(
            1,
            allocation["last_allocated_ordinal"] + 1,
        )
    )


def _attempt_is_eligible_snapshot(attempt: Any) -> bool:
    identity = attempt.identity
    return (
        attempt.outcome == "v2_snapshot"
        and isinstance(identity, Mapping)
        and identity.get("schema_version")
        == PROMPT_ATTEMPT_IDENTITY_VERSION
    )


def _reached_state(
    state: Mapping[str, Any],
    scope: ProviderAttemptScope,
) -> Mapping[str, Any]:
    current = state
    for frame_id in scope.resume_scope.call_frame_ids:
        frames = current.get("call_frames")
        frame = frames.get(frame_id) if isinstance(frames, Mapping) else None
        nested = frame.get("state") if isinstance(frame, Mapping) else None
        if (
            not isinstance(frame, Mapping)
            or frame.get("call_frame_id") != frame_id
            or not isinstance(nested, Mapping)
        ):
            raise ValueError("judgment result call-frame coordinate is invalid")
        current = nested
    return current


def _committed_result(
    reached_state: Mapping[str, Any],
    scope: ProviderAttemptScope,
) -> tuple[Mapping[str, Any] | None, str | None]:
    steps = reached_state.get("steps")
    if not isinstance(steps, Mapping):
        return None, None
    matches = [
        result
        for result in steps.values()
        if isinstance(result, Mapping)
        and result.get("step_id") == scope.runtime_step_id
    ]
    if len(matches) > 1:
        return None, JUDGMENT_RESULT_COORDINATE_INVALID
    if not matches:
        return None, None
    result = matches[0]
    if result.get("status") != "completed" or result.get("exit_code") != 0:
        return None, None
    if result.get("visit_count") != scope.enclosing_step.visit_count:
        return None, JUDGMENT_RESULT_COORDINATE_INVALID
    return result, None


def _result_has_locator(result: Mapping[str, Any] | None) -> bool:
    if not isinstance(result, Mapping):
        return False
    debug = result.get("debug")
    return (
        isinstance(debug, Mapping)
        and PROMPT_ATTEMPT_RESULT_BINDING_DEBUG_KEY in debug
    )


def _coordinate(
    root_identity: str,
    scope: ProviderAttemptScope,
) -> dict[str, Any]:
    loop = scope.loop_iteration
    return {
        "root_workflow_identity": root_identity,
        "call_frame_path": list(
            scope.resume_scope.call_frame_ids
        ),
        "runtime_step_id": scope.runtime_step_id,
        "enclosing_step_id": scope.enclosing_step.step_id,
        "enclosing_visit": scope.enclosing_step.visit_count,
        "loop": (
            None
            if loop is None
            else {
                "kind": loop.kind,
                "step_id": loop.loop_step_id,
                "iteration": loop.iteration,
            }
        ),
    }


def _validated_bound_attempt(
    *,
    result: Mapping[str, Any],
    scope: ProviderAttemptScope,
    allocation: Mapping[str, Any],
    attempts: tuple[Any, ...],
) -> Any:
    debug = result.get("debug")
    if debug is None:
        _binding_failure(
            JUDGMENT_RESULT_BINDING_MISSING,
            "eligible completed result has no locator",
        )
    if not isinstance(debug, Mapping):
        _binding_failure(
            JUDGMENT_RESULT_BINDING_INVALID,
            "eligible completed result debug is invalid",
        )
    assert isinstance(debug, Mapping)
    if PROMPT_ATTEMPT_RESULT_BINDING_DEBUG_KEY not in debug:
        _binding_failure(
            JUDGMENT_RESULT_BINDING_MISSING,
            "eligible completed result has no locator",
        )
    binding = validate_prompt_attempt_result_binding(
        debug[PROMPT_ATTEMPT_RESULT_BINDING_DEBUG_KEY]
    )
    if binding["scope_sha256"] != scope.key:
        _binding_failure(
            JUDGMENT_RESULT_SCOPE_MISMATCH,
            "result locator scope disagrees with allocator scope",
        )
    ordinal = binding["attempt_ordinal"]
    if ordinal > allocation["last_allocated_ordinal"]:
        _binding_failure(
            JUDGMENT_RESULT_ATTEMPT_MISMATCH,
            "result locator attempt was not allocated",
        )
    publications = [
        event
        for event in allocation["events"]
        if event["event"] == "evidence_published"
    ]
    matches = [
        event
        for event in publications
        if event["ordinal"] == ordinal
    ]
    if len(matches) > 1:
        _binding_failure(
            JUDGMENT_RESULT_BINDING_AMBIGUOUS,
            "multiple publications claim the result locator",
        )
    if not matches:
        _binding_failure(
            (
                JUDGMENT_RESULT_ATTEMPT_MISMATCH
                if publications
                else JUDGMENT_RESULT_BINDING_MISSING
            ),
            "result locator has no exact allocator publication",
        )
    event = matches[0]
    if (
        event["relative_path"] != binding["evidence_relative_path"]
        or event["file_sha256"]
        != binding["evidence_file_sha256"]
        or event["record_kind"] != binding["record_kind"]
    ):
        _binding_failure(
            JUDGMENT_RESULT_EVIDENCE_INVALID,
            "result locator contradicts its allocator publication",
        )
    attempt = attempts[ordinal - 1]
    if not _attempt_is_eligible_snapshot(attempt):
        _binding_failure(
            JUDGMENT_RESULT_EVIDENCE_INVALID,
            "bound evidence is not canonical functional-v2 identity-v1",
        )
    return attempt


def _binding_failure(code: str, message: str) -> None:
    raise PromptAttemptResultBindingError(code, message)


def _rehydrate_result_value(
    *,
    result: Mapping[str, Any],
    resolved: ResolvedPersistedResultContract,
    workspace: Path,
) -> Any:
    artifacts = result.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise ValueError("committed result artifacts are missing")
    contract = resolved.contract
    if resolved.contract_kind == "output_bundle":
        fields = contract["fields"]
        if resolved.declared_shape == "root_value":
            field = fields[0]
            return _validated_artifact_value(
                artifacts,
                field,
                workspace,
            )
        value: dict[str, Any] = {}
        for field in fields:
            _set_json_pointer(
                value,
                field["json_pointer"],
                _validated_artifact_value(
                    artifacts,
                    field,
                    workspace,
                ),
            )
        return value

    discriminant = contract["discriminant"]
    selected = _validated_artifact_value(
        artifacts,
        discriminant,
        workspace,
    )
    variants = contract["variants"]
    if selected not in variants:
        raise ValueError("committed result selected an unknown variant")
    active_fields = (
        *contract["shared_fields"],
        *variants[selected]["fields"],
    )
    active_names = {field["name"] for field in active_fields}
    inactive_names = {
        field["name"]
        for name, payload in variants.items()
        if name != selected
        for field in payload["fields"]
    } - active_names
    if any(name in artifacts for name in inactive_names):
        raise ValueError(
            "committed result retains an inactive variant field"
        )
    payload: dict[str, Any] = {}
    for field in active_fields:
        _set_json_pointer(
            payload,
            field["json_pointer"],
            _validated_artifact_value(
                artifacts,
                field,
                workspace,
            ),
        )
    return {"variant": selected, "value": payload}


def _validated_artifact_value(
    artifacts: Mapping[str, Any],
    field: Mapping[str, Any],
    workspace: Path,
) -> Any:
    name = field["name"]
    if name not in artifacts:
        raise ValueError("committed result artifact is missing")
    raw = artifacts[name]
    parsed = validate_contract_value(
        raw,
        _thaw(field),
        workspace,
    )
    if canonical_json_bytes(raw) != canonical_json_bytes(parsed):
        raise ValueError(
            "committed result artifact requires forbidden coercion"
        )
    return parsed


def _set_json_pointer(
    value: dict[str, Any],
    pointer: str,
    leaf: Any,
) -> None:
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise ValueError("record result pointer is invalid")
    parts = [
        token.replace("~1", "/").replace("~0", "~")
        for token in pointer[1:].split("/")
    ]
    if not parts or any(not part for part in parts):
        raise ValueError("record result pointer is invalid")
    current = value
    for part in parts[:-1]:
        existing = current.get(part)
        if existing is None:
            nested: dict[str, Any] = {}
            current[part] = nested
            current = nested
        elif isinstance(existing, dict):
            current = existing
        else:
            raise ValueError("record result pointers overlap")
    if parts[-1] in current:
        raise ValueError("record result pointers are ambiguous")
    current[parts[-1]] = leaf


def _available_judgment(
    *,
    coordinate: Mapping[str, Any],
    resolved: ResolvedPersistedResultContract,
    value: Any,
    attempt: Any,
    attempts: tuple[Any, ...],
) -> dict[str, Any]:
    identity = _identity_projection(
        attempt.identity,
        report_schema=PROMPT_CONTEXT_REPORT_SCHEMA,
    )
    if (
        not isinstance(identity, Mapping)
        or attempt.record_sha256 is None
    ):
        _binding_failure(
            JUDGMENT_RESULT_EVIDENCE_INVALID,
            "bound evidence identity is unavailable",
        )
    comparison = _result_comparison(resolved, value)
    return {
        "schema_version": JUDGMENT_INSPECTION_SCHEMA,
        "status": "available",
        "coordinate": dict(coordinate),
        "attempt_ordinal": attempt.ordinal,
        "result": {
            "declared_shape": resolved.declared_shape,
            "contract_sha256": resolved.contract_sha256,
            "value_sha256": canonical_sha256(value),
            "value": value,
            "comparison": comparison,
        },
        "provenance": {
            "evidence_record_sha256": attempt.record_sha256,
            "identity_schema_version": (
                PROMPT_ATTEMPT_IDENTITY_VERSION
            ),
            "role_sha256": {
                role: identity["role_sha256"][role]
                for role in ROLE_ORDER
            },
            "final_prompt_sha256": identity[
                "final_prompt_sha256"
            ],
            "composition_sha256": identity[
                "composition_sha256"
            ],
            "comparison": _comparison(attempt, attempts),
        },
    }


def _result_comparison(
    resolved: ResolvedPersistedResultContract,
    value: Any,
) -> dict[str, Any] | None:
    if resolved.declared_shape == "union_value":
        if (
            not isinstance(value, Mapping)
            or not isinstance(value.get("variant"), str)
        ):
            raise ValueError("union result value is invalid")
        return {
            "kind": "union_variant",
            "value": value["variant"],
        }
    if resolved.declared_shape != "root_value":
        return None
    field = resolved.contract["fields"][0]
    if field.get("type") not in {
        "bool",
        "integer",
        "float",
        "string",
        "enum",
    }:
        return None
    return {"kind": "canonical_value", "value": value}


def _unavailable_judgment(
    coordinate: Mapping[str, Any],
    reason: str,
) -> dict[str, Any]:
    if reason not in _UNAVAILABLE_REASONS:
        raise ValueError("judgment unavailable reason is invalid")
    return {
        "schema_version": JUDGMENT_INSPECTION_SCHEMA,
        "status": "unavailable",
        "coordinate": dict(coordinate),
        "reason": reason,
    }


def _iteration_series(
    *,
    scope: ProviderAttemptScope,
    coordinate: Mapping[str, Any],
    attempts: tuple[Any, ...],
    committed_result_status: str,
    bound_ordinal: int | None = None,
) -> dict[str, Any]:
    if committed_result_status not in {
        "bound",
        "not_bound",
        "unknown_pre_q4",
    }:
        raise ValueError("committed result status is invalid")
    rows = []
    for attempt in attempts:
        status = committed_result_status
        if committed_result_status == "bound":
            status = (
                "bound"
                if attempt.ordinal == bound_ordinal
                else "not_bound"
            )
        rows.append(
            {
                "attempt_ordinal": attempt.ordinal,
                "record_status": attempt.record_status,
                "record_sha256": attempt.record_sha256,
                "comparison": _comparison(attempt, attempts),
                "committed_result_status": status,
            }
        )
    return {
        "schema_version": JUDGMENT_ITERATION_SERIES_SCHEMA,
        "scope_sha256": scope.key,
        "coordinate": dict(coordinate),
        "attempts": rows,
    }


def _project_group_views(
    judgments: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    judgments = _normalize_group_ambiguities(judgments)
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for judgment in judgments:
        coordinate = judgment.get("coordinate")
        if not isinstance(coordinate, Mapping):
            raise ValueError(JUDGMENT_VIEW_GROUP_INVALID)
        group_key = (
            coordinate["root_workflow_identity"],
            coordinate["runtime_step_id"],
        )
        grouped.setdefault(group_key, []).append(judgment)

    matrices: list[dict[str, Any]] = []
    disagreements: list[dict[str, Any]] = []
    for root_identity, runtime_step_id in sorted(
        grouped,
        key=lambda key: (
            key[0].encode("utf-8"),
            key[1].encode("utf-8"),
        ),
    ):
        rows = sorted(
            grouped[(root_identity, runtime_step_id)],
            key=_judgment_sort_key,
        )
        members = [_matrix_member(row) for row in rows]
        group = {
            "root_workflow_identity": root_identity,
            "runtime_step_id": runtime_step_id,
        }
        matrices.append(
            {
                "schema_version": JUDGMENT_MATRIX_SCHEMA,
                "group": group,
                "members": members,
            }
        )
        available = [
            member
            for member in members
            if member["status"] != "unavailable"
        ]
        comparable = [
            member
            for member in available
            if member["status"] == "comparable"
        ]
        not_comparable = [
            member
            for member in available
            if member["status"] == "not_comparable"
        ]
        comparison_keys = {
            canonical_json_bytes(member["comparison"])
            for member in comparable
        }
        if len(available) < 2:
            status = "insufficient_members"
        elif not_comparable:
            status = "not_comparable"
        elif len(comparison_keys) == 1:
            status = "agree"
        else:
            status = "disagree"
        disagreements.append(
            {
                "schema_version": JUDGMENT_DISAGREEMENT_SCHEMA,
                "group": dict(group),
                "status": status,
                "available_member_count": len(available),
                "comparable_member_count": len(comparable),
                "not_comparable_member_count": len(
                    not_comparable
                ),
                "unavailable_member_count": (
                    len(members) - len(available)
                ),
                "distinct_comparison_key_count": len(
                    comparison_keys
                ),
            }
        )
    return matrices, disagreements


def _normalize_group_ambiguities(
    judgments: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    by_coordinate: dict[bytes, list[Mapping[str, Any]]] = {}
    for judgment in judgments:
        coordinate = judgment.get("coordinate")
        if not isinstance(coordinate, Mapping):
            raise ValueError(JUDGMENT_VIEW_GROUP_INVALID)
        by_coordinate.setdefault(
            canonical_json_bytes(coordinate),
            [],
        ).append(judgment)
    normalized: list[dict[str, Any]] = []
    for rows in by_coordinate.values():
        if len(rows) == 1:
            normalized.append(dict(rows[0]))
        else:
            normalized.append(
                _unavailable_judgment(
                    rows[0]["coordinate"],
                    JUDGMENT_VIEW_GROUP_INVALID,
                )
            )
    normalized.sort(key=_judgment_sort_key)
    return normalized


def _matrix_member(
    judgment: Mapping[str, Any],
) -> dict[str, Any]:
    if judgment.get("status") == "unavailable":
        return {
            "coordinate": dict(judgment["coordinate"]),
            "status": "unavailable",
            "comparison": None,
            "result_value_sha256": None,
            "evidence_record_sha256": None,
            "reason": judgment["reason"],
        }
    result = judgment["result"]
    provenance = judgment["provenance"]
    comparison = result["comparison"]
    return {
        "coordinate": dict(judgment["coordinate"]),
        "status": (
            "comparable"
            if comparison is not None
            else "not_comparable"
        ),
        "comparison": comparison,
        "result_value_sha256": result["value_sha256"],
        "evidence_record_sha256": provenance[
            "evidence_record_sha256"
        ],
        "reason": None,
    }


def _judgment_sort_key(
    row: Mapping[str, Any],
) -> tuple[Any, ...]:
    coordinate = row["coordinate"]
    attempt = (
        row.get("attempt_ordinal")
        if row.get("status") == "available"
        else None
    )
    digest = (
        row.get("result", {}).get("value_sha256")
        if row.get("status") == "available"
        else None
    )
    return (
        *_coordinate_sort_key(coordinate),
        (0, 0) if attempt is None else (1, attempt),
        (0, b"")
        if digest is None
        else (1, digest.encode("utf-8")),
    )


def _coordinate_sort_key(
    coordinate: Mapping[str, Any],
) -> tuple[Any, ...]:
    loop = coordinate["loop"]
    if loop is None:
        loop_key: tuple[Any, ...] = (0, b"", b"", -1)
    else:
        loop_key = (
            1,
            loop["kind"].encode("utf-8"),
            loop["step_id"].encode("utf-8"),
            loop["iteration"],
        )
    return (
        coordinate["root_workflow_identity"].encode("utf-8"),
        coordinate["runtime_step_id"].encode("utf-8"),
        canonical_json_bytes(coordinate["call_frame_path"]),
        coordinate["enclosing_step_id"].encode("utf-8"),
        coordinate["enclosing_visit"],
        *loop_key,
    )


def _root_workflow_identity(state: Mapping[str, Any]) -> str:
    value = state.get("workflow_checksum")
    if (
        not isinstance(value, str)
        or len(value) != 71
        or not value.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise ValueError("root workflow identity is invalid")
    return value


def _workspace_from_run_root(run_root: Path) -> Path:
    root = run_root.resolve(strict=False)
    if (
        root.parent.name == "runs"
        and root.parent.parent.name == ".orchestrate"
    ):
        return root.parents[2]
    return root


def validate_judgment_views_projection(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the closed Q4 projection and return a canonical deep copy."""

    if (
        not isinstance(value, Mapping)
        or set(value)
        != {
            "schema_version",
            "judgments",
            "matrices",
            "disagreements",
            "iteration_series",
        }
        or value.get("schema_version") != JUDGMENT_VIEWS_SCHEMA
        or any(
            not isinstance(value.get(key), list)
            for key in (
                "judgments",
                "matrices",
                "disagreements",
                "iteration_series",
            )
        )
    ):
        raise ValueError("judgment views projection is invalid")
    _validate_judgment_rows(value["judgments"])
    if list(value["judgments"]) != _normalize_group_ambiguities(
        value["judgments"]
    ):
        raise ValueError(
            "judgment structural member ambiguity is not normalized"
        )
    expected_matrices, expected_disagreements = _project_group_views(
        value["judgments"]
    )
    if (
        value["matrices"] != expected_matrices
        or value["disagreements"] != expected_disagreements
    ):
        raise ValueError("judgment group projections are invalid")
    _validate_series_rows(value["iteration_series"])
    if value["judgments"] != sorted(
        value["judgments"],
        key=_judgment_sort_key,
    ):
        raise ValueError("judgment rows are not canonically ordered")
    if value["iteration_series"] != sorted(
        value["iteration_series"],
        key=lambda row: (
            *_coordinate_sort_key(row["coordinate"]),
            row["scope_sha256"].encode("utf-8"),
        ),
    ):
        raise ValueError("judgment series are not canonically ordered")
    return json.loads(
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )


def _validate_judgment_rows(rows: Sequence[Any]) -> None:
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("judgment row is invalid")
        status = row.get("status")
        if status == "unavailable":
            if (
                set(row)
                != {
                    "schema_version",
                    "status",
                    "coordinate",
                    "reason",
                }
                or row.get("schema_version")
                != JUDGMENT_INSPECTION_SCHEMA
                or row.get("reason") not in _UNAVAILABLE_REASONS
            ):
                raise ValueError("unavailable judgment row is invalid")
        elif status == "available":
            if (
                set(row)
                != {
                    "schema_version",
                    "status",
                    "coordinate",
                    "attempt_ordinal",
                    "result",
                    "provenance",
                }
                or row.get("schema_version")
                != JUDGMENT_INSPECTION_SCHEMA
                or isinstance(row.get("attempt_ordinal"), bool)
                or not isinstance(row.get("attempt_ordinal"), int)
                or row["attempt_ordinal"] < 1
            ):
                raise ValueError("available judgment row is invalid")
            _validate_available_payload(row)
        else:
            raise ValueError("judgment row status is invalid")
        _validate_coordinate(row.get("coordinate"))


def _validate_available_payload(row: Mapping[str, Any]) -> None:
    result = row["result"]
    provenance = row["provenance"]
    if (
        not isinstance(result, Mapping)
        or set(result)
        != {
            "declared_shape",
            "contract_sha256",
            "value_sha256",
            "value",
            "comparison",
        }
        or result["declared_shape"]
        not in {"root_value", "record_value", "union_value"}
        or not _is_sha256(result["contract_sha256"])
        or not _is_sha256(result["value_sha256"])
        or canonical_sha256(result["value"])
        != result["value_sha256"]
    ):
        raise ValueError("available judgment result is invalid")
    comparison = result["comparison"]
    if comparison is not None and (
        not isinstance(comparison, Mapping)
        or set(comparison) != {"kind", "value"}
        or comparison["kind"]
        not in {"canonical_value", "union_variant"}
    ):
        raise ValueError("judgment comparison key is invalid")
    declared_shape = result["declared_shape"]
    result_value = result["value"]
    if declared_shape == "record_value":
        if not isinstance(result_value, Mapping) or comparison is not None:
            raise ValueError(
                "record judgment comparison must be null"
            )
    elif declared_shape == "union_value":
        if (
            not isinstance(result_value, Mapping)
            or set(result_value) != {"variant", "value"}
            or not isinstance(result_value["variant"], str)
            or not result_value["variant"]
            or not isinstance(result_value["value"], Mapping)
            or not isinstance(comparison, Mapping)
            or comparison["kind"] != "union_variant"
            or canonical_json_bytes(comparison["value"])
            != canonical_json_bytes(result_value["variant"])
        ):
            raise ValueError(
                "union judgment comparison is invalid"
            )
    elif comparison is not None and (
        comparison["kind"] != "canonical_value"
        or canonical_json_bytes(comparison["value"])
        != canonical_json_bytes(result_value)
    ):
        raise ValueError("root judgment comparison is invalid")
    if (
        not isinstance(provenance, Mapping)
        or set(provenance)
        != {
            "evidence_record_sha256",
            "identity_schema_version",
            "role_sha256",
            "final_prompt_sha256",
            "composition_sha256",
            "comparison",
        }
        or not _is_sha256(provenance["evidence_record_sha256"])
        or provenance["identity_schema_version"]
        != PROMPT_ATTEMPT_IDENTITY_VERSION
        or not _is_sha256(provenance["final_prompt_sha256"])
        or not _is_sha256(provenance["composition_sha256"])
        or not isinstance(provenance["role_sha256"], Mapping)
        or tuple(provenance["role_sha256"]) != ROLE_ORDER
        or any(
            not _is_sha256(provenance["role_sha256"][role])
            for role in ROLE_ORDER
        )
    ):
        raise ValueError("judgment provenance is invalid")
    _validate_q3_comparison(provenance["comparison"])


def _validate_coordinate(value: Any) -> None:
    if (
        not isinstance(value, Mapping)
        or set(value)
        != {
            "root_workflow_identity",
            "call_frame_path",
            "runtime_step_id",
            "enclosing_step_id",
            "enclosing_visit",
            "loop",
        }
        or not _is_sha256(value["root_workflow_identity"])
        or not isinstance(value["call_frame_path"], list)
        or any(
            not isinstance(frame, str) or not frame
            for frame in value["call_frame_path"]
        )
        or not isinstance(value["runtime_step_id"], str)
        or not value["runtime_step_id"]
        or not isinstance(value["enclosing_step_id"], str)
        or not value["enclosing_step_id"]
        or isinstance(value["enclosing_visit"], bool)
        or not isinstance(value["enclosing_visit"], int)
        or value["enclosing_visit"] < 1
    ):
        raise ValueError("judgment coordinate is invalid")
    loop = value["loop"]
    if loop is not None and (
        not isinstance(loop, Mapping)
        or set(loop) != {"kind", "step_id", "iteration"}
        or loop["kind"] not in {"for_each", "repeat_until"}
        or not isinstance(loop["step_id"], str)
        or not loop["step_id"]
        or isinstance(loop["iteration"], bool)
        or not isinstance(loop["iteration"], int)
        or loop["iteration"] < 0
    ):
        raise ValueError("judgment loop coordinate is invalid")


def _validate_series_rows(rows: Sequence[Any]) -> None:
    for row in rows:
        if (
            not isinstance(row, Mapping)
            or set(row)
            != {
                "schema_version",
                "scope_sha256",
                "coordinate",
                "attempts",
            }
            or row.get("schema_version")
            != JUDGMENT_ITERATION_SERIES_SCHEMA
            or not _is_sha256(row.get("scope_sha256"))
            or not isinstance(row.get("attempts"), list)
        ):
            raise ValueError("judgment iteration series is invalid")
        _validate_coordinate(row["coordinate"])
        previous = 0
        bound = 0
        commit_statuses: list[str] = []
        for attempt in row["attempts"]:
            if (
                not isinstance(attempt, Mapping)
                or set(attempt)
                != {
                    "attempt_ordinal",
                    "record_status",
                    "record_sha256",
                    "comparison",
                    "committed_result_status",
                }
                or isinstance(attempt["attempt_ordinal"], bool)
                or not isinstance(attempt["attempt_ordinal"], int)
                or attempt["attempt_ordinal"] <= previous
                or attempt["record_status"]
                not in {
                    "snapshot",
                    "legacy_snapshot",
                    "failure",
                    "allocation_only",
                    "invalid",
                }
                or attempt["committed_result_status"]
                not in {"bound", "not_bound", "unknown_pre_q4"}
            ):
                raise ValueError("judgment iteration attempt is invalid")
            previous = attempt["attempt_ordinal"]
            bound += attempt["committed_result_status"] == "bound"
            commit_statuses.append(
                attempt["committed_result_status"]
            )
            record_sha = attempt["record_sha256"]
            if (
                attempt["record_status"]
                in {"snapshot", "legacy_snapshot", "failure"}
            ) != _is_sha256(record_sha):
                raise ValueError(
                    "judgment iteration record digest is invalid"
                )
            _validate_q3_comparison(attempt["comparison"])
        status_set = set(commit_statuses)
        if (
            not commit_statuses
            or (
                bound == 1
                and not status_set <= {"bound", "not_bound"}
            )
            or (
                bound == 0
                and status_set
                not in ({"not_bound"}, {"unknown_pre_q4"})
            )
            or bound > 1
        ):
            raise ValueError(
                "judgment iteration commit statuses are invalid"
            )


def _validate_q3_comparison(value: Any) -> None:
    if (
        not isinstance(value, Mapping)
        or set(value)
        != {
            "status",
            "previous_attempt_ordinal",
            "classifications",
            "reason",
        }
        or value["status"] not in {"available", "unavailable"}
        or not isinstance(value["classifications"], list)
    ):
        raise ValueError("Q3 comparison projection is invalid")
    status = value["status"]
    previous = value["previous_attempt_ordinal"]
    classifications = value["classifications"]
    reason = value["reason"]
    if status == "unavailable":
        if (
            previous is not None
            or classifications
            or reason not in _Q3_COMPARISON_UNAVAILABLE_REASONS
        ):
            raise ValueError("Q3 comparison unavailable fields are invalid")
        return
    if (
        isinstance(previous, bool)
        or not isinstance(previous, int)
        or previous < 1
        or reason is not None
        or not classifications
        or any(not isinstance(item, str) for item in classifications)
        or len(classifications) != len(set(classifications))
    ):
        raise ValueError("Q3 comparison available fields are invalid")
    if any(
        item in _Q3_SINGLE_CLASSIFICATIONS for item in classifications
    ):
        if len(classifications) != 1:
            raise ValueError(
                "Q3 comparison special classification is invalid"
            )
        return
    try:
        indices = [
            _Q3_ROLE_CLASSIFICATION_ORDER.index(item)
            for item in classifications
        ]
    except ValueError as exc:
        raise ValueError(
            "Q3 comparison classification is invalid"
        ) from exc
    if indices != sorted(indices):
        raise ValueError(
            "Q3 comparison classifications are not canonically ordered"
        )


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 71
        and value.startswith("sha256:")
        and all(
            character in "0123456789abcdef"
            for character in value[7:]
        )
    )


def resolve_persisted_result_contract(
    *,
    workspace_root: Path,
    state: Mapping[str, Any],
    scope: ProviderAttemptScope,
) -> ResolvedPersistedResultContract:
    """Resolve one provider result contract without source or bundle access."""

    if not isinstance(state, Mapping) or not isinstance(
        scope, ProviderAttemptScope
    ):
        _coordinate_failure("result-contract scope or run state is invalid")
    workspace = _workspace(workspace_root)
    workflow_file = state.get("workflow_file")
    run_id = state.get("run_id")
    if (
        not isinstance(workflow_file, str)
        or not workflow_file
        or not isinstance(run_id, str)
        or not run_id
        or run_id != scope.run_id
    ):
        _coordinate_failure("result-contract root run identity is invalid")
    if _lexical_workspace_path(
        workspace,
        workflow_file,
    ) != _lexical_workspace_path(
        workspace,
        scope.resume_scope.root_workflow_file,
    ):
        _coordinate_failure(
            "result-contract scope root workflow does not match run state"
        )

    try:
        graph = load_persisted_compiled_workflow_surface(
            workspace_root=workspace,
            workflow_path=Path(workflow_file),
            state=state,
        )
    except PersistedCompiledWorkflowError as exc:
        if exc.reason == "coordinate":
            _coordinate_failure(str(exc))
        _contract_failure(str(exc))
    try:
        reached = traverse_persisted_compiled_workflow_call_frames(
            graph,
            state=state,
            call_frame_ids=scope.resume_scope.call_frame_ids,
        )
    except PersistedCompiledWorkflowError as exc:
        _coordinate_failure(str(exc))

    step = _resolve_coordinate_step(reached.node, reached.state, scope)
    contract_kind, declared_shape, contract = _result_contract(step)
    try:
        digest = persisted_surface_sha256(
            canonical_persisted_surface_bytes(
                {contract_kind: _thaw(contract)}
            )
        )
    except (TypeError, ValueError):
        _contract_failure("persisted result contract is not canonical JSON")
    return ResolvedPersistedResultContract(
        workflow_name=reached.node.workflow_name,
        persisted_step_id=step.step_id,
        contract_kind=contract_kind,
        declared_shape=declared_shape,
        contract=contract,
        contract_sha256=digest,
    )


def _resolve_coordinate_step(
    node: PersistedWorkflowSurfaceNode,
    reached_state: Mapping[str, Any],
    scope: ProviderAttemptScope,
) -> PersistedSurfaceStep:
    all_steps = tuple(_walk_node_steps(node))
    loop = scope.loop_iteration
    if loop is None:
        if scope.enclosing_step.step_id != scope.runtime_step_id:
            _coordinate_failure(
                "non-loop result coordinate has contradictory step identities"
            )
        matches = tuple(
            step
            for step in all_steps
            if step.step_id == scope.runtime_step_id
        )
        if len(matches) != 1:
            _coordinate_failure(
                "result coordinate does not select one persisted step"
            )
        selected = matches[0]
    else:
        if scope.enclosing_step.step_id != loop.loop_step_id:
            _coordinate_failure(
                "loop result coordinate has contradictory owner identities"
            )
        owners = tuple(
            step
            for step in all_steps
            if step.step_id == loop.loop_step_id
            and _step_loop_kind(step) == loop.kind
        )
        if len(owners) != 1:
            _coordinate_failure(
                "loop result coordinate does not select one persisted owner"
            )
        owner = owners[0]
        if scope.enclosing_step.step_name != owner.name:
            _coordinate_failure(
                "loop result coordinate has contradictory owner name"
            )
        descendants = tuple(_walk_loop_steps(owner, loop.kind))
        matches = tuple(
            step
            for step in descendants
            if _runtime_iteration_step_id(
                loop.loop_step_id,
                loop.iteration,
                step.step_id,
            )
            == scope.runtime_step_id
        )
        if len(matches) != 1:
            _coordinate_failure(
                "loop result coordinate does not select one persisted step"
            )
        selected = matches[0]

    if selected.kind is not SurfaceStepKind.PROVIDER:
        _contract_failure(
            "persisted result coordinate does not select a provider contract"
        )
    if loop is None and scope.enclosing_step.step_name != selected.name:
        _coordinate_failure(
            "result coordinate has contradictory persisted step name"
        )
    visits = reached_state.get("step_visits")
    observed_visit = (
        visits.get(scope.enclosing_step.step_name)
        if isinstance(visits, Mapping)
        else None
    )
    if observed_visit != scope.enclosing_step.visit_count:
        _coordinate_failure(
            "result coordinate visit does not match persisted run state"
        )
    return selected


def _walk_node_steps(
    node: PersistedWorkflowSurfaceNode,
) -> Sequence[PersistedSurfaceStep]:
    return tuple(
        step
        for root in (*node.steps, *node.finalization_steps)
        for step in _walk_step(root)
    )


def _walk_step(step: PersistedSurfaceStep) -> Sequence[PersistedSurfaceStep]:
    nested: list[PersistedSurfaceStep] = [
        *step.for_each_steps,
        *step.then_steps,
        *step.else_steps,
    ]
    for case_steps in step.match_cases.values():
        nested.extend(case_steps)
    if step.repeat_until is not None:
        nested.extend(step.repeat_until.steps)
    return (
        step,
        *(
            descendant
            for child in nested
            for descendant in _walk_step(child)
        ),
    )


def _walk_loop_steps(
    owner: PersistedSurfaceStep,
    kind: str,
) -> Sequence[PersistedSurfaceStep]:
    if kind == "for_each":
        roots = owner.for_each_steps
    elif kind == "repeat_until" and owner.repeat_until is not None:
        roots = owner.repeat_until.steps
    else:
        _coordinate_failure("persisted loop owner kind is contradictory")
    return tuple(
        descendant
        for root in roots
        for descendant in _walk_step(root)
    )


def _step_loop_kind(step: PersistedSurfaceStep) -> str | None:
    has_for_each = bool(step.for_each_steps)
    has_repeat = step.repeat_until is not None
    if has_for_each == has_repeat:
        return None
    return "for_each" if has_for_each else "repeat_until"


def _runtime_iteration_step_id(
    loop_step_id: str,
    iteration: int,
    persisted_step_id: str,
) -> str:
    prefix = f"{loop_step_id}."
    if not persisted_step_id.startswith(prefix):
        _coordinate_failure(
            "persisted loop descendant is outside its owner identity"
        )
    suffix = persisted_step_id[len(prefix) :]
    if not suffix:
        _coordinate_failure("persisted loop descendant identity is invalid")
    return f"{loop_step_id}#{iteration}.{suffix}"


def _result_contract(
    step: PersistedSurfaceStep,
) -> tuple[str, str, Mapping[str, Any]]:
    output_bundle = step.common.output_bundle
    variant_output = step.common.variant_output
    output_present = output_bundle is not None
    variant_present = variant_output is not None
    if output_present == variant_present:
        _contract_failure(
            "persisted provider step must contain exactly one result contract"
        )
    if variant_present:
        if not isinstance(variant_output, Mapping):
            _contract_failure("persisted variant result contract is malformed")
        _validate_variant_contract(variant_output)
        return "variant_output", "union_value", variant_output
    if not isinstance(output_bundle, Mapping):
        _contract_failure("persisted output result contract is malformed")
    declared_shape = _validate_output_contract(output_bundle)
    return "output_bundle", declared_shape, output_bundle


def _validate_output_contract(contract: Mapping[str, Any]) -> str:
    path = contract.get("path")
    fields = contract.get("fields")
    if (
        not isinstance(path, str)
        or not path
        or not isinstance(fields, tuple)
        or not fields
    ):
        _contract_failure("persisted output result contract is malformed")
    names: set[str] = set()
    pointers: set[str] = set()
    root_fields = 0
    for field in fields:
        name, pointer = _validated_contract_field(field)
        if name in names or pointer in pointers:
            _contract_failure(
                "persisted output result fields are ambiguous"
            )
        names.add(name)
        pointers.add(pointer)
        root_fields += pointer == ""
    if root_fields:
        if (
            len(fields) != 1
            or fields[0].get("name") != "__result__"
            or fields[0].get("json_pointer") != ""
        ):
            _contract_failure(
                "persisted output result contract mixes root and record fields"
            )
        return "root_value"
    return "record_value"


def _validate_variant_contract(contract: Mapping[str, Any]) -> None:
    path = contract.get("path")
    discriminant = contract.get("discriminant")
    shared_fields = contract.get("shared_fields")
    variants = contract.get("variants")
    if (
        not isinstance(path, str)
        or not path
        or not isinstance(discriminant, Mapping)
        or not isinstance(shared_fields, tuple)
        or not isinstance(variants, Mapping)
        or not variants
        or not all(
            isinstance(name, str)
            and name
            and isinstance(payload, Mapping)
            for name, payload in variants.items()
        )
    ):
        _contract_failure("persisted variant result contract is malformed")
    discriminant_name = discriminant.get("name")
    discriminant_pointer = discriminant.get("json_pointer")
    allowed = discriminant.get("allowed")
    if (
        not isinstance(discriminant_name, str)
        or not discriminant_name
        or not isinstance(discriminant_pointer, str)
        or not discriminant_pointer.startswith("/")
        or discriminant.get("type") != "enum"
        or not isinstance(allowed, tuple)
        or not allowed
        or any(not isinstance(item, str) or not item for item in allowed)
        or len(set(allowed)) != len(allowed)
        or tuple(variants) != allowed
    ):
        _contract_failure(
            "persisted variant discriminant contract is malformed"
        )
    names = {discriminant_name}
    pointers = {discriminant_pointer}
    for field in shared_fields:
        name, pointer = _validated_contract_field(field)
        if name in names or pointer in pointers:
            _contract_failure(
                "persisted variant result fields are ambiguous"
            )
        names.add(name)
        pointers.add(pointer)
    for payload in variants.values():
        fields = payload.get("fields")
        if not isinstance(fields, tuple):
            _contract_failure(
                "persisted variant result fields are malformed"
            )
        variant_names = set(names)
        variant_pointers = set(pointers)
        for field in fields:
            name, pointer = _validated_contract_field(field)
            if name in variant_names or pointer in variant_pointers:
                _contract_failure(
                    "persisted variant result fields are ambiguous"
                )
            variant_names.add(name)
            variant_pointers.add(pointer)


def _validated_contract_field(
    field: Any,
) -> tuple[str, str]:
    if not isinstance(field, Mapping):
        _contract_failure("persisted result field is malformed")
    name = field.get("name")
    pointer = field.get("json_pointer")
    value_type = field.get("type")
    if (
        not isinstance(name, str)
        or not name
        or not isinstance(pointer, str)
        or (pointer and not pointer.startswith("/"))
        or not isinstance(value_type, str)
        or not value_type
    ):
        _contract_failure("persisted result field is malformed")
    return name, pointer


def _workspace(path: Path) -> Path:
    try:
        workspace = Path(path).resolve(strict=True)
    except (OSError, RuntimeError, TypeError):
        _coordinate_failure("judgment workspace root is missing or invalid")
    if not workspace.is_dir():
        _coordinate_failure("judgment workspace root is not a directory")
    return workspace


def _lexical_workspace_path(workspace: Path, raw: str) -> Path:
    candidate = Path(raw)
    candidate = candidate if candidate.is_absolute() else workspace / candidate
    try:
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(workspace)
    except (OSError, RuntimeError, ValueError):
        _coordinate_failure(
            "result-contract workflow path is outside the workspace"
        )
    return resolved


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _contract_failure(message: str) -> None:
    raise JudgmentResultContractError(
        JUDGMENT_RESULT_CONTRACT_MISMATCH,
        message,
    )


def _coordinate_failure(message: str) -> None:
    raise JudgmentResultContractError(
        JUDGMENT_RESULT_COORDINATE_INVALID,
        message,
    )
