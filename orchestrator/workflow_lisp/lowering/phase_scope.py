"""Phase-scope owner surface for stdlib lowering and retained intrinsic compatibility."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from orchestrator.workflow.references import StructuredStepReference
from orchestrator.workflow.surface_ast import SurfaceStep
from orchestrator.workflow_lisp.typed_prompt_inputs import normalize_typed_prompt_input_entry

from ..contracts import derive_reusable_state_contract_metadata, derive_structured_result_contract, derive_workflow_boundary_fields
from ..diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from ..expression_traversal import iter_child_exprs
from ..expressions import (
    BacklogDrainExpr,
    BindProcExpr,
    CallExpr,
    CommandResultExpr,
    ContinueExpr,
    EnumMemberExpr,
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
from ..spans import SourcePosition, SourceSpan
from ..type_env import PathTypeRef, PrimitiveTypeRef, ProcRefTypeRef, RecordTypeRef, TypeRef, UnionTypeRef
from ..typecheck import TypedExpr
from ..workflow_refs import ResolvedWorkflowRef, resolve_workflow_ref_literal, resolve_workflow_ref_name, workflow_ref_target_name
from ..workflows import CertifiedAdapterBinding, PromptExtern, ProviderExtern, analyze_workflow_boundary_type
from .context import (
    _ActivePhaseScope,
    _compile_error,
    _copy_context_with_phase_scope,
    _copy_context_with_step_prefix,
    _LoweringContext,
    _TerminalResult,
)
from .control_loops import _conditional_case_ref, _materialize_values_step
from .generated_paths import allocate_materialized_value_view
from .origins import (
    LoweringOrigin,
    _origin_from_context_source,
    _record_missing_step_origins,
    _record_step_origin,
    _rekey_origin_map,
)
from .values import (
    _assign_nested_local_value,
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
    _declare_runtime_context_hidden_inputs,
    _managed_inputs_from_bundle,
    _managed_inputs_from_mapping,
    _managed_write_root_bindings,
    _managed_write_root_requirements_for_callable,
    _record_call_binding_label,
    _render_argv_tail,
    _render_boolean_predicate,
    _render_call_binding_leaf_ref,
    _render_call_binding_ref,
    _render_record_call_bindings,
    _render_repeat_until_max_iterations,
    _render_scalar_expr,
)


def _template_for_ref(ref: str) -> str:
    if ref.startswith("${"):
        return ref
    return "${" + ref + "}"


def _lower_with_phase(*args, **kwargs):
    return _phase_stdlib_lower_with_phase_impl(*args, **kwargs)

def _phase_prompt_artifact_definition(
    *,
    contract: Mapping[str, Any],
    input_name: str | None,
    context: _LoweringContext,
    pointer_path: str,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> dict[str, Any]:
    """Build the top-level artifact entry for a phase prompt input."""

    artifact_contract = dict(contract)
    if artifact_contract.get("inherit") == "source":
        if input_name is None:
            raise _compile_error(
                code="phase_translation_body_invalid",
                message="missing flattened workflow input contract for inherited phase prompt artifact",
                span=span,
                form_path=form_path,
            )
        input_contract = context.authored_input_contracts.get(input_name)
        if input_contract is None:
            raise _compile_error(
                code="phase_translation_body_invalid",
                message=f"missing flattened workflow input contract for `{input_name}`",
                span=span,
                form_path=form_path,
            )
        artifact_contract = dict(input_contract)
    if artifact_contract.get("kind") == "relpath" or artifact_contract.get("type") == "relpath":
        artifact_contract["pointer"] = pointer_path
    return artifact_contract


def _phase_prompt_input_pointer_path(workflow_name: str, artifact_name: str) -> str:
    """Return the compatibility pointer path for a phase prompt artifact."""

    return f".orchestrate/workflow_lisp/{workflow_name}/materialized/{artifact_name}.txt"


def _resolve_active_phase_scope(
    expr: WithPhaseExpr,
    *,
    local_values: Mapping[str, Any],
) -> _ActivePhaseScope:
    """Resolve derived phase paths and targets for a `with-phase` body."""

    return _resolve_active_phase_scope_parts(
        ctx_expr=expr.ctx_expr,
        phase_name=expr.phase_name,
        span=expr.span,
        form_path=expr.form_path,
        local_values=local_values,
    )


def _resolve_active_phase_scope_parts(
    *,
    ctx_expr: Any,
    phase_name: str,
    span: SourceSpan,
    form_path: tuple[str, ...],
    local_values: Mapping[str, Any],
) -> _ActivePhaseScope:
    """Resolve derived phase paths and targets for a transparent phase-scope wrapper."""

    context_value = _resolve_inline_expr_value(ctx_expr, local_values=local_values)
    if not isinstance(context_value, Mapping):
        raise _compile_error(
            code="phase_translation_body_invalid",
            message="`with-phase` lowering requires the phase context to resolve from workflow inputs",
            span=ctx_expr.span,
            form_path=ctx_expr.form_path,
        )
    if "implementation_state_bundle_path" not in context_value:
        state_root_ref = context_value.get("state-root")
        artifact_root_ref = context_value.get("artifact-root")
        runtime_phase_name_ref = context_value.get("phase-name")
        if not isinstance(state_root_ref, str) or not isinstance(artifact_root_ref, str):
            raise _compile_error(
                code="phase_translation_body_invalid",
                message="`with-phase` lowering requires generic phase roots to resolve from workflow inputs",
                span=ctx_expr.span,
                form_path=ctx_expr.form_path,
            )
        target_refs = {
            target_name: _join_ref_path(artifact_root_ref, f"{phase_name}/{suffix}")
            for target_name, (_, _, suffix) in PHASE_TARGET_SPECS.items()
        }
        return _ActivePhaseScope(
            scope=PhaseScope(
                context_record_name="PhaseCtx",
                phase_name=phase_name,
                target_types={},
            ),
            bundle_path_ref=_join_ref_path(state_root_ref, f"phases/{phase_name}/state.json"),
            temp_bundle_path_ref=_join_ref_path(state_root_ref, f"phases/{phase_name}/state.tmp.json"),
            snapshot_root_ref=_join_ref_path(state_root_ref, f"phases/{phase_name}/snapshots"),
            candidate_root_ref=_join_ref_path(state_root_ref, f"phases/{phase_name}/candidates"),
            target_refs=target_refs,
            runtime_phase_name_ref=runtime_phase_name_ref if isinstance(runtime_phase_name_ref, str) else None,
        )
    if phase_name != IMPLEMENTATION_ATTEMPT_PHASE_NAME:
        raise _compile_error(
            code="phase_context_invalid",
            message="`with-phase` supports only the `implementation` phase in the legacy bridge",
            span=span,
            form_path=form_path,
        )
    bundle_ref = context_value.get("implementation_state_bundle_path")
    execution_ref = context_value.get("execution_report_target")
    progress_ref = context_value.get("progress_report_target")
    if not all(isinstance(ref, str) for ref in (bundle_ref, execution_ref, progress_ref)):
        raise _compile_error(
            code="phase_translation_body_invalid",
            message="`with-phase` lowering requires bound relpath fields on the phase context",
            span=ctx_expr.span,
            form_path=ctx_expr.form_path,
        )
    return _ActivePhaseScope(
        scope=PhaseScope(
            context_record_name="ImplementationAttemptPhaseCtx",
            phase_name=phase_name,
            bundle_path_field="implementation_state_bundle_path",
            target_fields={
                "execution-report": "execution_report_target",
                "progress-report": "progress_report_target",
            },
        ),
        bundle_path_ref=bundle_ref,
        target_refs={
            "execution-report": execution_ref,
            "progress-report": progress_ref,
        },
    )


def _require_phase_scope_name_match(
    phase_scope: _ActivePhaseScope,
    *,
    authored_name: str,
    form_name: str,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> None:
    """Require stdlib phase forms to use the enclosing `with-phase` name."""

    if phase_scope.scope.phase_name == authored_name:
        return
    raise _compile_error(
        code="phase_scope_name_mismatch",
        message=f"`{form_name}` name `{authored_name}` must match the active `with-phase` scope `{phase_scope.scope.phase_name}`",
        span=span,
        form_path=form_path,
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
        elif isinstance(expr, RunProviderPhaseExpr):
            if isinstance(expr.provider, NameExpr):
                provider_names.add(expr.provider.name)
            if isinstance(expr.prompt, NameExpr):
                prompt_names.add(expr.prompt.name)
        elif isinstance(expr, ProduceOneOfExpr):
            if isinstance(expr.producer.provider_expr, NameExpr):
                provider_names.add(expr.producer.provider_expr.name)
            if isinstance(expr.producer.prompt_expr, NameExpr):
                prompt_names.add(expr.producer.prompt_expr.name)
        if isinstance(expr, ProcedureCallExpr):
            for child in iter_child_exprs(expr):
                walk(child)
            procedure = typed_procedures.get(expr.callee_name)
            if procedure is None or procedure.definition.name in visiting_procedures:
                return
            visiting_procedures.add(procedure.definition.name)
            walk(procedure.typed_body.expr)
            visiting_procedures.remove(procedure.definition.name)
            return
        for child in iter_child_exprs(expr):
            walk(child)

    walk(typed_workflow.typed_body.expr)
    return provider_names, prompt_names


def _same_file_workflow_provider_requirements(
    typed_workflow: TypedWorkflowDef | None,
    *,
    typed_procedures: Mapping[str, TypedProcedureDef],
) -> tuple[int, int]:
    """Count provider and prompt extern requirements for one same-file workflow."""

    if typed_workflow is None:
        return 0, 0
    provider_names, prompt_names = _workflow_extern_requirements(
        typed_workflow,
        typed_procedures=typed_procedures,
    )
    return len(provider_names), len(prompt_names)



def _phase_stdlib_lower_with_phase_impl(
    typed_expr: TypedExpr,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    """Enter a derived phase scope and lower the body inside it."""

    expr = typed_expr.expr
    assert isinstance(expr, WithPhaseExpr)
    return _lower_composed_with_phase(
        expr,
        result_type=typed_expr.type_ref,
        context=context,
        local_values=local_values,
    )


def _lower_composed_with_phase(
    expr: WithPhaseExpr,
    *,
    result_type: TypeRef,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
    step_name_prefix: str | None = None,
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    """Lower a `with-phase` wrapper by lowering only its body under phase scope."""

    lowering_phase_scope = _resolve_active_phase_scope(expr, local_values=local_values)
    scoped_context = _copy_context_with_phase_scope(context, lowering_phase_scope)
    if step_name_prefix is not None:
        # emitter: with-phase composition reuses the provider-result owner emitter.
        if isinstance(expr.body, ProviderResultExpr):
            from .effects import _lower_provider_result

            return _lower_provider_result(
                expr.body,
                result_type=result_type,
                context=scoped_context,
                local_values=local_values,
                step_name=step_name_prefix,
            )
        scoped_context = _copy_context_with_step_prefix(
            scoped_context,
            step_name_prefix=step_name_prefix,
        )
    return scoped_context.lower_expression(
        TypedExpr(
            expr=expr.body,
            type_ref=result_type,
            span=expr.body.span,
            form_path=expr.body.form_path,
        ),
        context=scoped_context,
        local_values=local_values,
    )


def _lower_workflow_outputs(
    *,
    typed_workflow: TypedWorkflowDef,
    authored_outputs: Mapping[str, dict[str, Any]],
    terminal: _TerminalResult,
    context: _LoweringContext,
) -> dict[str, Any]:
    """Connect terminal expression refs to the workflow's declared outputs."""

    lowered_outputs: dict[str, Any] = {}
    for output_name, definition in authored_outputs.items():
        source_ref = terminal.output_refs.get(output_name)
        if source_ref is None:
            field_name = output_name.removeprefix("return__")
            raise _compile_error(
                code="workflow_return_not_exportable",
                message=f"workflow `{typed_workflow.definition.name}` cannot export return field `{field_name}`",
                span=typed_workflow.definition.body.span,
                form_path=typed_workflow.definition.body.form_path,
            )
        lowered_outputs[output_name] = {
            **definition,
            "from": {"ref": source_ref},
        }
        if output_name in context.output_projection_metadata:
            lowered_outputs[output_name]["projection"] = dict(
                context.output_projection_metadata[output_name]
            )
    return lowered_outputs


