"""C6 author-facing rendering ergonomics: consumer-slot resolution over C0-C5 evidence.

Contract: docs/plans/LISP-PRIVATE-RUNTIME-VALUE-FLOW-DRAIN/design-gaps/
workflow-lisp-private-runtime-state-and-consumer-value-flow-c6-author-facing-rendering-ergonomics/
implementation_architecture.md
Target design: docs/design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md
(Sec 7.2, 7.6, 8, 10 C6, 12, 13).

This module adds no renderer, no runtime node, and no rendering semantics. It joins
already-checked C0-C5 evidence and resolves exactly one registered renderer per
rendered slot. Runtime behavior stays owned by C1-C5.
"""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from orchestrator.workflow.view_renderer import resolve_view_renderer, ViewRendererError

RENDERING_ERGONOMICS_POLICY_SCHEMA_VERSION = (
    "workflow_lisp_rendering_ergonomics_policy.v1"
)
RENDERING_ERGONOMICS_REPORT_SCHEMA_VERSION = (
    "workflow_lisp_rendering_ergonomics_report.v1"
)

ALLOWED_CONSUMER_LANES = frozenset(
    {
        "typed_step",
        "prompt_input",
        "observability",
        "entry_publication",
        "compatibility_bridge",
        "timed_body_materialization",
    }
)
ALLOWED_RESOLUTIONS = frozenset(
    {
        "selected",
        "not_rendered",
        "requires_override",
        "blocked",
    }
)

# Canonical Track-C lane each consumer slot must source its evidence from.
LANE_TO_TRACK_C = {
    "typed_step": None,
    "prompt_input": "C1",
    "observability": "C2",
    "entry_publication": "C3",
    "compatibility_bridge": "C4",
    "timed_body_materialization": "C5",
}

# Author-facing lint codes: explicit body-level rendering or command-glue that
# an author should replace with a consumer-owned lane. Surfaced from the C6
# report (mirroring how C5 surfaces body_materialization diagnostics) rather than
# through the frontend required-lint registry.
RENDERING_ERGONOMICS_AUTHOR_LINT_CODES = frozenset(
    {
        "rendering_ergonomics_body_render_not_timed",
        "rendering_ergonomics_command_glue_forbidden",
        "rendering_ergonomics_publication_not_at_entry_boundary",
        "rendering_ergonomics_bridge_not_metadata",
        "rendering_ergonomics_view_used_as_state",
    }
)

# Body-level rendering misuses surfaced under the report's body_render_lints.
_BODY_RENDER_LINT_CODES = frozenset(
    {
        "rendering_ergonomics_body_render_not_timed",
        "rendering_ergonomics_command_glue_forbidden",
        "rendering_ergonomics_view_used_as_state",
    }
)

# Rendering implementations an author must never use for ergonomic rendering.
FORBIDDEN_RENDERING_IMPLEMENTATIONS = frozenset(
    {
        "command",
        "command_glue",
        "certified_adapter",
        "inline_python",
        "inline_shell",
        "report_parse",
        "stdout_as_state",
        "pointer_as_state",
    }
)

# Six prerequisite reports the C6 report joins (schema key differs for C2).
PREREQUISITE_REPORTS = (
    ("consumer_rendering_census_report", "schema_version"),
    ("typed_prompt_input_report", "schema_version"),
    ("observability_summary_report", "schema_id"),
    ("entry_publication_report", "schema_version"),
    ("compatibility_bridge_report", "schema_version"),
    ("rendering_cleanup_report", "schema_version"),
)


class RenderingErgonomicsError(ValueError):
    """Fail-closed C6 policy/report validation error carrying a stable code."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.metadata = dict(metadata or {})


def load_rendering_ergonomics_policy(path: Path) -> dict[str, Any]:
    """Load and fail-closed validate the checked C6 policy manifest."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise RenderingErgonomicsError(
            "rendering_ergonomics_policy_schema_invalid",
            "policy manifest must be a JSON object",
        )
    if payload.get("schema_version") != RENDERING_ERGONOMICS_POLICY_SCHEMA_VERSION:
        raise RenderingErgonomicsError(
            "rendering_ergonomics_policy_schema_invalid",
            "policy schema_version mismatch",
            metadata={"found": payload.get("schema_version")},
        )
    slots = payload.get("consumer_slots")
    if not isinstance(slots, list) or not slots:
        raise RenderingErgonomicsError(
            "rendering_ergonomics_policy_schema_invalid",
            "consumer_slots must be a non-empty list",
        )
    seen: set[str] = set()
    for slot in slots:
        _validate_policy_slot(slot, seen)
    return dict(payload)


