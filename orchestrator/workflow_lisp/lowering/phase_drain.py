"""Phase-drain owner surface for stdlib lowering and retained intrinsic compatibility."""

from __future__ import annotations

import json
import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass, replace
from types import SimpleNamespace
from pathlib import Path
from types import MappingProxyType
from typing import Any

from orchestrator.workflow.loaded_bundle import (
    LoadedWorkflowBundle,
    workflow_boundary_projection,
    workflow_input_contracts,
    workflow_managed_write_root_inputs,
    workflow_runtime_context_inputs,
)
from orchestrator.workflow.references import StructuredStepReference
from orchestrator.workflow.executable_ir import ProviderStepConfig
from orchestrator.workflow.surface_ast import PrivateExecContextBinding, SurfaceStep, SurfaceStepKind

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
    ResumeOrStartExpr,
    RunProviderPhaseExpr,
    UnionVariantExpr,
    WorkflowRefLiteralExpr,
    WithPhaseExpr,
)
from ..phase import IMPLEMENTATION_ATTEMPT_PHASE_NAME, PHASE_TARGET_SPECS, PhaseScope
from ..phase import (
    derived_private_child_context_eligibility,
    eligible_private_context_source_param_names,
    private_exec_context_kind,
)
from ..procedure_refs import ResolvedProcRefValue, resolve_proc_ref_value
from ..procedures import ProcedureCatalog
from ..spans import SourceSpan
from ..type_env import PathTypeRef, ProcRefTypeRef, RecordTypeRef, TypeRef, UnionTypeRef
from ..typecheck import TypedExpr
from ..workflow_refs import ResolvedWorkflowRef, resolve_workflow_ref_literal, resolve_workflow_ref_name, workflow_ref_target_name
from ..workflows import (
    CertifiedAdapterBinding,
    PromptExtern,
    ProviderExtern,
    WorkflowDef,
    WorkflowParam,
    WorkflowSignature,
    TypedWorkflowDef,
    analyze_workflow_boundary_type,
)
from . import core as lowering_core
from . import workflow_calls as lowering_workflow_calls
from .context import (
    _ActivePhaseScope,
    _compile_error,
    _copy_context_with_phase_scope,
    _copy_context_with_step_prefix,
    _LoweringContext,
    _TerminalResult,
)
from .control_loops import _conditional_case_ref, _materialize_values_step
from .effects import _lower_provider_result
from .drain_terminal import lower_shared_drain_terminal_result
from .origins import (
    LoweringOrigin,
    _origin_from_context_source,
    _record_missing_step_origins,
    _record_step_origin,
    _rekey_origin_map,
)
from .phase_flow import _build_match_projection_anchor_step, _provider_metadata_names
from .phase_scope import (
    _build_call_bindings_from_record_value,
    _join_ref_path,
    _managed_write_root_bindings,
    _managed_write_root_requirements_for_callable,
    _render_repeat_until_max_iterations,
    _same_file_workflow_provider_requirements,
)
from .values import (
    _assign_nested_local_value,
    _build_output_step_local_value,
    _flatten_boundary_leaf_paths,
    _normalize_union_field_path,
    _phase_target_inline_ref,
    _record_expr_value_at_path,
    _record_output_refs,
    _render_existing_output_ref,
    _resolve_inline_expr_value,
    _resolve_nested_local_value,
    _union_variant_expr_value_at_path,
)
from .workflow_calls import (
    _lower_call_expr,
    _render_boolean_predicate,
    _render_call_binding_ref,
    _render_record_call_bindings,
)


def _normalize_generated_step_id(*args, **kwargs):
    return lowering_core._normalize_generated_step_id(*args, **kwargs)


def _template_for_ref(ref: str) -> str:
    if ref.startswith("${"):
        return ref
    return "${" + ref + "}"


def _runtime_proof_generated_source(source: object) -> object:
    if getattr(source, "expansion_stack", ()):
        return source
    return SimpleNamespace(
        span=getattr(source, "span"),
        form_path=getattr(source, "form_path", ()),
        expansion_stack=(object(),),
    )


def _record_compatibility_backlog_drain_hit() -> None:
    from .control_dispatch import record_intrinsic_form_lowering

    record_intrinsic_form_lowering("backlog-drain")


def _callable_backlog_drain_enabled(
    *,
    expr: BacklogDrainExpr,
    context: _LoweringContext,
) -> bool:
    return bool(
        expr.spec.preserve_owner_boundary
        and context.lowering_schema_version not in (None, 1)
    )


def _callable_backlog_drain_workflow_name() -> str:
    return "std/drain::backlog-drain"


def _semantic_specialization_identity(value: object) -> str:
    if is_dataclass(value):
        return (
            f"{type(value).__name__}("
            + ",".join(
                f"{field.name}={_semantic_specialization_identity(getattr(value, field.name))}"
                for field in fields(value)
                if field.name not in {"span", "form_path", "expansion_stack"}
            )
            + ")"
        )
    if isinstance(value, tuple):
        return "(" + ",".join(_semantic_specialization_identity(item) for item in value) + ")"
    if isinstance(value, list):
        return "[" + ",".join(_semantic_specialization_identity(item) for item in value) + "]"
    if isinstance(value, Mapping):
        return (
            "{"
            + ",".join(
                f"{_semantic_specialization_identity(key)}:{_semantic_specialization_identity(value[key])}"
                for key in sorted(value, key=repr)
            )
            + "}"
        )
    if isinstance(value, frozenset):
        return "frozenset(" + ",".join(sorted(_semantic_specialization_identity(item) for item in value)) + ")"
    return repr(value)


def _callable_backlog_drain_specialization_key(
    *,
    ctx_type: TypeRef,
    return_type: TypeRef,
    selector_call_target: str,
    run_item_call_target: str,
    gap_drafter_call_target: str,
    max_iterations_expr: object,
) -> tuple[object, ...]:
    return (
        getattr(ctx_type, "name", None),
        getattr(return_type, "name", None),
        selector_call_target,
        run_item_call_target,
        gap_drafter_call_target,
        _semantic_specialization_identity(max_iterations_expr),
    )


def _generated_callable_backlog_drain_matches_specialization(
    workflow: TypedWorkflowDef | None,
    *,
    specialization_key: tuple[object, ...],
) -> bool:
    if workflow is None:
        return False
    typed_body_expr = getattr(workflow.typed_body, "expr", None)
    if not isinstance(typed_body_expr, BacklogDrainExpr):
        return False
    return _callable_backlog_drain_specialization_key(
        ctx_type=workflow.signature.params[0][1],
        return_type=workflow.signature.return_type_ref,
        selector_call_target=typed_body_expr.spec.selector_name,
        run_item_call_target=typed_body_expr.spec.run_item_name,
        gap_drafter_call_target=typed_body_expr.spec.gap_drafter_name,
        max_iterations_expr=typed_body_expr.spec.max_iterations_expr,
    ) == specialization_key


