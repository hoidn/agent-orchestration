"""Phase-resource owner surface for stdlib lowering."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle, workflow_managed_write_root_inputs
from orchestrator.workflow.references import StructuredStepReference
from orchestrator.workflow.state_layout import GeneratedPathSemanticRole
from orchestrator.workflow.surface_ast import SurfaceStep
from orchestrator.workflow.transition_contract import validate_transition_declaration

from ..contracts import derive_reusable_state_contract_metadata, derive_structured_result_contract, derive_workflow_boundary_fields
from ..diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from ..expressions import (
    BacklogDrainExpr,
    BindProcExpr,
    CallExpr,
    CommandResultExpr,
    ContinueExpr,
    DoneExpr,
    FieldAccessExpr,
    FinalizeSelectedItemExpr,
    GeneratedRelpathSeedExpr,
    IfExpr,
    LetStarExpr,
    LiteralExpr,
    LoopRecurExpr,
    MatchExpr,
    NameExpr,
    PhaseTargetExpr,
    ProcRefLiteralExpr,
    ProcedureCallExpr,
    ProduceOneOfExpr,
    ProviderResultExpr,
    RecordExpr,
    ResourceTransitionExpr,
    ResumeOrStartExpr,
    RunProviderPhaseExpr,
    UnionVariantExpr,
    WorkflowRefLiteralExpr,
    WithPhaseExpr,
)
from ..phase import IMPLEMENTATION_ATTEMPT_PHASE_NAME, PHASE_TARGET_SPECS, PhaseScope
from ..procedure_refs import ResolvedProcRefValue, resolve_proc_ref_value
from ..procedures import ProcedureCatalog
from ..spans import SourceSpan
from ..type_env import ListTypeRef, MapTypeRef, OptionalTypeRef, PathTypeRef, PrimitiveTypeRef, ProcRefTypeRef, RecordTypeRef, TypeRef, UnionTypeRef
from ..typecheck import TypedExpr
from ..workflow_refs import ResolvedWorkflowRef, resolve_workflow_ref_literal, resolve_workflow_ref_name, workflow_ref_target_name
from ..workflows import CertifiedAdapterBinding, PromptExtern, ProviderExtern, analyze_workflow_boundary_type
from . import core as lowering_core
from .context import (
    _ActivePhaseScope,
    _copy_context_with_phase_scope,
    _copy_context_with_step_prefix,
    _LoweringContext,
    _TerminalResult,
)
from .effects import _lower_provider_result
from .generated_paths import allocate_generated_result_bundle, allocate_materialized_value_view, allocate_private_generated_path
from .phase_drain import _selected_item_summary_pointer_path
from .phase_flow import _build_match_projection_anchor_step
from .origins import LoweringOrigin, _rekey_origin_map
from .pure_projection import build_pure_projection_payload, _infer_expr_type as _infer_pure_projection_expr_type, _output_bundle_fields, _output_contracts_for_type
from .phase_scope import _resolve_signature_expr_type
from .values import _render_existing_output_ref, _resolve_inline_expr_value


def _compile_error(*args, **kwargs):
    return lowering_core._compile_error(*args, **kwargs)


def _normalize_generated_step_id(*args, **kwargs):
    return lowering_core._normalize_generated_step_id(*args, **kwargs)


def _record_step_origin(*args, **kwargs):
    return lowering_core._record_step_origin(*args, **kwargs)


def _origin_from_context_source(*args, **kwargs):
    return lowering_core._origin_from_context_source(*args, **kwargs)


def _record_output_refs(*args, **kwargs):
    return lowering_core._record_output_refs(*args, **kwargs)


def _record_missing_step_origins(*args, **kwargs):
    return lowering_core._record_missing_step_origins(*args, **kwargs)


def _materialize_values_step(*args, **kwargs):
    return lowering_core._materialize_values_step(*args, **kwargs)


def _conditional_case_ref(*args, **kwargs):
    return lowering_core._conditional_case_ref(*args, **kwargs)


def _render_boolean_predicate(*args, **kwargs):
    return lowering_core._render_boolean_predicate(*args, **kwargs)


def _template_for_ref(ref: str) -> str:
    if ref.startswith("${"):
        return ref
    return "${" + ref + "}"


def _lower_expression(*args, **kwargs):
    return lowering_core._lower_expression(*args, **kwargs)


def _lower_call_expr(*args, **kwargs):
    return lowering_core._lower_call_expr(*args, **kwargs)


def _render_call_binding_ref(*args, **kwargs):
    return lowering_core._render_call_binding_ref(*args, **kwargs)


def _required_output_contract(
    context: _LoweringContext,
    field_name: str,
    source_expr: Any,
) -> Mapping[str, Any]:
    """Return a declared workflow output contract or raise a frontend error."""

    contract = context.return_output_contracts.get(field_name)
    if contract is None:
        raise _compile_error(
            code="workflow_return_not_exportable",
            message=f"missing lowered workflow return contract for `{field_name}`",
            span=source_expr.span,
            form_path=source_expr.form_path,
        )
    return contract


def _render_record_call_bindings(*args, **kwargs):
    return lowering_core._render_record_call_bindings(*args, **kwargs)


def _flatten_boundary_leaf_paths(*args, **kwargs):
    return lowering_core._flatten_boundary_leaf_paths(*args, **kwargs)


def _record_expr_value_at_path(*args, **kwargs):
    return lowering_core._record_expr_value_at_path(*args, **kwargs)


def _normalize_union_field_path(*args, **kwargs):
    return lowering_core._normalize_union_field_path(*args, **kwargs)


def _union_variant_expr_value_at_path(*args, **kwargs):
    return lowering_core._union_variant_expr_value_at_path(*args, **kwargs)


def _phase_target_inline_ref(*args, **kwargs):
    return lowering_core._phase_target_inline_ref(*args, **kwargs)


def _join_ref_path(*args, **kwargs):
    return lowering_core._join_ref_path(*args, **kwargs)


def _resolve_nested_local_value(*args, **kwargs):
    return lowering_core._resolve_nested_local_value(*args, **kwargs)




def _lower_resource_transition(*args, **kwargs):
    return _phase_stdlib_lower_resource_transition_impl(*args, **kwargs)

def _lower_finalize_selected_item(*args, **kwargs):
    return _phase_stdlib_lower_finalize_selected_item_impl(*args, **kwargs)

def _phase_stdlib_lower_resource_transition_impl(
    typed_expr: TypedExpr,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    """Lower a resource move into a typed certified-adapter command.

    `resource-transition` is the frontend form for queue/item movement plus
    any associated ledger update. The current backend is a named Python adapter
    with declared inputs, outputs, and effects, so workflow source does not need
    inline Python to move files or reconstruct run state.
    """

    expr = typed_expr.expr
    assert isinstance(expr, ResourceTransitionExpr)
    step_name = context.step_name_prefix
    step_id = _normalize_generated_step_id(step_name)
    if expr.spec.mode == "declared_transition":
        bundle_allocation = allocate_generated_result_bundle(
            context=context,
            source_expr=expr,
            step_name=step_name,
            step_id=step_id,
            semantic_role=GeneratedPathSemanticRole.COMMAND_RESULT_BUNDLE,
        )
        state_allocation = allocate_private_generated_path(
            context=context,
            source_expr=expr,
            semantic_role=GeneratedPathSemanticRole.RESOURCE_STATE,
            stable_target=f"{expr.spec.resource_ref_name or 'resource'}_state",
        )
        audit_allocation = allocate_private_generated_path(
            context=context,
            source_expr=expr,
            semantic_role=GeneratedPathSemanticRole.TRANSITION_AUDIT,
            stable_target=f"{expr.spec.transition_ref_name or 'transition'}_audit",
        )
        _record_step_origin(context, step_name=step_name, step_id=step_id, source=expr)
        resource_transition = _declared_resource_transition_config(
            typed_expr,
            context=context,
            local_values=local_values,
            state_path=state_allocation.concrete_path_template,
            audit_path=audit_allocation.concrete_path_template,
        )
        output_contracts = _output_contracts_for_type(
            typed_expr.type_ref,
            context=context,
            span=expr.span,
            form_path=expr.form_path,
        )
        output_fields = _output_bundle_fields(output_contracts)
        if isinstance(typed_expr.type_ref, RecordTypeRef):
            output_fields = [
                {
                    **field,
                    "name": field["name"].removeprefix("return__"),
                }
                for field in output_fields
            ]
        step = {
            "name": step_name,
            "id": step_id,
            "resource_transition": resource_transition,
            "output_bundle": {
                "path": bundle_allocation.concrete_path_template,
                "fields": output_fields,
            },
        }
        return [step], _TerminalResult(
            step_name=step_name,
            step_id=step_id,
            output_refs=_record_output_refs(step_name, typed_expr.type_ref),
            output_kind="step",
            hidden_inputs={bundle_allocation.generated_input_name: _origin_from_context_source(context, expr)},
        )

    binding = context.command_boundary_environment.bindings_by_name["apply_resource_transition"]
    bundle_contract = derive_structured_result_contract(
        typed_expr.type_ref,
        workflow_name=context.workflow_name,
        step_id=step_name,
        span=expr.span,
        form_path=expr.form_path,
    )
    allocation = allocate_generated_result_bundle(
        context=context,
        source_expr=expr,
        step_name=step_name,
        step_id=step_id,
        semantic_role=GeneratedPathSemanticRole.COMMAND_RESULT_BUNDLE,
    )
    authored_contract = dict(bundle_contract.payload)
    authored_contract["path"] = allocation.concrete_path_template
    _record_step_origin(context, step_name=step_name, step_id=step_id, source=expr)
    payload = _resource_transition_payload(expr, context=context, local_values=local_values)
    step = {
        "name": step_name,
        "id": step_id,
        "command": [*binding.stable_command, json.dumps(payload)],
        bundle_contract.contract_kind: authored_contract,
    }
    when = _render_boolean_predicate(expr.spec.when_expr, local_values=local_values)
    if when is not None:
        step["when"] = when
    return [step], _TerminalResult(
        step_name=step_name,
        step_id=step_id,
        output_refs=_record_output_refs(step_name, typed_expr.type_ref),
        output_kind="step",
        hidden_inputs={allocation.generated_input_name: _origin_from_context_source(context, expr)},
    )



def _phase_stdlib_lower_finalize_selected_item_impl(
    typed_expr: TypedExpr,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    """Lower selected-item finalization into typed routing steps.

    The selected-item workflow has several possible terminal causes: completed
    implementation, selection rejection, roadmap block, plan block, or
    implementation block. This helper emits the branch logic and state
    materialization needed to return one `SelectedItemResult` union instead of
    scattering that logic across handwritten scripts.
    """

    expr = typed_expr.expr
    assert isinstance(expr, FinalizeSelectedItemExpr)
    roadmap_value = _resolve_inline_expr_value(expr.spec.roadmap_expr, local_values=local_values)
    plan_value = _resolve_inline_expr_value(expr.spec.plan_expr, local_values=local_values)
    implementation_value = _resolve_inline_expr_value(expr.spec.implementation_expr, local_values=local_values)
    selected_value = _resolve_inline_expr_value(expr.spec.selected_expr, local_values=local_values)
    queue_transition_value = _resolve_inline_expr_value(expr.spec.queue_transition_expr, local_values=local_values)
    if not all(
        isinstance(value, Mapping)
        for value in (roadmap_value, plan_value, implementation_value, selected_value, queue_transition_value)
    ):
        raise _compile_error(
            code="workflow_return_not_exportable",
            message="`finalize-selected-item` lowering requires prior structured results and selected-item inputs",
            span=expr.span,
            form_path=expr.form_path,
        )
    step_name = context.step_name_prefix
    step_id = _normalize_generated_step_id(step_name)
    run_state_ref = selected_value.get("final-plan-gate-state")
    roadmap_status_ref = roadmap_value.get("status")
    plan_variant_ref = plan_value.get("variant")
    plan_summary_ref = plan_value.get("progress-report-path")
    plan_blocker_ref = plan_value.get("blocker-class")
    implementation_variant_ref = implementation_value.get("variant")
    implementation_summary_ref = implementation_value.get("execution-report-path")
    implementation_blocked_summary_ref = implementation_value.get("progress-report-path")
    implementation_blocker_ref = implementation_value.get("blocker-class")
    queue_transition_id_ref = queue_transition_value.get("transition-id")
    if not all(
        isinstance(ref, str)
        for ref in (
            run_state_ref,
            roadmap_status_ref,
            plan_variant_ref,
            plan_summary_ref,
            plan_blocker_ref,
            implementation_variant_ref,
            implementation_summary_ref,
            implementation_blocked_summary_ref,
            implementation_blocker_ref,
            queue_transition_id_ref,
        )
    ):
        raise _compile_error(
            code="workflow_return_not_exportable",
            message="`finalize-selected-item` lowering requires roadmap, plan, implementation, queue-transition, and selection refs",
            span=expr.span,
            form_path=expr.form_path,
        )
    summary_contract = dict(_required_output_contract(context, "summary-path", expr))
    run_state_contract = dict(_required_output_contract(context, "run-state", expr))
    variant_contract = dict(_required_output_contract(context, "variant", expr))
    blocker_contract = context.return_output_contracts.get("blocker-class")
    if blocker_contract is None:
        raise _compile_error(
            code="workflow_return_not_exportable",
            message="`finalize-selected-item` requires the `SelectedItemResult.blocker-class` contract",
            span=expr.span,
            form_path=expr.form_path,
        )
    summary_artifact_name = "selected_item_summary"
    summary_pointer_path = _selected_item_summary_pointer_path(context.workflow_name)
    context.top_level_artifacts[summary_artifact_name] = {
        **summary_contract,
        "pointer": summary_pointer_path,
    }
    allocate_materialized_value_view(
        context=context,
        source_expr=expr,
        path_template=summary_pointer_path,
        stable_target="selected_item_summary",
    )
    selected_active_value = selected_value.get("is-active")
    placeholder_blocker_value = blocker_contract["allowed"][0]
    result_output_definitions = {
        "return__variant": dict(variant_contract),
        "return__summary-path": dict(summary_contract),
        "return__run-state": dict(run_state_contract),
        "return__blocker-class": dict(blocker_contract),
    }

    def _when_from_value(value: Any) -> dict[str, Any] | None:
        if isinstance(value, LiteralExpr):
            operand: bool | dict[str, str] = bool(value.value)
        elif isinstance(value, str):
            operand = {"ref": value}
        else:
            return None
        return {
            "compare": {
                "left": operand,
                "op": "eq",
                "right": True,
            }
        }

    queue_transition_materialize_step = {
        "name": "FinalizeSelectedItemQueueTransition",
        "id": _normalize_generated_step_id("FinalizeSelectedItemQueueTransition"),
        "materialize_artifacts": {
            "values": [
                {
                    "name": "queue_transition_id",
                    "source": {"ref": queue_transition_id_ref},
                    "contract": {"kind": "scalar", "type": "string"},
                }
            ],
        },
    }
    queue_transition_when = _when_from_value(selected_active_value)
    if queue_transition_when is not None:
        queue_transition_materialize_step["when"] = queue_transition_when
    _record_step_origin(
        context,
        step_name=queue_transition_materialize_step["name"],
        step_id=queue_transition_materialize_step["id"],
        source=expr,
    )

    def _outcome_values(*, variant: str, summary_ref: str, include_blocker_ref: str | None) -> list[dict[str, Any]]:
        values: list[dict[str, Any]] = [
            {
                "name": "return__variant",
                "source": {"literal": variant},
                "contract": dict(variant_contract),
            },
            {
                "name": "return__summary-path",
                "source": {"ref": summary_ref},
                "contract": dict(summary_contract),
            },
            {
                "name": "return__run-state",
                "source": {"ref": run_state_ref},
                "contract": dict(run_state_contract),
            },
            {
                "name": "roadmap_status",
                "source": {"ref": roadmap_status_ref},
                "contract": {"kind": "scalar", "type": "string"},
            },
        ]
        if include_blocker_ref is not None:
            values.append(
                {
                    "name": "return__blocker-class",
                    "source": {"ref": include_blocker_ref},
                    "contract": dict(blocker_contract),
                }
            )
        return values

    def _publish_summary_step(*, name: str, summary_ref: str) -> dict[str, Any]:
        return {
            "name": name,
            "id": _normalize_generated_step_id(name),
            "materialize_artifacts": {
                "values": [
                    {
                        "name": summary_artifact_name,
                        "source": {"ref": summary_ref},
                        "contract": dict(summary_contract),
                        "pointer": {"path": summary_pointer_path},
                    }
                ]
            },
            "publishes": [{"artifact": summary_artifact_name, "from": summary_artifact_name}],
        }

    def _forward_result_outputs(source_ref_prefix: str) -> dict[str, Any]:
        return {
            name: {
                **definition,
                "from": {"ref": f"{source_ref_prefix}.{name}"},
            }
            for name, definition in result_output_definitions.items()
        }

    plan_blocked_outcome_name = "FinalizeSelectedItemOutcomeBlockedByPlan"
    plan_approved_match_name = "FinalizeSelectedItemImplementationResult"
    implementation_completed_outcome_name = "FinalizeSelectedItemOutcomeCompleted"
    implementation_blocked_outcome_name = "FinalizeSelectedItemOutcomeBlockedByImplementation"
    implementation_cases = {
        "COMPLETED": {
            "id": _normalize_generated_step_id(f"{step_name}__completed"),
            "outputs": _forward_result_outputs(
                f"self.steps.{implementation_completed_outcome_name}.artifacts"
            ),
            "steps": [
                {
                    "name": implementation_completed_outcome_name,
                    "id": _normalize_generated_step_id(implementation_completed_outcome_name),
                    "materialize_artifacts": {
                        "values": _outcome_values(
                            variant="CONTINUE",
                            summary_ref=implementation_summary_ref,
                            include_blocker_ref=None,
                        )
                        + [
                            {
                                "name": "return__blocker-class",
                                "source": {"literal": placeholder_blocker_value},
                                "contract": dict(blocker_contract),
                            }
                        ]
                    },
                }
            ],
        },
        "BLOCKED": {
            "id": _normalize_generated_step_id(f"{step_name}__blocked"),
            "outputs": _forward_result_outputs(
                f"self.steps.{implementation_blocked_outcome_name}.artifacts"
            ),
            "steps": [
                {
                    "name": implementation_blocked_outcome_name,
                    "id": _normalize_generated_step_id(implementation_blocked_outcome_name),
                    "materialize_artifacts": {
                        "values": _outcome_values(
                            variant="BLOCKED",
                            summary_ref=implementation_blocked_summary_ref,
                            include_blocker_ref=implementation_blocker_ref,
                        )
                    },
                }
            ],
        },
    }
    implementation_match_step = {
        "name": plan_approved_match_name,
        "id": _normalize_generated_step_id(plan_approved_match_name),
        "match": {
            "ref": implementation_variant_ref,
            "cases": implementation_cases,
        },
    }
    plan_cases = {
        "APPROVED": {
            "id": _normalize_generated_step_id(f"{step_name}__plan_approved"),
            "outputs": _forward_result_outputs(
                f"root.steps.{plan_approved_match_name}.artifacts"
            ),
            "steps": [
                _publish_summary_step(
                    name="PublishSelectedItemApprovedSummary",
                    summary_ref=f"root.steps.{plan_approved_match_name}.artifacts.return__summary-path",
                ),
                _build_match_projection_anchor_step(
                    match_step_name=step_name,
                    variant_name="APPROVED",
                    case_outputs=_forward_result_outputs(
                        f"root.steps.{plan_approved_match_name}.artifacts"
                    ),
                    context=context,
                    span=expr.span,
                ),
            ],
        },
        "BLOCKED": {
            "id": _normalize_generated_step_id(f"{step_name}__plan_blocked"),
            "outputs": _forward_result_outputs(
                f"self.steps.{plan_blocked_outcome_name}.artifacts"
            ),
            "steps": [
                {
                    "name": plan_blocked_outcome_name,
                    "id": _normalize_generated_step_id(plan_blocked_outcome_name),
                    "materialize_artifacts": {
                        "values": _outcome_values(
                            variant="BLOCKED",
                            summary_ref=plan_summary_ref,
                            include_blocker_ref=plan_blocker_ref,
                        )
                    },
                },
                _publish_summary_step(
                    name="PublishSelectedItemPlanBlockedSummary",
                    summary_ref=plan_summary_ref,
                ),
                _build_match_projection_anchor_step(
                    match_step_name=step_name,
                    variant_name="BLOCKED",
                    case_outputs=_forward_result_outputs(
                        f"self.steps.{plan_blocked_outcome_name}.artifacts"
                    ),
                    context=context,
                    span=expr.span,
                ),
            ],
        },
    }
    _record_step_origin(context, step_name=step_name, step_id=step_id, source=expr)
    _record_step_origin(
        context,
        step_name=implementation_match_step["name"],
        step_id=implementation_match_step["id"],
        source=expr,
    )
    step = {
        "name": step_name,
        "id": step_id,
        "match": {
            "ref": plan_variant_ref,
            "cases": plan_cases,
        },
    }
    _record_missing_step_origins(context, [queue_transition_materialize_step, implementation_match_step, step], source=expr)
    return [queue_transition_materialize_step, implementation_match_step, step], _TerminalResult(
        step_name=step_name,
        step_id=step_id,
        output_refs={
            f"return__{field_name}": f"root.steps.{step_name}.artifacts.return__{field_name}"
            for field_name in context.return_output_contracts
        },
        output_kind="match",
        hidden_inputs={},
    )


def _declared_resource_transition_config(
    typed_expr: TypedExpr,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
    state_path: str,
    audit_path: str,
) -> dict[str, Any]:
    expr = typed_expr.expr
    assert isinstance(expr, ResourceTransitionExpr)
    transition_def = context.type_env.resolve_transition_declaration(
        expr.spec.transition_ref_name or "",
        span=expr.span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    resource_def = context.type_env.resolve_resource_declaration(
        expr.spec.resource_ref_name or "",
        span=expr.span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    declaration = validate_transition_declaration(
        _transition_declaration_payload(
            transition_def,
            resource_def=resource_def,
            context=context,
        )
    )
    config = {
        "declaration": declaration,
        "resource": {
            "resource_id": resource_def.name,
            "resource_kind": declaration.resource.resource_kind,
            "audit_path": audit_path,
        },
        "request_bindings": _normalize_runtime_binding_value(
            _resolve_inline_expr_value(expr.spec.request_expr, local_values=local_values)
        ),
    }
    if resource_def.backing_kind == "bridge":
        bridge_input = resource_def.backing_path_input or ""
        config["resource"]["bridge_path"] = _normalize_runtime_binding_value(local_values[bridge_input])
    else:
        config["resource"]["state_path"] = state_path
    if expr.spec.expected_version_expr is not None:
        config["expected_version"] = _normalize_runtime_binding_value(
            _resolve_inline_expr_value(expr.spec.expected_version_expr, local_values=local_values)
        )
    return config


def _transition_declaration_payload(
    transition_def: Any,
    *,
    resource_def: Any,
    context: _LoweringContext,
) -> dict[str, Any]:
    resource_state_type = context.type_env.resolve_type(
        resource_def.state_type_name,
        span=resource_def.span,
        form_path=resource_def.form_path,
    )
    request_type = context.type_env.resolve_type(
        transition_def.request_type_name,
        span=transition_def.span,
        form_path=transition_def.form_path,
    )
    result_type = context.type_env.resolve_type(
        transition_def.result_type_name,
        span=transition_def.span,
        form_path=transition_def.form_path,
    )
    transition_context = replace(
        context,
        local_type_bindings={
            **dict(context.local_type_bindings),
            "state": resource_state_type,
            "request": request_type,
        },
    )
    placeholder_values = {"state": {"ref": "state"}, "request": {"ref": "request"}}
    preconditions = [
        _build_transition_pure_payload(
            precondition_expr,
            result_type=PrimitiveTypeRef(name="Bool"),
            context=transition_context,
            local_values=placeholder_values,
            state_type=resource_state_type,
            request_type=request_type,
        )[0]
        for precondition_expr in transition_def.preconditions
    ]
    updates: list[dict[str, Any]] = []
    for update in transition_def.updates:
        payload: dict[str, Any] | None = None
        if update.value_expr is not None:
            target_type = resource_state_type.field_types[update.target]
            value_type = target_type.item_type_ref if update.op == "append_item" and isinstance(target_type, ListTypeRef) else target_type
            payload = _build_transition_pure_payload(
                update.value_expr,
                result_type=value_type,
                context=transition_context,
                local_values=placeholder_values,
                state_type=resource_state_type,
                request_type=request_type,
            )[0]
        update_entry = {"op": update.op, "target": update.target}
        if payload is not None:
            update_entry["value"] = payload
        updates.append(update_entry)
    result_projection = _build_transition_pure_payload(
        transition_def.result_expr,
        result_type=result_type,
        context=transition_context,
        local_values=placeholder_values,
        state_type=resource_state_type,
        request_type=request_type,
    )[0]
    audit_projection_type = _infer_pure_projection_expr_type(
        transition_def.audit_expr,
        context=transition_context,
        lexical_types={},
    )
    audit_projection = _build_transition_pure_payload(
        transition_def.audit_expr,
        result_type=audit_projection_type,
        context=transition_context,
        local_values=placeholder_values,
        state_type=resource_state_type,
        request_type=request_type,
    )[0]
    return {
        "transition_schema_version": 1,
        "resource": {
            "resource_kind": resource_def.name.replace("-", "_"),
            "state_type": _transition_type_descriptor(resource_state_type),
            "backing": (
                {"kind": "bridge", "path_input": resource_def.backing_path_input}
                if resource_def.backing_kind == "bridge"
                else {"kind": "state_layout"}
            ),
        },
        "transition": {
            "name": transition_def.name,
            "request_type": _transition_type_descriptor(request_type),
            "result_type": _transition_type_descriptor(result_type),
            "preconditions": preconditions,
            "updates": updates,
            "write_set": list(transition_def.write_set),
            "idempotency_fields": list(transition_def.idempotency_fields),
            "result_projection": result_projection,
            "audit_projection": audit_projection,
            "conflict_policy": transition_def.conflict_policy,
            "backend": _transition_backend_payload(
                transition_def,
                context=context,
            ),
        },
    }


def _transition_backend_payload(
    transition_def: Any,
    *,
    context: _LoweringContext,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"kind": transition_def.backend_kind}
    if transition_def.backend_kind == "runtime_native":
        return payload

    binding = context.command_boundary_environment.bindings_by_name.get(
        transition_def.backend_kind
    )
    if not isinstance(binding, CertifiedAdapterBinding):
        raise _compile_error(
            code="resource_transition_requires_runtime_backend",
            message=(
                f"declared transition backend `{transition_def.backend_kind}` must resolve "
                "to a certified resource_transition adapter"
            ),
            span=transition_def.span,
            form_path=transition_def.form_path,
        )
    payload["stable_command"] = list(binding.stable_command)
    payload["invocation_protocol"] = binding.invocation_protocol
    return payload


def _transition_type_descriptor(type_ref: TypeRef) -> dict[str, Any]:
    if isinstance(type_ref, PrimitiveTypeRef):
        if type_ref.allowed_values:
            return {"kind": "enum", "name": type_ref.name, "allowed": list(type_ref.allowed_values)}
        return {"kind": "primitive", "name": type_ref.name}
    if isinstance(type_ref, PathTypeRef):
        return {"kind": "path", "name": type_ref.name}
    if isinstance(type_ref, OptionalTypeRef):
        return {"kind": "optional", "item": _transition_type_descriptor(type_ref.item_type_ref)}
    if isinstance(type_ref, ListTypeRef):
        return {"kind": "list", "item": _transition_type_descriptor(type_ref.item_type_ref)}
    if isinstance(type_ref, MapTypeRef):
        return {
            "kind": "map",
            "key": _transition_type_descriptor(type_ref.key_type_ref),
            "value": _transition_type_descriptor(type_ref.value_type_ref),
        }
    if isinstance(type_ref, RecordTypeRef):
        return {
            "kind": "record",
            "name": type_ref.name,
            "fields": [
                {
                    "name": field.name,
                    "type": _transition_type_descriptor(type_ref.field_types[field.name]),
                }
                for field in type_ref.definition.fields
            ],
        }
    if isinstance(type_ref, UnionTypeRef):
        return {
            "kind": "union",
            "name": type_ref.name,
            "variants": [
                {
                    "name": variant.name,
                    "fields": [
                        {
                            "name": field.name,
                            "type": _transition_type_descriptor(type_ref.variant_field_types[variant.name][field.name]),
                        }
                        for field in variant.fields
                    ],
                }
                for variant in type_ref.definition.variants
            ],
        }
    raise TypeError(f"unsupported transition type descriptor `{type(type_ref).__name__}`")


def _build_transition_pure_payload(
    expr: Any,
    *,
    result_type: TypeRef,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
    state_type: TypeRef,
    request_type: TypeRef,
) -> tuple[dict[str, Any], dict[str, Any]]:
    payload, binding_refs = build_pure_projection_payload(
        expr,
        result_type=result_type,
        context=context,
        local_values=local_values,
    )
    bindings = dict(payload.get("bindings", {}))
    bindings.setdefault("state", {"type": _transition_type_descriptor(state_type)})
    bindings.setdefault("request", {"type": _transition_type_descriptor(request_type)})
    payload["bindings"] = bindings
    return payload, binding_refs


def _normalize_runtime_binding_value(value: Any) -> Any:
    if isinstance(value, LiteralExpr):
        return value.value
    if isinstance(value, GeneratedRelpathSeedExpr):
        return value.literal_path
    if isinstance(value, str):
        return {"ref": value}
    if isinstance(value, Mapping):
        return {
            str(key): _normalize_runtime_binding_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_normalize_runtime_binding_value(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_runtime_binding_value(item) for item in value]
    return value


def _resource_transition_payload(
    expr: ResourceTransitionExpr,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the JSON payload sent to the resource-transition adapter."""

    payload: dict[str, Any] = {
        "transition_name": expr.spec.transition_name,
        "from": expr.spec.from_queue_name.rsplit(".", 1)[-1],
        "to": expr.spec.to_queue_name.rsplit(".", 1)[-1],
        "event": expr.spec.event_name,
    }
    ledger_value = _resolve_inline_expr_value(expr.spec.ledger_expr, local_values=local_values)
    if isinstance(ledger_value, LiteralExpr):
        payload["ledger_path"] = str(ledger_value.value)
    elif isinstance(ledger_value, str):
        payload["ledger_path"] = "${" + ledger_value + "}"
    else:
        raise _compile_error(
            code="workflow_return_not_exportable",
            message="`resource-transition :ledger` must lower from a literal or workflow input path",
            span=expr.spec.ledger_expr.span,
            form_path=expr.spec.ledger_expr.form_path,
        )

    resource_value = _resolve_inline_expr_value(expr.spec.resource_expr, local_values=local_values)
    resource_type = _resolve_signature_expr_type(expr.spec.resource_expr, context=context)
    if isinstance(resource_value, LiteralExpr):
        if isinstance(resource_type, PathTypeRef):
            payload["resource_path"] = str(resource_value.value)
        else:
            payload["resource_id"] = str(resource_value.value)
    elif isinstance(resource_value, str):
        if isinstance(resource_type, PathTypeRef):
            payload["resource_path"] = "${" + resource_value + "}"
        else:
            payload["resource_id"] = "${" + resource_value + "}"
    else:
        raise _compile_error(
            code="workflow_return_not_exportable",
            message="`resource-transition :resource` must lower from a literal or workflow input value",
            span=expr.spec.resource_expr.span,
            form_path=expr.spec.resource_expr.form_path,
        )

    if isinstance(expr.spec.resource_expr, FieldAccessExpr):
        base_value = local_values.get(expr.spec.resource_expr.base.name)
        if isinstance(base_value, Mapping):
            sibling_path_ref = base_value.get("item-path")
            if "resource_path" not in payload and isinstance(sibling_path_ref, str):
                payload["resource_path"] = "${" + sibling_path_ref + "}"
            sibling_id_ref = base_value.get("item-id")
            if "resource_id" not in payload and isinstance(sibling_id_ref, str):
                payload["resource_id"] = "${" + sibling_id_ref + "}"
    return payload
