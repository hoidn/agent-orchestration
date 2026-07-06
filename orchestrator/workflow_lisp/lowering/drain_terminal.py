"""Shared terminal-finalization helper for backlog-drain lowering."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from orchestrator.workflow.references import MaterializeViewBindingReference
from orchestrator.workflow.state_layout import GeneratedPathSemanticRole
from orchestrator.workflow.transition_contract import validate_transition_declaration
from orchestrator.workflow.view_renderer import VIEW_RENDERER_SCHEMA_VERSION

from . import core as lowering_core
from .context import _LoweringContext, _TerminalResult
from .generated_paths import allocate_generated_result_bundle, allocate_private_generated_path
from .origins import GeneratedSemanticEffectBinding, LoweringOrigin


def _normalize_generated_step_id(*args, **kwargs):
    return lowering_core._normalize_generated_step_id(*args, **kwargs)


def _record_step_origin(*args, **kwargs):
    return lowering_core._record_step_origin(*args, **kwargs)


def _origin_from_context_source(*args, **kwargs):
    return lowering_core._origin_from_context_source(*args, **kwargs)


def _materialize_outputs_step(*args, **kwargs):
    return lowering_core._materialize_values_step(*args, **kwargs)


def _drain_terminal_transition_config(
    *,
    state_path: str,
    audit_path: str,
    request_bindings: Mapping[str, Any],
    blocker_allowed_values: tuple[str, ...],
) -> dict[str, Any]:
    string_descriptor = {"kind": "primitive", "name": "String"}
    int_descriptor = {"kind": "primitive", "name": "Int"}
    bool_descriptor = {"kind": "primitive", "name": "Bool"}
    progress_descriptor = {"kind": "path", "name": "std/resource::WorkReport"}
    blocker_descriptor = {
        "kind": "enum",
        "name": "std/resource::BlockerClass",
        "allowed": list(blocker_allowed_values),
    }

    def _record_descriptor(name: str) -> dict[str, Any]:
        return {
            "kind": "record",
            "name": name,
            "fields": [
                {"name": "variant", "type": dict(string_descriptor)},
                {"name": "items_processed", "type": dict(int_descriptor)},
                {"name": "progress_report_path", "type": dict(progress_descriptor)},
                {"name": "blocker_class", "type": dict(blocker_descriptor)},
                {"name": "has_blocker", "type": dict(bool_descriptor)},
            ],
        }

    state_type = _record_descriptor("std/drain::DrainOutcomeState")
    request_type = _record_descriptor("std/drain::DrainOutcomeRequest")
    result_type = _record_descriptor("std/drain::DrainOutcomeResult")
    audit_type = _record_descriptor("std/drain::DrainOutcomeAudit")

    def _binding_field(field_name: str) -> dict[str, Any]:
        return {
            "kind": "field_access",
            "base": {"kind": "binding", "name": "request"},
            "field": field_name,
        }

    def _pure_payload(result_type_descriptor: Mapping[str, Any], expr_payload: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "pure_expr_schema_version": 1,
            "result_type": dict(result_type_descriptor),
            "bindings": {
                "request": {"type": dict(request_type)},
                "state": {"type": dict(state_type)},
            },
            "expr": dict(expr_payload),
        }

    def _record_projection(record_type: Mapping[str, Any]) -> dict[str, Any]:
        return _pure_payload(
            record_type,
            {
                "kind": "record",
                "type": dict(record_type),
                "fields": [
                    {"name": "variant", "value": _binding_field("variant")},
                    {"name": "items_processed", "value": _binding_field("items_processed")},
                    {"name": "progress_report_path", "value": _binding_field("progress_report_path")},
                    {"name": "blocker_class", "value": _binding_field("blocker_class")},
                    {"name": "has_blocker", "value": _binding_field("has_blocker")},
                ],
            },
        )

    declaration = validate_transition_declaration(
        {
            "transition_schema_version": 1,
            "resource": {
                "resource_kind": "drain_run_state",
                "state_type": state_type,
                "backing": {"kind": "state_layout"},
            },
            "transition": {
                "name": "record-drain-outcome",
                "request_type": request_type,
                "result_type": result_type,
                "preconditions": [
                    _pure_payload(
                        bool_descriptor,
                        {
                            "kind": "op",
                            "operator": "!=",
                            "args": [
                                _binding_field("variant"),
                                {
                                    "kind": "literal",
                                    "type": dict(string_descriptor),
                                    "value": "",
                                },
                            ],
                        },
                    )
                ],
                "updates": [
                    {"op": "set_field", "target": "variant", "value": _pure_payload(string_descriptor, _binding_field("variant"))},
                    {"op": "set_field", "target": "items_processed", "value": _pure_payload(int_descriptor, _binding_field("items_processed"))},
                    {"op": "set_field", "target": "progress_report_path", "value": _pure_payload(progress_descriptor, _binding_field("progress_report_path"))},
                    {"op": "set_field", "target": "blocker_class", "value": _pure_payload(blocker_descriptor, _binding_field("blocker_class"))},
                    {"op": "set_field", "target": "has_blocker", "value": _pure_payload(bool_descriptor, _binding_field("has_blocker"))},
                ],
                "write_set": [
                    "variant",
                    "items_processed",
                    "progress_report_path",
                    "blocker_class",
                    "has_blocker",
                ],
                "idempotency_fields": [
                    "variant",
                    "items_processed",
                    "progress_report_path",
                    "blocker_class",
                    "has_blocker",
                ],
                "result_projection": _record_projection(result_type),
                "audit_projection": _record_projection(audit_type),
                "conflict_policy": "fail_closed",
                "backend": {"kind": "runtime_native"},
            },
        }
    )
    return {
        "declaration": declaration,
        "resource": {
            "resource_id": "drain-run-state",
            "resource_kind": "drain_run_state",
            "state_path": state_path,
            "audit_path": audit_path,
        },
        "request_bindings": dict(request_bindings),
    }


def lower_shared_drain_terminal_result(
    *,
    context: _LoweringContext,
    source_expr: Any,
    step_name_prefix: str,
    terminal_variant: str,
    terminal_items_ref: str,
    terminal_progress_ref: str,
    terminal_blocker_ref: str,
    result_output_contracts: Mapping[str, Mapping[str, Any]],
    accumulator_progress_contract: Mapping[str, Any],
    accumulator_blocker_contract: Mapping[str, Any],
    placeholder_blocker_value: str,
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    result_variant = "BLOCKED" if terminal_variant == "EXHAUSTED" else terminal_variant
    has_blocker = result_variant == "BLOCKED"
    transition_step_name = f"{step_name_prefix}__shared_drain_result"
    transition_step_id = _normalize_generated_step_id(transition_step_name)
    bundle_allocation = allocate_generated_result_bundle(
        context=context,
        source_expr=source_expr,
        step_name=transition_step_name,
        step_id=transition_step_id,
        semantic_role=GeneratedPathSemanticRole.COMMAND_RESULT_BUNDLE,
    )
    state_allocation = allocate_private_generated_path(
        context=context,
        source_expr=source_expr,
        semantic_role=GeneratedPathSemanticRole.RESOURCE_STATE,
        stable_target=f"{transition_step_name}_drain_run_state",
    )
    audit_allocation = allocate_private_generated_path(
        context=context,
        source_expr=source_expr,
        semantic_role=GeneratedPathSemanticRole.TRANSITION_AUDIT,
        stable_target=f"{transition_step_name}_record_drain_outcome",
    )
    hidden_inputs: dict[str, LoweringOrigin] = {}
    if bundle_allocation.generated_input_name is not None:
        hidden_inputs[bundle_allocation.generated_input_name] = _origin_from_context_source(context, source_expr)
    transition_output_fields = [
        {
            "name": "variant",
            "json_pointer": "/result/variant",
            "kind": "scalar",
            "type": "string",
        },
        {
            "name": "items_processed",
            "json_pointer": "/result/items_processed",
            "kind": "scalar",
            "type": "integer",
        },
        {
            "name": "progress_report_path",
            "json_pointer": "/result/progress_report_path",
            **dict(accumulator_progress_contract),
        },
        {
            "name": "blocker_class",
            "json_pointer": "/result/blocker_class",
            **dict(accumulator_blocker_contract),
        },
        {
            "name": "has_blocker",
            "json_pointer": "/result/has_blocker",
            "kind": "scalar",
            "type": "bool",
        },
    ]
    transition_step = {
        "name": transition_step_name,
        "id": transition_step_id,
        "resource_transition": _drain_terminal_transition_config(
            state_path=state_allocation.concrete_path_template,
            audit_path=audit_allocation.concrete_path_template,
            request_bindings={
                "variant": result_variant,
                "items_processed": {"ref": terminal_items_ref},
                "progress_report_path": {"ref": terminal_progress_ref},
                "blocker_class": {"ref": terminal_blocker_ref},
                "has_blocker": has_blocker,
            },
            blocker_allowed_values=tuple(accumulator_blocker_contract["allowed"]),
        ),
        "output_bundle": {
            "path": bundle_allocation.concrete_path_template,
            "fields": transition_output_fields,
        },
    }
    summary_step_name = f"{transition_step_name}__summary"
    summary_step_id = _normalize_generated_step_id(summary_step_name)
    summary_output_contract = dict(accumulator_progress_contract)
    summary_output_contract["must_exist_target"] = True
    summary_value_type = {
        "kind": "record",
        "name": "DrainSummaryValue",
        "fields": [
            {"name": "variant", "type": {"kind": "primitive", "name": "String"}},
            {"name": "items_processed", "type": {"kind": "primitive", "name": "Int"}},
            {"name": "progress_report_path", "type": {"kind": "path", "name": "WorkReport"}},
            {"name": "blocker_class", "type": {"kind": "enum", "name": "BlockerClass"}},
            {"name": "has_blocker", "type": {"kind": "primitive", "name": "Bool"}},
        ],
    }
    summary_value_document = {
        "variant": MaterializeViewBindingReference(ref=f"self.steps.{transition_step_name}.artifacts.variant"),
        "items_processed": MaterializeViewBindingReference(
            ref=f"self.steps.{transition_step_name}.artifacts.items_processed"
        ),
        "progress_report_path": MaterializeViewBindingReference(
            ref=terminal_progress_ref
        ),
        "blocker_class": MaterializeViewBindingReference(
            ref=f"self.steps.{transition_step_name}.artifacts.blocker_class"
        ),
        "has_blocker": MaterializeViewBindingReference(
            ref=f"self.steps.{transition_step_name}.artifacts.has_blocker"
        ),
    }
    context.generated_semantic_effects.append(
        GeneratedSemanticEffectBinding(
            effect_key=f"materialize_view:{summary_step_id}",
            step_id=summary_step_id,
            effect_kind="materialize_view",
            origin=_origin_from_context_source(context, source_expr),
            details={
                "renderer_id": "canonical-json",
                "renderer_version": 1,
                "view_renderer_schema_version": VIEW_RENDERER_SCHEMA_VERSION,
                "value_type": summary_value_type,
                "target_path": {"ref": terminal_progress_ref},
                "target_allocation_id": None,
                "authority_class": "materialized_view",
            },
        )
    )
    summary_step = {
        "name": summary_step_name,
        "id": summary_step_id,
        "materialize_view": {
            "renderer_id": "canonical-json",
            "renderer_version": 1,
            "view_renderer_schema_version": VIEW_RENDERER_SCHEMA_VERSION,
            "value_type": summary_value_type,
            "value_document": summary_value_document,
            "target_path": {"ref": terminal_progress_ref},
            "target_allocation_id": None,
            "authority_class": "materialized_view",
            "output_contracts": {"return": summary_output_contract},
        },
    }
    result_step_name = f"{transition_step_name}__result"
    result_step_id = _normalize_generated_step_id(result_step_name)
    result_values = [
        {
            "name": "return__variant",
            "source": {"literal": result_variant},
            "contract": dict(result_output_contracts["return__variant"]),
        },
    ]
    result_values.extend(
        [
            {
                "name": "return__items-processed",
                "source": {"ref": terminal_items_ref},
                "contract": dict(result_output_contracts["return__items-processed"]),
            },
            {
                "name": "return__progress-report-path",
                "source": {"ref": terminal_progress_ref},
                "contract": dict(result_output_contracts["return__progress-report-path"]),
            },
            {
                "name": "return__blocker-class",
                "source": (
                    {"ref": terminal_blocker_ref}
                    if has_blocker
                    else {"literal": placeholder_blocker_value}
                ),
                "contract": dict(result_output_contracts["return__blocker-class"]),
            },
        ]
    )
    result_step = _materialize_outputs_step(
        step_name=result_step_name,
        step_id=result_step_id,
        values=result_values,
    )
    _record_step_origin(context, step_name=transition_step_name, step_id=transition_step_id, source=source_expr)
    _record_step_origin(context, step_name=summary_step_name, step_id=summary_step_id, source=source_expr)
    _record_step_origin(context, step_name=result_step_name, step_id=result_step_id, source=source_expr)
    return [result_step, transition_step, summary_step], _TerminalResult(
        step_name=result_step_name,
        step_id=result_step_id,
        output_refs={
            output_name: f"self.steps.{result_step_name}.artifacts.{output_name}"
            for output_name in result_output_contracts
        },
        output_kind="projection",
        hidden_inputs=hidden_inputs,
    )