def _validate_policy_slot(slot: Any, seen: set[str]) -> None:
    if not isinstance(slot, Mapping):
        raise RenderingErgonomicsError(
            "rendering_ergonomics_policy_schema_invalid",
            "consumer_slots entries must be objects",
        )
    slot_id = slot.get("slot_id")
    if not isinstance(slot_id, str) or not slot_id:
        raise RenderingErgonomicsError(
            "rendering_ergonomics_policy_schema_invalid",
            "slot_id must be a non-empty string",
        )
    if slot_id in seen:
        raise RenderingErgonomicsError(
            "rendering_ergonomics_policy_schema_invalid",
            "duplicate slot_id",
            metadata={"slot_id": slot_id},
        )
    seen.add(slot_id)
    lane = slot.get("consumer_lane")
    if lane not in ALLOWED_CONSUMER_LANES:
        raise RenderingErgonomicsError(
            "rendering_ergonomics_policy_schema_invalid",
            "unknown consumer_lane",
            metadata={"slot_id": slot_id, "consumer_lane": lane},
        )
    expected = slot.get("expected_track_c_lane")
    if lane != "typed_step" and expected != LANE_TO_TRACK_C[lane]:
        raise RenderingErgonomicsError(
            "rendering_ergonomics_policy_schema_invalid",
            "expected_track_c_lane inconsistent with consumer_lane",
            metadata={"slot_id": slot_id, "consumer_lane": lane, "expected": expected},
        )
    mode = slot.get("renderer_selection", {}).get("mode")
    if lane == "typed_step" and mode != "none":
        raise RenderingErgonomicsError(
            "rendering_ergonomics_policy_schema_invalid",
            "typed_step slots must declare renderer_selection.mode == 'none'",
            metadata={"slot_id": slot_id},
        )


# --------------------------------------------------------------------------- #
# Renderer resolution
# --------------------------------------------------------------------------- #


def _diagnostic(code: str, slot_id: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"code": code, "slot_id": slot_id, "message": message, **extra}


def _override_surface_for_lane(lane: str | None) -> str:
    return {
        "prompt_input": "typed prompt-input lowering :renderer",
        "entry_publication": ":publish ... :renderer",
        "compatibility_bridge": "C4 bridge metadata renderer descriptor",
        "timed_body_materialization": "materialize-view :renderer",
    }.get(lane or "", "")


def _empty_resolution(slot_id: str) -> dict[str, Any]:
    return {
        "slot_id": slot_id,
        "resolution": None,
        "selected_lane": None,
        "selected_renderer": None,
        "local_override": None,
        "evidence": {},
        "diagnostics": [],
    }


def _resolve_override(
    base: dict[str, Any], slot: Mapping[str, Any], selection: Mapping[str, Any]
) -> dict[str, Any]:
    slot_id = base["slot_id"]
    override = selection.get("local_override") or {}
    try:
        descriptor = resolve_view_renderer(
            override.get("renderer_id"), override.get("renderer_version")
        )
    except ViewRendererError:
        base["resolution"] = "requires_override"
        base["diagnostics"].append(
            _diagnostic(
                "rendering_ergonomics_renderer_unknown",
                slot_id,
                "local override names an unregistered renderer",
                local_override=dict(override),
            )
        )
        return base
    if not _shape_accepts(descriptor.accepted_shape, slot.get("value", {})):
        base["resolution"] = "requires_override"
        base["diagnostics"].append(
            _diagnostic(
                "rendering_ergonomics_renderer_shape_mismatch",
                slot_id,
                "local override renderer cannot accept this value shape",
                local_override=dict(override),
                accepted_shape=descriptor.accepted_shape,
            )
        )
        return base
    base["resolution"] = "selected"
    base["selected_renderer"] = {**dict(override), "selection_source": "local_override"}
    base["local_override"] = dict(override)
    return base


