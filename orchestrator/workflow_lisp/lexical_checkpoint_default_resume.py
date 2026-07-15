"""R6 default-resume classification, reporting, and cleanup helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from orchestrator.workflow.loaded_bundle import workflow_context, workflow_provenance

from .lexical_checkpoints import canonical_json_dumps


DEFAULT_RESUME_POLICY_SCHEMA_VERSION = "workflow_lisp_checkpoint_default_resume.v1"
DEFAULT_RESUME_REPORT_SCHEMA_VERSION = "workflow_lisp_checkpoint_default_resume_report.v1"

MODE_LEXICAL_CHECKPOINT_DEFAULT = "LEXICAL_CHECKPOINT_DEFAULT"
MODE_HISTORICAL_STEP_GRANULAR_COMPATIBILITY = (
    "HISTORICAL_STEP_GRANULAR_COMPATIBILITY"
)
MODE_INELIGIBLE_STEP_GRANULAR = "INELIGIBLE_STEP_GRANULAR"
MODE_FAIL_CLOSED = "FAIL_CLOSED"
DEFAULT_RESUME_MODES = frozenset(
    {
        MODE_LEXICAL_CHECKPOINT_DEFAULT,
        MODE_HISTORICAL_STEP_GRANULAR_COMPATIBILITY,
        MODE_INELIGIBLE_STEP_GRANULAR,
        MODE_FAIL_CLOSED,
    }
)

CLEANUP_ACTION_REMOVE_COMPATIBILITY_ALLOWLIST = "REMOVE_COMPATIBILITY_ALLOWLIST"
CLEANUP_ACTION_DELETE_DEAD_COMPATIBILITY_WRAPPER = "DELETE_DEAD_COMPATIBILITY_WRAPPER"
CLEANUP_ACTION_KEEP_HISTORICAL_ONLY = "KEEP_HISTORICAL_ONLY"
CLEANUP_ACTION_BLOCKED = "BLOCKED"

_POINTS_SCHEMA_VERSION = "workflow_lisp_lexical_checkpoint_points.v1"
_SHADOW_REPORT_SCHEMA_VERSION = "workflow_lisp_lexical_checkpoint_shadow_report.v1"
_RETIREMENT_REPORT_SCHEMA_VERSION = "workflow_lisp_resume_plumbing_retirement_report.v1"
_ALLOWED_CLEANUP_DECISIONS = frozenset({"RETIRED", "HIDDEN_PRIVATE", "KEPT_COMPATIBILITY"})
_ERROR_DIAGNOSTICS = frozenset(
    {
        "lexical_default_resume_schema_invalid",
        "lexical_default_resume_checkpoint_points_missing",
        "lexical_default_resume_restore_metadata_missing",
        "lexical_default_resume_effect_policy_missing",
        "lexical_default_resume_transition_evidence_missing",
        "lexical_default_resume_retirement_evidence_missing",
        "lexical_default_resume_not_restorable",
        "lexical_default_resume_invalid_checkpoint",
        "lexical_default_resume_step_granular_bypass",
        "lexical_default_resume_command_glue_invalid",
        "lexical_default_resume_checkpoint_used_as_authority",
        "lexical_default_resume_prior_boundary_missing",
        "lexical_default_resume_prior_boundary_unordered",
        "lexical_default_resume_prior_boundary_duplicate_order",
        "lexical_default_resume_prior_boundary_duplicate",
        "lexical_default_resume_prior_boundary_ambiguous",
        "lexical_default_resume_prior_boundary_not_restorable",
    }
)

AUTHORITY_FORBIDDEN_SOURCES = {
    "checkpoint_record": "lexical_default_resume_checkpoint_used_as_authority",
    "checkpoint_path": "lexical_default_resume_checkpoint_used_as_authority",
    "report_path": "lexical_default_resume_checkpoint_used_as_authority",
}


def _nearest_prior_effect_boundary(
    *,
    runtime_plan: Any,
    restart_node_id: str,
) -> tuple[Any | None, str | None]:
    ordered_node_ids = tuple(getattr(runtime_plan, "ordered_node_ids", ()) or ())
    if len(set(ordered_node_ids)) != len(ordered_node_ids):
        return None, "lexical_default_resume_prior_boundary_duplicate_order"
    if ordered_node_ids.count(restart_node_id) != 1:
        return None, "lexical_default_resume_prior_boundary_unordered"

    order = {node_id: index for index, node_id in enumerate(ordered_node_ids)}
    restart_index = order[restart_node_id]
    checkpoint_points = tuple(
        getattr(runtime_plan, "lexical_checkpoint_points", ()) or ()
    )
    effect_points = tuple(
        point
        for point in checkpoint_points
        if getattr(point, "point_kind", None) == "effect_boundary"
    )
    if any(getattr(point, "node_id", None) not in order for point in effect_points):
        return None, "lexical_default_resume_prior_boundary_unordered"

    prior_points = tuple(
        point
        for point in effect_points
        if order[str(getattr(point, "node_id"))] < restart_index
    )
    if not prior_points:
        return None, "lexical_default_resume_prior_boundary_missing"
    nearest_index = max(order[str(getattr(point, "node_id"))] for point in prior_points)
    nearest_points = tuple(
        point
        for point in prior_points
        if order[str(getattr(point, "node_id"))] == nearest_index
    )
    checkpoint_ids = tuple(getattr(point, "checkpoint_id", None) for point in nearest_points)
    if any(not isinstance(checkpoint_id, str) or not checkpoint_id for checkpoint_id in checkpoint_ids):
        return None, "lexical_default_resume_prior_boundary_unordered"
    if len(set(checkpoint_ids)) != len(checkpoint_ids):
        return None, "lexical_default_resume_prior_boundary_duplicate"
    if len(nearest_points) != 1:
        return None, "lexical_default_resume_prior_boundary_ambiguous"
    if (
        sum(
            getattr(point, "checkpoint_id", None) == checkpoint_ids[0]
            for point in checkpoint_points
        )
        != 1
    ):
        return None, "lexical_default_resume_prior_boundary_duplicate"
    return nearest_points[0], None


def serialize_default_resume_payload(payload: Mapping[str, Any]) -> str:
    return canonical_json_dumps(_json_data(payload))


def build_default_resume_policy(
    *,
    workflow_name: str,
    lowering_schema_version: int | None,
    is_workflow_lisp: bool,
    runtime_plan: Any | None = None,
    historical_compatibility: bool = False,
) -> dict[str, Any]:
    points = tuple(getattr(runtime_plan, "lexical_checkpoint_points", ()) or ())
    route_kind = "non_workflow_lisp"
    diagnostics: list[str] = []
    if is_workflow_lisp and lowering_schema_version == 2:
        route_kind = "wcc_schema_2"
    elif is_workflow_lisp and lowering_schema_version == 1:
        route_kind = "legacy_schema_1"
    elif is_workflow_lisp:
        route_kind = "workflow_lisp_schema_invalid"

    if not is_workflow_lisp:
        default_mode = MODE_INELIGIBLE_STEP_GRANULAR
        diagnostics.append("lexical_default_resume_route_ineligible")
    elif lowering_schema_version not in {1, 2}:
        default_mode = MODE_FAIL_CLOSED
        diagnostics.append("lexical_default_resume_schema_invalid")
    elif historical_compatibility or lowering_schema_version == 1:
        default_mode = MODE_HISTORICAL_STEP_GRANULAR_COMPATIBILITY
        diagnostics.append("lexical_default_resume_historical_compatibility")
    elif lowering_schema_version == 2 and points:
        default_mode = MODE_LEXICAL_CHECKPOINT_DEFAULT
    elif lowering_schema_version == 2:
        default_mode = MODE_FAIL_CLOSED
        diagnostics.append("lexical_default_resume_checkpoint_points_missing")
    else:
        default_mode = MODE_INELIGIBLE_STEP_GRANULAR
        diagnostics.append("lexical_default_resume_route_ineligible")

    return {
        "schema_version": DEFAULT_RESUME_POLICY_SCHEMA_VERSION,
        "workflow_name": workflow_name,
        "route": {
            "lowering_schema_version": lowering_schema_version,
            "route_kind": route_kind,
            "historical_compatibility": historical_compatibility or lowering_schema_version == 1,
        },
        "required_evidence": {
            "checkpoint_points": _POINTS_SCHEMA_VERSION,
            "restore_payloads": "workflow_lisp_lexical_restore_payload.v1",
            "effect_policies": "workflow_lisp_effect_resume_policy.v1",
            "transition_evidence": "workflow_lisp_transition_checkpoint_evidence.v1",
            "retirement_report": _RETIREMENT_REPORT_SCHEMA_VERSION,
        },
        "default_mode": default_mode,
        "diagnostics": diagnostics,
    }


def determine_runtime_default_resume_decision(
    *,
    state: Mapping[str, Any],
    runtime_plan: Any,
    restart_node_id: str | None,
    state_manager: Any | None = None,
    restore_selector: Any | None = None,
    loaded_workflow: Any | None = None,
    executable_workflow: Any | None = None,
    is_workflow_lisp: bool | None = None,
) -> dict[str, Any]:
    workflow_name = str(getattr(runtime_plan, "workflow_name", "") or "")
    if is_workflow_lisp is None:
        is_workflow_lisp = _is_workflow_lisp_route(loaded_workflow, state=state)
    lowering_schema_version = _lowering_schema_version(loaded_workflow, state=state)
    historical_compatibility = _historical_compatibility(loaded_workflow, state=state)
    policy = build_default_resume_policy(
        workflow_name=workflow_name,
        lowering_schema_version=lowering_schema_version,
        is_workflow_lisp=bool(is_workflow_lisp),
        runtime_plan=runtime_plan,
        historical_compatibility=historical_compatibility,
    )
    points = tuple(getattr(runtime_plan, "lexical_checkpoint_points", ()) or ())
    payload = {
        "schema_version": DEFAULT_RESUME_POLICY_SCHEMA_VERSION,
        "workflow_name": workflow_name,
        "route": dict(policy["route"]),
        "required_evidence": dict(policy["required_evidence"]),
        "mode": policy["default_mode"],
        "restart_node_id": restart_node_id,
        "restore_decision": None,
        "restore_candidate": None,
        "checkpoint_id": None,
        "record_id": None,
        "source_map_origin_key": None,
        "selection_reason": None,
        "compatibility_reason": None,
        "diagnostics": list(policy["diagnostics"]),
    }

    if payload["mode"] == MODE_INELIGIBLE_STEP_GRANULAR:
        payload["compatibility_reason"] = "route_ineligible"
        return payload
    if payload["mode"] == MODE_HISTORICAL_STEP_GRANULAR_COMPATIBILITY:
        payload["compatibility_reason"] = "historical_compatibility"
        return payload
    if payload["mode"] == MODE_FAIL_CLOSED and not points:
        return payload
    if restart_node_id is None:
        payload["compatibility_reason"] = "no_restart_node"
        payload["mode"] = MODE_LEXICAL_CHECKPOINT_DEFAULT
        return payload

    if restore_selector is None:
        from orchestrator.workflow_lisp.lexical_checkpoint_restore import (
            select_restore_candidate,
        )

        restore_selector = select_restore_candidate

    restore_decision = restore_selector(
        state_manager=state_manager,
        runtime_plan=runtime_plan,
        state=state,
        restart_node_id=restart_node_id,
        executable_workflow=executable_workflow,
        loaded_workflow=loaded_workflow,
    )
    payload.update(
        {
            "restore_decision": getattr(restore_decision, "kind", None),
            "restore_candidate": {
                "kind": getattr(restore_decision, "kind", None),
                "checkpoint_id": getattr(restore_decision, "checkpoint_id", None),
                "record_id": getattr(restore_decision, "record_id", None),
                "source_map_origin_key": getattr(
                    restore_decision, "source_map_origin_key", None
                ),
                "restore_payload": _json_data(
                    getattr(restore_decision, "restore_payload", None)
                ),
                "policy_decision": getattr(restore_decision, "policy_decision", None),
                "diagnostics": list(getattr(restore_decision, "diagnostics", ()) or ()),
                "transition_resume": _json_data(
                    getattr(restore_decision, "transition_resume", None)
                ),
                "selection_observation": getattr(
                    restore_decision, "selection_observation", None
                ),
                "selection_reason": "node_local",
            },
            "checkpoint_id": getattr(restore_decision, "checkpoint_id", None),
            "record_id": getattr(restore_decision, "record_id", None),
            "source_map_origin_key": getattr(
                restore_decision, "source_map_origin_key", None
            ),
            "selection_reason": "node_local",
        }
    )
    decision_diagnostics = list(getattr(restore_decision, "diagnostics", ()) or ())
    relevant_points = [
        point
        for point in points
        if getattr(point, "node_id", None) == restart_node_id
    ]
    if payload["restore_decision"] == "RESTORED":
        payload["mode"] = MODE_LEXICAL_CHECKPOINT_DEFAULT
        payload["diagnostics"].extend(decision_diagnostics)
        return payload
    if payload["restore_decision"] == "INVALID":
        payload["mode"] = MODE_FAIL_CLOSED
        payload["diagnostics"] = [
            "lexical_default_resume_invalid_checkpoint",
            *decision_diagnostics,
        ]
        return payload
    if payload["restore_decision"] == "NOT_RESTORABLE":
        if relevant_points:
            if (
                getattr(restore_decision, "selection_observation", None)
                == "record_absent"
            ):
                prior_point, prior_diagnostic = _nearest_prior_effect_boundary(
                    runtime_plan=runtime_plan,
                    restart_node_id=restart_node_id,
                )
                if prior_diagnostic is not None:
                    payload["mode"] = MODE_FAIL_CLOSED
                    payload["diagnostics"] = [prior_diagnostic]
                    return payload
                prior_decision = restore_selector(
                    state_manager=state_manager,
                    runtime_plan=runtime_plan,
                    state=state,
                    checkpoint_id=getattr(prior_point, "checkpoint_id"),
                    executable_workflow=executable_workflow,
                    loaded_workflow=loaded_workflow,
                )
                prior_diagnostics = list(
                    getattr(prior_decision, "diagnostics", ()) or ()
                )
                payload.update(
                    {
                        "restore_decision": getattr(prior_decision, "kind", None),
                        "restore_candidate": {
                            "kind": getattr(prior_decision, "kind", None),
                            "checkpoint_id": getattr(
                                prior_decision, "checkpoint_id", None
                            ),
                            "record_id": getattr(prior_decision, "record_id", None),
                            "source_map_origin_key": getattr(
                                prior_decision, "source_map_origin_key", None
                            ),
                            "restore_payload": _json_data(
                                getattr(prior_decision, "restore_payload", None)
                            ),
                            "policy_decision": getattr(
                                prior_decision, "policy_decision", None
                            ),
                            "diagnostics": prior_diagnostics,
                            "transition_resume": _json_data(
                                getattr(prior_decision, "transition_resume", None)
                            ),
                            "selection_observation": getattr(
                                prior_decision, "selection_observation", None
                            ),
                            "selection_reason": "validated_prior_boundary",
                        },
                        "checkpoint_id": getattr(
                            prior_decision, "checkpoint_id", None
                        ),
                        "record_id": getattr(prior_decision, "record_id", None),
                        "source_map_origin_key": getattr(
                            prior_decision, "source_map_origin_key", None
                        ),
                        "selection_reason": "validated_prior_boundary",
                    }
                )
                if payload["restore_decision"] == "RESTORED":
                    payload["mode"] = MODE_LEXICAL_CHECKPOINT_DEFAULT
                    payload["diagnostics"].extend(prior_diagnostics)
                    return payload
                payload["mode"] = MODE_FAIL_CLOSED
                if payload["restore_decision"] == "INVALID":
                    payload["diagnostics"] = [
                        "lexical_default_resume_invalid_checkpoint",
                        *prior_diagnostics,
                    ]
                else:
                    payload["diagnostics"] = [
                        "lexical_default_resume_prior_boundary_not_restorable",
                        *prior_diagnostics,
                    ]
                return payload
            payload["mode"] = MODE_FAIL_CLOSED
            payload["diagnostics"] = [
                "lexical_default_resume_not_restorable",
                *decision_diagnostics,
            ]
            return payload
        payload["mode"] = MODE_LEXICAL_CHECKPOINT_DEFAULT
        payload["compatibility_reason"] = "no_relevant_checkpoint"
        payload["diagnostics"].extend(decision_diagnostics)
        return payload

    payload["mode"] = MODE_FAIL_CLOSED
    payload["diagnostics"] = [
        "lexical_default_resume_step_granular_bypass",
        *decision_diagnostics,
    ]
    return payload


def build_runtime_default_resume_report(
    *,
    workflow_name: str,
    decision: Mapping[str, Any],
    workflow_family: str | None = None,
    call_frame_bound_inputs: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    route = {
        **_mapping(decision.get("route")),
        "default_mode": decision.get("mode"),
    }
    diagnostic_entries = _diagnostic_entries(
        decision.get("diagnostics", ()),
        row_id=workflow_name,
    )
    mode_entry = _mode_entry(
        workflow_name=workflow_name,
        route=route,
        diagnostics=diagnostic_entries,
        restore_decision=decision.get("restore_decision"),
        checkpoint_id=decision.get("checkpoint_id"),
        record_id=decision.get("record_id"),
        restart_node_id=decision.get("restart_node_id"),
        source_map_origin_key=decision.get("source_map_origin_key"),
        compatibility_reason=decision.get("compatibility_reason"),
    )
    checked_workflow = {
        "workflow_name": workflow_name,
        "status": "fail" if _report_status(route["default_mode"], diagnostic_entries) == "fail" else "pass",
        "route": route,
        "decision": {
            "restore_decision": decision.get("restore_decision"),
            "checkpoint_id": decision.get("checkpoint_id"),
            "record_id": decision.get("record_id"),
            "restart_node_id": decision.get("restart_node_id"),
            "source_map_origin_key": decision.get("source_map_origin_key"),
            "selection_reason": decision.get("selection_reason"),
            "compatibility_reason": decision.get("compatibility_reason"),
        },
        "evidence": {
            "required_evidence": _json_data(_mapping(decision.get("required_evidence"))),
        },
        "diagnostics": diagnostic_entries,
    }
    report = _compose_report(
        workflow_family=workflow_family or workflow_name,
        workflow_name=workflow_name,
        route=route,
        evidence=checked_workflow["evidence"],
        checked_workflows=[checked_workflow],
        default_modes=[mode_entry],
        cleanup_candidates=[],
        diagnostics=diagnostic_entries,
    )
    report.update(
        {
            "mode": decision.get("mode"),
            "restore_decision": decision.get("restore_decision"),
            "checkpoint_id": decision.get("checkpoint_id"),
            "record_id": decision.get("record_id"),
            "restart_node_id": decision.get("restart_node_id"),
            "source_map_origin_key": decision.get("source_map_origin_key"),
            "selection_reason": decision.get("selection_reason"),
            "compatibility_reason": decision.get("compatibility_reason"),
            "call_frame_bound_inputs": [
                dict(entry) for entry in (call_frame_bound_inputs or [])
            ],
        }
    )
    return report


def validate_default_resume_cleanup_candidate(
    row: Mapping[str, Any],
    *,
    default_mode: str | None = None,
) -> dict[str, Any]:
    authority_source = row.get("authority_source")
    if authority_source in AUTHORITY_FORBIDDEN_SOURCES:
        raise ValueError(AUTHORITY_FORBIDDEN_SOURCES[str(authority_source)])

    row_id = str(row.get("row_id", ""))
    decision = str(row.get("decision", row.get("r5_decision", "")))
    track_owner = str(row.get("track_owner", _infer_track_owner(row_id)))
    plumbing_class = str(row.get("plumbing_class", "") or "")
    boundary_authority_class = str(row.get("boundary_authority_class", "") or "")
    semantic_owner = str(row.get("semantic_owner", "") or "")
    current_consumer = _current_consumer(row)
    payload = {
        "row_id": row_id,
        "r5_decision": decision,
        "r6_default_mode": default_mode or row.get("r6_default_mode"),
        "workflow_surface": row.get("workflow_surface"),
        "current_consumer": current_consumer,
        "cleanup_action": CLEANUP_ACTION_KEEP_HISTORICAL_ONLY,
        "diagnostics": [],
        "evidence": [
            "resume_plumbing_retirement_report.json",
            "lexical_checkpoint_default_resume_report.json",
            "boundary_authority_report.json",
        ],
    }
    if track_owner != "R" or (plumbing_class and plumbing_class != "resume_only"):
        payload["cleanup_action"] = CLEANUP_ACTION_BLOCKED
        payload["diagnostics"] = [
            _diagnostic("lexical_default_resume_cleanup_wrong_track", row_id=row_id)
        ]
        return payload
    if _has_command_glue(row):
        payload["cleanup_action"] = CLEANUP_ACTION_BLOCKED
        payload["diagnostics"] = [
            _diagnostic("lexical_default_resume_command_glue_invalid", row_id=row_id)
        ]
        return payload
    if boundary_authority_class == "public_artifact":
        payload["cleanup_action"] = CLEANUP_ACTION_KEEP_HISTORICAL_ONLY
        return payload
    if semantic_owner == "domain_resource":
        payload["cleanup_action"] = CLEANUP_ACTION_BLOCKED
        return payload
    if current_consumer:
        payload["cleanup_action"] = CLEANUP_ACTION_KEEP_HISTORICAL_ONLY
        payload["diagnostics"] = [
            _diagnostic("lexical_default_resume_cleanup_consumer_exists", row_id=row_id)
        ]
        return payload
    if decision == "RETIRED":
        payload["cleanup_action"] = CLEANUP_ACTION_REMOVE_COMPATIBILITY_ALLOWLIST
        return payload
    if decision == "HIDDEN_PRIVATE":
        payload["cleanup_action"] = CLEANUP_ACTION_DELETE_DEAD_COMPATIBILITY_WRAPPER
        return payload
    payload["cleanup_action"] = CLEANUP_ACTION_KEEP_HISTORICAL_ONLY
    return payload


def build_default_resume_report(
    *,
    workflow_family: str,
    workflow_name: str,
    lowering_schema_version: int | None,
    checkpoint_points_payload: Mapping[str, Any] | None,
    checkpoint_shadow_report_payload: Mapping[str, Any] | None,
    resume_plumbing_retirement_report_payload: Mapping[str, Any] | None,
    historical_compatibility: bool = False,
) -> dict[str, Any]:
    points_payload = dict(checkpoint_points_payload or {})
    points = [
        point
        for point in points_payload.get("points", [])
        if isinstance(point, Mapping)
    ]
    policy = build_default_resume_policy(
        workflow_name=workflow_name,
        lowering_schema_version=lowering_schema_version,
        is_workflow_lisp=True,
        runtime_plan=_runtime_plan_from_points(workflow_name, points),
        historical_compatibility=historical_compatibility,
    )
    route = {
        **policy["route"],
        "default_mode": policy["default_mode"],
    }
    diagnostics = _diagnostic_entries(policy["diagnostics"], row_id=workflow_name)
    evidence = _build_evidence_summary(
        points=points,
        checkpoint_points_payload=points_payload,
        checkpoint_shadow_report_payload=checkpoint_shadow_report_payload,
        resume_plumbing_retirement_report_payload=resume_plumbing_retirement_report_payload,
    )
    diagnostics.extend(
        _default_resume_report_diagnostics(
            workflow_name=workflow_name,
            route=route,
            points_payload=points_payload,
            points=points,
            checkpoint_shadow_report_payload=checkpoint_shadow_report_payload,
            resume_plumbing_retirement_report_payload=resume_plumbing_retirement_report_payload,
        )
    )
    cleanup_candidates, cleanup_diagnostics = _build_cleanup_candidates(
        workflow_name=workflow_name,
        default_mode=route["default_mode"],
        resume_plumbing_retirement_report_payload=resume_plumbing_retirement_report_payload,
    )
    diagnostics.extend(cleanup_diagnostics)
    diagnostics = _dedupe_diagnostics(diagnostics)
    checked_workflow = {
        "workflow_name": workflow_name,
        "status": _report_status(route["default_mode"], diagnostics),
        "route": route,
        "evidence": evidence,
        "diagnostics": diagnostics,
    }
    mode_entry = _mode_entry(
        workflow_name=workflow_name,
        route=route,
        diagnostics=diagnostics,
    )
    return _compose_report(
        workflow_family=workflow_family,
        workflow_name=workflow_name,
        route=route,
        evidence=evidence,
        checked_workflows=[checked_workflow],
        default_modes=[mode_entry],
        cleanup_candidates=cleanup_candidates,
        diagnostics=diagnostics,
    )


def _json_data(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_data(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_data(item) for item in value]
    if isinstance(value, list):
        return [_json_data(item) for item in value]
    return value


def _compose_report(
    *,
    workflow_family: str,
    workflow_name: str,
    route: Mapping[str, Any],
    evidence: Mapping[str, Any],
    checked_workflows: Sequence[Mapping[str, Any]],
    default_modes: Sequence[Mapping[str, Any]],
    cleanup_candidates: Sequence[Mapping[str, Any]],
    diagnostics: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    report = {
        "schema_version": DEFAULT_RESUME_REPORT_SCHEMA_VERSION,
        "workflow_family": workflow_family,
        "workflow_name": workflow_name,
        "status": _report_status(route.get("default_mode"), diagnostics),
        "route": _json_data(route),
        "evidence": _json_data(evidence),
        "checked_workflows": [_json_data(item) for item in checked_workflows],
        "default_modes": [_json_data(item) for item in default_modes],
        "historical_compatibility": [
            _json_data(item)
            for item in default_modes
            if item.get("mode") == MODE_HISTORICAL_STEP_GRANULAR_COMPATIBILITY
        ],
        "fail_closed": [
            _json_data(item)
            for item in default_modes
            if item.get("mode") == MODE_FAIL_CLOSED
            or any(
                _diagnostic_level(_mapping(diag).get("code")) == "error"
                for diag in item.get("diagnostics", [])
                if isinstance(diag, Mapping)
            )
        ],
        "cleanup_candidates": [_json_data(item) for item in cleanup_candidates],
        "diagnostics": [_json_data(item) for item in diagnostics],
    }
    return report


def _mode_entry(
    *,
    workflow_name: str,
    route: Mapping[str, Any],
    diagnostics: Sequence[Mapping[str, Any]],
    restore_decision: str | None = None,
    checkpoint_id: str | None = None,
    record_id: str | None = None,
    restart_node_id: str | None = None,
    source_map_origin_key: str | None = None,
    compatibility_reason: str | None = None,
) -> dict[str, Any]:
    return {
        "workflow_name": workflow_name,
        "mode": route.get("default_mode"),
        "route_kind": route.get("route_kind"),
        "lowering_schema_version": route.get("lowering_schema_version"),
        "historical_compatibility": bool(route.get("historical_compatibility")),
        "restore_decision": restore_decision,
        "checkpoint_id": checkpoint_id,
        "record_id": record_id,
        "restart_node_id": restart_node_id,
        "source_map_origin_key": source_map_origin_key,
        "compatibility_reason": compatibility_reason,
        "diagnostics": [_json_data(item) for item in diagnostics],
    }


def _build_evidence_summary(
    *,
    points: Sequence[Mapping[str, Any]],
    checkpoint_points_payload: Mapping[str, Any],
    checkpoint_shadow_report_payload: Mapping[str, Any] | None,
    resume_plumbing_retirement_report_payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    effect_points = [
        point for point in points if point.get("point_kind") == "effect_boundary"
    ]
    transition_relevant_points = _transition_relevant_points(points)
    transition_points = [
        point
        for point in transition_relevant_points
        if _mapping(
            _mapping(
                _mapping(_mapping(point.get("effect_boundary")).get("policy")).get(
                    "evidence_requirements"
                )
            ).get("transition")
        ).get("transition_identity")
    ]
    restore_points = [
        point for point in points if _mapping(point.get("restore")).get("eligibility")
    ]
    missing_restore_points = [
        _point_node_id(point)
        for point in points
        if not _mapping(point.get("restore")).get("eligibility")
    ]
    effect_policy_points = [
        _point_node_id(point)
        for point in effect_points
        if _mapping(_mapping(point.get("effect_boundary")).get("policy"))
    ]
    return {
        "checkpoint_points": {
            "schema_version": checkpoint_points_payload.get("schema_version"),
            "count": len(points),
        },
        "restore_metadata": {
            "covered_points": len(restore_points),
            "missing_points": missing_restore_points,
            "status": "pass" if not missing_restore_points else "fail",
        },
        "effect_policies": {
            "effect_boundary_points": len(effect_points),
            "covered_points": len(effect_policy_points),
            "status": "pass" if len(effect_policy_points) == len(effect_points) else "fail",
        },
        "transition_evidence": {
            "transition_points": len(transition_points),
            "required_points": len(transition_relevant_points),
            "status": (
                "pass"
                if len(transition_points) == len(transition_relevant_points)
                else "fail"
            ),
        },
        "checkpoint_shadow_report": {
            "schema_version": (
                checkpoint_shadow_report_payload.get("schema_version")
                if isinstance(checkpoint_shadow_report_payload, Mapping)
                else None
            ),
            "status": (
                checkpoint_shadow_report_payload.get("status")
                if isinstance(checkpoint_shadow_report_payload, Mapping)
                else None
            ),
        },
        "retirement_report": {
            "schema_version": (
                resume_plumbing_retirement_report_payload.get("schema_version")
                if isinstance(resume_plumbing_retirement_report_payload, Mapping)
                else None
            ),
            "status": (
                resume_plumbing_retirement_report_payload.get("status")
                if isinstance(resume_plumbing_retirement_report_payload, Mapping)
                else None
            ),
            "decision_count": len(
                resume_plumbing_retirement_report_payload.get("decisions", [])
            )
            if isinstance(resume_plumbing_retirement_report_payload, Mapping)
            and isinstance(
                resume_plumbing_retirement_report_payload.get("decisions"), list
            )
            else 0,
        },
    }


def _default_resume_report_diagnostics(
    *,
    workflow_name: str,
    route: Mapping[str, Any],
    points_payload: Mapping[str, Any],
    points: Sequence[Mapping[str, Any]],
    checkpoint_shadow_report_payload: Mapping[str, Any] | None,
    resume_plumbing_retirement_report_payload: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    if points_payload.get("schema_version") not in {None, _POINTS_SCHEMA_VERSION}:
        diagnostics.append(
            _diagnostic("lexical_default_resume_schema_invalid", row_id=workflow_name)
        )
    if isinstance(checkpoint_shadow_report_payload, Mapping) and checkpoint_shadow_report_payload.get(
        "schema_version"
    ) not in {None, _SHADOW_REPORT_SCHEMA_VERSION}:
        diagnostics.append(
            _diagnostic("lexical_default_resume_schema_invalid", row_id=workflow_name)
        )
    if isinstance(resume_plumbing_retirement_report_payload, Mapping) and resume_plumbing_retirement_report_payload.get(
        "schema_version"
    ) not in {None, _RETIREMENT_REPORT_SCHEMA_VERSION}:
        diagnostics.append(
            _diagnostic("lexical_default_resume_schema_invalid", row_id=workflow_name)
        )
    if route.get("default_mode") == MODE_FAIL_CLOSED and not points:
        diagnostics.append(
            _diagnostic(
                "lexical_default_resume_step_granular_bypass",
                row_id=workflow_name,
            )
        )
    if points and not _has_restore_metadata(points):
        diagnostics.append(
            _diagnostic(
                "lexical_default_resume_restore_metadata_missing",
                row_id=workflow_name,
            )
        )
    effect_points = [
        point for point in points if point.get("point_kind") == "effect_boundary"
    ]
    if effect_points and not _has_effect_policy(points):
        diagnostics.append(
            _diagnostic(
                "lexical_default_resume_effect_policy_missing",
                row_id=workflow_name,
            )
        )
    if effect_points and not _has_transition_evidence(points):
        diagnostics.append(
            _diagnostic(
                "lexical_default_resume_transition_evidence_missing",
                row_id=workflow_name,
            )
        )
    if not isinstance(resume_plumbing_retirement_report_payload, Mapping):
        diagnostics.append(
            _diagnostic(
                "lexical_default_resume_retirement_evidence_missing",
                row_id=workflow_name,
            )
        )
    return diagnostics


def _build_cleanup_candidates(
    *,
    workflow_name: str,
    default_mode: str | None,
    resume_plumbing_retirement_report_payload: Mapping[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    diagnostics: list[dict[str, Any]] = []
    cleanup_candidates: list[dict[str, Any]] = []
    if not isinstance(resume_plumbing_retirement_report_payload, Mapping):
        return cleanup_candidates, diagnostics
    raw_rows = resume_plumbing_retirement_report_payload.get("decisions")
    if not isinstance(raw_rows, list):
        return cleanup_candidates, diagnostics
    for row in raw_rows:
        if not isinstance(row, Mapping):
            continue
        if not _include_cleanup_candidate(row):
            continue
        try:
            candidate = validate_default_resume_cleanup_candidate(
                row,
                default_mode=default_mode,
            )
        except ValueError as exc:
            diagnostics.append(_diagnostic(str(exc), row_id=str(row.get("row_id", workflow_name))))
            continue
        cleanup_candidates.append(candidate)
        diagnostics.extend(
            diag
            for diag in candidate.get("diagnostics", [])
            if isinstance(diag, Mapping)
            and _diagnostic_level(diag.get("code")) == "error"
        )
    return cleanup_candidates, diagnostics


def _include_cleanup_candidate(row: Mapping[str, Any]) -> bool:
    decision = str(row.get("decision", row.get("r5_decision", "")))
    if decision not in _ALLOWED_CLEANUP_DECISIONS:
        return False
    if str(row.get("track_owner", _infer_track_owner(str(row.get("row_id", ""))))) != "R":
        return False
    plumbing_class = row.get("plumbing_class")
    if plumbing_class is None:
        return True
    return str(plumbing_class) == "resume_only"


def _diagnostic_entries(
    raw_diagnostics: Sequence[Any],
    *,
    row_id: str,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for raw in raw_diagnostics:
        if isinstance(raw, str):
            entries.append(_diagnostic(raw, row_id=row_id))
            continue
        if isinstance(raw, Mapping):
            code = raw.get("code")
            if isinstance(code, str) and code:
                entry = dict(raw)
                entry.setdefault("row_id", row_id)
                entry.setdefault("level", _diagnostic_level(code))
                entries.append(_json_data(entry))
    return _dedupe_diagnostics(entries)


def _diagnostic(code: str, *, row_id: str) -> dict[str, Any]:
    return {"code": code, "row_id": row_id, "level": _diagnostic_level(code)}


def _diagnostic_level(code: Any) -> str:
    return "error" if isinstance(code, str) and code in _ERROR_DIAGNOSTICS else "info"


def _report_status(default_mode: Any, diagnostics: Sequence[Mapping[str, Any]]) -> str:
    if default_mode == MODE_FAIL_CLOSED:
        return "fail"
    if any(
        _diagnostic_level(_mapping(diag).get("code")) == "error"
        for diag in diagnostics
        if isinstance(diag, Mapping)
    ):
        return "fail"
    return "pass"


def _dedupe_diagnostics(
    diagnostics: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for raw in diagnostics:
        if not isinstance(raw, Mapping):
            continue
        code = str(raw.get("code", ""))
        row_id = str(raw.get("row_id", ""))
        key = (code, row_id)
        if key in seen:
            continue
        seen.add(key)
        entry = dict(raw)
        entry.setdefault("level", _diagnostic_level(code))
        deduped.append(_json_data(entry))
    return deduped


def _runtime_plan_from_points(workflow_name: str, points: Sequence[Mapping[str, Any]]) -> Any:
    runtime_points = []
    for point in points:
        runtime_points.append(
            type(
                "_Point",
                (),
                {
                    "checkpoint_id": point.get("checkpoint_id"),
                    "node_id": _point_node_id(point),
                    "point_kind": point.get("point_kind"),
                    "workflow_name": point.get("workflow_name"),
                    "details": dict(point),
                    "origin_key": _mapping(point.get("source_lineage")).get("origin_key"),
                },
            )()
        )
    return type(
        "_RuntimePlan",
        (),
        {
            "workflow_name": workflow_name,
            "lexical_checkpoint_points": tuple(runtime_points),
        },
    )()


def _lowering_schema_version(
    loaded_workflow: Any | None, *, state: Mapping[str, Any]
) -> int | None:
    for candidate in (
        _mapping(_mapping(state.get("context")).get("workflow_lisp")).get(
            "lowering_schema_version"
        ),
        _mapping(_mapping(workflow_context(loaded_workflow)).get("workflow_lisp")).get(
            "lowering_schema_version"
        )
        if loaded_workflow is not None
        else None,
    ):
        if isinstance(candidate, int):
            return candidate
    provenance = workflow_provenance(loaded_workflow) if loaded_workflow is not None else None
    if provenance is not None and provenance.lexical_checkpoint_points:
        return 2
    return None


def _historical_compatibility(
    loaded_workflow: Any | None, *, state: Mapping[str, Any]
) -> bool:
    for context in (
        _mapping(state.get("context")),
        workflow_context(loaded_workflow) if loaded_workflow is not None else {},
    ):
        value = _mapping(context.get("workflow_lisp")).get("historical_compatibility")
        if isinstance(value, bool):
            return value
    return False


def _is_workflow_lisp_route(
    loaded_workflow: Any | None, *, state: Mapping[str, Any]
) -> bool:
    state_context = _mapping(state.get("context"))
    if _mapping(state_context.get("workflow_lisp")):
        return True
    if loaded_workflow is None:
        return False
    provenance = workflow_provenance(loaded_workflow)
    if provenance is not None and provenance.frontend_kind == "workflow_lisp":
        return True
    if provenance is not None and provenance.lexical_checkpoint_points:
        return True
    return bool(_mapping(workflow_context(loaded_workflow)).get("workflow_lisp"))


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _has_restore_metadata(points: Sequence[Mapping[str, Any]]) -> bool:
    return all(_mapping(point.get("restore")).get("eligibility") for point in points)


def _has_effect_policy(points: Sequence[Mapping[str, Any]]) -> bool:
    return all(
        _mapping(_mapping(point.get("effect_boundary")).get("policy"))
        for point in points
        if point.get("point_kind") == "effect_boundary"
    )


def _has_transition_evidence(points: Sequence[Mapping[str, Any]]) -> bool:
    relevant_points = _transition_relevant_points(points)
    if not relevant_points:
        return True
    for point in relevant_points:
        policy = _mapping(_mapping(point.get("effect_boundary")).get("policy"))
        transition = _mapping(_mapping(policy.get("evidence_requirements")).get("transition"))
        if not transition.get("transition_identity"):
            return False
    return True


def _point_node_id(point: Mapping[str, Any]) -> str | None:
    return _mapping(point.get("executable_identity")).get("node_id")


def _transition_relevant_points(
    points: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    relevant: list[Mapping[str, Any]] = []
    for point in points:
        if point.get("point_kind") != "effect_boundary":
            continue
        effect_boundary = _mapping(point.get("effect_boundary"))
        if effect_boundary.get("effect_kind") == "resource_transition":
            relevant.append(point)
            continue
        if effect_boundary.get("boundary_kind") == "resource_transition":
            relevant.append(point)
    return relevant


def _current_consumer(row: Mapping[str, Any]) -> str | None:
    for key in ("current_consumer", "remaining_consumer"):
        value = row.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _has_command_glue(row: Mapping[str, Any]) -> bool:
    command_boundary = row.get("command_boundary")
    if isinstance(command_boundary, Mapping):
        return bool(command_boundary)
    return command_boundary not in (None, "", False)


def _infer_track_owner(row_id: str) -> str:
    if row_id.startswith("drain.output.") or row_id.startswith("drain.publish."):
        return "C"
    return "R"
