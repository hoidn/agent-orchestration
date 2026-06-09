"""Phase-drain owner surface for stdlib lowering."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle, workflow_managed_write_root_inputs
from orchestrator.workflow.references import StructuredStepReference
from orchestrator.workflow.surface_ast import SurfaceStep

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
from ..type_env import PathTypeRef, PrimitiveTypeRef, ProcRefTypeRef, RecordTypeRef, TypeRef, UnionTypeRef
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
from .origins import LoweringOrigin, _rekey_origin_map
from .phase_flow import _build_match_projection_anchor_step, _provider_metadata_names
from .phase_scope import (
    _build_call_bindings_from_record_value,
    _managed_write_root_bindings,
    _managed_write_root_requirements_for_callable,
    _render_repeat_until_max_iterations,
    _same_file_workflow_provider_requirements,
)
from .values import _assign_nested_local_value, _render_existing_output_ref, _resolve_inline_expr_value


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




def _lower_backlog_drain(*args, **kwargs):
    return _phase_stdlib_lower_backlog_drain_impl(*args, **kwargs)

def _phase_stdlib_lower_backlog_drain_impl(
    typed_expr: TypedExpr,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    """Lower the autonomous backlog loop to a runtime repeat-until workflow.

    `backlog-drain` is the frontend form for "keep selecting work until there
    is no work, a block occurs, or the iteration cap is reached." Lowering emits
    the loop, calls the selector/runner/gap-drafter workflows through checked
    workflow refs, carries loop state, and normalizes the final result with a
    certified adapter.
    """

    expr = typed_expr.expr
    assert isinstance(expr, BacklogDrainExpr)
    step_name = context.step_name_prefix
    step_id = _normalize_generated_step_id(step_name)
    selector_call_name = f"{step_name}__selector"
    run_item_call_name = f"{step_name}__run_item"
    gap_drafter_call_name = f"{step_name}__gap_drafter"
    selector_ref = resolve_workflow_ref_name(
        expr.spec.selector_name,
        workflow_catalog=context.workflow_catalog,
        span=expr.span,
        form_path=expr.form_path,
        typed_workflows_by_name=context.workflows_by_name,
        allow_extern_rebinding=True,
    )
    run_item_ref = resolve_workflow_ref_name(
        expr.spec.run_item_name,
        workflow_catalog=context.workflow_catalog,
        span=expr.span,
        form_path=expr.form_path,
        typed_workflows_by_name=context.workflows_by_name,
        allow_extern_rebinding=True,
    )
    gap_drafter_ref = resolve_workflow_ref_name(
        expr.spec.gap_drafter_name,
        workflow_catalog=context.workflow_catalog,
        span=expr.span,
        form_path=expr.form_path,
        typed_workflows_by_name=context.workflows_by_name,
        allow_extern_rebinding=True,
    )
    selector_signature = type(
        "WorkflowRefSignature",
        (),
        {
            "name": selector_ref.workflow_name,
            "params": selector_ref.signature_params,
            "return_type_ref": selector_ref.return_type_ref,
        },
    )()
    run_item_signature = type(
        "WorkflowRefSignature",
        (),
        {
            "name": run_item_ref.workflow_name,
            "params": run_item_ref.signature_params,
            "return_type_ref": run_item_ref.return_type_ref,
        },
    )()
    gap_drafter_signature = type(
        "WorkflowRefSignature",
        (),
        {
            "name": gap_drafter_ref.workflow_name,
            "params": gap_drafter_ref.signature_params,
            "return_type_ref": gap_drafter_ref.return_type_ref,
        },
    )()
    selector_callee = context.lowered_callees.get(selector_ref.workflow_name)
    run_item_callee = context.lowered_callees.get(run_item_ref.workflow_name)
    gap_drafter_callee = context.lowered_callees.get(gap_drafter_ref.workflow_name)
    selector_imported = context.imported_workflow_bundles.get(selector_ref.workflow_name)
    run_item_imported = context.imported_workflow_bundles.get(run_item_ref.workflow_name)
    gap_drafter_imported = context.imported_workflow_bundles.get(gap_drafter_ref.workflow_name)
    if (
        (selector_callee is None and selector_imported is None)
        or (run_item_callee is None and run_item_imported is None)
        or (gap_drafter_callee is None and gap_drafter_imported is None)
    ):
        raise _compile_error(
            code="workflow_call_unknown",
            message="`backlog-drain` lowering requires referenced workflows to be available as same-file callees or registered imported bundles",
            span=expr.span,
            form_path=expr.form_path,
        )
    ctx_value = _resolve_inline_expr_value(expr.spec.ctx_expr, local_values=local_values)
    if not isinstance(ctx_value, Mapping):
        raise _compile_error(
            code="workflow_signature_mismatch",
            message="`backlog-drain :ctx` must lower from workflow inputs in this Stage 3 slice",
            span=expr.spec.ctx_expr.span,
            form_path=expr.spec.ctx_expr.form_path,
        )
    _validate_backlog_drain_provider_metadata(
        expr,
        context=context,
        local_values=local_values,
        selector_workflow=selector_callee.typed_workflow if selector_callee is not None else None,
        run_item_workflow=run_item_callee.typed_workflow if run_item_callee is not None else None,
        gap_drafter_workflow=gap_drafter_callee.typed_workflow if gap_drafter_callee is not None else None,
        selector_imported=selector_imported,
        run_item_imported=run_item_imported,
        gap_drafter_imported=gap_drafter_imported,
    )
    selector_call_target = _specialize_backlog_drain_call_target(
        resolved_ref=selector_ref,
        role_name="selector",
        providers_expr=expr.spec.providers_expr,
        context=context,
        local_values=local_values,
    )
    run_item_call_target = _specialize_backlog_drain_call_target(
        resolved_ref=run_item_ref,
        role_name="run-item",
        providers_expr=expr.spec.providers_expr,
        context=context,
        local_values=local_values,
    )
    gap_drafter_call_target = _specialize_backlog_drain_call_target(
        resolved_ref=gap_drafter_ref,
        role_name="gap-drafter",
        providers_expr=expr.spec.providers_expr,
        context=context,
        local_values=local_values,
    )
    selection_payload_type = run_item_signature.params[1][1]
    if not isinstance(selection_payload_type, RecordTypeRef):
        raise _compile_error(
            code="workflow_signature_mismatch",
            message="`backlog-drain :run-item` second parameter must remain a record payload",
            span=expr.span,
            form_path=expr.form_path,
        )
    selection_value: dict[str, Any] = {}
    for _, field_path in _flatten_boundary_leaf_paths(
        selection_payload_type,
        generated_name=run_item_signature.params[1][0],
    ):
        _assign_nested_local_value(
            selection_value,
            field_path,
            f"self.steps.{selector_call_name}.artifacts.return__selection__{'__'.join(field_path)}",
        )
    gap_value = {
        "gap-id": f"self.steps.{selector_call_name}.artifacts.return__gap__gap-id",
    }
    run_mapping = ctx_value.get("run")
    if not isinstance(selection_value, Mapping) or not isinstance(gap_value, Mapping) or not isinstance(run_mapping, Mapping):
        raise _compile_error(
            code="workflow_signature_mismatch",
            message="`backlog-drain` lowering requires typed selector outputs and DrainCtx.run fields",
            span=expr.span,
            form_path=expr.form_path,
        )

    def _return_contract(field_name: str) -> dict[str, Any]:
        contract = context.return_output_contracts.get(field_name)
        if contract is None:
            raise _compile_error(
                code="workflow_return_not_exportable",
                message=f"`backlog-drain` cannot lower missing return contract `{field_name}`",
                span=expr.span,
                form_path=expr.form_path,
            )
        return dict(contract)

    selector_with = _build_call_bindings_from_record_value(
        selector_signature.params[0][0],
        selector_signature.params[0][1],
        ctx_value,
        source_expr=expr.spec.ctx_expr,
    )
    item_ctx_value = {
        "run": run_mapping,
        "item-id": selection_value.get("item-id"),
        "state-root": selection_value.get("item-state-root"),
        "artifact-root": run_mapping.get("artifact-root"),
        "ledger": ctx_value.get("ledger"),
    }
    run_item_with = {
        **_build_call_bindings_from_record_value(
            run_item_signature.params[0][0],
            run_item_signature.params[0][1],
            item_ctx_value,
            source_expr=expr.spec.ctx_expr,
        ),
        **_build_call_bindings_from_record_value(
            run_item_signature.params[1][0],
            run_item_signature.params[1][1],
            selection_value,
            source_expr=expr.spec.ctx_expr,
        ),
    }
    gap_drafter_with = {
        **_build_call_bindings_from_record_value(
            gap_drafter_signature.params[0][0],
            gap_drafter_signature.params[0][1],
            ctx_value,
            source_expr=expr.spec.ctx_expr,
        ),
        **_build_call_bindings_from_record_value(
            gap_drafter_signature.params[1][0],
            gap_drafter_signature.params[1][1],
            gap_value,
            source_expr=expr.spec.ctx_expr,
        ),
    }
    items_processed_artifact = f"{step_name}__items_processed"
    items_processed_contract = {"kind": "scalar", "type": "integer"}
    context.top_level_artifacts[items_processed_artifact] = dict(items_processed_contract)
    accumulator_status_contract = {
        "kind": "scalar",
        "type": "enum",
        "allowed": ["CONTINUE", "EMPTY", "COMPLETED", "BLOCKED"],
    }
    accumulator_run_state_contract = {
        "kind": "relpath",
        "type": "relpath",
        "under": "state",
        "must_exist_target": False,
    }
    accumulator_progress_contract = {
        "kind": "relpath",
        "type": "relpath",
        "under": "artifacts/work",
        "must_exist_target": False,
    }
    accumulator_blocker_contract = dict(_return_contract("blocker-class"))
    placeholder_run_state_ref = "inputs.ctx__manifest"
    placeholder_progress_ref = f"artifacts/work/.orchestrate/workflow_lisp/{step_name}/unused_progress_report.md"
    placeholder_blocker_value = accumulator_blocker_contract["allowed"][0]
    hidden_inputs: dict[str, LoweringOrigin] = {}

    loop_output_definitions = {
        "acc__loop-status": dict(accumulator_status_contract),
        "acc__items-processed": dict(items_processed_contract),
        "acc__run-state": dict(accumulator_run_state_contract),
        "acc__progress-report-path": dict(accumulator_progress_contract),
        "acc__blocker-class": dict(accumulator_blocker_contract),
    }
    loop_outputs = {
        name: {
            **definition,
            "from": {"ref": f"self.steps.{step_name}__route_selection.artifacts.{name}"},
        }
        for name, definition in loop_output_definitions.items()
    }

    def _materialize_outputs_step(
        *,
        name: str,
        step_id_value: str,
        values: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "name": name,
            "id": step_id_value,
            "materialize_artifacts": {
                "values": values,
            },
        }

    def _scalar_step(
        *,
        name: str,
        step_id_value: str,
        operation: str,
        by: int | None = None,
        publish: bool = False,
    ) -> dict[str, Any]:
        payload = {"artifact": items_processed_artifact}
        if operation == "set":
            payload["value"] = 0
        else:
            assert by is not None
            payload["by"] = by
        step: dict[str, Any] = {
            "name": name,
            "id": step_id_value,
            f"{operation}_scalar": payload,
        }
        if publish:
            step["publishes"] = [{"artifact": items_processed_artifact, "from": items_processed_artifact}]
        return step

    def _managed_call_step(
        *,
        generated_name: str,
        call_target: str,
        with_bindings: Mapping[str, Any],
        lowered_callee: LoweredWorkflow | None,
        imported_bundle: LoadedWorkflowBundle | None,
    ) -> dict[str, Any]:
        step = {
            "name": generated_name,
            "id": _normalize_generated_step_id(generated_name),
            "call": call_target,
            "with": dict(with_bindings),
        }
        managed_inputs = _managed_write_root_requirements_for_callable(
            lowered_callee=lowered_callee,
            imported_bundle=imported_bundle,
            span=expr.span,
            form_path=expr.form_path,
        )
        step["with"].update(
            _managed_write_root_bindings(
                caller_workflow_name=context.workflow_name,
                call_step_name=generated_name,
                callee_name=call_target,
                managed_inputs=managed_inputs,
                iteration_scope="${loop.index}",
            )
        )
        for managed_input in managed_inputs:
            hidden_inputs[managed_input] = _origin_from_context_source(context, expr)
        _record_step_origin(context, step_name=generated_name, step_id=step["id"], source=expr)
        return step

    def _accumulator_marker_step(
        *,
        name: str,
        step_id_value: str,
        loop_status: str,
        run_state_ref: str,
        progress_ref: str | None = None,
        blocker_ref: str | None = None,
    ) -> dict[str, Any]:
        return _materialize_outputs_step(
            name=name,
            step_id_value=step_id_value,
            values=[
                {
                    "name": "acc__loop-status",
                    "source": {"literal": loop_status},
                    "contract": dict(accumulator_status_contract),
                },
                {
                    "name": "acc__run-state",
                    "source": {"ref": run_state_ref},
                    "contract": dict(accumulator_run_state_contract),
                },
                {
                    "name": "acc__progress-report-path",
                    "source": {"ref": progress_ref} if progress_ref is not None else {"literal": placeholder_progress_ref},
                    "contract": dict(accumulator_progress_contract),
                },
                {
                    "name": "acc__blocker-class",
                    "source": {"ref": blocker_ref} if blocker_ref is not None else {"literal": placeholder_blocker_value},
                    "contract": dict(accumulator_blocker_contract),
                },
            ],
        )

    def _accumulator_outputs(
        *,
        marker_step_name: str,
        items_processed_ref: str,
    ) -> dict[str, Any]:
        return {
            "acc__loop-status": {
                **loop_output_definitions["acc__loop-status"],
                "from": {"ref": f"self.steps.{marker_step_name}.artifacts.acc__loop-status"},
            },
            "acc__items-processed": {
                **loop_output_definitions["acc__items-processed"],
                "from": {"ref": items_processed_ref},
            },
            "acc__run-state": {
                **loop_output_definitions["acc__run-state"],
                "from": {"ref": f"self.steps.{marker_step_name}.artifacts.acc__run-state"},
            },
            "acc__progress-report-path": {
                **loop_output_definitions["acc__progress-report-path"],
                "from": {"ref": f"self.steps.{marker_step_name}.artifacts.acc__progress-report-path"},
            },
            "acc__blocker-class": {
                **loop_output_definitions["acc__blocker-class"],
                "from": {"ref": f"self.steps.{marker_step_name}.artifacts.acc__blocker-class"},
            },
        }

    selector_call_step = _managed_call_step(
        generated_name=selector_call_name,
        call_target=selector_call_target,
        with_bindings=selector_with,
        lowered_callee=selector_callee,
        imported_bundle=selector_imported,
    )
    gap_drafter_call_step = _managed_call_step(
        generated_name=gap_drafter_call_name,
        call_target=gap_drafter_call_target,
        with_bindings=gap_drafter_with,
        lowered_callee=gap_drafter_callee,
        imported_bundle=gap_drafter_imported,
    )
    gap_drafter_call_step["when"] = {
        "compare": {
            "left": {"ref": f"self.steps.{selector_call_name}.artifacts.return__variant"},
            "op": "eq",
            "right": "GAP",
        }
    }
    run_item_call_step = _managed_call_step(
        generated_name=run_item_call_name,
        call_target=run_item_call_target,
        with_bindings=run_item_with,
        lowered_callee=run_item_callee,
        imported_bundle=run_item_imported,
    )
    run_item_call_step["when"] = {
        "compare": {
            "left": {"ref": f"self.steps.{selector_call_name}.artifacts.return__variant"},
            "op": "eq",
            "right": "SELECTED",
        }
    }

    current_items_step_name = f"{step_name}__current_items_processed"
    current_items_ref = f"self.steps.{current_items_step_name}.artifacts.{items_processed_artifact}"
    parent_current_items_ref = f"parent.steps.{current_items_step_name}.artifacts.{items_processed_artifact}"
    current_items_step = _scalar_step(
        name=current_items_step_name,
        step_id_value=_normalize_generated_step_id(current_items_step_name),
        operation="increment",
        by=0,
    )

    empty_route_step_name = f"{step_name}__route_empty_selection"
    empty_marker_name = "MarkEmptySelection"
    completed_marker_name = "MarkCompletedSelection"
    empty_route_step = {
        "name": empty_route_step_name,
        "id": _normalize_generated_step_id(empty_route_step_name),
        "when": {
            "compare": {
                "left": {"ref": f"self.steps.{selector_call_name}.artifacts.return__variant"},
                "op": "eq",
                "right": "EMPTY",
            }
        },
        "if": {
            "compare": {
                "left": {"ref": current_items_ref},
                "op": "eq",
                "right": 0,
            }
        },
        "then": {
            "id": _normalize_generated_step_id(f"{empty_route_step_name}__empty"),
            "outputs": _accumulator_outputs(
                marker_step_name=empty_marker_name,
                items_processed_ref=parent_current_items_ref,
            ),
            "steps": [
                _accumulator_marker_step(
                    name=empty_marker_name,
                    step_id_value="mark_empty_selection",
                    loop_status="EMPTY",
                    run_state_ref=f"parent.steps.{selector_call_name}.artifacts.return__run-state",
                )
            ],
        },
        "else": {
            "id": _normalize_generated_step_id(f"{empty_route_step_name}__completed"),
            "outputs": _accumulator_outputs(
                marker_step_name=completed_marker_name,
                items_processed_ref=parent_current_items_ref,
            ),
            "steps": [
                _accumulator_marker_step(
                    name=completed_marker_name,
                    step_id_value="mark_completed_selection",
                    loop_status="COMPLETED",
                    run_state_ref=f"parent.steps.{selector_call_name}.artifacts.return__run-state",
                )
            ],
        },
    }

    gap_route_step_name = f"{step_name}__route_gap_result"
    if isinstance(gap_drafter_signature.return_type_ref, RecordTypeRef):
        gap_marker_name = "MarkGapContinue"
        gap_route_step = {
            "name": gap_route_step_name,
            "id": _normalize_generated_step_id(gap_route_step_name),
            "when": {
                "compare": {
                    "left": {"ref": f"self.steps.{selector_call_name}.artifacts.return__variant"},
                    "op": "eq",
                    "right": "GAP",
                }
            },
            "if": {
                "compare": {
                    "left": 1,
                    "op": "eq",
                    "right": 1,
                }
            },
            "then": {
                "id": _normalize_generated_step_id(f"{gap_route_step_name}__continue"),
                "outputs": _accumulator_outputs(
                    marker_step_name=gap_marker_name,
                    items_processed_ref=parent_current_items_ref,
                ),
                "steps": [
                    _accumulator_marker_step(
                        name=gap_marker_name,
                        step_id_value="mark_gap_continue",
                        loop_status="CONTINUE",
                        run_state_ref=f"parent.steps.{gap_drafter_call_name}.artifacts.return__run-state",
                    )
                ],
            },
            "else": {
                "id": _normalize_generated_step_id(f"{gap_route_step_name}__continue_else"),
                "outputs": _accumulator_outputs(
                    marker_step_name=gap_marker_name,
                    items_processed_ref=parent_current_items_ref,
                ),
                "steps": [
                    _accumulator_marker_step(
                        name=gap_marker_name,
                        step_id_value="mark_gap_continue_else",
                        loop_status="CONTINUE",
                        run_state_ref=f"parent.steps.{gap_drafter_call_name}.artifacts.return__run-state",
                    )
                ],
            },
        }
    else:
        gap_continue_marker_name = "MarkGapContinue"
        gap_blocked_marker_name = "MarkGapBlocked"
        gap_route_step = {
            "name": gap_route_step_name,
            "id": _normalize_generated_step_id(gap_route_step_name),
            "when": {
                "compare": {
                    "left": {"ref": f"self.steps.{selector_call_name}.artifacts.return__variant"},
                    "op": "eq",
                    "right": "GAP",
                }
            },
            "match": {
                "ref": f"self.steps.{gap_drafter_call_name}.artifacts.return__variant",
                "cases": {
                    "CONTINUE": {
                        "id": _normalize_generated_step_id(f"{gap_route_step_name}__continue"),
                        "outputs": _accumulator_outputs(
                            marker_step_name=gap_continue_marker_name,
                            items_processed_ref=parent_current_items_ref,
                        ),
                        "steps": [
                            _accumulator_marker_step(
                                name=gap_continue_marker_name,
                                step_id_value="mark_gap_continue",
                                loop_status="CONTINUE",
                                run_state_ref=f"parent.steps.{gap_drafter_call_name}.artifacts.return__run-state",
                            )
                        ],
                    },
                    "BLOCKED": {
                        "id": _normalize_generated_step_id(f"{gap_route_step_name}__blocked"),
                        "outputs": _accumulator_outputs(
                            marker_step_name=gap_blocked_marker_name,
                            items_processed_ref=parent_current_items_ref,
                        ),
                        "steps": [
                            _accumulator_marker_step(
                                name=gap_blocked_marker_name,
                                step_id_value="mark_gap_blocked",
                                loop_status="BLOCKED",
                                run_state_ref=placeholder_run_state_ref,
                                progress_ref=f"parent.steps.{gap_drafter_call_name}.artifacts.return__progress-report-path",
                                blocker_ref=f"parent.steps.{gap_drafter_call_name}.artifacts.return__blocker-class",
                            )
                        ],
                    },
                },
            },
        }

    selected_route_step_name = f"{step_name}__route_selected_result"
    increment_selected_step_name = "IncrementSelectedItemsProcessed"
    incremented_items_ref = f"self.steps.{increment_selected_step_name}.artifacts.{items_processed_artifact}"
    selected_continue_marker_name = "MarkSelectedContinue"
    selected_blocked_marker_name = "MarkSelectedBlocked"
    selected_route_step = {
        "name": selected_route_step_name,
        "id": _normalize_generated_step_id(selected_route_step_name),
        "when": {
            "compare": {
                "left": {"ref": f"self.steps.{selector_call_name}.artifacts.return__variant"},
                "op": "eq",
                "right": "SELECTED",
            }
        },
        "match": {
            "ref": f"self.steps.{run_item_call_name}.artifacts.return__variant",
            "cases": {
                "CONTINUE": {
                    "id": _normalize_generated_step_id(f"{selected_route_step_name}__continue"),
                    "outputs": _accumulator_outputs(
                        marker_step_name=selected_continue_marker_name,
                        items_processed_ref=incremented_items_ref,
                    ),
                    "steps": [
                        _scalar_step(
                            name=increment_selected_step_name,
                            step_id_value="increment_selected_items_processed",
                            operation="increment",
                            by=1,
                            publish=True,
                        ),
                        _accumulator_marker_step(
                            name=selected_continue_marker_name,
                            step_id_value="mark_selected_continue",
                            loop_status="CONTINUE",
                            run_state_ref=f"parent.steps.{run_item_call_name}.artifacts.return__run-state",
                        ),
                    ],
                },
                "BLOCKED": {
                    "id": _normalize_generated_step_id(f"{selected_route_step_name}__blocked"),
                    "outputs": _accumulator_outputs(
                        marker_step_name=selected_blocked_marker_name,
                        items_processed_ref=parent_current_items_ref,
                    ),
                    "steps": [
                        _accumulator_marker_step(
                            name=selected_blocked_marker_name,
                            step_id_value="mark_selected_blocked",
                            loop_status="BLOCKED",
                            run_state_ref=f"parent.steps.{run_item_call_name}.artifacts.return__run-state",
                            progress_ref=f"parent.steps.{run_item_call_name}.artifacts.return__summary-path",
                            blocker_ref=f"parent.steps.{run_item_call_name}.artifacts.return__blocker-class",
                        )
                    ],
                },
            },
        },
    }

    route_selection_step_name = f"{step_name}__route_selection"

    def _forward_accumulator_outputs(source_step_name: str) -> dict[str, Any]:
        return {
            name: {
                **definition,
                "from": {"ref": f"parent.steps.{source_step_name}.artifacts.{name}"},
            }
            for name, definition in loop_output_definitions.items()
        }

    route_selection_step = {
        "name": route_selection_step_name,
        "id": _normalize_generated_step_id(route_selection_step_name),
        "match": {
            "ref": f"self.steps.{selector_call_name}.artifacts.return__variant",
            "cases": {
                "EMPTY": {
                    "id": _normalize_generated_step_id(f"{route_selection_step_name}__empty"),
                    "outputs": _forward_accumulator_outputs(empty_route_step_name),
                    "steps": [
                        _build_match_projection_anchor_step(
                            match_step_name=route_selection_step_name,
                            variant_name="EMPTY",
                            case_outputs=_forward_accumulator_outputs(empty_route_step_name),
                            context=context,
                            span=expr.span,
                        )
                    ],
                },
                "GAP": {
                    "id": _normalize_generated_step_id(f"{route_selection_step_name}__gap"),
                    "outputs": _forward_accumulator_outputs(gap_route_step_name),
                    "steps": [
                        _build_match_projection_anchor_step(
                            match_step_name=route_selection_step_name,
                            variant_name="GAP",
                            case_outputs=_forward_accumulator_outputs(gap_route_step_name),
                            context=context,
                            span=expr.span,
                        )
                    ],
                },
                "SELECTED": {
                    "id": _normalize_generated_step_id(f"{route_selection_step_name}__selected"),
                    "outputs": _forward_accumulator_outputs(selected_route_step_name),
                    "steps": [
                        _build_match_projection_anchor_step(
                            match_step_name=route_selection_step_name,
                            variant_name="SELECTED",
                            case_outputs=_forward_accumulator_outputs(selected_route_step_name),
                            context=context,
                            span=expr.span,
                        )
                    ],
                },
            },
        },
    }

    seed_items_processed_step_name = f"{step_name}__seed_items_processed"
    seed_items_processed_step = _scalar_step(
        name=seed_items_processed_step_name,
        step_id_value=_normalize_generated_step_id(seed_items_processed_step_name),
        operation="set",
        publish=True,
    )
    _record_step_origin(
        context,
        step_name=seed_items_processed_step_name,
        step_id=seed_items_processed_step["id"],
        source=expr,
    )
    _record_step_origin(context, step_name=step_name, step_id=step_id, source=expr)
    _record_step_origin(context, step_name=current_items_step_name, step_id=current_items_step["id"], source=expr)
    _record_step_origin(context, step_name=empty_route_step_name, step_id=empty_route_step["id"], source=expr)
    _record_step_origin(context, step_name=gap_route_step_name, step_id=gap_route_step["id"], source=expr)
    _record_step_origin(context, step_name=selected_route_step_name, step_id=selected_route_step["id"], source=expr)
    _record_step_origin(context, step_name=route_selection_step_name, step_id=route_selection_step["id"], source=expr)

    repeat_step = {
        "name": step_name,
        "id": step_id,
        "repeat_until": {
            "id": f"{step_id}__iteration",
            "max_iterations": _render_repeat_until_max_iterations(
                expr.spec.max_iterations_expr,
                local_values=local_values,
            ),
            "steps": [
                selector_call_step,
                current_items_step,
                empty_route_step,
                gap_drafter_call_step,
                gap_route_step,
                run_item_call_step,
                selected_route_step,
                route_selection_step,
            ],
            "outputs": loop_outputs,
            "condition": {
                "compare": {
                    "left": {"ref": "self.outputs.acc__loop-status"},
                    "op": "ne",
                    "right": "CONTINUE",
                }
            },
        },
    }

    result_output_definitions = {
        f"return__{field_name}": dict(contract)
        for field_name, contract in context.return_output_contracts.items()
    }

    def _return_marker_step(
        *,
        name: str,
        step_id_value: str,
        variant: str,
        run_state_ref: str,
        items_processed_ref: str,
        progress_ref: str,
        blocker_ref: str,
    ) -> dict[str, Any]:
        return _materialize_outputs_step(
            name=name,
            step_id_value=step_id_value,
            values=[
                {
                    "name": "return__variant",
                    "source": {"literal": variant},
                    "contract": dict(result_output_definitions["return__variant"]),
                },
                {
                    "name": "return__run-state",
                    "source": {"ref": run_state_ref},
                    "contract": dict(result_output_definitions["return__run-state"]),
                },
                {
                    "name": "return__items-processed",
                    "source": {"ref": items_processed_ref},
                    "contract": dict(result_output_definitions["return__items-processed"]),
                },
                {
                    "name": "return__progress-report-path",
                    "source": {"ref": progress_ref},
                    "contract": dict(result_output_definitions["return__progress-report-path"]),
                },
                {
                    "name": "return__blocker-class",
                    "source": {"ref": blocker_ref},
                    "contract": dict(result_output_definitions["return__blocker-class"]),
                },
            ],
        )

    def _forward_return_outputs(source_step_name: str) -> dict[str, Any]:
        return {
            name: {
                **definition,
                "from": {"ref": f"self.steps.{source_step_name}.artifacts.{name}"},
            }
            for name, definition in result_output_definitions.items()
        }

    normalize_step_name = f"{step_name}__normalize_result"
    normalize_step_id = _normalize_generated_step_id(normalize_step_name)
    _record_step_origin(context, step_name=normalize_step_name, step_id=normalize_step_id, source=expr)
    normalize_step = {
        "name": normalize_step_name,
        "id": normalize_step_id,
        "match": {
            "ref": f"root.steps.{step_name}.artifacts.acc__loop-status",
            "cases": {
                "EMPTY": {
                    "id": _normalize_generated_step_id(f"{normalize_step_name}__empty"),
                    "outputs": _forward_return_outputs("EmitDrainEmpty"),
                    "steps": [
                        _return_marker_step(
                            name="EmitDrainEmpty",
                            step_id_value="emit_drain_empty",
                            variant="EMPTY",
                            run_state_ref=f"root.steps.{step_name}.artifacts.acc__run-state",
                            items_processed_ref=f"root.steps.{step_name}.artifacts.acc__items-processed",
                            progress_ref=f"root.steps.{step_name}.artifacts.acc__progress-report-path",
                            blocker_ref=f"root.steps.{step_name}.artifacts.acc__blocker-class",
                        )
                    ],
                },
                "COMPLETED": {
                    "id": _normalize_generated_step_id(f"{normalize_step_name}__completed"),
                    "outputs": _forward_return_outputs("EmitDrainCompleted"),
                    "steps": [
                        _return_marker_step(
                            name="EmitDrainCompleted",
                            step_id_value="emit_drain_completed",
                            variant="COMPLETED",
                            run_state_ref=f"root.steps.{step_name}.artifacts.acc__run-state",
                            items_processed_ref=f"root.steps.{step_name}.artifacts.acc__items-processed",
                            progress_ref=f"root.steps.{step_name}.artifacts.acc__progress-report-path",
                            blocker_ref=f"root.steps.{step_name}.artifacts.acc__blocker-class",
                        )
                    ],
                },
                "BLOCKED": {
                    "id": _normalize_generated_step_id(f"{normalize_step_name}__blocked"),
                    "outputs": _forward_return_outputs("EmitDrainBlocked"),
                    "steps": [
                        _return_marker_step(
                            name="EmitDrainBlocked",
                            step_id_value="emit_drain_blocked",
                            variant="BLOCKED",
                            run_state_ref=f"root.steps.{step_name}.artifacts.acc__run-state",
                            items_processed_ref=f"root.steps.{step_name}.artifacts.acc__items-processed",
                            progress_ref=f"root.steps.{step_name}.artifacts.acc__progress-report-path",
                            blocker_ref=f"root.steps.{step_name}.artifacts.acc__blocker-class",
                        )
                    ],
                },
                "CONTINUE": {
                    "id": _normalize_generated_step_id(f"{normalize_step_name}__continue"),
                    "outputs": _forward_return_outputs("EmitDrainContinue"),
                    "steps": [
                        _return_marker_step(
                            name="EmitDrainContinue",
                            step_id_value="emit_drain_continue",
                            variant="BLOCKED",
                            run_state_ref=f"root.steps.{step_name}.artifacts.acc__run-state",
                            items_processed_ref=f"root.steps.{step_name}.artifacts.acc__items-processed",
                            progress_ref=f"root.steps.{step_name}.artifacts.acc__progress-report-path",
                            blocker_ref=f"root.steps.{step_name}.artifacts.acc__blocker-class",
                        )
                    ],
                },
            },
        },
    }
    _record_missing_step_origins(context, [seed_items_processed_step, repeat_step, normalize_step], source=expr)
    return [seed_items_processed_step, repeat_step, normalize_step], _TerminalResult(
        step_name=normalize_step_name,
        step_id=normalize_step_id,
        output_refs={
            f"return__{field_name}": f"root.steps.{normalize_step_name}.artifacts.return__{field_name}"
            for field_name in context.return_output_contracts
        },
        output_kind="match",
        hidden_inputs=hidden_inputs,
    )


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


def _selected_item_summary_pointer_path(workflow_name: str) -> str:
    """Return the compatibility pointer path for selected-item summaries."""

    return f".orchestrate/workflow_lisp/{workflow_name}/selected_item_summary.txt"


def _validate_backlog_drain_provider_metadata(
    expr: BacklogDrainExpr,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
    selector_workflow: TypedWorkflowDef | None,
    run_item_workflow: TypedWorkflowDef | None,
    gap_drafter_workflow: TypedWorkflowDef | None,
    selector_imported: LoadedWorkflowBundle | None,
    run_item_imported: LoadedWorkflowBundle | None,
    gap_drafter_imported: LoadedWorkflowBundle | None,
) -> None:
    """Verify backlog-drain provider metadata covers callee requirements."""

    required_provider_names = set()
    required_prompt_names = set()
    for role_name, workflow in (
        ("selector", selector_workflow),
        ("run-item", run_item_workflow),
        ("gap-drafter", gap_drafter_workflow),
    ):
        provider_count, prompt_count = _same_file_workflow_provider_requirements(
            workflow,
            typed_procedures=context.typed_procedures,
        )
        if provider_count:
            required_provider_names.add(f"providers.{role_name}")
        if prompt_count:
            required_prompt_names.add(f"prompts.{role_name}")
    for role_name, imported_bundle in (
        ("selector", selector_imported),
        ("run-item", run_item_imported),
        ("gap-drafter", gap_drafter_imported),
    ):
        provider_count, prompt_count = _imported_bundle_provider_requirements(imported_bundle)
        if provider_count:
            required_provider_names.add(f"providers.{role_name}")
        if prompt_count:
            required_prompt_names.add(f"prompts.{role_name}")

    if not required_provider_names and not required_prompt_names:
        return
    if expr.spec.providers_expr is None:
        raise _compile_error(
            code="backlog_drain_contract_invalid",
            message="`backlog-drain :providers` must satisfy the provider/prompt extern requirements of the selected workflows",
            span=expr.span,
            form_path=expr.form_path,
        )
    available_names = _provider_metadata_names(expr.spec.providers_expr, local_values=local_values)
    missing_names = sorted((required_provider_names | required_prompt_names) - available_names)
    if missing_names:
        raise _compile_error(
            code="backlog_drain_contract_invalid",
            message=(
                "`backlog-drain :providers` is missing required extern bindings: "
                + ", ".join(missing_names)
            ),
            span=expr.spec.providers_expr.span,
            form_path=expr.spec.providers_expr.form_path,
        )


def _imported_bundle_provider_requirements(bundle: LoadedWorkflowBundle | None) -> tuple[int, int]:
    """Count provider/prompt use inside an imported workflow bundle."""

    if bundle is None:
        return 0, 0
    provider_count = 0
    prompt_count = 0
    for step in bundle.surface.steps:
        provider_count += _count_surface_provider_steps(step)
        prompt_count += _count_surface_prompt_steps(step)
    return provider_count, prompt_count


def _count_surface_provider_steps(step: Any) -> int:
    """Count provider steps recursively in an elaborated workflow step tree."""

    total = 1 if getattr(step, "kind", None) == SurfaceStepKind.PROVIDER else 0
    total += sum(_count_surface_provider_steps(nested) for nested in _surface_nested_steps(step))
    return total


def _count_surface_prompt_steps(step: Any) -> int:
    """Count provider steps with prompt assets in an elaborated step tree."""

    total = 1 if getattr(step, "kind", None) == SurfaceStepKind.PROVIDER and getattr(step, "asset_file", None) else 0
    total += sum(_count_surface_prompt_steps(nested) for nested in _surface_nested_steps(step))
    return total


def _surface_nested_steps(step: Any) -> tuple[Any, ...]:
    """Return child steps nested under structured control-flow nodes."""

    nested: list[Any] = []
    then_branch = getattr(step, "then_branch", None)
    else_branch = getattr(step, "else_branch", None)
    if then_branch is not None:
        nested.extend(getattr(then_branch, "steps", ()))
    if else_branch is not None:
        nested.extend(getattr(else_branch, "steps", ()))
    match_cases = getattr(step, "match_cases", None)
    if isinstance(match_cases, Mapping):
        for case in match_cases.values():
            nested.extend(getattr(case, "steps", ()))
    repeat_until = getattr(step, "repeat_until", None)
    if repeat_until is not None:
        nested.extend(getattr(repeat_until, "steps", ()))
    nested.extend(getattr(step, "for_each_steps", ()))
    return tuple(nested)


def _specialize_backlog_drain_call_target(
    *,
    resolved_ref: ResolvedWorkflowRef,
    role_name: str,
    providers_expr: Any | None,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> str:
    """Create a provider/prompt-rebound call target for a drain role if needed."""

    workflow_name = resolved_ref.workflow_name
    imported_bundle = context.imported_workflow_bundles.get(workflow_name)
    same_file_callee = context.lowered_callees.get(workflow_name)
    if (imported_bundle is None and same_file_callee is None) or providers_expr is None:
        return workflow_name
    provider_name, prompt_name = _provider_role_binding_names(
        providers_expr,
        role_name=role_name,
        local_values=local_values,
    )
    if provider_name is None and prompt_name is None:
        return workflow_name
    provider_binding = context.extern_environment.bindings_by_name.get(provider_name) if provider_name else None
    prompt_binding = context.extern_environment.bindings_by_name.get(prompt_name) if prompt_name else None
    provider_id = provider_binding.provider_id if isinstance(provider_binding, ProviderExtern) else None
    prompt_path = prompt_binding.asset_file if isinstance(prompt_binding, PromptExtern) else None
    specialized_name = f"{workflow_name}__{role_name.replace('-', '_')}_rebound"
    if imported_bundle is not None:
        specialized_bundle = _specialize_imported_bundle_provider_metadata(
            imported_bundle,
            provider_id=provider_id,
            prompt_path=prompt_path,
            alias=specialized_name,
        )
        mutable_imports = context.imported_workflow_bundles
        if isinstance(mutable_imports, dict):
            mutable_imports[specialized_name] = specialized_bundle
    if same_file_callee is not None:
        specialized_workflow = _specialize_same_file_lowered_workflow_provider_metadata(
            same_file_callee,
            provider_id=provider_id,
            prompt_path=prompt_path,
            alias=specialized_name,
        )
        mutable_callees = context.lowered_callees
        if isinstance(mutable_callees, dict):
            mutable_callees[specialized_name] = specialized_workflow
    return specialized_name


def _provider_role_binding_names(
    expr: Any,
    *,
    role_name: str,
    local_values: Mapping[str, Any],
) -> tuple[str | None, str | None]:
    """Extract provider and prompt binding names for one drain role."""

    resolved = _resolve_inline_expr_value(expr, local_values=local_values)
    role_value = _mapping_field(resolved, role_name)
    if role_value is None:
        role_value = _mapping_field(resolved, role_name.replace("-", "_"))
    return _find_first_nameexpr(role_value, prefix="providers."), _find_first_nameexpr(role_value, prefix="prompts.")


def _mapping_field(value: Any, field_name: str) -> Any | None:
    """Read a field from a resolved mapping or frontend record expression."""

    if isinstance(value, Mapping):
        return value.get(field_name)
    if isinstance(value, RecordExpr):
        for name, field_value in value.fields:
            if name == field_name:
                return field_value
        return None
    return None


def _find_first_nameexpr(value: Any, *, prefix: str) -> str | None:
    """Find the first nested name expression with the requested prefix."""

    if isinstance(value, NameExpr):
        return value.name if value.name.startswith(prefix) else None
    if isinstance(value, RecordExpr):
        for _, field_value in value.fields:
            name = _find_first_nameexpr(field_value, prefix=prefix)
            if name is not None:
                return name
        return None
    if isinstance(value, Mapping):
        for field_value in value.values():
            name = _find_first_nameexpr(field_value, prefix=prefix)
            if name is not None:
                return name
    if isinstance(value, tuple):
        for item in value:
            name = _find_first_nameexpr(item, prefix=prefix)
            if name is not None:
                return name
    return None


def _specialize_imported_bundle_provider_metadata(
    bundle: LoadedWorkflowBundle,
    *,
    provider_id: str | None,
    prompt_path: str | None,
    alias: str,
) -> LoadedWorkflowBundle:
    """Clone an imported bundle with provider or prompt metadata rebound."""

    if provider_id is None and prompt_path is None:
        return bundle

    def rewrite_surface_step(step: Any) -> Any:
        updated_step = step
        if getattr(step, "kind", None) == SurfaceStepKind.PROVIDER:
            updated_step = replace(
                updated_step,
                provider=provider_id or getattr(updated_step, "provider", None),
                asset_file=prompt_path or getattr(updated_step, "asset_file", None),
            )
        then_branch = getattr(updated_step, "then_branch", None)
        else_branch = getattr(updated_step, "else_branch", None)
        match_cases = getattr(updated_step, "match_cases", None)
        repeat_until = getattr(updated_step, "repeat_until", None)
        for_each_steps = getattr(updated_step, "for_each_steps", ())
        replacements: dict[str, Any] = {}
        if then_branch is not None:
            replacements["then_branch"] = replace(
                then_branch,
                steps=tuple(rewrite_surface_step(step) for step in then_branch.steps),
            )
        if else_branch is not None:
            replacements["else_branch"] = replace(
                else_branch,
                steps=tuple(rewrite_surface_step(step) for step in else_branch.steps),
            )
        if isinstance(match_cases, Mapping):
            replacements["match_cases"] = MappingProxyType(
                {
                    name: replace(case, steps=tuple(rewrite_surface_step(step) for step in case.steps))
                    for name, case in match_cases.items()
                }
            )
        if repeat_until is not None:
            replacements["repeat_until"] = replace(
                repeat_until,
                steps=tuple(rewrite_surface_step(step) for step in repeat_until.steps),
            )
        if for_each_steps:
            replacements["for_each_steps"] = tuple(rewrite_surface_step(step) for step in for_each_steps)
        if replacements:
            updated_step = replace(updated_step, **replacements)
        return updated_step

    rewritten_surface = replace(
        bundle.surface,
        name=alias,
        steps=tuple(rewrite_surface_step(step) for step in bundle.surface.steps),
    )
    rewritten_nodes = {}
    for node_id, node in bundle.ir.nodes.items():
        execution_config = getattr(node, "execution_config", None)
        if isinstance(execution_config, ProviderStepConfig):
            execution_config = replace(
                execution_config,
                provider=provider_id or execution_config.provider,
                asset_file=prompt_path or execution_config.asset_file,
            )
            rewritten_nodes[node_id] = replace(node, execution_config=execution_config)
        else:
            rewritten_nodes[node_id] = node
    rewritten_ir = replace(
        bundle.ir,
        name=alias,
        nodes=MappingProxyType(rewritten_nodes),
    )
    return replace(bundle, surface=rewritten_surface, ir=rewritten_ir)


def _specialize_same_file_lowered_workflow_provider_metadata(
    lowered_workflow: LoweredWorkflow,
    *,
    provider_id: str | None,
    prompt_path: str | None,
    alias: str,
) -> LoweredWorkflow:
    """Clone a same-file lowered workflow with provider/prompt metadata rebound."""

    from .core import LoweredWorkflow

    if provider_id is None and prompt_path is None:
        return lowered_workflow

    def rewrite(value: Any) -> Any:
        if isinstance(value, list):
            return [rewrite(item) for item in value]
        if isinstance(value, Mapping):
            rewritten = {
                key: rewrite(item)
                for key, item in value.items()
            }
            if isinstance(value.get("provider"), str):
                rewritten["provider"] = provider_id or str(value["provider"])
                if "asset_file" in rewritten:
                    rewritten["asset_file"] = prompt_path or rewritten["asset_file"]
            return rewritten
        return value

    definition = replace(lowered_workflow.typed_workflow.definition, name=alias)
    signature = replace(lowered_workflow.typed_workflow.signature, name=alias)
    typed_workflow = replace(
        lowered_workflow.typed_workflow,
        definition=definition,
        signature=signature,
    )
    origin_map = _rekey_origin_map(
        lowered_workflow.origin_map,
        workflow_name=alias,
    )
    authored_mapping = rewrite(lowered_workflow.authored_mapping)
    assert isinstance(authored_mapping, dict)
    authored_mapping["name"] = alias
    return LoweredWorkflow(
        typed_workflow=typed_workflow,
        authored_mapping=authored_mapping,
        origin_map=origin_map,
        boundary_projection=lowered_workflow.boundary_projection,
        private_artifact_ids=lowered_workflow.private_artifact_ids,
    )


def _workflow_extern_requirements(
    typed_workflow: TypedWorkflowDef,
    *,
    typed_procedures: Mapping[str, TypedProcedureDef],
) -> tuple[set[str], set[str]]:
    """Collect provider and prompt extern names required by a typed workflow."""

    provider_names: set[str] = set()
    prompt_names: set[str] = set()
    visiting_procedures: set[str] = set()

    def walk(expr: Any) -> None:
        if isinstance(expr, ProviderResultExpr):
            if isinstance(expr.provider, NameExpr):
                provider_names.add(expr.provider.name)
            if isinstance(expr.prompt, NameExpr):
                prompt_names.add(expr.prompt.name)
            for value in expr.inputs:
                walk(value)
            return
        if isinstance(expr, RunProviderPhaseExpr):
            if isinstance(expr.provider, NameExpr):
                provider_names.add(expr.provider.name)
            if isinstance(expr.prompt, NameExpr):
                prompt_names.add(expr.prompt.name)
            walk(expr.ctx_expr)
            walk(expr.inputs_expr)
            return
        if isinstance(expr, ProduceOneOfExpr):
            if isinstance(expr.producer.provider_expr, NameExpr):
                provider_names.add(expr.producer.provider_expr.name)
            if isinstance(expr.producer.prompt_expr, NameExpr):
                prompt_names.add(expr.producer.prompt_expr.name)
            for value in expr.producer.inputs:
                walk(value)
            return
        if isinstance(expr, ProcedureCallExpr):
            for value in expr.args:
                walk(value)
            procedure = typed_procedures.get(expr.callee_name)
            if procedure is None or procedure.definition.name in visiting_procedures:
                return
            visiting_procedures.add(procedure.definition.name)
            walk(procedure.typed_body.expr)
            visiting_procedures.remove(procedure.definition.name)
            return
        if isinstance(expr, LetStarExpr):
            for _, binding in expr.bindings:
                walk(binding)
            walk(expr.body)
            return
        if isinstance(expr, MatchExpr):
            walk(expr.subject)
            for arm in expr.arms:
                walk(arm.body)
            return
        if isinstance(expr, IfExpr):
            walk(expr.condition_expr)
            walk(expr.then_expr)
            walk(expr.else_expr)
            return
        if isinstance(expr, LoopRecurExpr):
            walk(expr.max_iterations_expr)
            walk(expr.initial_state_expr)
            walk(expr.body_expr)
            return
        if isinstance(expr, ContinueExpr):
            walk(expr.state_expr)
            return
        if isinstance(expr, DoneExpr):
            walk(expr.result_expr)
            return
        if isinstance(expr, RecordExpr):
            for _, value in expr.fields:
                walk(value)
            return
        if isinstance(expr, CallExpr):
            for _, value in expr.bindings:
                walk(value)
            return
        if isinstance(expr, CommandResultExpr):
            for value in expr.argv:
                walk(value)

    walk(typed_workflow.typed_body.expr)
    return provider_names, prompt_names