def _signature_local_values(typed_workflow: TypedWorkflowDef | _LoweringContext) -> dict[str, Any]:
    """Seed local value refs from a workflow signature."""

    if isinstance(typed_workflow, _LoweringContext):
        signature = typed_workflow.signature
    else:
        signature = typed_workflow.signature
    local_values: dict[str, Any] = {}
    for param_name, param_type in signature.params:
        if isinstance(param_type, RecordTypeRef):
            local_values[param_name] = _build_record_local_value(param_type, generated_name=param_name)
        elif isinstance(param_type, UnionTypeRef):
            local_values[param_name] = _build_union_local_value(param_type, generated_name=param_name)
        else:
            local_values[param_name] = f"inputs.{param_name}"
    specialization = getattr(typed_workflow, "specialization", None)
    if specialization is not None:
        local_values.update(dict(getattr(specialization, "workflow_ref_bindings", {})))
        local_values.update(dict(getattr(specialization, "proc_ref_bindings", {})))
        local_values.update(dict(getattr(specialization, "value_bindings", {})))
    return local_values


def _procedure_signature_local_values(procedure: TypedProcedureDef) -> dict[str, Any]:
    """Seed local value refs from a private workflow procedure signature."""

    local_values: dict[str, Any] = {}
    for param_name, param_type in procedure.signature.params:
        if isinstance(param_type, RecordTypeRef):
            local_values[param_name] = _build_record_local_value(
                param_type,
                generated_name=param_name,
            )
            continue
        if isinstance(param_type, UnionTypeRef):
            local_values[param_name] = _build_union_local_value(
                param_type,
                generated_name=param_name,
            )
            continue
        local_values[param_name] = f"inputs.{param_name}"
    if procedure.specialization is not None:
        local_values.update(dict(getattr(procedure.specialization, "workflow_ref_bindings", {})))
        local_values.update(dict(getattr(procedure.specialization, "proc_ref_bindings", {})))
        local_values.update(dict(getattr(procedure.specialization, "value_bindings", {})))
    return local_values


def _procedure_signature_local_type_bindings(procedure: TypedProcedureDef) -> dict[str, TypeRef]:
    """Seed local type bindings from a private workflow procedure signature."""

    local_type_bindings = {
        param_name: param_type
        for param_name, param_type in procedure.signature.params
    }
    specialization = getattr(procedure, "specialization", None)
    if specialization is not None:
        local_type_bindings.update(dict(getattr(specialization, "bound_param_types", {})))
    return local_type_bindings


def _build_union_local_value(type_ref: UnionTypeRef, *, generated_name: str) -> dict[str, Any]:
    """Represent a union parameter as nested refs to flattened inputs."""

    local_value: dict[str, Any] = {}
    for leaf_name, field_path in _flatten_boundary_leaf_paths(type_ref, generated_name=generated_name):
        _assign_nested_local_value(local_value, field_path, f"inputs.{leaf_name}")
    return local_value


