"""R5 checked retirement decisions over the U0 value-flow census."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .lexical_checkpoints import canonical_json_dumps
from .value_flow_census import (
    normalize_resume_plumbing_retirement_compiled_rows as _normalize_compiled_rows,
    resume_plumbing_retirement_target_status,
    select_resume_plumbing_retirement_candidates,
    summarize_resume_plumbing_retirement_stale_rows,
    validate_resume_plumbing_retirement_decision,
)


RESUME_PLUMBING_RETIREMENT_SCHEMA_VERSION = (
    "workflow_lisp_resume_plumbing_retirement.v1"
)
RESUME_PLUMBING_RETIREMENT_REPORT_SCHEMA_VERSION = (
    "workflow_lisp_resume_plumbing_retirement_report.v1"
)
RESUME_PLUMBING_RETIREMENT_DECISIONS = frozenset(
    {
        "RETIRED",
        "HIDDEN_PRIVATE",
        "KEPT_COMPATIBILITY",
        "BLOCKED",
        "NOT_R5_TARGET",
    }
)
TARGET_FAMILY = "lisp_frontend_design_delta_parent_drain"
AUTHORITY_FORBIDDEN_SOURCES = {
    "checkpoint_record": "resume_plumbing_retirement_checkpoint_used_as_authority",
    "checkpoint_path": "resume_plumbing_retirement_checkpoint_used_as_authority",
    "report_path": "resume_plumbing_retirement_checkpoint_used_as_authority",
}
CHECKPOINT_POINTS_SCHEMA_VERSION = "workflow_lisp_lexical_checkpoint_points.v1"
CHECKPOINT_SHADOW_REPORT_SCHEMA_VERSION = (
    "workflow_lisp_lexical_checkpoint_shadow_report.v1"
)
EFFECT_RESUME_POLICY_SCHEMA_VERSION = "workflow_lisp_effect_resume_policy.v1"
REQUIRED_TRANSITION_IDENTITIES = frozenset({"write-drain-status-runtime-native"})
DRAIN_RUN_STATE_BRIDGE_ROW_ID = "transitions.resource.drain_run_state"
DRAIN_RUN_STATE_BRIDGE_WORKFLOW_SURFACE = "lisp_frontend_design_delta/transitions"
DRAIN_RUN_STATE_BRIDGE_SYMBOL = "drain-run-state"
DRAIN_RUN_STATE_BRIDGE_REPLACEMENT_TARGET = (
    "Track R runtime-derived drain-run-state backing"
)
DRAIN_RUN_STATE_BRIDGE_ALLOWED_DECISIONS = frozenset({"RETIRED"})
RETIREMENT_EVIDENCE_REQUIREMENTS: dict[str, dict[str, Any]] = {
    "drain.loop.run_state_path": {
        "requires_loop_restore": True,
        "required_transition_identities": frozenset({"write-drain-status-runtime-native"}),
    },
    "work_item.loop.run_state_path": {
        "requires_loop_restore": False,
        "required_transition_identities": frozenset({"record-terminal-work-item"}),
    },
}


def load_resume_plumbing_retirement_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("resume_plumbing_retirement_schema_invalid: manifest must be an object")
    if payload.get("schema_version") != RESUME_PLUMBING_RETIREMENT_SCHEMA_VERSION:
        raise ValueError(
            "resume_plumbing_retirement_schema_invalid: "
            f"expected schema_version {RESUME_PLUMBING_RETIREMENT_SCHEMA_VERSION}"
        )
    if payload.get("target_family") != TARGET_FAMILY:
        raise ValueError(
            "resume_plumbing_retirement_schema_invalid: "
            f"expected target_family {TARGET_FAMILY}"
        )
    source_census = payload.get("source_census")
    if not isinstance(source_census, Mapping):
        raise ValueError(
            "resume_plumbing_retirement_schema_invalid: source_census must be an object"
        )
    if not _non_empty_string(source_census.get("path")) or not _non_empty_string(
        source_census.get("fingerprint")
    ):
        raise ValueError(
            "resume_plumbing_retirement_schema_invalid: source_census requires path and fingerprint"
        )
    raw_decisions = payload.get("decisions")
    if not isinstance(raw_decisions, list):
        raise ValueError(
            "resume_plumbing_retirement_schema_invalid: decisions must be an array"
        )
    decisions: list[dict[str, Any]] = []
    for index, raw_decision in enumerate(raw_decisions):
        if not isinstance(raw_decision, Mapping):
            raise ValueError(
                "resume_plumbing_retirement_schema_invalid: "
                f"decisions[{index}] must be an object"
            )
        decision = dict(raw_decision)
        row_id = decision.get("row_id")
        status = decision.get("decision")
        if not _non_empty_string(row_id):
            raise ValueError(
                "resume_plumbing_retirement_schema_invalid: decision row_id is required"
            )
        if status not in RESUME_PLUMBING_RETIREMENT_DECISIONS:
            raise ValueError(
                "resume_plumbing_retirement_schema_invalid: "
                f"decision `{status}` is not allowed"
            )
        if status in {"KEPT_COMPATIBILITY", "BLOCKED"}:
            for field_name in (
                "remaining_consumer",
                "retirement_condition",
                "parity_constraint",
            ):
                if not _non_empty_string(decision.get(field_name)):
                    raise ValueError(
                        "resume_plumbing_retirement_compatibility_unjustified: "
                        f"decision `{row_id}` requires `{field_name}`"
                    )
        decisions.append(decision)
    return {
        "schema_version": RESUME_PLUMBING_RETIREMENT_SCHEMA_VERSION,
        "target_family": TARGET_FAMILY,
        "source_census": {
            "path": str(source_census["path"]),
            "fingerprint": str(source_census["fingerprint"]),
        },
        "decisions": decisions,
    }


def normalize_resume_plumbing_retirement_compiled_rows(
    candidate_rows: list[Mapping[str, Any]],
    *,
    boundary_authority_report: Mapping[str, Any],
    source_text_by_surface: Mapping[str, str],
) -> dict[str, dict[str, Any]]:
    normalized = _normalize_compiled_rows(
        candidate_rows,
        boundary_authority_report=boundary_authority_report,
        source_text_by_surface=source_text_by_surface,
    )
    transitions_source = source_text_by_surface.get(
        "lisp_frontend_design_delta/transitions", ""
    )
    if (
        "(defresource drain-run-state" in transitions_source
        and ":backing (bridge run_state_path)" in transitions_source
    ):
        normalized[DRAIN_RUN_STATE_BRIDGE_ROW_ID] = {
            "row_id": DRAIN_RUN_STATE_BRIDGE_ROW_ID,
            "workflow_surface": DRAIN_RUN_STATE_BRIDGE_WORKFLOW_SURFACE,
            "symbol_or_field": DRAIN_RUN_STATE_BRIDGE_SYMBOL,
            "source_kind": "bridge_file",
            "boundary_authority_class": "compatibility_bridge",
            "observed_locations": ["resource_bridge_backing"],
            "semantic_authority_source": "typed_runtime_resource",
        }
    return normalized


def build_resume_plumbing_retirement_report(
    *,
    workflow_family: str,
    census: Mapping[str, Any],
    census_fingerprint: str,
    compiled_rows: Mapping[str, Mapping[str, Any]] | list[Mapping[str, Any]],
    manifest: Mapping[str, Any] | None,
    manifest_fingerprint: str | None,
    checkpoint_points_payload: Mapping[str, Any] | None,
    checkpoint_shadow_report_payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    decisions_by_row_id = _manifest_decisions_by_row_id(manifest)
    if manifest is not None and manifest.get("source_census", {}).get("fingerprint") != census_fingerprint:
        raise ValueError(
            "resume_plumbing_retirement_census_fingerprint_mismatch: "
            "checked compatibility decisions do not match the checked U0 census"
        )
    if isinstance(compiled_rows, Mapping):
        compiled_rows_by_id = {
            str(row_id): dict(row)
            for row_id, row in compiled_rows.items()
            if isinstance(row, Mapping)
        }
    else:
        compiled_rows_by_id = {
            str(row.get("row_id", "")): dict(row)
            for row in compiled_rows
            if isinstance(row, Mapping) and _non_empty_string(row.get("row_id"))
        }
    report_decisions: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    candidate_rows = select_resume_plumbing_retirement_candidates(census)

    for row in census.get("rows", []):
        if not isinstance(row, Mapping):
            continue
        row_id = str(row.get("row_id", ""))
        manifest_decision = decisions_by_row_id.get(row_id)
        if manifest_decision is not None:
            decision = str(manifest_decision["decision"])
        else:
            decision = resume_plumbing_retirement_target_status(row)
        validate_resume_plumbing_retirement_decision(row, decision=decision)

        compiled_row = compiled_rows_by_id.get(row_id)
        authority_code = _authority_violation_code(compiled_row)
        if authority_code is not None:
            raise ValueError(
                f"{authority_code}: row `{row_id}` cannot treat checkpoint or report paths as semantic authority"
            )
        if decision == "RETIRED":
            diagnostics.extend(
                _retirement_evidence_diagnostics(
                    row,
                    checkpoint_points_payload=checkpoint_points_payload,
                    checkpoint_shadow_report_payload=checkpoint_shadow_report_payload,
                )
            )
            if compiled_row is not None:
                locations = set(compiled_row.get("observed_locations", []))
                boundary_class = compiled_row.get("boundary_authority_class")
                if boundary_class == "public_authored" or "public_boundary" in locations:
                    diagnostics.append(
                        _diagnostic(
                            "resume_plumbing_retirement_public_boundary_exposed",
                            row,
                            compiled_row,
                        )
                    )
                elif "loop_state_field" in locations:
                    diagnostics.append(
                        _diagnostic(
                            "resume_plumbing_retirement_loop_state_exposed",
                            row,
                            compiled_row,
                        )
                    )
                elif "call_signature" in locations:
                    diagnostics.append(
                        _diagnostic(
                            "resume_plumbing_retirement_call_signature_exposed",
                            row,
                            compiled_row,
                        )
                    )
        elif decision == "HIDDEN_PRIVATE":
            if compiled_row is None:
                diagnostics.append(
                    _diagnostic("resume_plumbing_retirement_row_stale", row, None)
                )
            elif compiled_row.get("boundary_authority_class") not in {
                "runtime_derived",
                "generated_internal",
                None,
            }:
                diagnostics.append(
                    _diagnostic(
                        "resume_plumbing_retirement_public_boundary_exposed",
                        row,
                        compiled_row,
                    )
                )
        elif decision == "KEPT_COMPATIBILITY":
            if compiled_row is None:
                diagnostics.append(
                    _diagnostic("resume_plumbing_retirement_row_stale", row, None)
                )
            else:
                boundary_class = compiled_row.get("boundary_authority_class")
                locations = set(compiled_row.get("observed_locations", []))
                if boundary_class == "public_authored" or "public_boundary" in locations:
                    diagnostics.append(
                        _diagnostic(
                            "resume_plumbing_retirement_public_boundary_exposed",
                            row,
                            compiled_row,
                        )
                    )
                elif "loop_state_field" in locations:
                    diagnostics.append(
                        _diagnostic(
                            "resume_plumbing_retirement_loop_state_exposed",
                            row,
                            compiled_row,
                        )
                    )
                elif "call_signature" in locations:
                    diagnostics.append(
                        _diagnostic(
                            "resume_plumbing_retirement_call_signature_exposed",
                            row,
                            compiled_row,
                        )
                    )
                elif (
                    row_id == "work_item.loop.run_state_path"
                    and boundary_class == "runtime_derived"
                ):
                    diagnostics.append(
                        _diagnostic(
                            "resume_plumbing_retirement_runtime_derived_reclassification",
                            row,
                            compiled_row,
                        )
                    )
                elif boundary_class not in {"compatibility_bridge", None}:
                    diagnostics.append(
                        _diagnostic(
                            "resume_plumbing_retirement_public_boundary_exposed",
                            row,
                            compiled_row,
                        )
                    )
        elif decision == "BLOCKED":
            if compiled_row is not None:
                boundary_class = compiled_row.get("boundary_authority_class")
                locations = set(compiled_row.get("observed_locations", []))
                if boundary_class == "public_authored" or "public_boundary" in locations:
                    diagnostics.append(
                        _diagnostic(
                            "resume_plumbing_retirement_public_boundary_exposed",
                            row,
                            compiled_row,
                        )
                    )
                elif "loop_state_field" in locations:
                    diagnostics.append(
                        _diagnostic(
                            "resume_plumbing_retirement_loop_state_exposed",
                            row,
                            compiled_row,
                        )
                    )
                elif "call_signature" in locations:
                    diagnostics.append(
                        _diagnostic(
                            "resume_plumbing_retirement_call_signature_exposed",
                            row,
                            compiled_row,
                        )
                    )
                elif (
                    row_id == "work_item.loop.run_state_path"
                    and boundary_class == "runtime_derived"
                ):
                    diagnostics.append(
                        _diagnostic(
                            "resume_plumbing_retirement_runtime_derived_reclassification",
                            row,
                            compiled_row,
                        )
                    )
                elif boundary_class not in {"compatibility_bridge", None}:
                    diagnostics.append(
                        _diagnostic(
                            "resume_plumbing_retirement_public_boundary_exposed",
                            row,
                            compiled_row,
                        )
                    )

        report_decisions.append(
            {
                "row_id": row_id,
                "workflow_surface": str(row.get("workflow_surface", "")),
                "symbol_or_field": str(row.get("symbol_or_field", "")),
                "source_kind": row.get("source_kind"),
                "plumbing_class": row.get("plumbing_class"),
                "track_owner": row.get("track_owner"),
                "boundary_authority_class": row.get("boundary_authority_class"),
                "semantic_owner": row.get("semantic_owner"),
                "current_consumer": (
                    manifest_decision.get("remaining_consumer")
                    if isinstance(manifest_decision, Mapping)
                    and _non_empty_string(manifest_decision.get("remaining_consumer"))
                    else row.get("current_consumer")
                ),
                "command_boundary": row.get("command_boundary"),
                "replacement_target": row.get("replacement_target"),
                "decision": decision,
                "observed_locations": list(compiled_row.get("observed_locations", []))
                if isinstance(compiled_row, Mapping)
                else [],
            }
        )

    report_decisions.extend(
        _required_compatibility_bridge_decisions(
            compiled_rows_by_id=compiled_rows_by_id,
            decisions_by_row_id=decisions_by_row_id,
            diagnostics=diagnostics,
        )
    )

    stale_candidates = summarize_resume_plumbing_retirement_stale_rows(
        candidate_rows,
        compiled_rows=compiled_rows_by_id,
    )
    decisions_by_row = {item["row_id"]: item["decision"] for item in report_decisions}
    diagnostics.extend(
        stale
        for stale in stale_candidates
        if decisions_by_row.get(str(stale.get("row_id", "")))
        in {"HIDDEN_PRIVATE", "KEPT_COMPATIBILITY"}
    )
    deduped_diagnostics = _dedupe_diagnostics(diagnostics)
    return {
        "schema_version": RESUME_PLUMBING_RETIREMENT_REPORT_SCHEMA_VERSION,
        "workflow_family": workflow_family,
        "status": "pass" if not deduped_diagnostics else "fail",
        "source_census": {
            "path": str(census.get("__census_path__", "")),
            "fingerprint": census_fingerprint,
        },
        "manifest": None
        if manifest is None
        else {
            "path": str(manifest.get("__manifest_path__", "")),
            "fingerprint": str(manifest_fingerprint or ""),
        },
        "decisions": sorted(report_decisions, key=lambda item: item["row_id"]),
        "diagnostics": deduped_diagnostics,
    }


def serialize_resume_plumbing_retirement_report(report: Mapping[str, Any]) -> str:
    return canonical_json_dumps(report)


def _required_compatibility_bridge_decisions(
    *,
    compiled_rows_by_id: Mapping[str, Mapping[str, Any]],
    decisions_by_row_id: Mapping[str, Mapping[str, Any]],
    diagnostics: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    compiled_row = compiled_rows_by_id.get(DRAIN_RUN_STATE_BRIDGE_ROW_ID)
    manifest_decision = decisions_by_row_id.get(DRAIN_RUN_STATE_BRIDGE_ROW_ID)
    if compiled_row is None and manifest_decision is None:
        return []
    if compiled_row is not None and manifest_decision is None:
        raise ValueError(
            "resume_plumbing_retirement_compatibility_unjustified: "
            f"row `{DRAIN_RUN_STATE_BRIDGE_ROW_ID}` requires a checked "
            "RETIRED decision while drain-run-state still uses "
            "run_state_path bridge backing"
        )
    decision = (
        str(manifest_decision.get("decision"))
        if isinstance(manifest_decision, Mapping)
        else "RETIRED"
    )
    if decision not in DRAIN_RUN_STATE_BRIDGE_ALLOWED_DECISIONS:
        raise ValueError(
            "resume_plumbing_retirement_compatibility_unjustified: "
            f"row `{DRAIN_RUN_STATE_BRIDGE_ROW_ID}` must be marked "
            "`RETIRED` once the drain-run-state bridge backing is removed"
        )
    if compiled_row is None:
        return [
            {
                "row_id": DRAIN_RUN_STATE_BRIDGE_ROW_ID,
                "workflow_surface": DRAIN_RUN_STATE_BRIDGE_WORKFLOW_SURFACE,
                "symbol_or_field": DRAIN_RUN_STATE_BRIDGE_SYMBOL,
                "source_kind": "bridge_file",
                "plumbing_class": "resume_only",
                "track_owner": "R",
                "boundary_authority_class": "compatibility_bridge",
                "semantic_owner": "runtime_resume",
                "current_consumer": None,
                "command_boundary": None,
                "replacement_target": DRAIN_RUN_STATE_BRIDGE_REPLACEMENT_TARGET,
                "observed_locations": [],
                "decision": decision,
            }
        ]
    observed_locations = []
    if isinstance(compiled_row, Mapping):
        observed_locations = list(compiled_row.get("observed_locations", []))
    return [
        {
            "row_id": DRAIN_RUN_STATE_BRIDGE_ROW_ID,
            "workflow_surface": DRAIN_RUN_STATE_BRIDGE_WORKFLOW_SURFACE,
            "symbol_or_field": DRAIN_RUN_STATE_BRIDGE_SYMBOL,
            "source_kind": "bridge_file",
            "plumbing_class": "resume_only",
            "track_owner": "R",
            "boundary_authority_class": "compatibility_bridge",
            "semantic_owner": "runtime_resume",
            "current_consumer": (
                manifest_decision.get("remaining_consumer")
                if isinstance(manifest_decision, Mapping)
                and _non_empty_string(manifest_decision.get("remaining_consumer"))
                else "runtime_transition_bridge"
                if compiled_row is not None
                else None
            ),
            "command_boundary": None,
            "replacement_target": DRAIN_RUN_STATE_BRIDGE_REPLACEMENT_TARGET,
            "decision": decision,
            "observed_locations": observed_locations,
        }
    ]


def _authority_violation_code(compiled_row: Mapping[str, Any] | None) -> str | None:
    if not isinstance(compiled_row, Mapping):
        return None
    source = compiled_row.get("semantic_authority_source")
    if not isinstance(source, str):
        return None
    return AUTHORITY_FORBIDDEN_SOURCES.get(source)


def _retirement_evidence_diagnostics(
    row: Mapping[str, Any],
    *,
    checkpoint_points_payload: Mapping[str, Any] | None,
    checkpoint_shadow_report_payload: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    workflow_name = str(row.get("workflow_surface", ""))
    evidence_requirements = _retirement_evidence_requirements(row)
    if (
        not _checkpoint_shadow_report_passes_for_workflow(
            checkpoint_shadow_report_payload,
            workflow_name=workflow_name,
        )
    ):
        diagnostics.append(_diagnostic("resume_plumbing_retirement_restore_evidence_missing", row, None))
        return diagnostics
    points = _checkpoint_points_for_retirement(
        checkpoint_points_payload,
        workflow_name=workflow_name,
    )
    if not points:
        diagnostics.append(_diagnostic("resume_plumbing_retirement_restore_evidence_missing", row, None))
        diagnostics.append(_diagnostic("resume_plumbing_retirement_effect_policy_missing", row, None))
        diagnostics.append(_diagnostic("resume_plumbing_retirement_transition_evidence_missing", row, None))
        return diagnostics
    if evidence_requirements["requires_loop_restore"] and not any(
        point.get("point_kind") == "loop_back_edge"
        and "loop_frame" in _restore_eligibility(point)
        for point in points
    ):
        diagnostics.append(_diagnostic("resume_plumbing_retirement_restore_evidence_missing", row, None))
    effect_points = [
        point
        for point in points
        if point.get("point_kind") == "effect_boundary"
    ]
    if not any(_effect_policy(point) is not None for point in effect_points):
        diagnostics.append(_diagnostic("resume_plumbing_retirement_effect_policy_missing", row, None))
    if not any(
        _transition_identity(point) in evidence_requirements["required_transition_identities"]
        for point in effect_points
    ):
        diagnostics.append(_diagnostic("resume_plumbing_retirement_transition_evidence_missing", row, None))
    return diagnostics


def _diagnostic(
    code: str,
    row: Mapping[str, Any],
    compiled_row: Mapping[str, Any] | None,
) -> dict[str, Any]:
    return {
        "code": code,
        "row_id": str(row.get("row_id", "")),
        "workflow_surface": str(row.get("workflow_surface", "")),
        "symbol_or_field": str(row.get("symbol_or_field", "")),
        "replacement_target": row.get("replacement_target"),
        **(
            {
                "observed_locations": list(compiled_row.get("observed_locations", [])),
            }
            if isinstance(compiled_row, Mapping)
            else {}
        ),
    }


def _dedupe_diagnostics(
    diagnostics: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for diagnostic in diagnostics:
        row_id = str(diagnostic.get("row_id", ""))
        code = str(diagnostic.get("code", diagnostic.get("reason", "")))
        key = (code, row_id)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(diagnostic)
    return sorted(
        deduped,
        key=lambda item: (
            str(item.get("row_id", "")),
            str(item.get("code", item.get("reason", ""))),
        ),
    )


def _manifest_decisions_by_row_id(
    manifest: Mapping[str, Any] | None,
) -> dict[str, Mapping[str, Any]]:
    if manifest is None:
        return {}
    raw_decisions = manifest.get("decisions")
    if not isinstance(raw_decisions, list):
        return {}
    return {
        str(decision["row_id"]): decision
        for decision in raw_decisions
        if isinstance(decision, Mapping) and _non_empty_string(decision.get("row_id"))
    }


def _non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _checkpoint_points_for_retirement(
    checkpoint_points_payload: Mapping[str, Any] | None,
    *,
    workflow_name: str,
) -> list[Mapping[str, Any]]:
    if (
        not isinstance(checkpoint_points_payload, Mapping)
        or checkpoint_points_payload.get("schema_version") != CHECKPOINT_POINTS_SCHEMA_VERSION
        or not workflow_name
    ):
        return []
    points = checkpoint_points_payload.get("points")
    if not isinstance(points, list):
        return []
    return [
        point
        for point in points
        if isinstance(point, Mapping)
        and point.get("workflow_name") == workflow_name
    ]


def _checkpoint_shadow_report_passes_for_workflow(
    checkpoint_shadow_report_payload: Mapping[str, Any] | None,
    *,
    workflow_name: str,
) -> bool:
    if (
        not isinstance(checkpoint_shadow_report_payload, Mapping)
        or checkpoint_shadow_report_payload.get("schema_version")
        != CHECKPOINT_SHADOW_REPORT_SCHEMA_VERSION
        or not workflow_name
    ):
        return False
    workflow_reports = checkpoint_shadow_report_payload.get("workflow_reports")
    if isinstance(workflow_reports, list):
        for report in workflow_reports:
            if (
                isinstance(report, Mapping)
                and report.get("workflow_name") == workflow_name
            ):
                return report.get("status") == "pass"
        return False
    return (
        checkpoint_shadow_report_payload.get("workflow_name") == workflow_name
        and checkpoint_shadow_report_payload.get("status") == "pass"
    )


def _retirement_evidence_requirements(row: Mapping[str, Any]) -> dict[str, Any]:
    row_id = str(row.get("row_id", ""))
    return RETIREMENT_EVIDENCE_REQUIREMENTS.get(
        row_id,
        {
            "requires_loop_restore": True,
            "required_transition_identities": REQUIRED_TRANSITION_IDENTITIES,
        },
    )


def _restore_eligibility(point: Mapping[str, Any]) -> tuple[str, ...]:
    restore = point.get("restore")
    if not isinstance(restore, Mapping):
        return ()
    eligibility = restore.get("eligibility")
    if not isinstance(eligibility, list):
        return ()
    return tuple(label for label in eligibility if isinstance(label, str))


def _effect_policy(point: Mapping[str, Any]) -> Mapping[str, Any] | None:
    effect_boundary = point.get("effect_boundary")
    if not isinstance(effect_boundary, Mapping):
        return None
    policy = effect_boundary.get("policy")
    if (
        not isinstance(policy, Mapping)
        or policy.get("schema_version") != EFFECT_RESUME_POLICY_SCHEMA_VERSION
    ):
        return None
    return policy


def _transition_identity(point: Mapping[str, Any]) -> str | None:
    policy = _effect_policy(point)
    if policy is None:
        return None
    evidence_requirements = policy.get("evidence_requirements")
    if not isinstance(evidence_requirements, Mapping):
        return None
    transition = evidence_requirements.get("transition")
    if not isinstance(transition, Mapping):
        return None
    value = transition.get("transition_identity")
    return str(value) if isinstance(value, str) else None
