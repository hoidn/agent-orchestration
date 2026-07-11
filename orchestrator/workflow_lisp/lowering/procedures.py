"""Procedure lowering ownership for Workflow Lisp."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any

from orchestrator.workflow.references import MaterializeViewBindingReference

from ..diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from ..expression_traversal import walk_expr
from ..expressions import (
    CallExpr,
    CommandResultExpr,
    EnumMemberExpr,
    LetStarExpr,
    LoopRecurExpr,
    MatchExpr,
    ProcRefLiteralExpr,
    ProcedureCallExpr,
    ProviderResultExpr,
    RecordExpr,
    WithPhaseExpr,
    WorkflowRefLiteralExpr,
)
from ..phase import eligible_private_context_source_param_names
from ..procedure_refs import ResolvedProcRefValue
from ..procedures import (
    ProcedureLoweringMode,
    TypedProcedureDef,
    proc_ref_specialization_name as proc_ref_call_specialization_name,
    procedure_type_env_for,
)
from ..spans import SourceSpan
from ..type_env import (
    FrontendTypeEnvironment,
    ProcRefTypeRef,
    RecordTypeRef,
    TypeParamRef,
    TypeRef,
    UnionTypeRef,
    WorkflowRefTypeRef,
    render_type_ref,
)
from ..workflow_refs import ResolvedWorkflowRef
from ..workflows import (
    PromptExtern,
    ProviderExtern,
    TypedWorkflowDef,
    WorkflowDef,
    WorkflowParam,
    WorkflowSignature,
)


@dataclass(frozen=True)
class LowerableProcedureCall:
    """Owner-level procedure-call payload shared by frontend and WCC lowering."""

    callee_name: str
    args: tuple[Any, ...]
    span: Any
    form_path: tuple[str, ...]
    expansion_stack: tuple[object, ...] = ()
    specialized_callee_name: str | None = None


@dataclass(frozen=True)
class ProcedureLoweringPlan:
    """Internal procedure-lowering plan before runtime-visible emission."""

    selected_procedure: TypedProcedureDef | None
    resolved_args: tuple[Any, ...]
    chosen_lowering_mode: ProcedureLoweringMode | None
    provenance_source: Any
    runtime_erasure_inputs: tuple[Any, ...]


def _procedure_type_env_for(
    procedure: TypedProcedureDef,
    *,
    procedure_type_envs: Mapping[str, FrontendTypeEnvironment] | None,
    default: FrontendTypeEnvironment,
) -> FrontendTypeEnvironment:
    """Resolve the lowering/typecheck environment for one procedure body."""

    return procedure_type_env_for(
        procedure,
        procedure_type_envs=procedure_type_envs,
        default=default,
    )


_COMPILE_TIME_ONLY_RUNTIME_TYPES = (
    ProcRefLiteralExpr,
    WorkflowRefLiteralExpr,
    ProcRefTypeRef,
    TypeParamRef,
    WorkflowRefTypeRef,
    ResolvedProcRefValue,
    ResolvedWorkflowRef,
    ProviderExtern,
    PromptExtern,
)


def _runtime_erasure_checked(
    steps: list[dict[str, Any]],
    terminal: Any,
    *,
    plan: ProcedureLoweringPlan,
) -> tuple[list[dict[str, Any]], Any]:
    _assert_runtime_erasure(
        {"steps": steps, "output_refs": terminal.output_refs, "hidden_inputs": terminal.hidden_inputs},
        span=plan.provenance_source.span,
        form_path=plan.provenance_source.form_path,
    )
    return steps, terminal


def _resolve_procedure_lowering(
    typed_procedures: tuple[TypedProcedureDef, ...],
    *,
    typed_workflows: tuple[TypedWorkflowDef, ...],
    workflow_path: Path,
    type_env: FrontendTypeEnvironment,
    procedure_type_envs: Mapping[str, FrontendTypeEnvironment] | None = None,
) -> Mapping[str, TypedProcedureDef]:
    from ..procedure_specialization import _procedure_private_body_valid, _procedure_private_boundary_valid
    from .context import _compile_error

    call_counts, lowerable_call_sites = _procedure_private_call_site_analysis(
        typed_procedures,
        typed_workflows=typed_workflows,
        type_env=type_env,
        procedure_type_envs=procedure_type_envs,
    )
    resolved: dict[str, TypedProcedureDef] = {}
    typed_procedures_by_name = {
        procedure.definition.name: procedure for procedure in typed_procedures
    }
    for procedure in typed_procedures:
        requested = procedure.signature.requested_lowering_mode
        boundary_valid = _procedure_private_boundary_valid(procedure)
        body_valid = _procedure_private_body_valid(
            procedure,
            typed_procedures_by_name=typed_procedures_by_name,
            type_env=type_env,
            procedure_type_envs=procedure_type_envs,
        )
        if requested == ProcedureLoweringMode.PRIVATE_WORKFLOW and not boundary_valid:
            raise _compile_error(
                code="proc_private_workflow_boundary_invalid",
                message=f"procedure `{procedure.definition.name}` cannot lower as `private-workflow` in Stage 3",
                span=procedure.definition.span,
                form_path=procedure.definition.form_path,
            )
        if requested == ProcedureLoweringMode.PRIVATE_WORKFLOW and not body_valid:
            raise _compile_error(
                code="proc_private_workflow_boundary_invalid",
                message=(
                    f"procedure `{procedure.definition.name}` cannot lower as `private-workflow` in Stage 3 "
                    "because its body would not export step-backed outputs through the shared-validation seam"
                ),
                span=procedure.definition.span,
                form_path=procedure.definition.form_path,
            )
        if requested == ProcedureLoweringMode.PRIVATE_WORKFLOW:
            mode = ProcedureLoweringMode.PRIVATE_WORKFLOW
        elif (
            requested == ProcedureLoweringMode.AUTO
            and boundary_valid
            and body_valid
            and call_counts.get(procedure.definition.name, 0) > 1
            and lowerable_call_sites.get(procedure.definition.name, True)
        ):
            mode = ProcedureLoweringMode.PRIVATE_WORKFLOW
        else:
            mode = ProcedureLoweringMode.INLINE
        generated_name = None
        if mode == ProcedureLoweringMode.PRIVATE_WORKFLOW:
            generated_name = f"%{workflow_path.stem}.{procedure.definition.name}.v1"
        resolved[procedure.definition.name] = TypedProcedureDef(
            definition=procedure.definition,
            signature=procedure.signature,
            typed_body=procedure.typed_body,
            direct_effect_summary=procedure.direct_effect_summary,
            transitive_effect_summary=procedure.transitive_effect_summary,
            resolved_lowering_mode=mode,
            generated_workflow_name=generated_name,
            specialization=procedure.specialization,
        )
    return MappingProxyType(resolved)


def _procedure_private_call_site_analysis(
    typed_procedures: tuple[TypedProcedureDef, ...],
    *,
    typed_workflows: tuple[TypedWorkflowDef, ...],
    type_env: FrontendTypeEnvironment,
    procedure_type_envs: Mapping[str, FrontendTypeEnvironment] | None = None,
) -> tuple[Mapping[str, int], Mapping[str, bool]]:
    """Count procedure call sites and whether each can cross a workflow boundary."""

    from .core import _resolve_expr_local_value, _signature_local_values
    from .values import _build_record_step_local_value

    typed_procedures_by_name = {
        procedure.definition.name: procedure for procedure in typed_procedures
    }
    distinct_call_sites: dict[str, set[tuple[SourceSpan, tuple[str, ...]]]] = {}
    lowerable: dict[str, bool] = {}

    def walk(
        expr: Any,
        *,
        local_values: Mapping[str, Any],
        current_type_env: FrontendTypeEnvironment,
    ) -> None:
        if isinstance(expr, ProcedureCallExpr):
            distinct_call_sites.setdefault(expr.callee_name, set()).add((expr.span, expr.form_path))
            call_site_lowerable = True
            for arg in expr.args:
                walk(arg, local_values=local_values, current_type_env=current_type_env)
                if _resolve_expr_local_value(arg, local_values=local_values) is None:
                    call_site_lowerable = False
            lowerable[expr.callee_name] = lowerable.get(expr.callee_name, True) and call_site_lowerable
            callee = typed_procedures_by_name.get(expr.callee_name)
            if callee is not None:
                child_locals = {}
                for arg_expr, (param_name, _) in zip(expr.args, callee.signature.params, strict=True):
                    child_locals[param_name] = _resolve_expr_local_value(arg_expr, local_values=local_values)
                walk(
                    callee.typed_body.expr,
                    local_values=child_locals,
                    current_type_env=_procedure_type_env_for(
                        callee,
                        procedure_type_envs=procedure_type_envs,
                        default=current_type_env,
                    ),
                )
            return
        if isinstance(expr, LetStarExpr):
            child_locals = dict(local_values)
            for binding_name, binding in expr.bindings:
                walk(binding, local_values=child_locals, current_type_env=current_type_env)
                resolved_binding = _resolve_expr_local_value(binding, local_values=child_locals)
                if resolved_binding is not None:
                    child_locals[binding_name] = resolved_binding
                # schema1_compatibility: legacy local-value projection for covered provider results.
                elif isinstance(binding, ProviderResultExpr):
                    binding_type = current_type_env.resolve_type(
                        binding.returns_type_name,
                        span=binding.span,
                        form_path=binding.form_path,
                    )
                    if isinstance(binding_type, RecordTypeRef):
                        child_locals[binding_name] = _build_record_step_local_value(
                            binding_type,
                            step_name=binding_name,
                        )
            walk(expr.body, local_values=child_locals, current_type_env=current_type_env)
            return
        # schema1_compatibility: legacy procedure traversal for covered match forms.
        if isinstance(expr, MatchExpr):
            walk(expr.subject, local_values=local_values, current_type_env=current_type_env)
            for arm in expr.arms:
                walk(arm.body, local_values=local_values, current_type_env=current_type_env)
            return
        if isinstance(expr, RecordExpr):
            for _, value in expr.fields:
                walk(value, local_values=local_values, current_type_env=current_type_env)
            return
        if isinstance(expr, WithPhaseExpr):
            walk(expr.ctx_expr, local_values=local_values, current_type_env=current_type_env)
            walk(expr.body, local_values=local_values, current_type_env=current_type_env)
            return
        # schema1_compatibility: legacy procedure traversal for covered provider results.
        if isinstance(expr, ProviderResultExpr):
            walk(expr.provider, local_values=local_values, current_type_env=current_type_env)
            walk(expr.prompt, local_values=local_values, current_type_env=current_type_env)
            for value in expr.inputs:
                walk(value, local_values=local_values, current_type_env=current_type_env)
            return
        # schema1_compatibility: legacy procedure traversal for covered command results.
        if isinstance(expr, CommandResultExpr):
            for value in expr.argv:
                walk(value, local_values=local_values, current_type_env=current_type_env)
            return
        if isinstance(expr, CallExpr):
            for _, value in expr.bindings:
                walk(value, local_values=local_values, current_type_env=current_type_env)

    for workflow in typed_workflows:
        walk(
            workflow.typed_body.expr,
            local_values=_signature_local_values(workflow),
            current_type_env=type_env,
        )
    return MappingProxyType(
        {
            callee_name: len(call_sites)
            for callee_name, call_sites in distinct_call_sites.items()
        }
    ), MappingProxyType(lowerable)


def _lower_procedure_call_expr(
    typed_expr: Any,
    *,
    context: Any,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], Any]:
    expr = typed_expr.expr
    assert isinstance(expr, ProcedureCallExpr)
    return _lower_procedure_call(
        LowerableProcedureCall(
            callee_name=expr.callee_name,
            args=tuple(expr.args),
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        ),
        result_type=typed_expr.type_ref,
        context=context,
        local_values=local_values,
    )


def _lower_procedure_call(
    expr: LowerableProcedureCall,
    *,
    result_type: TypeRef,
    context: Any,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], Any]:
    """Lower a reusable procedure call without adding a second runtime model.

    A `defproc` is reusable workflow behavior, not just syntax. Lowering either
    inlines its body into the caller or emits a hidden workflow and calls it
    through the same runtime call step used for authored workflows.
    """

    from ..procedure_specialization import specialize_typed_procedure
    from .context import _LoweringContext, _TerminalResult
    from .origins import _record_step_origin
    from .core import (
        _compile_error,
        _inline_procedure_step_prefix,
        _lower_expression,
        _normalize_generated_step_id,
        _render_call_binding_ref,
        _render_record_call_bindings,
        _resolved_proc_ref_value,
        _resolved_workflow_ref_value,
    )
    from .values import (
        _flatten_boundary_leaf_paths,
        _procedure_signature_local_type_bindings,
        _resolve_inline_expr_value,
    )
    from .workflow_calls import (
        _managed_write_root_binding_step,
        _managed_write_root_requirements_for_callable,
    )

    arg_exprs = expr.args
    parent_origin_notes = context.origin_notes
    plan = ProcedureLoweringPlan(
        selected_procedure=context.typed_procedures.get(expr.callee_name),
        resolved_args=tuple(arg_exprs),
        chosen_lowering_mode=(
            None
            if context.typed_procedures.get(expr.callee_name) is None
            else context.typed_procedures[expr.callee_name].resolved_lowering_mode
        ),
        provenance_source=expr,
        runtime_erasure_inputs=(local_values, context.origin_notes),
    )
    if expr.specialized_callee_name is not None:
        procedure = context.typed_procedures.get(expr.specialized_callee_name)
        if procedure is None:
            raise _compile_error(
                code="procedure_call_unknown",
                message=f"unknown procedure callee `{expr.specialized_callee_name}` during lowering",
                span=expr.span,
                form_path=expr.form_path,
            )
    else:
        bound_proc_ref = _resolved_proc_ref_value(
            local_values.get(expr.callee_name),
            context=context,
            local_values=local_values,
        )
        if bound_proc_ref is not None:
            procedure = context.typed_procedures.get(bound_proc_ref.call_target_name)
            if procedure is None:
                base_procedure = context.typed_procedures.get(bound_proc_ref.procedure_name)
                if base_procedure is None:
                    raise _compile_error(
                        code="procedure_call_unknown",
                        message=f"unknown procedure callee `{bound_proc_ref.procedure_name}` during lowering",
                        span=expr.span,
                        form_path=expr.form_path,
                    )
                procedure = specialize_typed_procedure(
                    base_procedure,
                    value_bindings={
                        binding.name: binding.value_expr
                        for binding in bound_proc_ref.bound_args
                        if not isinstance(binding.type_ref, ProcRefTypeRef)
                    },
                    proc_ref_bindings={
                        binding.name: resolved_binding
                        for binding in bound_proc_ref.bound_args
                        if isinstance(binding.type_ref, ProcRefTypeRef)
                        for resolved_binding in (
                            _resolved_proc_ref_value(
                                binding.value_expr,
                                context=context,
                                local_values=local_values,
                            ),
                        )
                        if resolved_binding is not None
                    },
                    remaining_params=bound_proc_ref.residual_params,
                    workflow_path=context.workflow_path,
                    type_env=context.type_env,
                    typed_procedures_by_name=context.typed_procedures,
                    specialized_name=bound_proc_ref.call_target_name,
                    origin_span=expr.span,
                    origin_form_path=expr.form_path,
                )
            arg_exprs = expr.args
        else:
            procedure = context.typed_procedures.get(expr.callee_name)
            if procedure is None:
                raise _compile_error(
                    code="procedure_call_unknown",
                    message=f"unknown procedure callee `{expr.callee_name}` during lowering",
                    span=expr.span,
                    form_path=expr.form_path,
                )
    if any(isinstance(type_ref, WorkflowRefTypeRef) for _, type_ref in procedure.signature.params):
        workflow_ref_bindings: dict[str, ResolvedWorkflowRef] = {}
        remaining_params: list[tuple[str, TypeRef]] = []
        remaining_args: list[Any] = []
        for arg_expr, (param_name, param_type) in zip(arg_exprs, procedure.signature.params, strict=True):
            if isinstance(param_type, WorkflowRefTypeRef):
                candidate_expr = (
                    arg_expr
                    if isinstance(arg_expr, EnumMemberExpr)
                    else _resolve_inline_expr_value(arg_expr, local_values=local_values) or arg_expr
                )
                resolved_binding = _resolved_workflow_ref_value(
                    candidate_expr,
                    context=context,
                    expected_type=param_type,
                )
                if resolved_binding is None:
                    raise _compile_error(
                        code="workflow_ref_literal_required",
                        message="workflow-ref arguments must be literals or forwarded workflow-ref bindings",
                        span=arg_expr.span,
                        form_path=arg_expr.form_path,
                    )
                workflow_ref_bindings[param_name] = resolved_binding
                continue
            remaining_params.append((param_name, param_type))
            remaining_args.append(arg_expr)
        procedure = specialize_typed_procedure(
            procedure,
            workflow_ref_bindings=workflow_ref_bindings,
            remaining_params=tuple(remaining_params),
            workflow_path=context.workflow_path,
            type_env=context.type_env,
            typed_procedures_by_name=context.typed_procedures,
        )
        arg_exprs = tuple(remaining_args)
    if any(isinstance(type_ref, ProcRefTypeRef) for _, type_ref in procedure.signature.params):
        proc_ref_bindings: dict[str, ResolvedProcRefValue] = {}
        remaining_params = []
        remaining_args = []
        for arg_expr, (param_name, param_type) in zip(arg_exprs, procedure.signature.params, strict=True):
            if isinstance(param_type, ProcRefTypeRef):
                resolved_binding = _resolved_proc_ref_value(
                    _resolve_inline_expr_value(arg_expr, local_values=local_values) or arg_expr,
                    context=context,
                    local_values=local_values,
                    expected_type=param_type,
                )
                if resolved_binding is not None:
                    proc_ref_bindings[param_name] = resolved_binding
                    continue
            remaining_params.append((param_name, param_type))
            remaining_args.append(arg_expr)
        if proc_ref_bindings:
            specialized_name = proc_ref_call_specialization_name(
                procedure.signature.name,
                proc_ref_bindings,
            )
            procedure = context.typed_procedures.get(specialized_name) or specialize_typed_procedure(
                procedure,
                proc_ref_bindings=proc_ref_bindings,
                remaining_params=tuple(remaining_params),
                workflow_path=context.workflow_path,
                type_env=context.type_env,
                typed_procedures_by_name=context.typed_procedures,
                specialized_name=specialized_name,
                origin_span=expr.span,
                origin_form_path=expr.form_path,
            )
            arg_exprs = tuple(remaining_args)
    if procedure.signature.name in context.active_procedure_calls:
        raise _compile_error(
            code=(
                "proc_ref_specialization_cycle"
                if procedure.specialization is not None
                and (
                    getattr(procedure.specialization, "proc_ref_bindings", {})
                    or getattr(procedure.specialization, "value_bindings", {})
                )
                else "proc_lowering_cycle"
            ),
            message=f"recursive procedure specialization cycle detected for `{procedure.signature.name}`",
            span=expr.span,
            form_path=expr.form_path,
        )
    plan = replace(
        plan,
        selected_procedure=procedure,
        resolved_args=tuple(arg_exprs),
        chosen_lowering_mode=procedure.resolved_lowering_mode,
    )
    canonical_name = procedure.signature.name if procedure is not None else expr.callee_name
    procedure_notes = _merge_origin_notes(
        parent_origin_notes,
        _procedure_provenance_notes(
            expr,
            procedure,
            typed_procedures=context.typed_procedures,
        ),
    )
    resolved_lowering_mode = procedure.resolved_lowering_mode
    generated_workflow_name = procedure.generated_workflow_name
    # schema1_compatibility: keep loop-recur bodies on the inline route inside
    # iteration scopes so recursive loop state remains owned by loop lowering.
    if (
        resolved_lowering_mode == ProcedureLoweringMode.INLINE
        and context.iteration_scope is not None
        and not context.workflow_name.startswith("%composition.")
        and not any(isinstance(node, LoopRecurExpr) for node in walk_expr(procedure.typed_body.expr))
    ):
        from ..procedure_specialization import (
            _procedure_private_body_valid,
            _procedure_private_boundary_valid,
        )

        procedure_type_env = _procedure_type_env_for(
            procedure,
            procedure_type_envs=context.procedure_type_envs,
            default=context.type_env,
        )
        if _procedure_private_boundary_valid(procedure) and _procedure_private_body_valid(
            procedure,
            typed_procedures_by_name=context.typed_procedures,
            type_env=procedure_type_env,
            procedure_type_envs=context.procedure_type_envs,
        ):
            resolved_lowering_mode = ProcedureLoweringMode.PRIVATE_WORKFLOW
            generated_workflow_name = procedure.generated_workflow_name or (
                f"%{Path(procedure.definition.span.start.path).stem}.{procedure.signature.name}.v1"
            )
            procedure = replace(
                procedure,
                resolved_lowering_mode=resolved_lowering_mode,
                generated_workflow_name=generated_workflow_name,
            )
    if resolved_lowering_mode == ProcedureLoweringMode.PRIVATE_WORKFLOW:
        context.origin_notes = procedure_notes
        assert procedure.generated_workflow_name is not None
        if procedure.generated_workflow_name not in context.workflows_by_name:
            mutable_workflows = context.workflows_by_name
            if isinstance(mutable_workflows, dict):
                mutable_workflows[procedure.generated_workflow_name] = _private_workflow_from_procedure(procedure)
            if isinstance(context.generated_private_workflow_type_envs, dict):
                context.generated_private_workflow_type_envs[procedure.generated_workflow_name] = _procedure_type_env_for(
                    procedure,
                    procedure_type_envs=context.procedure_type_envs,
                    default=context.type_env,
                )
        callee = context.lowered_callees.get(procedure.generated_workflow_name)
        if callee is None:
            callee = context.ensure_workflow_lowered(procedure.generated_workflow_name)
        if callee is None:
            raise _compile_error(
                code="proc_private_workflow_boundary_invalid",
                message=f"generated private workflow `{procedure.generated_workflow_name}` was not lowered",
                span=expr.span,
                form_path=expr.form_path,
            )
        step_name = f"{context.step_name_prefix}__call_{canonical_name}"
        step_id = _normalize_generated_step_id(step_name)
        with_bindings: dict[str, Any] = {}
        for arg_expr, (param_name, param_type) in zip(arg_exprs, procedure.signature.params, strict=True):
            if isinstance(param_type, RecordTypeRef):
                with_bindings.update(
                    _render_record_call_bindings(
                        param_name,
                        param_type,
                        arg_expr,
                        local_values=local_values,
                    )
                )
            else:
                with_bindings[param_name] = _render_call_binding_ref(arg_expr, local_values=local_values)
        binding_steps, managed_bindings = _managed_write_root_binding_step(
            context=context,
            source_expr=expr,
            call_step_name=step_name,
            callee_name=canonical_name,
            managed_inputs=_managed_write_root_requirements_for_callable(
                lowered_callee=callee,
                imported_bundle=None,
                span=expr.span,
                form_path=expr.form_path,
            ),
        )
        with_bindings.update(managed_bindings)
        _record_step_origin(context, step_name=step_name, step_id=step_id, source=expr)
        return _runtime_erasure_checked(
            [*binding_steps, {"name": step_name, "id": step_id, "call": procedure.generated_workflow_name, "with": with_bindings}],
            _TerminalResult(
                step_name=step_name,
                step_id=step_id,
                output_refs={
                    output_name: f"root.steps.{step_name}.artifacts.{output_name}"
                    for output_name, _ in _flatten_boundary_leaf_paths(result_type, generated_name="return")
                },
                output_kind="call",
                hidden_inputs={},
                returned_union_type_name=result_type.name if isinstance(result_type, UnionTypeRef) else None,
            ),
            plan=plan,
        )

    prefix_ordinal = context.inline_call_counters.get(expr.callee_name, 0) + 1
    context.inline_call_counters[expr.callee_name] = prefix_ordinal
    context.origin_notes = procedure_notes
    child_locals = dict(local_values)
    if procedure.specialization is not None:
        child_locals.update(dict(getattr(procedure.specialization, "workflow_ref_bindings", {})))
        child_locals.update(dict(getattr(procedure.specialization, "proc_ref_bindings", {})))
        child_locals.update(dict(getattr(procedure.specialization, "value_bindings", {})))
    for arg_expr, (param_name, _) in zip(arg_exprs, procedure.signature.params, strict=True):
        child_locals[param_name] = _resolve_inline_expr_value(arg_expr, local_values=local_values)
    child_context = _LoweringContext(
        workflow_name=context.workflow_name,
        step_name_prefix=_inline_procedure_step_prefix(
            context=context,
            callee_name=expr.callee_name,
            procedure=procedure,
            ordinal=prefix_ordinal,
        ),
        workflow_path=context.workflow_path,
        signature=context.signature,
        # An inline proc body evaluates derived-private-child hidden-context
        # eligibility against the proc's own signature, not the enclosing
        # caller being lowered — mirroring the proc-shaped active signature
        # procedure body typechecking activates (structural
        # private-exec-context / std/context contract,
        # docs/design/workflow_lisp_frontend_specification.md).
        procedure_hidden_context_signature=(
            procedure.signature
            if eligible_private_context_source_param_names(procedure.signature)
            else None
        ),
        authored_input_contracts=context.authored_input_contracts,
        workflow_catalog=context.workflow_catalog,
        imported_workflow_bundles=context.imported_workflow_bundles,
        extern_environment=context.extern_environment,
        command_boundary_environment=context.command_boundary_environment,
        lowered_callees=context.lowered_callees,
        typed_procedures=context.typed_procedures,
        workflows_by_name=context.workflows_by_name,
        ensure_workflow_lowered=context.ensure_workflow_lowered,
        specialize_workflow=context.specialize_workflow,
        type_env=_procedure_type_env_for(
            procedure,
            procedure_type_envs=context.procedure_type_envs,
            default=context.type_env,
        ),
        generated_private_workflow_type_envs=context.generated_private_workflow_type_envs,
        step_spans=context.step_spans,
        generated_input_spans=context.generated_input_spans,
        authored_generated_inputs=context.authored_generated_inputs,
        internal_generated_input_reasons=context.internal_generated_input_reasons,
        internal_generated_input_contracts=context.internal_generated_input_contracts,
        private_exec_context_bindings=context.private_exec_context_bindings,
        generated_output_spans=context.generated_output_spans,
        generated_path_spans=context.generated_path_spans,
        generated_path_allocations=context.generated_path_allocations,
        generated_semantic_effects=context.generated_semantic_effects,
        generated_contract_field_bindings=context.generated_contract_field_bindings,
        output_projection_metadata=context.output_projection_metadata,
        top_level_artifacts=context.top_level_artifacts,
        inline_call_counters=context.inline_call_counters,
        origin_notes=procedure_notes,
        boundary_projection=context.boundary_projection,
        return_output_contracts=context.return_output_contracts,
        local_type_bindings={
            **context.local_type_bindings,
            **_procedure_signature_local_type_bindings(procedure),
        },
        is_generated_private_workflow=context.is_generated_private_workflow,
        phase_scope=context.phase_scope,
        iteration_scope=context.iteration_scope,
        lowering_schema_version=context.lowering_schema_version,
        procedure_type_envs=context.procedure_type_envs,
        active_procedure_calls=context.active_procedure_calls | {procedure.signature.name},
        lower_expression=context.lower_expression,
        lower_call_expr=context.lower_call_expr,
        record_step_origin=context.record_step_origin,
        normalize_generated_step_id=context.normalize_generated_step_id,
    )
    steps, terminal = _lower_expression(procedure.typed_body, context=child_context, local_values=child_locals)
    _rewrite_nested_sibling_step_refs(steps)
    return _runtime_erasure_checked(steps, terminal, plan=plan)


def _private_workflow_from_procedure(procedure: TypedProcedureDef) -> TypedWorkflowDef:
    """Synthesize a typed private workflow wrapper for a procedure body."""

    assert procedure.generated_workflow_name is not None
    assert isinstance(procedure.signature.return_type_ref, (RecordTypeRef, UnionTypeRef))
    definition = WorkflowDef(
        name=procedure.generated_workflow_name,
        params=tuple(
            WorkflowParam(
                name=param.name,
                type_name=param.type_name,
                span=param.span,
                form_path=param.form_path,
                expansion_stack=param.expansion_stack,
            )
            for param in procedure.definition.params
        ),
        return_type_name=procedure.definition.return_type_name,
        body=procedure.definition.body,
        span=procedure.definition.span,
        form_path=procedure.definition.form_path,
        expansion_stack=procedure.definition.expansion_stack,
    )
    signature = WorkflowSignature(
        name=procedure.generated_workflow_name,
        params=procedure.signature.params,
        return_type_ref=procedure.signature.return_type_ref,
        span=procedure.signature.span,
        form_path=procedure.signature.form_path,
        param_defaults={},
    )
    return TypedWorkflowDef(
        definition=definition,
        signature=signature,
        typed_body=procedure.typed_body,
        effect_summary=procedure.transitive_effect_summary,
        specialization=procedure.specialization,
    )


def _rewrite_nested_sibling_step_refs(steps: list[dict[str, Any]]) -> None:
    """Rewrite nested sibling refs to `self.steps.*` inside inline procedure fragments."""

    for step in steps:
        for nested_steps in _iter_nested_step_lists(step):
            _rewrite_step_list_refs_in_scope(nested_steps)


def _rewrite_step_list_refs_in_scope(steps: list[dict[str, Any]]) -> None:
    sibling_names = tuple(
        step_name
        for step in steps
        for step_name in (step.get("name"),)
        if isinstance(step_name, str)
    )
    for step in steps:
        rewritten_step = _rewrite_refs_in_sibling_scope(step, sibling_names)
        step.clear()
        step.update(rewritten_step)
        for nested_steps in _iter_nested_step_lists(step):
            _rewrite_step_list_refs_in_scope(nested_steps)


def _iter_nested_step_lists(step: Mapping[str, Any]) -> tuple[list[dict[str, Any]], ...]:
    nested: list[list[dict[str, Any]]] = []
    repeat_until = step.get("repeat_until")
    if isinstance(repeat_until, Mapping) and isinstance(repeat_until.get("steps"), list):
        nested.append(repeat_until["steps"])
    for branch_name in ("then", "else"):
        branch = step.get(branch_name)
        if isinstance(branch, Mapping) and isinstance(branch.get("steps"), list):
            nested.append(branch["steps"])
    match = step.get("match")
    if isinstance(match, Mapping):
        for case in (match.get("cases") or {}).values():
            if isinstance(case, Mapping) and isinstance(case.get("steps"), list):
                nested.append(case["steps"])
    return tuple(nested)


def _rewrite_refs_in_sibling_scope(value: Any, sibling_names: tuple[str, ...]) -> Any:
    if isinstance(value, MaterializeViewBindingReference):
        return replace(
            value,
            ref=_rewrite_refs_in_sibling_scope(value.ref, sibling_names),
        )
    if isinstance(value, str):
        for step_name in sibling_names:
            prefix = f"root.steps.{step_name}."
            if value.startswith(prefix):
                return "self.steps." + value.removeprefix("root.steps.")
        return value
    if isinstance(value, list):
        return [_rewrite_refs_in_sibling_scope(item, sibling_names) for item in value]
    if isinstance(value, Mapping):
        rewritten: dict[Any, Any] = {}
        for key, item in value.items():
            if key == "steps" and isinstance(item, list):
                rewritten[key] = item
                continue
            rewritten[key] = _rewrite_refs_in_sibling_scope(item, sibling_names)
        return rewritten
    return value


def _procedure_provenance_notes(
    expr: Any,
    procedure: TypedProcedureDef,
    *,
    typed_procedures: Mapping[str, TypedProcedureDef] | None = None,
) -> tuple[str, ...]:
    """Describe the source locations behind generated procedure code."""

    call = expr.span.start
    definition = procedure.definition.span.start
    notes = [
        f"procedure call site at {call.path}:{call.line}:{call.column}",
        f"procedure definition at {definition.path}:{definition.line}:{definition.column}",
    ]
    specialization = procedure.specialization
    notes.extend(
        _parametric_specialization_notes(
            procedure,
            typed_procedures=typed_procedures,
        )
    )
    if specialization is not None and (
        getattr(specialization, "proc_ref_bindings", {})
        or getattr(specialization, "value_bindings", {})
    ):
        notes.append(f"proc-ref specialization selected for `{procedure.signature.name}`")
        if getattr(specialization, "value_bindings", {}):
            notes.append("bind-proc keyword bindings were applied before lowering")
        if getattr(specialization, "proc_ref_bindings", {}):
            notes.append("proc-ref call bindings were specialized before lowering")
    generated_local = getattr(procedure.definition, "generated_local_procedure", None)
    if generated_local is not None:
        origin = generated_local.origin_span.start
        notes.append(
            f"let-proc `{generated_local.authored_local_name}` originated at {origin.path}:{origin.line}:{origin.column}"
        )
        params = ", ".join(
            f"{name}: {type_name}" for name, type_name in generated_local.residual_params
        ) or "()"
        notes.append(
            f"let-proc local signature: ({params}) -> {generated_local.return_type_name}"
        )
        if generated_local.capture_names:
            notes.append(
                "let-proc captures lowered through bind-proc: "
                + ", ".join(generated_local.capture_names)
            )
        for span in generated_local.consumer_proc_ref_spans:
            start = span.start
            notes.append(
                f"consuming (proc-ref {generated_local.authored_local_name}) site at {start.path}:{start.line}:{start.column}"
            )
    return tuple(notes)


def _parametric_specialization_notes(
    procedure: TypedProcedureDef,
    *,
    typed_procedures: Mapping[str, TypedProcedureDef] | None,
    seen: frozenset[str] = frozenset(),
) -> tuple[str, ...]:
    specialization = procedure.specialization
    if specialization is None:
        return ()
    notes: list[str] = []
    if getattr(specialization, "type_bindings", {}):
        rendered_bindings = ", ".join(
            f"{name} = {render_type_ref(type_ref)}"
            for name, type_ref in sorted(specialization.type_bindings.items())
        )
        notes.append(f"parametric specialization selected for `{specialization.base_name}`")
        notes.append(f"parametric type bindings: {rendered_bindings}")
    base_name = getattr(specialization, "base_name", None)
    if (
        typed_procedures is not None
        and isinstance(base_name, str)
        and base_name not in seen
        and base_name in typed_procedures
    ):
        notes.extend(
            _parametric_specialization_notes(
                typed_procedures[base_name],
                typed_procedures=typed_procedures,
                seen=seen | {base_name},
            )
    )
    return tuple(notes)


def _merge_origin_notes(existing: tuple[str, ...], new: tuple[str, ...]) -> tuple[str, ...]:
    merged: list[str] = []
    for note in (*existing, *new):
        if note not in merged:
            merged.append(note)
    return tuple(merged)


def _assert_runtime_erasure(value: Any, *, span: SourceSpan, form_path: tuple[str, ...]) -> None:
    if isinstance(value, _COMPILE_TIME_ONLY_RUNTIME_TYPES):
        raise LispFrontendCompileError(
            (
                LispFrontendDiagnostic(
                    code="proc_runtime_erasure_failed",
                    message=(
                        f"compile-time-only `{type(value).__name__}` escaped into procedure lowering output"
                    ),
                    span=span,
                    form_path=form_path,
                ),
            )
        )
    if isinstance(value, Mapping):
        for key, item in value.items():
            _assert_runtime_erasure(key, span=span, form_path=form_path)
            _assert_runtime_erasure(item, span=span, form_path=form_path)
        return
    if isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            _assert_runtime_erasure(item, span=span, form_path=form_path)