def _build_call_bindings_from_record_value(
    param_name: str,
    param_type: Any,
    value: Mapping[str, Any],
    *,
    source_expr: Any,
) -> dict[str, Any]:
    """Flatten a record value into `call.with` bindings for one parameter."""

    if not isinstance(param_type, RecordTypeRef):
        raise _compile_error(
            code="workflow_signature_mismatch",
            message="record binding helper requires a record-typed workflow parameter",
            span=source_expr.span,
            form_path=source_expr.form_path,
        )
    bindings: dict[str, Any] = {}
    for generated_name, field_path in _flatten_boundary_leaf_paths(param_type, generated_name=param_name):
        ref = _resolve_nested_local_value(value, field_path)
        bindings[generated_name] = _render_call_binding_leaf_ref(
            ref,
            source_expr=source_expr,
            binding_label=_record_call_binding_label(param_name, field_path),
        )
    return bindings


def _resolve_expr_local_value(expr: Any, *, local_values: Mapping[str, Any]) -> Any:
    """Resolve simple name, field, and phase-target expressions from locals."""

    if isinstance(expr, NameExpr):
        return local_values.get(expr.name)
    if isinstance(expr, FieldAccessExpr):
        base_value = _resolve_expr_local_value(expr.base, local_values=local_values)
        return _resolve_nested_local_value(base_value, tuple(expr.fields))
    if isinstance(expr, PhaseTargetExpr):
        return None
    return None


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