def _shape_accepts(accepted_shape: str, value: Mapping[str, Any]) -> bool:
    """Conservative shape gate: canonical-json accepts any pure value."""

    if accepted_shape == "any_pure_value":
        return True
    if accepted_shape == "path_value":
        declared = str(value.get("shape", "")) if isinstance(value, Mapping) else ""
        return declared in {"", "path_value", "path_string"}
    return False


def resolve_renderer_for_slot(slot: Mapping[str, Any]) -> dict[str, Any]:
    """Resolve exactly one registered renderer (or none) for one consumer slot.

    Fail-closed: zero or multiple inferable candidates produce a consumer-slot
    diagnostic and resolution ``requires_override`` rather than a guessed renderer.
    """

    slot_id = str(slot.get("slot_id", ""))
    lane = slot.get("consumer_lane")
    selection = slot.get("renderer_selection", {}) or {}
    mode = selection.get("mode")
    base = _empty_resolution(slot_id)
    base["selected_lane"] = _selected_lane_label(slot)

    if lane == "typed_step" or mode == "none":
        base["resolution"] = "not_rendered"
        return base

    if mode == "override":
        return _resolve_override(base, slot, selection)

    candidates = list(selection.get("allowed_renderers", []))
    if len(candidates) == 1:
        base["resolution"] = "selected"
        base["selected_renderer"] = {
            **dict(candidates[0]),
            "selection_source": "single_consumer_slot_candidate",
        }
        return base
    if not candidates:
        base["resolution"] = "requires_override"
        base["diagnostics"].append(
            _diagnostic(
                "rendering_ergonomics_renderer_required",
                slot_id,
                "no registered renderer can be inferred for this consumer slot",
                value_type=slot.get("value", {}).get("type_name"),
                local_override_surface=_override_surface_for_lane(lane),
            )
        )
        return base
    base["resolution"] = "requires_override"
    base["diagnostics"].append(
        _diagnostic(
            "rendering_ergonomics_renderer_ambiguous",
            slot_id,
            "multiple registered renderers are valid; a local override is required",
            value_type=slot.get("value", {}).get("type_name"),
            candidate_renderers=[dict(c) for c in candidates],
            local_override_surface=_override_surface_for_lane(lane),
        )
    )
    return base


# --------------------------------------------------------------------------- #
# Report assembly: join C0-C5 evidence
# --------------------------------------------------------------------------- #


def _report_present_and_pass(report: Any) -> bool:
    return isinstance(report, Mapping) and report.get("status") == "pass"


def _row_ids(rows: Any, key: str) -> set[str]:
    out: set[str] = set()
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        return out
    for row in rows:
        if isinstance(row, str):
            out.add(row)
        elif isinstance(row, Mapping) and isinstance(row.get(key), str):
            out.add(row[key])
    return out


def _c1_row_ids(report: Mapping[str, Any]) -> set[str]:
    return _row_ids(report.get("selected_rows"), "c0_row_id")


def _c1_row(report: Mapping[str, Any], c0_row_id: str) -> Mapping[str, Any] | None:
    for row in report.get("selected_rows", []) or []:
        if isinstance(row, Mapping) and row.get("c0_row_id") == c0_row_id:
            return row
    return None


def _c4_row_ids(report: Mapping[str, Any]) -> set[str]:
    return _row_ids(report.get("generated_bridges"), "c0_row_id") | _row_ids(
        report.get("blocked_bridges"), "c0_row_id"
    )


def _c5_timed_row_ids(report: Mapping[str, Any]) -> set[str]:
    timed = {
        str(row.get("c0_row_id", ""))
        for row in report.get("cleanup_decisions", []) or []
        if isinstance(row, Mapping)
        and row.get("cleanup_decision") == "KEEP_TIMED_PUBLICATION"
    }
    timed.update(
        str(row_id)
        for row_id in report.get("surviving_body_materialization_row_ids", []) or []
        if isinstance(row_id, str)
    )
    timed.discard("")
    return timed