def _specialized_callable_backlog_drain_workflow_name(
    specialization_key: tuple[object, ...],
) -> str:
    digest = hashlib.sha1(repr(specialization_key).encode("utf-8")).hexdigest()[:12]
    return f"{_callable_backlog_drain_workflow_name()}__{digest}"


def _is_generated_callable_backlog_drain_workflow(workflow_name: str) -> bool:
    base_name = _callable_backlog_drain_workflow_name()
    return workflow_name == base_name or workflow_name.startswith(f"{base_name}__")


def _compatibility_backlog_drain_accounting_enabled(*, context: _LoweringContext) -> bool:
    return not _is_generated_callable_backlog_drain_workflow(context.workflow_name)


def _ensure_callable_backlog_drain_workflow(
    *,
    typed_expr: TypedExpr,
    context: _LoweringContext,
    ctx_type: TypeRef,
    selector_call_target: str,
    run_item_call_target: str,
    gap_drafter_call_target: str,
) -> str:
    expr = typed_expr.expr
    assert isinstance(expr, BacklogDrainExpr)
    specialization_key = _callable_backlog_drain_specialization_key(
        ctx_type=ctx_type,
        return_type=typed_expr.type_ref,
        selector_call_target=selector_call_target,
        run_item_call_target=run_item_call_target,
        gap_drafter_call_target=gap_drafter_call_target,
        max_iterations_expr=expr.spec.max_iterations_expr,
    )
    workflow_name = _callable_backlog_drain_workflow_name()
    existing_shared_workflow = context.workflows_by_name.get(workflow_name)
    if _generated_callable_backlog_drain_matches_specialization(
        existing_shared_workflow,
        specialization_key=specialization_key,
    ):
        return workflow_name
    if existing_shared_workflow is not None:
        workflow_name = _specialized_callable_backlog_drain_workflow_name(specialization_key)
        if context.workflows_by_name.get(workflow_name) is not None:
            return workflow_name

    child_expr = BacklogDrainExpr(
        spec=replace(
            expr.spec,
            ctx_expr=NameExpr(
                name="ctx",
                span=expr.spec.ctx_expr.span,
                form_path=expr.spec.ctx_expr.form_path,
                expansion_stack=expr.spec.ctx_expr.expansion_stack,
            ),
            selector_name=selector_call_target,
            run_item_name=run_item_call_target,
            gap_drafter_name=gap_drafter_call_target,
            providers_expr=expr.spec.providers_expr,
            preserve_owner_boundary=False,
        ),
        span=expr.span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    child_workflow = TypedWorkflowDef(
        definition=WorkflowDef(
            name=workflow_name,
            params=(
                WorkflowParam(
                    name="ctx",
                    type_name=getattr(ctx_type, "name", "DrainCtx"),
                    span=expr.spec.ctx_expr.span,
                    form_path=expr.spec.ctx_expr.form_path,
                    expansion_stack=expr.spec.ctx_expr.expansion_stack,
                ),
            ),
            return_type_name=getattr(typed_expr.type_ref, "name", "DrainResult"),
            body=child_expr,
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        ),
        signature=WorkflowSignature(
            name=workflow_name,
            params=(("ctx", ctx_type),),
            return_type_ref=typed_expr.type_ref,
            span=expr.span,
            form_path=expr.form_path,
        ),
        typed_body=replace(typed_expr, expr=child_expr),
        effect_summary=typed_expr.effect_summary,
    )
    if isinstance(context.workflows_by_name, dict):
        context.workflows_by_name[workflow_name] = child_workflow
    if isinstance(context.workflow_catalog.signatures_by_name, dict):
        context.workflow_catalog.signatures_by_name[workflow_name] = child_workflow.signature
    if isinstance(context.workflow_catalog.definitions_by_name, dict):
        context.workflow_catalog.definitions_by_name[workflow_name] = child_workflow.definition
    return workflow_name




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
    def _require_backlog_drain_public_params(
        *,
        role_name: str,
        signature: Any,
        expected_count: int,
    ) -> None:
        actual_params = tuple(signature.params)
        if len(actual_params) == expected_count:
            return
        if len(actual_params) > expected_count:
            unexpected_name = actual_params[expected_count][0]
            message = (
                f"`backlog-drain :{role_name}` must not expose public binding "
                f"`{unexpected_name}`; compatibility bridge inputs must stay private"
            )
        else:
            message = (
                f"`backlog-drain :{role_name}` must expose exactly {expected_count} public "
                f"parameter{'s' if expected_count != 1 else ''}"
            )
        raise _compile_error(
            code="workflow_signature_mismatch",
            message=message,
            span=expr.span,
            form_path=expr.form_path,
        )

    _require_backlog_drain_public_params(
        role_name="selector",
        signature=selector_signature,
        expected_count=1,
    )
    _require_backlog_drain_public_params(
        role_name="run-item",
        signature=run_item_signature,
        expected_count=2,
    )
    _require_backlog_drain_public_params(
        role_name="gap-drafter",
        signature=gap_drafter_signature,
        expected_count=2,
    )
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
        selector_resolved_ref=selector_ref,
        run_item_resolved_ref=run_item_ref,
        gap_drafter_resolved_ref=gap_drafter_ref,
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
    if _callable_backlog_drain_enabled(expr=expr, context=context):
        callable_workflow_name = _ensure_callable_backlog_drain_workflow(
            typed_expr=typed_expr,
            context=context,
            ctx_type=selector_signature.params[0][1],
            selector_call_target=selector_call_target,
            run_item_call_target=run_item_call_target,
            gap_drafter_call_target=gap_drafter_call_target,
        )
        context.ensure_workflow_lowered(callable_workflow_name)
        return _lower_call_expr(
            replace(
                typed_expr,
                expr=CallExpr(
                    callee_name=callable_workflow_name,
                    bindings=(("ctx", expr.spec.ctx_expr),),
                    span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
            ),
            context=context,
            local_values=local_values,
        )
    if _compatibility_backlog_drain_accounting_enabled(context=context):
        _record_compatibility_backlog_drain_hit()
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
    gap_payload_type = gap_drafter_signature.params[1][1]
    if not isinstance(gap_payload_type, RecordTypeRef):
        raise _compile_error(
            code="workflow_signature_mismatch",
            message="`backlog-drain :gap-drafter` second parameter must remain a record payload",
            span=expr.span,
            form_path=expr.form_path,
        )
    gap_value: dict[str, Any] = {}
    for _, field_path in _flatten_boundary_leaf_paths(
        gap_payload_type,
        generated_name=gap_drafter_signature.params[1][0],
    ):
        _assign_nested_local_value(
            gap_value,
            field_path,
            f"self.steps.{selector_call_name}.artifacts.return__gap__{'__'.join(field_path)}",
        )
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
        "allowed": ["CONTINUE", "EMPTY", "COMPLETED", "BLOCKED", "EXHAUSTED"],
    }
    accumulator_progress_contract = {
        "kind": "relpath",
        "type": "relpath",
        "under": "artifacts/work",
        "must_exist_target": False,
    }
    accumulator_blocker_contract = dict(_return_contract("blocker-class"))
    accumulator_blocker_contract.pop("projection", None)
    selector_blocked_compatibility_blocker = "user_decision_required"
    seed_progress_literal = "artifacts/work/drain-progress-report.md"
    placeholder_progress_ref = f"artifacts/work/.orchestrate/workflow_lisp/{step_name}/unused_progress_report.md"
    placeholder_blocker_value = accumulator_blocker_contract["allowed"][0]
    hidden_inputs: dict[str, LoweringOrigin] = {}

    loop_output_definitions = {
        "acc__loop-status": dict(accumulator_status_contract),
        "acc__items-processed": dict(items_processed_contract),
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
        source_record_values: Mapping[str, Any] | None,
        lowered_callee: LoweredWorkflow | None,
        imported_bundle: LoadedWorkflowBundle | None,
        callee_signature: Any,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        def _param_has_authored_binding(param_name: str, param_type: Any) -> bool:
            if param_name in step["with"]:
                return True
            if not isinstance(param_type, RecordTypeRef):
                return False
            flattened_field_names = {
                field.generated_name
                for field in derive_workflow_boundary_fields(
                    param_type,
                    generated_name=param_name,
                    source_path=(param_name,),
                    span=expr.span,
                    form_path=expr.form_path,
                )
            }
            return any(field_name in step["with"] for field_name in flattened_field_names)

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
        prepare_steps: list[dict[str, Any]] = []
        if managed_inputs:
            bundle_input_name = f"__write_root__{step['id']}__managed_write_roots_bundle"
            hidden_inputs[bundle_input_name] = _origin_from_context_source(context, expr)
            prepare_step_name = f"{generated_name}__managed_write_roots"
            prepare_step_id = _normalize_generated_step_id(prepare_step_name)
            binding_values = _managed_write_root_bindings(
                caller_workflow_name=context.workflow_name,
                call_step_name=generated_name,
                callee_name=call_target,
                managed_inputs=managed_inputs,
                iteration_scope="${loop.index}",
            )
            command = [
                "python",
                "-c",
                (
                    "import json, pathlib, sys; "
                    "out = pathlib.Path(sys.argv[1]); "
                    "out.parent.mkdir(parents=True, exist_ok=True); "
                    "args = sys.argv[2:]; "
                    "payload = {args[i]: args[i + 1] for i in range(0, len(args), 2)}; "
                    "out.write_text(json.dumps(payload, sort_keys=True) + '\\n', encoding='utf-8')"
                ),
                f"${{inputs.{bundle_input_name}}}",
            ]
            for managed_input, value in binding_values.items():
                command.extend((managed_input, value))
            prepare_steps = [
                {
                    "name": prepare_step_name,
                    "id": prepare_step_id,
                    "command": command,
                    "output_bundle": {
                        "path": f"${{inputs.{bundle_input_name}}}",
                        "fields": [
                            {
                                "name": managed_input,
                                "json_pointer": f"/{managed_input}",
                                "type": "relpath",
                            }
                            for managed_input in sorted(managed_inputs)
                        ],
                    },
                }
            ]
            _record_step_origin(
                context,
                step_name=prepare_step_name,
                step_id=prepare_step_id,
                source=expr,
            )
            managed_bindings = {
                managed_input: {"ref": f"self.steps.{prepare_step_name}.artifacts.{managed_input}"}
                for managed_input in sorted(managed_inputs)
            }
            step["with"].update(managed_bindings)
        for param_name, param_type in callee_signature.params:
            if _param_has_authored_binding(param_name, param_type) or not isinstance(param_type, RecordTypeRef):
                continue
            requirement = getattr(callee_signature, "hidden_context_requirements", {}).get(param_name)
            if requirement is not None and requirement.binding_kind == "derived_private_child_context":
                ambiguities = getattr(callee_signature, "hidden_context_ambiguities", {})
                if requirement.phase_name is None or param_name in ambiguities:
                    raise lowering_core._compile_error(
                        code="derived_phase_context_ambiguous",
                        message=f"derived child phase context for `{param_name}` is ambiguous in this callee",
                        span=expr.span,
                        form_path=expr.form_path,
                    )
                eligibility = derived_private_child_context_eligibility(
                    context.signature,
                    param_name=param_name,
                )
                if not eligibility.allowed:
                    raise lowering_core._compile_error(
                        code=eligibility.diagnostic_code or "derived_phase_context_binding_invalid",
                        message=eligibility.diagnostic_message
                        or f"invalid derived child phase context for `{param_name}`",
                        span=expr.span,
                        form_path=expr.form_path,
                    )
                generated_binding_name = f"{param_name}__{requirement.phase_name}"
                step["with"].update(
                    lowering_workflow_calls._declare_runtime_context_hidden_inputs(
                        context=context,
                        param_name=param_name,
                        param_type=param_type,
                        requirement=requirement,
                        source_expr=expr,
                        source_param_name=eligibility.source_param_name,
                        bridge_class="derived_private_child_context",
                        binding_id=generated_binding_name,
                        generated_name=generated_binding_name,
                        carried_input_sources=eligibility.carried_input_sources,
                        carried_source_expr=(
                            source_record_values.get(eligibility.source_param_name)
                            if source_record_values is not None
                            and eligibility.source_param_name is not None
                            else None
                        ),
                        local_values=local_values,
                    )
                )
                continue
            if requirement is not None:
                step["with"].update(
                    lowering_core._declare_runtime_context_hidden_inputs(
                        context=context,
                        param_name=param_name,
                        param_type=param_type,
                        requirement=requirement,
                        source_expr=expr,
                    )
                )
                continue
            if private_exec_context_kind(param_type) is not None:
                code = "promoted_entry_hidden_context_metadata_missing"
                ambiguities = getattr(callee_signature, "hidden_context_ambiguities", {})
                if param_name in ambiguities:
                    code = "promoted_entry_hidden_phase_ctx_ambiguous"
                raise lowering_core._compile_error(
                    code=code,
                    message=f"promoted-entry hidden binding metadata is unavailable for `{param_name}`",
                    span=expr.span,
                    form_path=expr.form_path,
                )
        private_exec_context_bindings: tuple[PrivateExecContextBinding, ...] = ()
        if lowered_callee is not None:
            private_exec_context_bindings = getattr(lowered_callee, "private_exec_context_bindings", ())
        elif imported_bundle is not None:
            private_exec_context_bindings = workflow_boundary_projection(
                imported_bundle
            ).private_runtime_context_bindings
        for binding in private_exec_context_bindings:
            if binding.bridge_class != "derived_private_child_context":
                continue
            source_value = (
                source_record_values.get(binding.source_param_name)
                if source_record_values is not None
                else None
            )
            if not isinstance(source_value, Mapping):
                continue
            carried_input_sources = binding.projection_hints.get("carried_input_sources", {})
            if isinstance(carried_input_sources, Mapping) and carried_input_sources:
                for generated_name, source_path in carried_input_sources.items():
                    if not isinstance(generated_name, str) or not isinstance(source_path, (tuple, list)):
                        continue
                    if not source_path or source_path[0] != binding.source_param_name:
                        continue
                    field_path = tuple(str(part) for part in source_path[1:])
                    if not field_path or generated_name in step["with"]:
                        continue
                    carried_value = _resolve_nested_local_value(source_value, field_path)
                    step["with"][generated_name] = lowering_core._render_call_binding_leaf_ref(
                        carried_value,
                        source_expr=expr,
                    )
        step["with"].update(
            lowering_workflow_calls._carry_callee_private_exec_context_bindings(
                context=context,
                source_expr=expr,
                lowered_callee=lowered_callee,
                imported_bundle=imported_bundle,
                already_bound=set(step["with"]),
            )
        )
        step["with"].update(
            lowering_workflow_calls._carry_callee_runtime_context_inputs(
                context=context,
                source_expr=expr,
                lowered_callee=lowered_callee,
                imported_bundle=imported_bundle,
                already_bound=set(step["with"]),
            )
        )
        for binding in private_exec_context_bindings:
            if binding.bridge_class != "derived_private_child_context":
                continue
            carried_input_sources = binding.projection_hints.get("carried_input_sources", {})
            if not isinstance(carried_input_sources, Mapping) or not carried_input_sources:
                continue
            remapped_sources: dict[str, tuple[str, ...]] = {}
            source_roots: set[str] = set()
            for generated_name in carried_input_sources:
                binding_value = step["with"].get(generated_name)
                if not isinstance(binding_value, Mapping):
                    continue
                ref_value = binding_value.get("ref")
                if not isinstance(ref_value, str) or not ref_value.startswith("inputs."):
                    continue
                ref_name = ref_value.removeprefix("inputs.")
                parts = tuple(part for part in ref_name.split("__") if part)
                if not parts:
                    continue
                remapped_sources[generated_name] = parts
                source_roots.add(parts[0])
            if not remapped_sources:
                continue
            remapped_source_param_name = (
                next(iter(source_roots))
                if len(source_roots) == 1
                else binding.source_param_name
            )
            remapped_projection_hints = dict(binding.projection_hints)
            remapped_projection_hints["carried_input_sources"] = remapped_sources
            for index, carried_binding in enumerate(context.private_exec_context_bindings):
                if (
                    carried_binding.binding_id == binding.binding_id
                    and carried_binding.bridge_class == binding.bridge_class
                ):
                    context.private_exec_context_bindings[index] = replace(
                        carried_binding,
                        source_param_name=remapped_source_param_name,
                        projection_hints=remapped_projection_hints,
                    )
                    break
        compatibility_bridge_owner = None
        if lowered_callee is not None:
            compatibility_bridge_owner = lowered_callee
        elif imported_bundle is not None:
            compatibility_bridge_owner = type(
                "ImportedBundleCompatibilityBridgeOwner",
                (),
                {
                    "compatibility_bridge_inputs": workflow_boundary_projection(
                        imported_bundle
                    ).private_compatibility_bridge_inputs
                },
            )()
        compatibility_bridge_input_names = set(
            getattr(compatibility_bridge_owner, "compatibility_bridge_inputs", ())
            if compatibility_bridge_owner is not None
            else ()
        )
        if not compatibility_bridge_input_names:
            compatibility_bridge_input_names.update(
                getattr(callee_signature, "private_compatibility_bridge_types", {}).keys()
            )
        omitted_compatibility_bridge_inputs = {
            input_name
            for input_name in compatibility_bridge_input_names
            if input_name not in step["with"]
        }
        if omitted_compatibility_bridge_inputs:
            bridge_owner = compatibility_bridge_owner
            if bridge_owner is None:
                bridge_owner = type(
                    "SignatureCompatibilityBridgeOwner",
                    (),
                    {
                        "compatibility_bridge_inputs": tuple(
                            sorted(omitted_compatibility_bridge_inputs)
                        )
                    },
                )()
            step["with"].update(
                lowering_workflow_calls._compatibility_bridge_bindings_for_lowered_callee(
                    context=context,
                    lowered_callee=bridge_owner,
                    source_expr=expr,
                    local_values=dict(local_values),
                    already_bound=set(step["with"]),
                    allowed_inputs=omitted_compatibility_bridge_inputs,
                )
            )
        for managed_input in managed_inputs:
            hidden_inputs[managed_input] = _origin_from_context_source(context, expr)
        _record_step_origin(context, step_name=generated_name, step_id=step["id"], source=expr)
        return prepare_steps, step

    def _accumulator_marker_step(
        *,
        name: str,
        step_id_value: str,
        loop_status: str,
        progress_ref: str | None = None,
        blocker_ref: str | None = None,
        blocker_literal: str | None = None,
    ) -> dict[str, Any]:
        blocker_source: dict[str, str]
        if blocker_ref is not None:
            blocker_source = {"ref": blocker_ref}
        elif blocker_literal is not None:
            blocker_source = {"literal": blocker_literal}
        else:
            blocker_source = {"literal": placeholder_blocker_value}
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
                    "name": "acc__progress-report-path",
                    "source": {"ref": progress_ref} if progress_ref is not None else {"literal": placeholder_progress_ref},
                    "contract": dict(accumulator_progress_contract),
                },
                {
                    "name": "acc__blocker-class",
                    "source": blocker_source,
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
            "acc__progress-report-path": {
                **loop_output_definitions["acc__progress-report-path"],
                "from": {"ref": f"self.steps.{marker_step_name}.artifacts.acc__progress-report-path"},
            },
            "acc__blocker-class": {
                **loop_output_definitions["acc__blocker-class"],
                "from": {"ref": f"self.steps.{marker_step_name}.artifacts.acc__blocker-class"},
            },
        }

    loop_state_seed_step_name = f"{step_name}__seed_loop_state"
    loop_state_seed_step = _materialize_outputs_step(
        name=loop_state_seed_step_name,
        step_id_value=_normalize_generated_step_id(loop_state_seed_step_name),
        values=[
            {
                "name": "acc__progress-report-path",
                "source": {"literal": seed_progress_literal},
                "contract": dict(accumulator_progress_contract),
            },
            {
                "name": "acc__blocker-class",
                "source": {"literal": placeholder_blocker_value},
                "contract": dict(accumulator_blocker_contract),
            },
        ],
    )

    current_loop_state_seed_marker_name = f"{step_name}__current_loop_state__seed_marker"
    current_loop_state_seed_marker_step = _materialize_outputs_step(
        name=current_loop_state_seed_marker_name,
        step_id_value=_normalize_generated_step_id(current_loop_state_seed_marker_name),
        values=[
            {
                "name": "seed_iteration",
                "source": {"literal": "seed"},
                "contract": {"kind": "scalar", "type": "string"},
            }
        ],
    )
    current_loop_state_seed_marker_step["when"] = {
        "equals": {
            "left": "${loop.index}",
            "right": "0",
        }
    }

    current_loop_state_name = f"{step_name}__current_loop_state"
    current_loop_state_use_carried_name = f"{current_loop_state_name}__use_carried_state"
    current_loop_state_use_seed_name = f"{current_loop_state_name}__use_seed_state"
    current_loop_state_step = {
        "name": current_loop_state_name,
        "id": _normalize_generated_step_id(current_loop_state_name),
        "if": {
            "compare": {
                "left": {"ref": f"self.steps.{current_loop_state_seed_marker_name}.outcome.class"},
                "op": "eq",
                "right": "skipped",
            }
        },
        "then": {
            "id": _normalize_generated_step_id(f"{current_loop_state_name}__carry"),
            "outputs": {
                "acc__progress-report-path": {
                    **dict(accumulator_progress_contract),
                    "from": {"ref": f"self.steps.{current_loop_state_use_carried_name}.artifacts.acc__progress-report-path"},
                },
                "acc__blocker-class": {
                    **dict(accumulator_blocker_contract),
                    "from": {"ref": f"self.steps.{current_loop_state_use_carried_name}.artifacts.acc__blocker-class"},
                },
            },
            "steps": [
                _materialize_outputs_step(
                    name=current_loop_state_use_carried_name,
                    step_id_value=_normalize_generated_step_id(current_loop_state_use_carried_name),
                    values=[
                        {
                            "name": "acc__progress-report-path",
                            "source": {"ref": f"root.steps.{step_name}.artifacts.acc__progress-report-path"},
                            "contract": dict(accumulator_progress_contract),
                        },
                        {
                            "name": "acc__blocker-class",
                            "source": {"ref": f"root.steps.{step_name}.artifacts.acc__blocker-class"},
                            "contract": dict(accumulator_blocker_contract),
                        },
                    ],
                )
            ],
        },
        "else": {
            "id": _normalize_generated_step_id(f"{current_loop_state_name}__seed"),
            "outputs": {
                "acc__progress-report-path": {
                    **dict(accumulator_progress_contract),
                    "from": {"ref": f"self.steps.{current_loop_state_use_seed_name}.artifacts.acc__progress-report-path"},
                },
                "acc__blocker-class": {
                    **dict(accumulator_blocker_contract),
                    "from": {"ref": f"self.steps.{current_loop_state_use_seed_name}.artifacts.acc__blocker-class"},
                },
            },
            "steps": [
                _materialize_outputs_step(
                    name=current_loop_state_use_seed_name,
                    step_id_value=_normalize_generated_step_id(current_loop_state_use_seed_name),
                    values=[
                        {
                            "name": "acc__progress-report-path",
                            "source": {"ref": f"root.steps.{loop_state_seed_step_name}.artifacts.acc__progress-report-path"},
                            "contract": dict(accumulator_progress_contract),
                        },
                        {
                            "name": "acc__blocker-class",
                            "source": {"ref": f"root.steps.{loop_state_seed_step_name}.artifacts.acc__blocker-class"},
                            "contract": dict(accumulator_blocker_contract),
                        },
                    ],
                )
            ],
        },
    }
    current_progress_ref = f"parent.steps.{current_loop_state_name}.artifacts.acc__progress-report-path"

    selector_prepare_steps, selector_call_step = _managed_call_step(
        generated_name=selector_call_name,
        call_target=selector_call_target,
        with_bindings=selector_with,
        source_record_values={selector_signature.params[0][0]: ctx_value},
        lowered_callee=selector_callee,
        imported_bundle=selector_imported,
        callee_signature=selector_signature,
    )
    gap_prepare_steps, gap_drafter_call_step = _managed_call_step(
        generated_name=gap_drafter_call_name,
        call_target=gap_drafter_call_target,
        with_bindings=gap_drafter_with,
        source_record_values={
            gap_drafter_signature.params[0][0]: ctx_value,
            gap_drafter_signature.params[1][0]: gap_value,
        },
        lowered_callee=gap_drafter_callee,
        imported_bundle=gap_drafter_imported,
        callee_signature=gap_drafter_signature,
    )
    gap_drafter_call_step["when"] = {
        "compare": {
            "left": {"ref": f"self.steps.{selector_call_name}.artifacts.return__variant"},
            "op": "eq",
            "right": "GAP",
        }
    }
    run_item_prepare_steps, run_item_call_step = _managed_call_step(
        generated_name=run_item_call_name,
        call_target=run_item_call_target,
        with_bindings=run_item_with,
        source_record_values={
            run_item_signature.params[0][0]: item_ctx_value,
            run_item_signature.params[1][0]: selection_value,
        },
        lowered_callee=run_item_callee,
        imported_bundle=run_item_imported,
        callee_signature=run_item_signature,
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
                    progress_ref=current_progress_ref,
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
                    progress_ref=current_progress_ref,
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
                        progress_ref=current_progress_ref,
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
                        progress_ref=current_progress_ref,
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
                            progress_ref=current_progress_ref,
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
                            progress_ref=f"parent.steps.{run_item_call_name}.artifacts.return__summary-path",
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
                            progress_ref=f"parent.steps.{run_item_call_name}.artifacts.return__summary-path",
                            blocker_ref=f"parent.steps.{run_item_call_name}.artifacts.return__blocker-class",
                        )
                    ],
                },
            },
        },
    }

    selector_blocked_route_step_name = f"{step_name}__route_selector_blocked"
    selector_blocked_marker_name = "MarkSelectorBlocked"
    selector_blocked_route_step = {
        "name": selector_blocked_route_step_name,
        "id": _normalize_generated_step_id(selector_blocked_route_step_name),
        "when": {
            "compare": {
                "left": {"ref": f"self.steps.{selector_call_name}.artifacts.return__variant"},
                "op": "eq",
                "right": "BLOCKED",
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
            "id": _normalize_generated_step_id(f"{selector_blocked_route_step_name}__blocked"),
            "outputs": _accumulator_outputs(
                marker_step_name=selector_blocked_marker_name,
                items_processed_ref=parent_current_items_ref,
            ),
            "steps": [
                _accumulator_marker_step(
                    name=selector_blocked_marker_name,
                    step_id_value="mark_selector_blocked",
                    loop_status="BLOCKED",
                    progress_ref=current_progress_ref,
                    blocker_literal=selector_blocked_compatibility_blocker,
                )
            ],
        },
        "else": {
            "id": _normalize_generated_step_id(f"{selector_blocked_route_step_name}__blocked_else"),
            "outputs": _accumulator_outputs(
                marker_step_name=selector_blocked_marker_name,
                items_processed_ref=parent_current_items_ref,
            ),
            "steps": [
                _accumulator_marker_step(
                    name=selector_blocked_marker_name,
                    step_id_value="mark_selector_blocked_else",
                    loop_status="BLOCKED",
                    progress_ref=current_progress_ref,
                    blocker_literal=selector_blocked_compatibility_blocker,
                )
            ],
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
                "BLOCKED": {
                    "id": _normalize_generated_step_id(f"{route_selection_step_name}__blocked"),
                    "outputs": _forward_accumulator_outputs(selector_blocked_route_step_name),
                    "steps": [
                        _build_match_projection_anchor_step(
                            match_step_name=route_selection_step_name,
                            variant_name="BLOCKED",
                            case_outputs=_forward_accumulator_outputs(selector_blocked_route_step_name),
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
    _record_step_origin(
        context,
        step_name=current_loop_state_seed_marker_name,
        step_id=current_loop_state_seed_marker_step["id"],
        source=expr,
    )
    runtime_proof_source = _runtime_proof_generated_source(expr)
    _record_step_origin(
        context,
        step_name=current_loop_state_name,
        step_id=current_loop_state_step["id"],
        source=runtime_proof_source,
    )
    _record_step_origin(
        context,
        step_name=current_loop_state_use_carried_name,
        step_id=_normalize_generated_step_id(current_loop_state_use_carried_name),
        source=runtime_proof_source,
    )
    _record_step_origin(
        context,
        step_name=current_loop_state_use_seed_name,
        step_id=_normalize_generated_step_id(current_loop_state_use_seed_name),
        source=runtime_proof_source,
    )
    _record_step_origin(context, step_name=current_items_step_name, step_id=current_items_step["id"], source=expr)
    _record_step_origin(context, step_name=empty_marker_name, step_id="mark_empty_selection", source=expr)
    _record_step_origin(context, step_name=completed_marker_name, step_id="mark_completed_selection", source=expr)
    _record_step_origin(
        context,
        step_name=empty_route_step_name,
        step_id=empty_route_step["id"],
        source=runtime_proof_source,
    )
    _record_step_origin(
        context,
        step_name=gap_route_step_name,
        step_id=gap_route_step["id"],
        source=runtime_proof_source,
    )
    _record_step_origin(
        context,
        step_name=selected_route_step_name,
        step_id=selected_route_step["id"],
        source=runtime_proof_source,
    )
    _record_step_origin(context, step_name=selector_blocked_marker_name, step_id="mark_selector_blocked", source=expr)
    _record_step_origin(context, step_name=selector_blocked_marker_name, step_id="mark_selector_blocked_else", source=expr)
    _record_step_origin(
        context,
        step_name=selector_blocked_route_step_name,
        step_id=selector_blocked_route_step["id"],
        source=runtime_proof_source,
    )
    _record_step_origin(
        context,
        step_name=route_selection_step_name,
        step_id=route_selection_step["id"],
        source=runtime_proof_source,
    )

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
                current_loop_state_seed_marker_step,
                current_loop_state_step,
                *selector_prepare_steps,
                selector_call_step,
                current_items_step,
                empty_route_step,
                *gap_prepare_steps,
                gap_drafter_call_step,
                gap_route_step,
                *run_item_prepare_steps,
                run_item_call_step,
                selected_route_step,
                selector_blocked_route_step,
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
            "on_exhausted": {
                "outputs": {
                    "acc__loop-status": "EXHAUSTED",
                    "acc__blocker-class": "unrecoverable_after_fix_attempt",
                }
            },
        },
    }

    result_output_definitions = {
        f"return__{field_name}": dict(contract)
        for field_name, contract in context.return_output_contracts.items()
    }
    terminal_status_contract = {
        "kind": "scalar",
        "type": "enum",
        "allowed": ["EMPTY", "COMPLETED", "BLOCKED", "EXHAUSTED"],
    }

    def _lower_terminal_finalizer_case(
        *,
        case_name: str,
        terminal_variant: str,
        terminal_items_ref: str,
        terminal_progress_ref: str,
        terminal_blocker_ref: str,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        case_context = _copy_context_with_step_prefix(
            context,
            step_name_prefix=f"{normalize_step_name}__{case_name}",
        )
        helper_terminal_steps, helper_terminal = lower_shared_drain_terminal_result(
            context=case_context,
            source_expr=expr,
            step_name_prefix=case_context.step_name_prefix,
            terminal_variant=terminal_variant,
            terminal_items_ref=terminal_items_ref,
            terminal_progress_ref=terminal_progress_ref,
            terminal_blocker_ref=terminal_blocker_ref,
            result_output_contracts=result_output_definitions,
            accumulator_progress_contract=accumulator_progress_contract,
            accumulator_blocker_contract=accumulator_blocker_contract,
            placeholder_blocker_value=placeholder_blocker_value,
        )
        hidden_inputs.update(helper_terminal.hidden_inputs)
        return helper_terminal_steps, {
            output_name: {
                **result_output_definitions[output_name],
                "from": {"ref": helper_terminal.output_refs[output_name]},
            }
            for output_name in result_output_definitions
        }

    normalize_step_name = f"{step_name}__normalize_result"
    normalize_step_id = _normalize_generated_step_id(normalize_step_name)
    _record_step_origin(context, step_name=normalize_step_name, step_id=normalize_step_id, source=expr)
    accumulator_items_ref = f"root.steps.{step_name}.artifacts.acc__items-processed"
    accumulator_progress_ref = f"root.steps.{step_name}.artifacts.acc__progress-report-path"
    accumulator_blocker_ref = f"root.steps.{step_name}.artifacts.acc__blocker-class"
    terminal_carrier_step_name = f"{step_name}__terminal_carrier"
    terminal_carrier_step_id = _normalize_generated_step_id(terminal_carrier_step_name)
    terminal_items_ref = f"root.steps.{terminal_carrier_step_name}.artifacts.terminal__items-processed"
    terminal_progress_ref = f"root.steps.{terminal_carrier_step_name}.artifacts.terminal__progress-report-path"
    terminal_blocker_ref = f"root.steps.{terminal_carrier_step_name}.artifacts.terminal__blocker-class"

    def _terminal_carrier_case(*, source_status: str, terminal_status: str) -> dict[str, Any]:
        case_step_name = f"{terminal_carrier_step_name}__{source_status.lower()}"
        case_step_id = _normalize_generated_step_id(case_step_name)
        materialize_step_name = f"{case_step_name}__materialize"
        materialize_step_id = _normalize_generated_step_id(materialize_step_name)
        outputs = {
            "terminal__variant": {
                **terminal_status_contract,
                "from": {"ref": f"self.steps.{materialize_step_name}.artifacts.terminal__variant"},
            },
            "terminal__items-processed": {
                **dict(items_processed_contract),
                "from": {"ref": f"self.steps.{materialize_step_name}.artifacts.terminal__items-processed"},
            },
            "terminal__progress-report-path": {
                **dict(accumulator_progress_contract),
                "from": {"ref": f"self.steps.{materialize_step_name}.artifacts.terminal__progress-report-path"},
            },
            "terminal__blocker-class": {
                **dict(accumulator_blocker_contract),
                "from": {"ref": f"self.steps.{materialize_step_name}.artifacts.terminal__blocker-class"},
            },
        }
        return {
            "id": case_step_id,
            "outputs": outputs,
            "steps": [
                _materialize_outputs_step(
                    name=materialize_step_name,
                    step_id_value=materialize_step_id,
                    values=[
                        {
                            "name": "terminal__variant",
                            "source": {"literal": terminal_status},
                            "contract": dict(terminal_status_contract),
                        },
                        {
                            "name": "terminal__items-processed",
                            "source": {"ref": accumulator_items_ref},
                            "contract": dict(items_processed_contract),
                        },
                        {
                            "name": "terminal__progress-report-path",
                            "source": {"ref": accumulator_progress_ref},
                            "contract": dict(accumulator_progress_contract),
                        },
                        {
                            "name": "terminal__blocker-class",
                            "source": {"ref": accumulator_blocker_ref},
                            "contract": dict(accumulator_blocker_contract),
                        },
                    ],
                )
            ],
        }

    terminal_carrier_step = {
        "name": terminal_carrier_step_name,
        "id": terminal_carrier_step_id,
        "match": {
            "ref": f"root.steps.{step_name}.artifacts.acc__loop-status",
            "cases": {
                "EMPTY": _terminal_carrier_case(source_status="EMPTY", terminal_status="EMPTY"),
                "COMPLETED": _terminal_carrier_case(source_status="COMPLETED", terminal_status="COMPLETED"),
                "BLOCKED": _terminal_carrier_case(source_status="BLOCKED", terminal_status="BLOCKED"),
                "EXHAUSTED": _terminal_carrier_case(source_status="EXHAUSTED", terminal_status="EXHAUSTED"),
                # Shared validation cannot infer the repeat_until exit predicate,
                # so keep an explicit exhaustive fallback while still narrowing
                # the helper-owned lane to terminal-only statuses.
                "CONTINUE": _terminal_carrier_case(source_status="CONTINUE", terminal_status="EXHAUSTED"),
            },
        },
    }
    _record_step_origin(
        context,
        step_name=terminal_carrier_step_name,
        step_id=terminal_carrier_step_id,
        source=expr,
    )
    empty_steps, empty_outputs = _lower_terminal_finalizer_case(
        case_name="empty",
        terminal_variant="EMPTY",
        terminal_items_ref=terminal_items_ref,
        terminal_progress_ref=terminal_progress_ref,
        terminal_blocker_ref=terminal_blocker_ref,
    )
    completed_steps, completed_outputs = _lower_terminal_finalizer_case(
        case_name="completed",
        terminal_variant="COMPLETED",
        terminal_items_ref=terminal_items_ref,
        terminal_progress_ref=terminal_progress_ref,
        terminal_blocker_ref=terminal_blocker_ref,
    )
    blocked_steps, blocked_outputs = _lower_terminal_finalizer_case(
        case_name="blocked",
        terminal_variant="BLOCKED",
        terminal_items_ref=terminal_items_ref,
        terminal_progress_ref=terminal_progress_ref,
        terminal_blocker_ref=terminal_blocker_ref,
    )
    exhausted_steps, exhausted_outputs = _lower_terminal_finalizer_case(
        case_name="exhausted",
        terminal_variant="EXHAUSTED",
        terminal_items_ref=terminal_items_ref,
        terminal_progress_ref=terminal_progress_ref,
        terminal_blocker_ref=terminal_blocker_ref,
    )
    # The loop owns non-terminal CONTINUE carriage. Once repeat_until exits, the
    # accumulator must already represent one canonical terminal carrier, and the
    # shared helper owns all terminal side effects from that point onward.
    normalize_step = {
        "name": normalize_step_name,
        "id": normalize_step_id,
        "match": {
            "ref": f"root.steps.{terminal_carrier_step_name}.artifacts.terminal__variant",
            "cases": {
                "EMPTY": {
                    "id": _normalize_generated_step_id(f"{normalize_step_name}__empty"),
                    "outputs": empty_outputs,
                    "steps": empty_steps,
                },
                "COMPLETED": {
                    "id": _normalize_generated_step_id(f"{normalize_step_name}__completed"),
                    "outputs": completed_outputs,
                    "steps": completed_steps,
                },
                "BLOCKED": {
                    "id": _normalize_generated_step_id(f"{normalize_step_name}__blocked"),
                    "outputs": blocked_outputs,
                    "steps": blocked_steps,
                },
                "EXHAUSTED": {
                    "id": _normalize_generated_step_id(f"{normalize_step_name}__exhausted"),
                    "outputs": exhausted_outputs,
                    "steps": exhausted_steps,
                },
            },
        },
    }
    _record_missing_step_origins(
        context,
        [seed_items_processed_step, loop_state_seed_step, repeat_step, terminal_carrier_step, normalize_step],
        source=expr,
    )
    return [seed_items_processed_step, loop_state_seed_step, repeat_step, terminal_carrier_step, normalize_step], _TerminalResult(
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


def _validate_backlog_drain_provider_metadata(
    expr: BacklogDrainExpr,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
    selector_resolved_ref: ResolvedWorkflowRef,
    run_item_resolved_ref: ResolvedWorkflowRef,
    gap_drafter_resolved_ref: ResolvedWorkflowRef,
) -> None:
    """Verify backlog-drain provider metadata covers callee requirements."""

    required_provider_names = set()
    required_prompt_names = set()
    for role_name, resolved_ref in (
        ("selector", selector_resolved_ref),
        ("run-item", run_item_resolved_ref),
        ("gap-drafter", gap_drafter_resolved_ref),
    ):
        if resolved_ref.extern_rebinding_plan.provider_bindings:
            required_provider_names.add(f"providers.{role_name}")
        if resolved_ref.extern_rebinding_plan.prompt_bindings:
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

    total = 1 if (
        getattr(step, "kind", None) == SurfaceStepKind.PROVIDER
        and (getattr(step, "asset_file", None) or getattr(step, "input_file", None))
    ) else 0
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
    prompt_binding_value = prompt_binding if isinstance(prompt_binding, PromptExtern) else None
    specialized_name = f"{workflow_name}__{role_name.replace('-', '_')}_rebound"
    if imported_bundle is not None:
        specialized_bundle = _specialize_imported_bundle_provider_metadata(
            imported_bundle,
            provider_id=provider_id,
            prompt_binding=prompt_binding_value,
            alias=specialized_name,
        )
        mutable_imports = context.imported_workflow_bundles
        if isinstance(mutable_imports, dict):
            mutable_imports[specialized_name] = specialized_bundle
        catalog_imports = context.workflow_catalog.imported_bundles_by_name
        if isinstance(catalog_imports, dict):
            catalog_imports[specialized_name] = specialized_bundle
        catalog_signatures = context.workflow_catalog.signatures_by_name
        base_signature = catalog_signatures.get(workflow_name)
        if isinstance(catalog_signatures, dict) and base_signature is not None:
            catalog_signatures[specialized_name] = replace(base_signature, name=specialized_name)
    if same_file_callee is not None:
        specialized_workflow = _specialize_same_file_lowered_workflow_provider_metadata(
            same_file_callee,
            provider_id=provider_id,
            prompt_binding=prompt_binding_value,
            alias=specialized_name,
        )
        mutable_callees = context.lowered_callees
        if isinstance(mutable_callees, dict):
            mutable_callees[specialized_name] = specialized_workflow
        catalog_signatures = context.workflow_catalog.signatures_by_name
        if isinstance(catalog_signatures, dict):
            catalog_signatures[specialized_name] = specialized_workflow.typed_workflow.signature
        catalog_definitions = context.workflow_catalog.definitions_by_name
        if isinstance(catalog_definitions, dict):
            catalog_definitions[specialized_name] = specialized_workflow.typed_workflow.definition
        mutable_workflows = context.workflows_by_name
        if isinstance(mutable_workflows, dict):
            mutable_workflows[specialized_name] = specialized_workflow.typed_workflow
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
    prompt_binding: PromptExtern | None,
    alias: str,
) -> LoadedWorkflowBundle:
    """Clone an imported bundle with provider or prompt metadata rebound."""

    if provider_id is None and prompt_binding is None:
        return bundle

    def rewrite_surface_step(step: Any) -> Any:
        updated_step = step
        if getattr(step, "kind", None) == SurfaceStepKind.PROVIDER:
            updated_step = replace(
                updated_step,
                provider=provider_id or getattr(updated_step, "provider", None),
                **lowering_core._prompt_source_replace_kwargs(prompt_binding),
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
                **lowering_core._prompt_source_replace_kwargs(prompt_binding),
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
    prompt_binding: PromptExtern | None,
    alias: str,
) -> LoweredWorkflow:
    """Clone a same-file lowered workflow with provider/prompt metadata rebound."""

    from .core import LoweredWorkflow

    if provider_id is None and prompt_binding is None:
        return lowered_workflow

    def rewrite(value: Any) -> Any:
        if isinstance(value, list):
            return [rewrite(item) for item in value]
        if isinstance(value, Mapping):
            rewritten: dict[Any, Any] = {}
            for key, item in value.items():
                if key == "source_map_subject" and isinstance(item, Mapping):
                    rewritten[key] = {**dict(item), "workflow_name": alias}
                elif key == "source_map_subjects_by_variant" and isinstance(item, Mapping):
                    rewritten[key] = {
                        variant: {**dict(subject), "workflow_name": alias}
                        if isinstance(subject, Mapping)
                        else subject
                        for variant, subject in item.items()
                    }
                else:
                    rewritten[key] = rewrite(item)
            if isinstance(value.get("provider"), str):
                rewritten["provider"] = provider_id or str(value["provider"])
                rewritten = lowering_core._rewrite_prompt_source_mapping(rewritten, prompt_binding)
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
        is_generated_private_workflow=lowered_workflow.is_generated_private_workflow,
        private_exec_context_bindings=lowered_workflow.private_exec_context_bindings,
        compatibility_bridge_inputs=lowered_workflow.compatibility_bridge_inputs,
        generated_path_allocations=lowered_workflow.generated_path_allocations,
        private_artifact_ids=lowered_workflow.private_artifact_ids,
        runtime_proof_nested_structured_step_names=(
            lowered_workflow.runtime_proof_nested_structured_step_names
        ),
        runtime_proof_shared_validation_parent_ref_allowances=(
            lowered_workflow.runtime_proof_shared_validation_parent_ref_allowances
        ),
        runtime_proof_executable_parent_ref_allowances=(
            lowered_workflow.runtime_proof_executable_parent_ref_allowances
        ),
        generated_repeat_until_on_exhausted_refs=(
            lowered_workflow.generated_repeat_until_on_exhausted_refs
        ),
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
        # schema1_compatibility: legacy extern discovery for covered provider result forms.
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
        # schema1_compatibility: legacy extern discovery for covered match forms.
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
        # schema1_compatibility: legacy extern discovery for covered loop forms.
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
        # schema1_compatibility: legacy extern discovery for covered command result forms.
        if isinstance(expr, CommandResultExpr):
            for value in expr.argv:
                walk(value)

    walk(typed_workflow.typed_body.expr)
    return provider_names, prompt_names