def _resolve_signature_expr_type(expr: Any, *, context: _LoweringContext) -> TypeRef | None:
    """Resolve the frontend type of a signature-rooted expression."""

    if isinstance(expr, NameExpr):
        return _signature_param_type(expr.name, context=context)
    if isinstance(expr, FieldAccessExpr):
        current_type = _signature_param_type(expr.base.name, context=context)
        for field_name in expr.fields:
            if not isinstance(current_type, RecordTypeRef):
                return None
            current_type = context.type_env.record_field(
                current_type,
                field_name,
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
        return current_type
    return None


def _signature_param_type(name: str, *, context: _LoweringContext) -> TypeRef | None:
    """Return the type of a workflow parameter in the active context."""

    for param_name, param_type in context.signature.params:
        if param_name == name:
            return param_type
    return None


def _resolve_inline_expr_value(expr: Any, *, local_values: Mapping[str, Any]) -> Any:
    """Resolve literals, names, fields, and record expressions for inline use."""

    if isinstance(expr, LiteralExpr):
        return expr
    if isinstance(expr, GeneratedRelpathSeedExpr):
        return expr
    if isinstance(expr, WorkflowRefLiteralExpr):
        return expr
    if isinstance(expr, (ProcRefLiteralExpr, BindProcExpr)):
        return expr
    if isinstance(expr, LetStarExpr):
        child_locals = dict(local_values)
        for binding_name, binding_expr in expr.bindings:
            resolved_binding = _resolve_inline_expr_value(binding_expr, local_values=child_locals)
            if resolved_binding is None:
                return expr
            child_locals[binding_name] = resolved_binding
        return _resolve_inline_expr_value(expr.body, local_values=child_locals)
    if isinstance(expr, IfExpr):
        condition_value = _resolve_inline_expr_value(expr.condition_expr, local_values=local_values)
        if isinstance(condition_value, LiteralExpr) and condition_value.literal_kind == "bool":
            branch = expr.then_expr if condition_value.value else expr.else_expr
            return _resolve_inline_expr_value(branch, local_values=local_values)
        return expr
    resolved = _resolve_expr_local_value(expr, local_values=local_values)
    if isinstance(resolved, (str, Mapping, LiteralExpr, RecordExpr)):
        return resolved
    if resolved is not None:
        if resolved is expr:
            return expr
        return _resolve_inline_expr_value(resolved, local_values=local_values)
    if isinstance(expr, NameExpr):
        bound = local_values.get(expr.name)
        if bound is None:
            return None
        if isinstance(bound, (str, Mapping)):
            return bound
        if bound is expr:
            return expr
        return _resolve_inline_expr_value(bound, local_values=local_values)
    if isinstance(expr, FieldAccessExpr):
        return _resolve_inline_field_value(
            local_values.get(expr.base.name),
            field_path=tuple(expr.fields),
            local_values=local_values,
        )
    return expr


def _resolved_workflow_ref_value(
    value: Any,
    *,
    context: _LoweringContext,
    expected_type: WorkflowRefTypeRef | None,
) -> ResolvedWorkflowRef | None:
    if isinstance(value, ResolvedWorkflowRef):
        return value
    if isinstance(value, WorkflowRefLiteralExpr):
        if expected_type is None:
            signature = context.workflow_catalog.signatures_by_name.get(value.target_name)
            if signature is None:
                raise _compile_error(
                    code="workflow_ref_unknown",
                    message=f"unknown workflow ref `{value.target_name}`",
                    span=value.span,
                    form_path=value.form_path,
                )
            expected_type = WorkflowRefTypeRef(
                name=f"WorkflowRef[{ ' '.join(type_ref.name for _, type_ref in signature.params) } -> {signature.return_type_ref.name}]",
                param_type_refs=tuple(type_ref for _, type_ref in signature.params),
                return_type_ref=signature.return_type_ref,
            )
        return resolve_workflow_ref_literal(
            value,
            expected_type=expected_type,
            workflow_catalog=context.workflow_catalog,
            typed_workflows_by_name=context.workflows_by_name,
            allow_extern_rebinding=False,
        )
    if isinstance(value, (NameExpr, EnumMemberExpr)):
        return resolve_workflow_ref_name(
            workflow_ref_target_name(value),
            workflow_catalog=context.workflow_catalog,
            span=value.span,
            form_path=value.form_path,
            expansion_stack=value.expansion_stack,
            expected_type=expected_type,
            typed_workflows_by_name=context.workflows_by_name,
            allow_extern_rebinding=False,
        )
    return None


def _proc_ref_env_from_local_values(
    local_values: Mapping[str, Any],
    *,
    context: _LoweringContext,
) -> dict[str, ResolvedProcRefValue]:
    env: dict[str, ResolvedProcRefValue] = {}
    for name, value in local_values.items():
        if isinstance(value, ResolvedProcRefValue):
            env[name] = value
    return env


def _resolved_proc_ref_value(
    value: Any,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
    expected_type: ProcRefTypeRef | None = None,
) -> ResolvedProcRefValue | None:
    if isinstance(value, ResolvedProcRefValue):
        return value
    if not isinstance(value, (NameExpr, ProcRefLiteralExpr, BindProcExpr)):
        return None
    procedure_catalog = getattr(context, "procedure_catalog", None)
    if procedure_catalog is None:
        procedure_catalog = ProcedureCatalog(
            signatures_by_name={
                name: procedure.signature
                for name, procedure in context.typed_procedures.items()
            },
            definitions_by_name={
                name: procedure.definition
                for name, procedure in context.typed_procedures.items()
            },
            call_graph={},
        )
    return resolve_proc_ref_value(
        value,
        procedure_catalog=procedure_catalog,
        proc_ref_env=_proc_ref_env_from_local_values(local_values, context=context),
        expected_type=expected_type,
    )


def _resolve_inline_field_value(
    value: Any,
    *,
    field_path: tuple[str, ...],
    local_values: Mapping[str, Any],
) -> Any:
    """Resolve a nested field path through inline mappings or record expressions."""

    current = value
    for field_name in field_path:
        if current is not None and not isinstance(current, (Mapping, RecordExpr, UnionVariantExpr)):
            next_current = _resolve_inline_expr_value(current, local_values=local_values)
            if next_current is current:
                return None
            current = next_current
        if isinstance(current, Mapping):
            current = current.get(field_name)
            continue
        if isinstance(current, RecordExpr):
            current = _record_field_value(current, field_name)
            current = _resolve_inline_expr_value(current, local_values=local_values)
            continue
        if isinstance(current, UnionVariantExpr):
            current = _union_variant_expr_value_at_path(current, (field_name,))
            current = _resolve_inline_expr_value(current, local_values=local_values)
            continue
        return None
    return current


def _build_phase_prompt_input_prelude(
    expr: ProviderResultExpr,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Build legacy implementation-phase prompt materialization steps."""

    phase_scope = context.phase_scope
    if phase_scope is None:
        return []

    if len(expr.inputs) != 4:
        raise _compile_error(
            code="phase_translation_body_invalid",
            message="phase-scoped provider-result requires design, plan, and both report targets in this slice",
            span=expr.span,
            form_path=expr.form_path,
        )

    design_expr, plan_expr, *report_target_exprs = expr.inputs
    target_inputs = _phase_prompt_report_target_inputs(
        report_target_exprs,
        local_values=local_values,
        span=expr.span,
        form_path=expr.form_path,
    )
    phase_prompt_inputs = (
        ("design", design_expr),
        ("plan", plan_expr),
        ("execution_report_target", target_inputs["execution_report_target"]),
        ("progress_report_target", target_inputs["progress_report_target"]),
    )

    values: list[dict[str, Any]] = []
    publishes: list[dict[str, str]] = []
    for artifact_name, input_expr in phase_prompt_inputs:
        raw_source_node, _ = _resolve_phase_prompt_input_source(
            input_expr,
            artifact_name=artifact_name,
            context=context,
            local_values=local_values,
        )
        input_name = _materialize_source_input_name(raw_source_node)
        if artifact_name in {"design", "plan"} and input_name is None:
            raise _compile_error(
                code="phase_translation_body_invalid",
                message="phase prompt-input materialization must lower from flattened workflow inputs",
                span=input_expr.span,
                form_path=input_expr.form_path,
            )
        source_node = raw_source_node
        contract_input_name = input_name
        if artifact_name in {"execution_report_target", "progress_report_target"}:
            if input_name is None:
                raise _compile_error(
                    code="phase_translation_body_invalid",
                    message="phase report targets must lower from flattened workflow inputs",
                    span=input_expr.span,
                    form_path=input_expr.form_path,
                )
            source_node = {"ref": f"inputs.{input_name}"}
            input_name = None
        pointer_path = _phase_prompt_input_pointer_path(context.workflow_name, artifact_name)
        artifact_contract = _phase_prompt_input_contract(
            artifact_name,
            input_name=contract_input_name,
            context=context,
            span=input_expr.span,
            form_path=input_expr.form_path,
        )
        values.append(
            {
                "name": artifact_name,
                "source": source_node,
                "contract": artifact_contract,
                "pointer": {"path": pointer_path},
            }
        )
        context.top_level_artifacts[artifact_name] = _phase_prompt_artifact_definition(
            contract=artifact_contract,
            input_name=contract_input_name,
            context=context,
            pointer_path=pointer_path,
            span=input_expr.span,
            form_path=input_expr.form_path,
        )
        allocate_materialized_value_view(
            context=context,
            source_expr=input_expr,
            path_template=pointer_path,
            stable_target=f"prompt_inputs/{artifact_name}",
        )
        publishes.append({"artifact": artifact_name, "from": artifact_name})

    step_name = "MaterializeImplementationAttemptPromptInputs"
    step_id = context.normalize_generated_step_id(step_name)
    _record_step_origin(context, step_name=step_name, step_id=step_id, source=expr)
    return [
        {
            "name": step_name,
            "id": step_id,
            "materialize_artifacts": {"values": values},
            "publishes": publishes,
        }
    ]


def _uses_legacy_phase_prompt_input_prelude(
    expr: ProviderResultExpr,
    *,
    local_values: Mapping[str, Any] | None = None,
) -> bool:
    """Return whether one phase-scoped provider-result uses the retained four-input surface."""

    if len(expr.inputs) != 4:
        return False
    report_targets = []
    for target_expr in expr.inputs[2:]:
        if (
            local_values is not None
            and isinstance(target_expr, NameExpr)
            and isinstance(local_values.get(target_expr.name), PhaseTargetExpr)
        ):
            report_targets.append(local_values[target_expr.name])
            continue
        report_targets.append(target_expr)
    return {
        target_expr.target_name
        for target_expr in report_targets
        if isinstance(target_expr, PhaseTargetExpr)
    } == {"execution-report", "progress-report"}


def _phase_prompt_inputs_are_direct(
    prompt_input_specs: tuple[tuple[str, Any], ...],
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> bool:
    """Return whether prompt inputs come directly from workflow inputs or approved targets."""

    for base_name, prompt_input in prompt_input_specs:
        for artifact_name, input_expr in _flatten_phase_stdlib_prompt_inputs(
            prompt_input,
            base_name=base_name,
            local_values=local_values,
        ):
            source_node, extra_hidden_inputs = _resolve_phase_prompt_input_source(
                input_expr,
                artifact_name=artifact_name,
                context=context,
                local_values=local_values,
            )
            if extra_hidden_inputs:
                return False
            input_name = source_node.get("input")
            if isinstance(input_name, str):
                continue
            source_ref = source_node.get("ref")
            if isinstance(source_ref, str) and source_ref.startswith("inputs."):
                continue
            return False
    return True

def _typed_prompt_input_row_metadata(
    workflow_name: str,
    provider_call_locator: str | None = None,
    *,
    context: _LoweringContext,
) -> dict[str, str] | None:
    family_profile_catalog = context.workflow_catalog.family_profile_catalog
    if family_profile_catalog is None:
        return None
    return family_profile_catalog.typed_prompt_input_row(
        workflow_name,
        provider_call_locator,
    )


def _value_type_name_for_prompt_input(expr: Any, *, context: _LoweringContext) -> str:
    type_ref = _type_ref_for_prompt_input(expr, context=context)
    if type_ref is not None:
        return _type_ref_display_name(type_ref)
    return expr.__class__.__name__


def _type_ref_for_prompt_input(expr: Any, *, context: _LoweringContext) -> TypeRef | None:
    if isinstance(expr, NameExpr):
        return context.local_type_bindings.get(expr.name)
    if isinstance(expr, FieldAccessExpr):
        type_ref = context.local_type_bindings.get(expr.base.name)
        current = type_ref
        for field_name in expr.fields:
            if isinstance(current, RecordTypeRef):
                current = current.field_types.get(field_name)
            else:
                current = None
                break
        return current
    return None


def _type_ref_display_name(type_ref: TypeRef) -> str:
    return getattr(type_ref.definition, "name", type_ref.__class__.__name__)


def _request_field_metadata_for_prompt_input(
    expr: Any,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
    preserved_value_source: Any | None = None,
) -> dict[str, Any]:
    type_ref = _type_ref_for_prompt_input(expr, context=context)
    if not isinstance(type_ref, RecordTypeRef):
        return {}

    field_names = sorted(str(name) for name in type_ref.field_types)
    metadata: dict[str, Any] = {
        "field_names": field_names,
        "has_subject": "subject" in type_ref.field_types,
        "has_targets": "targets" in type_ref.field_types,
        "semantic_field_count": 0,
        "write_target_field_count": 0,
    }

    subject_type = type_ref.field_types.get("subject")
    if subject_type is not None:
        metadata["subject_type_name"] = _type_ref_display_name(subject_type)
        if isinstance(subject_type, RecordTypeRef):
            metadata["semantic_field_count"] = len(subject_type.field_types)

    targets_type = type_ref.field_types.get("targets")
    if targets_type is not None:
        metadata["targets_type_name"] = _type_ref_display_name(targets_type)
        if isinstance(targets_type, RecordTypeRef):
            metadata["write_target_field_count"] = len(targets_type.field_types)

    field_authority = _collect_preserved_request_field_authority(
        expr,
        context=context,
        local_values=local_values,
    )
    if not field_authority and preserved_value_source is not None:
        field_authority = _collect_request_field_authority_from_value_source(
            preserved_value_source
        )
    if field_authority:
        metadata["field_authority"] = field_authority

    return metadata


def _collect_preserved_request_field_authority(
    expr: Any,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
    field_path: tuple[str, ...] = (),
) -> dict[str, Any]:
    if isinstance(expr, NameExpr):
        bound_value = local_values.get(expr.name)
        if bound_value is not None and bound_value is not expr:
            return _collect_preserved_request_field_authority(
                bound_value,
                context=context,
                local_values=local_values,
                field_path=field_path,
            )

    if isinstance(expr, RecordExpr):
        metadata: dict[str, Any] = {}
        for field_name, field_expr in expr.fields:
            metadata.update(
                _collect_preserved_request_field_authority(
                    field_expr,
                    context=context,
                    local_values=local_values,
                    field_path=field_path + (field_name,),
                )
            )
        return metadata

    if (
        isinstance(expr, Mapping)
        and set(expr) == {"ref"}
        and isinstance(expr.get("ref"), str)
    ):
        compatibility_bridge = _compatibility_bridge_request_field_authority_from_ref(
            str(expr["ref"])
        )
        if compatibility_bridge is not None and field_path:
            return {".".join(field_path): compatibility_bridge}
        return {}

    if isinstance(expr, Mapping):
        metadata: dict[str, Any] = {}
        for field_name, field_expr in expr.items():
            metadata.update(
                _collect_preserved_request_field_authority(
                    field_expr,
                    context=context,
                    local_values=local_values,
                    field_path=field_path + (str(field_name),),
                )
            )
        return metadata

    if isinstance(expr, tuple):
        metadata: dict[str, Any] = {}
        for index, item in enumerate(expr):
            metadata.update(
                _collect_preserved_request_field_authority(
                    item,
                    context=context,
                    local_values=local_values,
                    field_path=field_path + (str(index),),
                )
            )
        return metadata

    compatibility_bridge = _compatibility_bridge_request_field_authority(expr)
    if compatibility_bridge is not None and field_path:
        return {".".join(field_path): compatibility_bridge}

    inline_value = _resolve_inline_expr_value(expr, local_values=local_values)
    if inline_value is not expr and isinstance(inline_value, (Mapping, RecordExpr, tuple)):
        return _collect_preserved_request_field_authority(
            inline_value,
            context=context,
            local_values=local_values,
            field_path=field_path,
        )
    return {}


def _compatibility_bridge_request_field_authority(expr: Any) -> dict[str, str] | None:
    if not isinstance(expr, FieldAccessExpr):
        return None
    base_name: str | None = None
    if isinstance(expr.base, NameExpr):
        base_name = expr.base.name
    fields = tuple(str(field) for field in expr.fields)
    if base_name == "ctx" and fields == ("progress_ledger_path",):
        return {
            "authority_class": "compatibility_bridge",
            "source_binding": "ctx.progress_ledger_path",
            "bridge_field_name": "progress_ledger_path",
        }
    if base_name == "inputs" and fields == ("ctx", "progress_ledger_path"):
        return {
            "authority_class": "compatibility_bridge",
            "source_binding": "ctx.progress_ledger_path",
            "bridge_field_name": "progress_ledger_path",
        }
    return None


def _compatibility_bridge_request_field_authority_from_ref(
    ref: str,
) -> dict[str, str] | None:
    if ref == "inputs.ctx__progress_ledger_path":
        return {
            "authority_class": "compatibility_bridge",
            "source_binding": "ctx.progress_ledger_path",
            "bridge_field_name": "progress_ledger_path",
        }
    return None


def _collect_request_field_authority_from_value_source(
    value: Any,
    *,
    field_path: tuple[str, ...] = (),
) -> dict[str, Any]:
    if isinstance(value, Mapping) and set(value) == {"ref"} and isinstance(value.get("ref"), str):
        metadata = _compatibility_bridge_request_field_authority_from_ref(str(value["ref"]))
        if metadata is not None and field_path:
            return {".".join(field_path): metadata}
        return {}
    if isinstance(value, Mapping):
        metadata: dict[str, Any] = {}
        for field_name, item in value.items():
            metadata.update(
                _collect_request_field_authority_from_value_source(
                    item,
                    field_path=field_path + (str(field_name),),
                )
            )
        return metadata
    if isinstance(value, (list, tuple)):
        metadata: dict[str, Any] = {}
        for index, item in enumerate(value):
            metadata.update(
                _collect_request_field_authority_from_value_source(
                    item,
                    field_path=field_path + (str(index),),
                )
            )
        return metadata
    return {}


def _typed_prompt_input_source_from_inline_value(
    value: Any,
    *,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> Any:
    if isinstance(value, LiteralExpr):
        return value.value
    if isinstance(value, Mapping):
        if "ref" in value and len(value) == 1 and isinstance(value.get("ref"), str):
            return {"ref": value["ref"]}
        return {
            str(key): _typed_prompt_input_source_from_inline_value(
                item,
                span=span,
                form_path=form_path,
            )
            for key, item in value.items()
        }
    if isinstance(value, str):
        if value.startswith("inputs.") or value.startswith("root.steps."):
            return {"ref": value}
        return value
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    raise _compile_error(
        code="phase_translation_body_invalid",
        message="typed prompt inputs must lower from resolvable workflow refs or pure literal values",
        span=span,
        form_path=form_path,
    )


def _typed_prompt_input_value_source_from_materialized_source(
    raw_source_node: Mapping[str, Any],
) -> Any:
    input_name = raw_source_node.get("input")
    if isinstance(input_name, str):
        return {"ref": f"inputs.{input_name}"}
    ref = raw_source_node.get("ref")
    if isinstance(ref, str):
        return {"ref": ref}
    if "literal" in raw_source_node:
        return raw_source_node["literal"]
    return dict(raw_source_node)


def _resolve_preserved_typed_prompt_input_binding(
    expr: Any,
    *,
    binding_name: str,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[Any, dict[str, LoweringOrigin]]:
    if isinstance(expr, NameExpr):
        bound_value = local_values.get(expr.name)
        if bound_value is not None:
            return _resolve_preserved_typed_prompt_input_binding(
                bound_value,
                binding_name=binding_name,
                context=context,
                local_values=local_values,
            )

    if isinstance(expr, RecordExpr):
        value: dict[str, Any] = {}
        hidden_inputs: dict[str, LoweringOrigin] = {}
        for field_name, field_expr in expr.fields:
            field_value, field_hidden_inputs = _resolve_preserved_typed_prompt_input_binding(
                field_expr,
                binding_name=f"{binding_name}__{field_name}",
                context=context,
                local_values=local_values,
            )
            value[field_name] = field_value
            hidden_inputs.update(field_hidden_inputs)
        return value, hidden_inputs

    if isinstance(expr, Mapping):
        value: dict[str, Any] = {}
        hidden_inputs: dict[str, LoweringOrigin] = {}
        for field_name, field_expr in expr.items():
            field_value, field_hidden_inputs = _resolve_preserved_typed_prompt_input_binding(
                field_expr,
                binding_name=f"{binding_name}__{field_name}",
                context=context,
                local_values=local_values,
            )
            value[str(field_name)] = field_value
            hidden_inputs.update(field_hidden_inputs)
        return value, hidden_inputs

    if isinstance(expr, tuple):
        values: list[Any] = []
        hidden_inputs: dict[str, LoweringOrigin] = {}
        for index, item in enumerate(expr):
            item_value, item_hidden_inputs = _resolve_preserved_typed_prompt_input_binding(
                item,
                binding_name=f"{binding_name}__{index}",
                context=context,
                local_values=local_values,
            )
            values.append(item_value)
            hidden_inputs.update(item_hidden_inputs)
        return values, hidden_inputs

    inline_value = _resolve_inline_expr_value(expr, local_values=local_values)
    if inline_value is not expr and isinstance(inline_value, (Mapping, RecordExpr, tuple)):
        return _resolve_preserved_typed_prompt_input_binding(
            inline_value,
            binding_name=binding_name,
            context=context,
            local_values=local_values,
        )
    if isinstance(inline_value, str):
        if inline_value.startswith("inputs.") or inline_value.startswith("root.steps."):
            return {"ref": inline_value}, {}
        return inline_value, {}
    if isinstance(inline_value, (bool, int, float)) or inline_value is None:
        return inline_value, {}
    if isinstance(inline_value, LiteralExpr):
        fallback_span = SourceSpan(
            SourcePosition("<generated>", 0, 0, 0),
            SourcePosition("<generated>", 0, 0, 0),
        )
        return (
            _typed_prompt_input_source_from_inline_value(
                inline_value,
                span=getattr(expr, "span", fallback_span),
                form_path=getattr(expr, "form_path", ("typed_prompt_input", binding_name)),
            ),
            {},
        )

    raw_source_node, hidden_inputs = _resolve_phase_prompt_input_source(
        expr,
        artifact_name=binding_name,
        context=context,
        local_values=local_values,
    )
    if hidden_inputs:
        for hidden_input_name in hidden_inputs:
            context.internal_generated_input_reasons.setdefault(
                hidden_input_name,
                "phase_prompt_transport",
            )
    return (
        _typed_prompt_input_value_source_from_materialized_source(raw_source_node),
        hidden_inputs,
    )


def _build_typed_prompt_inputs_for_prompt_specs(
    prompt_input_specs: tuple[tuple[str, Any], ...],
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
    source_expr: Any,
    provider_call_locator: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, LoweringOrigin]]:
    row_metadata = _typed_prompt_input_row_metadata(
        context.workflow_name,
        provider_call_locator,
        context=context,
    )
    if row_metadata is None:
        return [], {}

    typed_prompt_inputs: list[dict[str, Any]] = []
    hidden_inputs: dict[str, LoweringOrigin] = {}
    preserve_request_record = bool(row_metadata.get("preserve_request_record"))
    if preserve_request_record:
        base_name, input_expr = prompt_input_specs[0]
        if isinstance(input_expr, tuple) and len(input_expr) == 1:
            input_expr = input_expr[0]
        binding_name = (
            input_expr.name
            if isinstance(input_expr, NameExpr)
            else base_name
        )
        value_source, extra_hidden_inputs = _resolve_preserved_typed_prompt_input_binding(
            input_expr,
            binding_name=binding_name,
            context=context,
            local_values=local_values,
        )
        hidden_inputs.update(extra_hidden_inputs)
        typed_prompt_inputs.append(
            normalize_typed_prompt_input_entry(
                {
                    "schema_version": "workflow_lisp_typed_prompt_input.v1",
                    "binding_name": binding_name,
                    "renderer": {
                        "renderer_id": "canonical-json"
                        if not isinstance(value_source, str)
                        else "posix-path-line",
                        "renderer_version": 1,
                        "accepted_shape": "any_pure_value"
                        if not isinstance(value_source, str)
                        else "path_value",
                    },
                    "value_source": {"kind": "typed_binding_ref", "binding": value_source},
                    "value_type_name": _value_type_name_for_prompt_input(
                        input_expr,
                        context=context,
                    ),
                    "source_map_origin_key": context.workflow_name,
                    "u0_row_id": row_metadata["u0_row_id"],
                    "c0_row_id": row_metadata["c0_row_id"],
                    "injection_order": 0,
                    "request_fields": _request_field_metadata_for_prompt_input(
                        input_expr,
                        context=context,
                        local_values=local_values,
                        preserved_value_source=value_source,
                    ),
                }
            )
        )
        return typed_prompt_inputs, hidden_inputs

    flattened_inputs: list[tuple[str, Any]] = []
    for base_name, prompt_input in prompt_input_specs:
        flattened_inputs.extend(
            _flatten_phase_stdlib_prompt_inputs(
                prompt_input,
                base_name=base_name,
                local_values=local_values,
            )
        )

    for injection_order, (binding_name, input_expr) in enumerate(flattened_inputs):
        raw_source_node, extra_hidden_inputs = _resolve_phase_prompt_input_source(
            input_expr,
            artifact_name=binding_name,
            context=context,
            local_values=local_values,
        )
        hidden_inputs.update(extra_hidden_inputs)
        for hidden_input_name in extra_hidden_inputs:
            context.internal_generated_input_reasons.setdefault(hidden_input_name, "phase_prompt_transport")
        if isinstance(raw_source_node.get("input"), str):
            value_source = {"ref": f"inputs.{raw_source_node['input']}"}
        elif isinstance(raw_source_node.get("ref"), str):
            value_source = {"ref": str(raw_source_node["ref"])}
        elif "literal" in raw_source_node:
            value_source = raw_source_node["literal"]
        else:
            inline_value = _resolve_inline_expr_value(input_expr, local_values=local_values)
            value_source = _typed_prompt_input_source_from_inline_value(
                inline_value,
                span=input_expr.span,
                form_path=input_expr.form_path,
            )
        typed_prompt_inputs.append(
            normalize_typed_prompt_input_entry(
                {
                    "schema_version": "workflow_lisp_typed_prompt_input.v1",
                    "binding_name": binding_name,
                    "renderer": {
                        "renderer_id": "canonical-json"
                        if not isinstance(value_source, str)
                        else "posix-path-line",
                        "renderer_version": 1,
                        "accepted_shape": "any_pure_value"
                        if not isinstance(value_source, str)
                        else "path_value",
                    },
                    "value_source": {"kind": "typed_binding_ref", "binding": value_source},
                    "value_type_name": _value_type_name_for_prompt_input(
                        input_expr,
                        context=context,
                    ),
                    "source_map_origin_key": context.workflow_name,
                    "u0_row_id": row_metadata["u0_row_id"],
                    "c0_row_id": row_metadata["c0_row_id"],
                    "injection_order": injection_order,
                }
            )
        )
    return typed_prompt_inputs, hidden_inputs


def _build_phase_stdlib_prompt_input_prelude(
    prompt_input_specs: tuple[tuple[str, Any], ...],
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
    source_expr: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, str]], list[str], dict[str, LoweringOrigin]]:
    """Build phase-stdlib prompt materialization, consumes, and hidden inputs."""

    phase_scope = context.phase_scope
    if phase_scope is None:
        return [], [], [], {}

    flattened_inputs: list[tuple[str, Any]] = []
    for base_name, prompt_input in prompt_input_specs:
        flattened_inputs.extend(
            _flatten_phase_stdlib_prompt_inputs(
                prompt_input,
                base_name=base_name,
                local_values=local_values,
            )
        )

    values: list[dict[str, Any]] = []
    publishes: list[dict[str, str]] = []
    artifact_names: list[str] = []
    hidden_inputs: dict[str, LoweringOrigin] = {}
    for artifact_name, input_expr in flattened_inputs:
        raw_source_node, extra_hidden_inputs = _resolve_phase_prompt_input_source(
            input_expr,
            artifact_name=artifact_name,
            context=context,
            local_values=local_values,
        )
        hidden_inputs.update(extra_hidden_inputs)
        for hidden_input_name in extra_hidden_inputs:
            context.internal_generated_input_reasons.setdefault(hidden_input_name, "phase_prompt_transport")
        contract_input_name = _materialize_contract_input_name(raw_source_node)
        pointer_path = _phase_prompt_input_pointer_path(context.workflow_name, artifact_name)
        if contract_input_name is None or contract_input_name.startswith("__phase_prompt__"):
            if not isinstance(input_expr, PhaseTargetExpr):
                value_contract = _phase_prompt_local_value_contract(
                    artifact_name,
                    source_expr=input_expr,
                    context=context,
                    span=source_expr.span,
                    form_path=source_expr.form_path,
                )
                if value_contract is None:
                    raise _compile_error(
                        code="phase_translation_body_invalid",
                        message=(
                            "phase stdlib prompt inputs must lower from flattened workflow inputs, "
                            "approved phase targets, or typed step-backed state"
                        ),
                        span=source_expr.span,
                        form_path=source_expr.form_path,
                    )
            else:
                value_contract = _phase_target_prompt_input_contract(input_expr)
        else:
            value_contract = (
                {"inherit": "source"}
                if raw_source_node.get("input") == contract_input_name
                else _authored_input_contract(
                    contract_input_name,
                    context=context,
                    span=source_expr.span,
                    form_path=source_expr.form_path,
                )
            )
        values.append(
            {
                "name": artifact_name,
                "source": raw_source_node,
                "contract": value_contract,
                "pointer": {"path": pointer_path},
            }
        )
        context.top_level_artifacts[artifact_name] = _phase_prompt_artifact_definition(
            contract=value_contract,
            input_name=contract_input_name,
            context=context,
            pointer_path=pointer_path,
            span=source_expr.span,
            form_path=source_expr.form_path,
        )
        allocate_materialized_value_view(
            context=context,
            source_expr=source_expr,
            path_template=pointer_path,
            stable_target=f"prompt_inputs/{artifact_name}",
        )
        publishes.append({"artifact": artifact_name, "from": artifact_name})
        artifact_names.append(artifact_name)

    step_name = f"{context.step_name_prefix}__prompt_inputs"
    step_id = context.normalize_generated_step_id(step_name)
    _record_step_origin(context, step_name=step_name, step_id=step_id, source=source_expr)
    return (
        [
            {
                "name": step_name,
                "id": step_id,
                "materialize_artifacts": {"values": values},
                "publishes": publishes,
            }
        ],
        [
            {
                "artifact": artifact_name,
                "policy": "latest_successful",
                "freshness": "any",
            }
            for artifact_name in artifact_names
        ],
        artifact_names,
        hidden_inputs,
    )


def _phase_prompt_local_value_contract(
    artifact_name: str,
    *,
    source_expr: Any,
    context: _LoweringContext,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> dict[str, Any] | None:
    """Infer one prompt-input contract from flattened local type bindings."""

    if isinstance(source_expr, NameExpr):
        field_path = (source_expr.name,)
    elif isinstance(source_expr, FieldAccessExpr) and isinstance(source_expr.base, NameExpr):
        field_path = (source_expr.base.name, *source_expr.fields)
    else:
        field_path = tuple(segment for segment in artifact_name.split("__") if segment)
    if not field_path:
        return None
    current_type = context.local_type_bindings.get(field_path[0])
    if current_type is None:
        return None
    for field_name in field_path[1:]:
        if not isinstance(current_type, RecordTypeRef):
            return None
        current_type = context.type_env.record_field(
            current_type,
            field_name,
            span=span,
            form_path=form_path,
        )
    fields = derive_workflow_boundary_fields(
        current_type,
        generated_name=artifact_name,
        source_path=(artifact_name,),
        span=span,
        form_path=form_path,
    )
    if len(fields) != 1:
        return None
    return dict(fields[0].contract_definition)


def _flatten_phase_stdlib_prompt_inputs(
    expr: Any,
    *,
    base_name: str,
    local_values: Mapping[str, Any],
) -> list[tuple[str, Any]]:
    """Flatten record/tuple prompt inputs into materializable artifact inputs."""

    if isinstance(expr, tuple):
        flattened: list[tuple[str, Any]] = []
        for item in expr:
            item_value = _resolve_inline_expr_value(item, local_values=local_values)
            child_name = base_name
            if isinstance(item, FieldAccessExpr) and item.fields:
                child_name = item.fields[-1]
            elif isinstance(item, NameExpr):
                child_name = item.name
            elif isinstance(item_value, str) and item_value.startswith("inputs."):
                child_name = item_value.removeprefix("inputs.").split("__")[-1]
            flattened.extend(
                _flatten_phase_stdlib_prompt_inputs(
                    item,
                    base_name=child_name,
                    local_values=local_values,
                )
            )
        return flattened

    value = _resolve_inline_expr_value(expr, local_values=local_values)
    if isinstance(value, Mapping):
        flattened = []
        for field_name, field_value in value.items():
            child_name = field_name if base_name in {"inputs", "producer"} else f"{base_name}__{field_name}"
            flattened.extend(
                _flatten_phase_stdlib_prompt_inputs(
                    field_value,
                    base_name=child_name,
                    local_values=local_values,
                )
            )
        return flattened
    if isinstance(value, RecordExpr):
        flattened = []
        for field_name, field_expr in value.fields:
            child_name = field_name if base_name in {"inputs", "producer"} else f"{base_name}__{field_name}"
            flattened.extend(
                _flatten_phase_stdlib_prompt_inputs(
                    field_expr,
                    base_name=child_name,
                    local_values=local_values,
                )
            )
        return flattened
    if isinstance(expr, (FieldAccessExpr, NameExpr, PhaseTargetExpr)):
        return [(base_name, expr)]
    return [(base_name, value if value is not None else expr)]


def _resolve_phase_prompt_input_source(
    expr: Any,
    *,
    artifact_name: str,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[dict[str, str], dict[str, LoweringOrigin]]:
    """Resolve a phase prompt input to a materialize_artifacts source node."""

    if isinstance(expr, NameExpr):
        bound_value = local_values.get(expr.name)
        if isinstance(bound_value, PhaseTargetExpr):
            expr = bound_value

    if isinstance(expr, PhaseTargetExpr):
        phase_scope = context.phase_scope
        if phase_scope is None:
            raise _compile_error(
                code="phase_translation_body_invalid",
                message="phase-target lowering requires an active phase scope",
                span=expr.span,
                form_path=expr.form_path,
            )
        target_ref = phase_scope.target_refs.get(expr.target_name)
        if target_ref is None:
            raise _compile_error(
                code="phase_target_unknown",
                message=f"`phase-target` does not support `{expr.target_name}` in this slice",
                span=expr.span,
                form_path=expr.form_path,
            )
        if (
            target_ref.startswith("inputs.")
            or target_ref.startswith("root.steps.")
            or target_ref.startswith("self.steps.")
            or target_ref.startswith("parent.steps.")
        ):
            return _materialize_source_from_ref(target_ref), {}
        hidden_input_name = f"__phase_prompt__{context.step_name_prefix}__{artifact_name}"
        return (
            {"input": hidden_input_name},
            {hidden_input_name: _origin_from_context_source(context, expr)},
        )

    value = _resolve_inline_expr_value(expr, local_values=local_values)
    if isinstance(value, str):
        return _materialize_source_from_ref(value), {}
    raise _compile_error(
        code="phase_translation_body_invalid",
        message="phase-scoped provider-result inputs must lower from workflow inputs or approved phase targets",
        span=expr.span,
        form_path=expr.form_path,
    )


def _materialize_source_from_ref(ref: str) -> dict[str, str]:
    """Convert a workflow ref into a materialize_artifacts source mapping."""

    if ref.startswith("inputs."):
        return {"input": ref.removeprefix("inputs.")}
    return {"ref": ref}


def _phase_prompt_report_target_inputs(
    exprs: list[Any],
    *,
    local_values: Mapping[str, Any] | None = None,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> dict[str, PhaseTargetExpr]:
    """Validate and classify execution/progress report target expressions."""

    if len(exprs) != 2:
        raise _compile_error(
            code="phase_translation_body_invalid",
            message="phase-scoped provider-result requires both execution and progress report targets",
            span=span,
            form_path=form_path,
        )

    inputs_by_artifact: dict[str, PhaseTargetExpr] = {}
    for expr in exprs:
        if (
            local_values is not None
            and isinstance(expr, NameExpr)
            and isinstance(local_values.get(expr.name), PhaseTargetExpr)
        ):
            expr = local_values[expr.name]
        if not isinstance(expr, PhaseTargetExpr):
            raise _compile_error(
                code="phase_translation_body_invalid",
                message="phase-scoped provider-result report inputs must be phase-target references",
                span=expr.span,
                form_path=expr.form_path,
            )
        artifact_name = _phase_prompt_artifact_name_for_target(expr)
        if artifact_name in inputs_by_artifact:
            raise _compile_error(
                code="phase_translation_body_invalid",
                message="phase-scoped provider-result requires each approved report target exactly once",
                span=expr.span,
                form_path=expr.form_path,
            )
        inputs_by_artifact[artifact_name] = expr

    missing = [
        artifact_name
        for artifact_name in ("execution_report_target", "progress_report_target")
        if artifact_name not in inputs_by_artifact
    ]
    if missing:
        raise _compile_error(
            code="phase_translation_body_invalid",
            message="phase-scoped provider-result requires both execution and progress report targets",
            span=span,
            form_path=form_path,
        )
    return inputs_by_artifact


def _phase_prompt_artifact_name_for_target(expr: PhaseTargetExpr) -> str:
    """Map approved phase targets to prompt artifact names."""

    if expr.target_name == "execution-report":
        return "execution_report_target"
    if expr.target_name == "progress-report":
        return "progress_report_target"
    raise _compile_error(
        code="phase_target_unknown",
        message=f"`phase-target` does not support `{expr.target_name}` in this slice",
        span=expr.span,
        form_path=expr.form_path,
    )


def _materialize_source_input_name(source: Mapping[str, str]) -> str | None:
    """Return the direct input name used by a materialization source."""

    input_name = source.get("input")
    if isinstance(input_name, str):
        return input_name
    return None


def _materialize_contract_input_name(source: Mapping[str, str]) -> str | None:
    """Return the input whose contract should govern a materialized source."""

    input_name = _materialize_source_input_name(source)
    if input_name is not None:
        return input_name
    ref = source.get("ref")
    if isinstance(ref, str) and ref.startswith("inputs."):
        return ref.removeprefix("inputs.")
    return None


def _authored_input_contract(
    input_name: str,
    *,
    context: _LoweringContext,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> dict[str, Any]:
    """Return a flattened workflow input contract by generated input name."""

    input_contract = context.authored_input_contracts.get(input_name)
    if input_contract is None:
        raise _compile_error(
            code="phase_translation_body_invalid",
            message=f"missing flattened workflow input contract for `{input_name}`",
            span=span,
            form_path=form_path,
        )
    return dict(input_contract)


def _phase_target_prompt_input_contract(target_expr: PhaseTargetExpr) -> dict[str, Any]:
    """Build the contract for an approved generated phase target."""

    spec = PHASE_TARGET_SPECS.get(target_expr.target_name)
    if spec is None:
        raise _compile_error(
            code="phase_target_unknown",
            message=f"`phase-target` does not support `{target_expr.target_name}` in this slice",
            span=target_expr.span,
            form_path=target_expr.form_path,
        )
    _, under_root, _ = spec
    return {
        "kind": "relpath",
        "type": "relpath",
        "under": under_root,
        "must_exist_target": False,
    }


def _phase_prompt_input_contract(
    artifact_name: str,
    *,
    input_name: str | None,
    context: _LoweringContext,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> dict[str, Any]:
    """Choose the contract for one phase prompt materialization artifact."""

    if artifact_name in {"design", "plan"}:
        return {"inherit": "source"}
    if input_name is None:
        raise _compile_error(
            code="phase_translation_body_invalid",
            message=f"missing flattened workflow input contract for `{artifact_name}`",
            span=span,
            form_path=form_path,
        )
    input_contract = context.authored_input_contracts.get(input_name)
    if input_contract is None:
        raise _compile_error(
            code="phase_translation_body_invalid",
            message=f"missing flattened workflow input contract for `{input_name}`",
            span=span,
            form_path=form_path,
        )
    return dict(input_contract)

def _surface_contract_from_structured_field(field: Mapping[str, Any]) -> dict[str, Any]:
    """Convert one JSON-bundle field contract to a workflow output contract.

    Structured-result contracts describe fields inside provider/command JSON
    bundles. Workflow outputs use the same basic scalar/path keys but omit
    bundle-only metadata, so this helper keeps just the fields the runtime
    output-contract validator understands.
    """

    definition = {
        key: value
        for key, value in field.items()
        if key in {"type", "allowed", "under", "must_exist_target", "item", "items", "keys", "values"}
    }
    if definition.get("type") == "relpath":
        definition["kind"] = "relpath"
    elif definition.get("type") in {"optional", "list", "map"}:
        definition["kind"] = "collection"
    else:
        definition["kind"] = "scalar"
    return definition


def _union_case_contract_definitions(
    type_ref: UnionTypeRef,
    *,
    variant_name: str,
    workflow_name: str,
    step_name: str,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    """Build the output contracts visible inside one union match case."""

    contract = derive_structured_result_contract(
        type_ref,
        workflow_name=workflow_name,
        step_id=step_name,
        span=span,
        form_path=form_path,
    )
    payload = contract.payload
    outputs = {
        "variant": _surface_contract_from_structured_field(payload["discriminant"]),
    }
    for field in payload["shared_fields"]:
        outputs[field["name"]] = _surface_contract_from_structured_field(field)
    variant_payload = payload["variants"][variant_name]
    for field in variant_payload["fields"]:
        outputs[field["name"]] = _surface_contract_from_structured_field(field)
    return outputs


def _union_output_contracts(
    type_ref: Any,
    *,
    payload: Mapping[str, Any],
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    """Flatten all shared and variant-specific union output contracts."""

    if not isinstance(type_ref, UnionTypeRef):
        raise _compile_error(
            code="review_loop_result_contract_invalid",
            message="`review-revise-loop` lowering requires a union return type",
            span=span,
            form_path=form_path,
        )
    outputs = {
        "variant": _surface_contract_from_structured_field(payload["discriminant"]),
    }
    for field in payload["shared_fields"]:
        outputs[field["name"]] = _surface_contract_from_structured_field(field)
    for variant_payload in payload["variants"].values():
        for field in variant_payload["fields"]:
            definition = _surface_contract_from_structured_field(field)
            if definition.get("type") == "relpath":
                definition["must_exist_target"] = False
            outputs.setdefault(field["name"], definition)
    return outputs



def _join_ref_path(base_ref: str, suffix: str) -> str:
    """Append a path suffix to a substitution ref without losing templating."""

    if base_ref.startswith("${"):
        return f"{base_ref}/{suffix}"
    return "${" + base_ref + "}/" + suffix