def _lane_evidence(reports: Mapping[str, Any]) -> dict[str, set[str]]:
    census = reports.get("consumer_rendering_census_report", {})
    c1 = reports.get("typed_prompt_input_report", {})
    c2 = reports.get("observability_summary_report", {})
    c3 = reports.get("entry_publication_report", {})
    c4 = reports.get("compatibility_bridge_report", {})
    c5 = reports.get("rendering_cleanup_report", {})
    return {
        "C1": _c1_row_ids(c1) if isinstance(c1, Mapping) else set(),
        "C2": set(c2.get("selected_c0_row_ids", []) or []) if isinstance(c2, Mapping) else set(),
        "C3": _row_ids(c3.get("selected_c0_rows"), "row_id") if isinstance(c3, Mapping) else set(),
        "C4": _c4_row_ids(c4) if isinstance(c4, Mapping) else set(),
        "C5": _c5_timed_row_ids(c5) if isinstance(c5, Mapping) else set(),
        "census": _active_census_row_ids(census) if isinstance(census, Mapping) else set(),
    }


def _active_census_row_ids(census: Mapping[str, Any]) -> set[str]:
    row_ids: set[str] = set()
    for row in census.get("rows", []):
        if not isinstance(row, Mapping):
            continue
        if (
            str(row.get("consumer_lane", "")) == "retirement_candidate"
            and str(row.get("track_c_decision", "")) == "BLOCKED"
        ):
            continue
        row_id = str(row.get("row_id", ""))
        if row_id:
            row_ids.add(row_id)
    return row_ids


def _check_prompt_slot(
    slot: Mapping[str, Any], c0_row_id: str, reports: Mapping[str, Any], evidence
) -> dict[str, Any] | None:
    if c0_row_id not in evidence["C1"]:
        return _diagnostic(
            "rendering_ergonomics_lane_mismatch",
            slot["slot_id"],
            "prompt slot has no covering C1 typed prompt-input evidence",
            c0_row_id=c0_row_id,
            expected_track_c_lane="C1",
        )
    c1 = reports.get("typed_prompt_input_report", {})
    row = _c1_row(c1, c0_row_id) if isinstance(c1, Mapping) else None
    if row is not None and (
        row.get("prompt_input_file") or row.get("producer_authored_prompt_file")
    ):
        return _diagnostic(
            "rendering_ergonomics_prompt_file_still_required",
            slot["slot_id"],
            "C1 prompt slot still requires a producer-authored prompt-input file",
            c0_row_id=c0_row_id,
        )
    return None


def _check_lane_slot(
    slot: Mapping[str, Any], c0_row_id: str, reports: Mapping[str, Any], evidence
) -> dict[str, Any] | None:
    lane = slot.get("consumer_lane")
    if lane == "typed_step":
        return None
    if lane == "prompt_input":
        return _check_prompt_slot(slot, c0_row_id, reports, evidence)
    if lane == "observability":
        if c0_row_id in evidence["C2"]:
            return None
        return _diagnostic(
            "rendering_ergonomics_lane_mismatch",
            slot["slot_id"],
            "observability slot has no covering C2 summary evidence",
            c0_row_id=c0_row_id,
            expected_track_c_lane="C2",
        )
    if lane == "entry_publication":
        if c0_row_id in evidence["C3"]:
            return None
        return _diagnostic(
            "rendering_ergonomics_publication_not_at_entry_boundary",
            slot["slot_id"],
            "entry publication is not covered by C3 :publish policy",
            c0_row_id=c0_row_id,
        )
    if lane == "compatibility_bridge":
        if c0_row_id in evidence["C4"]:
            return None
        return _diagnostic(
            "rendering_ergonomics_bridge_not_metadata",
            slot["slot_id"],
            "compatibility bridge is not covered by C4 bridge metadata",
            c0_row_id=c0_row_id,
        )
    if lane == "timed_body_materialization":
        if c0_row_id in evidence["C5"] or c0_row_id in evidence["C4"]:
            return None
        return _diagnostic(
            "rendering_ergonomics_body_render_not_timed",
            slot["slot_id"],
            "body-level materialize-view lacks a C5 timed-publication or C4 "
            "compatibility justification",
            c0_row_id=c0_row_id,
            replacement_lane="C1/C2/C3/C4",
        )
    return None


def _authoring_lint_diag(slot: Mapping[str, Any], c0_row_id: str) -> dict[str, Any] | None:
    """Detect author-side command-glue or view-as-state misuse for one slot."""

    implementation = str(slot.get("rendering_implementation", "") or "")
    if implementation in FORBIDDEN_RENDERING_IMPLEMENTATIONS:
        return _diagnostic(
            "rendering_ergonomics_command_glue_forbidden",
            str(slot.get("slot_id", "")),
            "ergonomic rendering must not be implemented via command glue, report "
            "parsing, stdout-as-state, or pointer-as-state",
            c0_row_id=c0_row_id,
            rendering_implementation=implementation,
        )
    value = slot.get("value", {})
    if (
        slot.get("consumer_lane") == "typed_step"
        and isinstance(value, Mapping)
        and value.get("authority") in {"rendered_view", "view"}
    ):
        return _diagnostic(
            "rendering_ergonomics_view_used_as_state",
            str(slot.get("slot_id", "")),
            "a rendered view is consumed as typed semantic state",
            c0_row_id=c0_row_id,
        )
    return None


def rendering_ergonomics_author_lints(
    report: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Surface the author-facing lint subset of a built C6 report.

    The lint hook reuses :func:`build_rendering_ergonomics_report` results so an
    author sees body-render/command-glue/publication/bridge/view-as-state misuse
    under one consumer-slot message naming the replacement lane.
    """

    return [
        dict(diagnostic)
        for diagnostic in report.get("diagnostics", [])
        if isinstance(diagnostic, Mapping)
        and diagnostic.get("code") in RENDERING_ERGONOMICS_AUTHOR_LINT_CODES
    ]


def _contract_isolation(diagnostics: Sequence[Mapping[str, Any]]) -> dict[str, bool]:
    codes = {d.get("code") for d in diagnostics}
    return {
        "typed_steps_do_not_consume_views": "rendering_ergonomics_view_used_as_state"
        not in codes,
        "provider_inputs_use_typed_prompt_lane": codes.isdisjoint(
            {
                "rendering_ergonomics_prompt_file_still_required",
            }
        )
        and not any(
            d.get("code") == "rendering_ergonomics_lane_mismatch"
            and d.get("expected_track_c_lane") == "C1"
            for d in diagnostics
        ),
        "entry_publications_use_publish_policy": "rendering_ergonomics_publication_not_at_entry_boundary"
        not in codes,
        "bridges_use_metadata": "rendering_ergonomics_bridge_not_metadata" not in codes,
        "body_materialize_views_timed_or_compatibility_only": "rendering_ergonomics_body_render_not_timed"
        not in codes,
    }


def _provider_input_slots(slots: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [
        slot
        for slot in slots
        if isinstance(slot.get("source_form"), Mapping)
        and slot["source_form"].get("kind") == "provider_input"
        and isinstance(slot.get("request_shape"), Mapping)
    ]


def _matching_provider_input_observations(
    slot: Mapping[str, Any],
    observations: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    workflow_surface = str(slot.get("workflow_surface", ""))
    c0_row_id = str(slot.get("c0_row_id", ""))
    source_form = slot.get("source_form", {})
    provider_call_locator = (
        str(source_form.get("provider_call_locator", ""))
        if isinstance(source_form, Mapping)
        else ""
    )
    matches: list[Mapping[str, Any]] = []
    for observation in observations:
        if not isinstance(observation, Mapping):
            continue
        if c0_row_id and observation.get("c0_row_id") == c0_row_id:
            matches.append(observation)
            continue
        if workflow_surface and observation.get("workflow_surface") != workflow_surface:
            continue
        if provider_call_locator and observation.get("provider_call_locator") != provider_call_locator:
            continue
        matches.append(observation)
    return matches


def _provider_input_shape_rows(
    *,
    slots: Sequence[Mapping[str, Any]],
    prerequisite_reports: Mapping[str, Any],
    provider_input_observations: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    c1 = prerequisite_reports.get("typed_prompt_input_report", {})
    provider_rows: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []

    for slot in _provider_input_slots(slots):
        c0_row_id = str(slot.get("c0_row_id", ""))
        request_shape = (
            dict(slot.get("request_shape", {}))
            if isinstance(slot.get("request_shape"), Mapping)
            else {}
        )
        expected_request_type = str(request_shape.get("request_type_name", ""))
        expected_subject_type = str(request_shape.get("subject_type_name", ""))
        expected_targets_type = str(request_shape.get("targets_type_name", ""))
        requires_target_split = bool(request_shape.get("requires_target_split"))
        c1_row = _c1_row(c1, c0_row_id) if isinstance(c1, Mapping) else None

        row = {
            "workflow_surface": str(slot.get("workflow_surface", "")),
            "provider_binding": str(
                slot.get("source_form", {}).get("provider_call_locator", "")
                if isinstance(slot.get("source_form"), Mapping)
                else ""
            ),
            "provider_step_id": "",
            "c0_row_id": c0_row_id,
            "u0_row_id": str(slot.get("u0_row_id", "")),
            "request_type_name": expected_request_type,
            "subject_type_name": expected_subject_type,
            "targets_type_name": expected_targets_type,
            "semantic_field_count": 0,
            "write_target_field_count": 0,
            "hidden_bridge_fields": [],
            "binding_names": list(c1_row.get("binding_names", []))
            if isinstance(c1_row, Mapping)
            and isinstance(c1_row.get("binding_names"), Sequence)
            and not isinstance(c1_row.get("binding_names"), (str, bytes))
            else [],
            "selected_lane": _selected_lane_label(slot),
            "status": "pass",
            "diagnostics": [],
        }

        matches = _matching_provider_input_observations(slot, provider_input_observations)
        if len(matches) != 1:
            row_diag = _diagnostic(
                "rendering_ergonomics_provider_request_record_missing",
                str(slot.get("slot_id", "")),
                "provider-input slot could not be matched to exactly one compiled observation",
                c0_row_id=c0_row_id,
                workflow_surface=row["workflow_surface"],
            )
            row["diagnostics"].append(row_diag)
            diagnostics.append(row_diag)
            row["status"] = "fail"
            provider_rows.append(row)
            continue

        observation = matches[0]
        observed_binding_names = observation.get("binding_names")
        if isinstance(observed_binding_names, Sequence) and not isinstance(
            observed_binding_names, (str, bytes)
        ):
            row["binding_names"] = [str(name) for name in observed_binding_names]
        row["provider_step_id"] = str(observation.get("provider_step_id", ""))
        observed_request_type = str(observation.get("value_type_name", ""))
        if observed_request_type:
            row["request_type_name"] = observed_request_type
        request_fields = (
            dict(observation.get("request_fields", {}))
            if isinstance(observation.get("request_fields"), Mapping)
            else {}
        )
        observed_subject_type = str(request_fields.get("subject_type_name", ""))
        observed_targets_type = str(request_fields.get("targets_type_name", ""))
        if observed_subject_type:
            row["subject_type_name"] = observed_subject_type
        if observed_targets_type:
            row["targets_type_name"] = observed_targets_type
        row["semantic_field_count"] = int(request_fields.get("semantic_field_count", 0) or 0)
        row["write_target_field_count"] = int(
            request_fields.get("write_target_field_count", 0) or 0
        )
        observed_hidden_bridge_fields = [
            dict(item)
            for item in request_fields.get("hidden_bridge_fields", [])
            if isinstance(item, Mapping)
        ]
        row["hidden_bridge_fields"] = observed_hidden_bridge_fields

        binding_count = observation.get("binding_count")
        if binding_count != 1:
            row_diag = _diagnostic(
                "rendering_ergonomics_provider_flat_input_list_nontrivial",
                str(slot.get("slot_id", "")),
                "provider-input slot still lowers multiple bindings instead of one request record",
                c0_row_id=c0_row_id,
                binding_count=binding_count,
                binding_names=row["binding_names"],
            )
            row["diagnostics"].append(row_diag)
            diagnostics.append(row_diag)

        if expected_request_type and observed_request_type != expected_request_type:
            row_diag = _diagnostic(
                "rendering_ergonomics_provider_request_record_missing",
                str(slot.get("slot_id", "")),
                "provider-input slot lowered an unexpected request type",
                c0_row_id=c0_row_id,
                expected_request_type=expected_request_type,
                observed_request_type=observed_request_type,
            )
            row["diagnostics"].append(row_diag)
            diagnostics.append(row_diag)

        if expected_subject_type and observed_subject_type != expected_subject_type:
            row_diag = _diagnostic(
                "rendering_ergonomics_provider_request_record_missing",
                str(slot.get("slot_id", "")),
                "provider-input slot lowered an unexpected nested `subject` type",
                c0_row_id=c0_row_id,
                expected_subject_type=expected_subject_type,
                observed_subject_type=observed_subject_type,
            )
            row["diagnostics"].append(row_diag)
            diagnostics.append(row_diag)

        if expected_targets_type and observed_targets_type != expected_targets_type:
            row_diag = _diagnostic(
                "rendering_ergonomics_provider_write_target_unclassified",
                str(slot.get("slot_id", "")),
                "provider-input slot lowered an unexpected nested `targets` type",
                c0_row_id=c0_row_id,
                expected_targets_type=expected_targets_type,
                observed_targets_type=observed_targets_type,
            )
            row["diagnostics"].append(row_diag)
            diagnostics.append(row_diag)

        field_names = {
            str(name)
            for name in request_fields.get("field_names", [])
            if isinstance(name, str)
        }
        has_subject = (
            bool(request_fields.get("has_subject"))
            or "subject" in field_names
            or bool(observed_subject_type)
        )
        has_targets = (
            bool(request_fields.get("has_targets"))
            or "targets" in field_names
            or bool(observed_targets_type)
        )
        unexpected_fields = sorted(field_names - {"subject", "targets"})
        if not has_subject or unexpected_fields:
            row_diag = _diagnostic(
                "rendering_ergonomics_provider_request_subject_mixed_with_targets",
                str(slot.get("slot_id", "")),
                "provider request must isolate semantic prompt facts under `subject`",
                c0_row_id=c0_row_id,
                unexpected_fields=unexpected_fields,
            )
            row["diagnostics"].append(row_diag)
            diagnostics.append(row_diag)

        if requires_target_split and not has_targets:
            row_diag = _diagnostic(
                "rendering_ergonomics_provider_write_target_unclassified",
                str(slot.get("slot_id", "")),
                "provider request is missing the required `targets` split for write destinations",
                c0_row_id=c0_row_id,
            )
            row["diagnostics"].append(row_diag)
            diagnostics.append(row_diag)

        expected_hidden_bridge_fields = [
            dict(item)
            for item in request_shape.get("hidden_bridge_fields", [])
            if isinstance(item, Mapping)
        ]
        for expected_field in expected_hidden_bridge_fields:
            field_path = str(expected_field.get("field_path", ""))
            observed_field = next(
                (
                    item
                    for item in observed_hidden_bridge_fields
                    if str(item.get("field_path", "")) == field_path
                ),
                None,
            )
            if observed_field is None:
                row_diag = _diagnostic(
                    "rendering_ergonomics_provider_hidden_bridge_field_missing",
                    str(slot.get("slot_id", "")),
                    "provider request is missing a required hidden compatibility-bridge field",
                    c0_row_id=c0_row_id,
                    field_path=field_path,
                )
                row["diagnostics"].append(row_diag)
                diagnostics.append(row_diag)
                continue
            mismatched_field = next(
                (
                    key
                    for key in ("authority_class", "source_binding", "bridge_field_name")
                    if expected_field.get(key) != observed_field.get(key)
                ),
                None,
            )
            if mismatched_field is not None:
                row_diag = _diagnostic(
                    "rendering_ergonomics_provider_hidden_bridge_field_mismatch",
                    str(slot.get("slot_id", "")),
                    "provider request hidden compatibility-bridge field metadata drifted",
                    c0_row_id=c0_row_id,
                    field_path=field_path,
                    mismatch_field=mismatched_field,
                    expected_value=expected_field.get(mismatched_field),
                    observed_value=observed_field.get(mismatched_field),
                )
                row["diagnostics"].append(row_diag)
                diagnostics.append(row_diag)

        if row["diagnostics"]:
            row["status"] = "fail"
        provider_rows.append(row)

    return provider_rows, diagnostics


def build_rendering_ergonomics_report(
    *,
    policy: Mapping[str, Any],
    prerequisite_reports: Mapping[str, Any],
    provider_input_observations: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Join C0-C5 evidence and validate every author-facing consumer slot."""

    diagnostics: list[dict[str, Any]] = []
    slots = [s for s in policy.get("consumer_slots", []) if isinstance(s, Mapping)]

    for report_key, _schema_key in PREREQUISITE_REPORTS:
        if not _report_present_and_pass(prerequisite_reports.get(report_key)):
            diagnostics.append(
                {
                    "code": "rendering_ergonomics_prerequisite_missing",
                    "report": report_key,
                    "message": "prerequisite Track-C report is missing or not passing",
                }
            )

    evidence = _lane_evidence(prerequisite_reports)
    slots_by_row = {str(s.get("c0_row_id", "")): s for s in slots}

    for row_id in sorted(evidence["census"]):
        if row_id not in slots_by_row:
            diagnostics.append(
                {
                    "code": "rendering_ergonomics_consumer_slot_missing",
                    "c0_row_id": row_id,
                    "message": "selected C0 rendering row has no C6 consumer slot",
                }
            )

    renderer_resolutions: list[dict[str, Any]] = []
    body_render_lints: list[dict[str, Any]] = []
    for slot in sorted(slots, key=lambda s: str(s.get("slot_id", ""))):
        c0_row_id = str(slot.get("c0_row_id", ""))
        author_diag = _authoring_lint_diag(slot, c0_row_id)
        if author_diag is not None:
            diagnostics.append(author_diag)
            if author_diag["code"] in _BODY_RENDER_LINT_CODES:
                body_render_lints.append(author_diag)
        lane_diag = _check_lane_slot(slot, c0_row_id, prerequisite_reports, evidence)
        if lane_diag is not None:
            diagnostics.append(lane_diag)
            if lane_diag["code"] in _BODY_RENDER_LINT_CODES:
                body_render_lints.append(lane_diag)
        resolution = resolve_renderer_for_slot(slot)
        resolution["selected_lane"] = _selected_lane_label(slot)
        resolution["evidence"] = {
            "c0_row_id": c0_row_id,
            "u0_row_id": slot.get("u0_row_id"),
            "source_map_origin_key": slot.get("source_form", {}).get(
                "source_map_origin_key"
            ),
        }
        diagnostics.extend(resolution["diagnostics"])
        renderer_resolutions.append(resolution)

    provider_input_shapes, provider_input_diagnostics = _provider_input_shape_rows(
        slots=slots,
        prerequisite_reports=prerequisite_reports,
        provider_input_observations=provider_input_observations,
    )
    diagnostics.extend(provider_input_diagnostics)
    diagnostics.sort(key=lambda d: (str(d.get("code", "")), str(d.get("c0_row_id", d.get("slot_id", "")))))
    return {
        "schema_version": RENDERING_ERGONOMICS_REPORT_SCHEMA_VERSION,
        "status": "pass" if not diagnostics else "fail",
        "target_family": policy.get("target_family", ""),
        "source_census": dict(policy.get("source_census", {})),
        "consumer_rendering_census": dict(policy.get("source_consumer_rendering_census", {})),
        "prerequisite_reports": _prerequisite_summaries(prerequisite_reports),
        "consumer_slots": [dict(s) for s in slots],
        "renderer_resolutions": renderer_resolutions,
        "provider_input_shapes": provider_input_shapes,
        "body_render_lints": body_render_lints,
        "contract_isolation": _contract_isolation(diagnostics),
        "diagnostics": diagnostics,
    }


def _selected_lane_label(slot: Mapping[str, Any]) -> str:
    return {
        "prompt_input": "C1_TYPED_PROMPT_INPUT",
        "observability": "C2_OBSERVABILITY_SUMMARY",
        "entry_publication": "C3_ENTRY_PUBLICATION",
        "compatibility_bridge": "C4_COMPATIBILITY_BRIDGE",
        "timed_body_materialization": "C5_TIMED_BODY_MATERIALIZATION",
        "typed_step": "TYPED_STEP",
    }.get(str(slot.get("consumer_lane", "")), "")


def _prerequisite_summaries(reports: Mapping[str, Any]) -> dict[str, Any]:
    summaries: dict[str, Any] = {}
    for report_key, schema_key in PREREQUISITE_REPORTS:
        report = reports.get(report_key)
        if isinstance(report, Mapping):
            summaries[report_key] = {
                "status": str(report.get("status", "")),
                "schema_version": str(report.get(schema_key, "")),
                "path": str(report.get("path", "")),
            }
        else:
            summaries[report_key] = {"status": "missing", "schema_version": "", "path": ""}
    return summaries
