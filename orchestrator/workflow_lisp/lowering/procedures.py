"""Procedure lowering ownership for Workflow Lisp."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any

from orchestrator.workflow.references import MaterializeViewBindingReference

from ..diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from ..expressions import (
    NameExpr,
    ProcRefLiteralExpr,
    ProcedureCallExpr,
    WorkflowRefLiteralExpr,
)
from ..phase import eligible_private_context_source_param_names
from ..procedure_refs import ResolvedProcRefValue
from ..procedures import (
    LowerableProcedureCall,
    ProcedureLoweringMode,
    TypedProcedureDef,
    _procedure_signature_local_type_bindings,
    effective_private_workflow_name,
    procedure_type_env_for,
)
from ..spans import SourceSpan
from ..syntax import target_dsl_supports_provider_context_values
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


def _validate_resolved_procedure_mapping(
    typed_procedures: tuple[TypedProcedureDef, ...],
    resolved_procedures_by_name: Mapping[str, TypedProcedureDef] | None,
) -> Mapping[str, TypedProcedureDef]:
    """Require the exact immutable Stage-3 procedure decision mapping."""

    mapping_proxy_type = type(MappingProxyType({}))
    if not typed_procedures:
        if resolved_procedures_by_name is None:
            return MappingProxyType({})
        if not isinstance(resolved_procedures_by_name, mapping_proxy_type):
            raise TypeError("resolved procedure mapping must be immutable")
        if resolved_procedures_by_name:
            offending = next(iter(resolved_procedures_by_name.values()))
            if not isinstance(offending, TypedProcedureDef):
                raise TypeError("resolved procedure mapping contains a non-procedure row")
            from .context import _compile_error

            raise _compile_error(
                code="procedure_lowering_unresolved",
                message="resolved procedure mapping contains rows absent from the typed tuple",
                span=offending.definition.span,
                form_path=offending.definition.form_path,
            )
        return resolved_procedures_by_name

    first = typed_procedures[0]
    reason: str | None = None
    if resolved_procedures_by_name is None:
        reason = "compiler-owned resolved procedure mapping is required"
    elif not isinstance(resolved_procedures_by_name, mapping_proxy_type):
        reason = "resolved procedure mapping must be immutable"
    elif tuple(resolved_procedures_by_name) != tuple(
        procedure.definition.name for procedure in typed_procedures
    ):
        reason = "resolved procedure mapping order or membership differs from the typed tuple"
    else:
        for procedure in typed_procedures:
            mapped = resolved_procedures_by_name.get(procedure.definition.name)
            if mapped is not procedure:
                reason = f"resolved procedure row differs for `{procedure.definition.name}`"
                break
            if procedure.resolved_lowering_mode is ProcedureLoweringMode.AUTO:
                reason = f"procedure `{procedure.definition.name}` has unresolved lowering mode"
                break
            if (
                procedure.resolved_lowering_mode is ProcedureLoweringMode.PRIVATE_WORKFLOW
                and not procedure.generated_workflow_name
            ):
                reason = (
                    f"private-workflow procedure `{procedure.definition.name}` "
                    "lacks a generated workflow name"
                )
                break
            if (
                procedure.resolved_lowering_mode is ProcedureLoweringMode.INLINE
                and procedure.generated_workflow_name is not None
            ):
                reason = (
                    f"inline procedure `{procedure.definition.name}` has a generated workflow name"
                )
                break

    if reason is not None:
        from .context import _compile_error

        raise _compile_error(
            code="procedure_lowering_unresolved",
            message=reason,
            span=first.definition.span,
            form_path=first.definition.form_path,
        )
    assert resolved_procedures_by_name is not None
    return resolved_procedures_by_name


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


def _schema1_iteration_private_override_applies(
    procedure: TypedProcedureDef,
    *,
    context: Any,
) -> bool:
    """Expose the legacy call-local override as an observable boolean decision."""

    from orchestrator.workflow_lisp.procedure_specialization import (
        schema1_iteration_private_override_applies,
    )

    return schema1_iteration_private_override_applies(
        procedure,
        iteration_scope=context.iteration_scope,
        workflow_name=context.workflow_name,
        default_type_env=context.type_env,
        typed_procedures=context.typed_procedures,
        procedure_type_envs=context.procedure_type_envs,
        workflow_signatures=context.workflow_catalog.signatures_by_name,
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

    from .context import _LoweringContext, _TerminalResult
    from .origins import _record_step_origin
    from .core import (
        _compile_error,
        _inline_output_refs_for_expr,
        _inline_procedure_step_prefix,
        _lower_expression,
        _normalize_generated_step_id,
        _render_call_binding_ref,
        _render_record_call_bindings,
    )
    from orchestrator.workflow_lisp.procedure_specialization import (
        _flatten_boundary_leaf_paths,
        _resolve_inline_expr_value,
    )
    from .workflow_calls import (
        _carry_callee_private_exec_context_bindings,
        _carry_callee_runtime_context_inputs,
        _lower_pure_call_binding_if_eligible,
        _managed_write_root_binding_step,
        _managed_write_root_requirements_for_callable,
        _render_callee_private_exec_context_call_bindings,
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
    from orchestrator.workflow_lisp.procedure_specialization import (
        select_surface_procedure_call,
        inline_procedure_bindings,
    )

    procedure, arg_exprs = select_surface_procedure_call(
        expr, local_values=local_values, typed_procedures=context.typed_procedures,
        procedure_catalog=getattr(context, "procedure_catalog", None),
        workflow_catalog=context.workflow_catalog, typed_workflows=context.workflows_by_name,
    )
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
    if _schema1_iteration_private_override_applies(procedure, context=context):
        resolved_lowering_mode = ProcedureLoweringMode.PRIVATE_WORKFLOW
        generated_workflow_name = effective_private_workflow_name(procedure)
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
        projection_binding_steps: list[dict[str, Any]] = []
        for arg_expr, (param_name, param_type) in zip(arg_exprs, procedure.signature.params, strict=True):
            if isinstance(param_type, RecordTypeRef):
                try:
                    with_bindings.update(
                        _render_record_call_bindings(
                            param_name,
                            param_type,
                            arg_expr,
                            local_values=local_values,
                        )
                    )
                except LispFrontendCompileError as exc:
                    lowered = _lower_pure_call_binding_if_eligible(
                        exc,
                        expr=arg_expr,
                        binding_name=param_name,
                        binding_type=param_type,
                        call_step_name=step_name,
                        context=context,
                        local_values=local_values,
                        allow_mapping=target_dsl_supports_provider_context_values(
                            context.type_env.target_dsl_version
                        ),
                    )
                    if lowered is None:
                        raise
                    projection_binding_steps.append(lowered.step)
                    with_bindings.update(
                        {
                            output_name: {"ref": output_ref}
                            for output_name, output_ref in lowered.output_refs.items()
                        }
                    )
            else:
                with_bindings[param_name] = _render_call_binding_ref(arg_expr, local_values=local_values)
        # The synthesized private workflow inherits the body's omitted-phase-ctx
        # calls, which ordinary workflow lowering bridges as generated internal
        # inputs (`phase-ctx__*` leaves, e.g. `phase-ctx__plan__run__run-id`);
        # thread them here through the same three bridge-input helpers an
        # ordinary workflow call step uses, with the promoted call's own args
        # as the authored source bindings (structural private-exec-context /
        # std/context contract,
        # docs/design/workflow_lisp_frontend_specification.md).
        call_arg_bindings = {
            param_name: arg_expr
            for arg_expr, (param_name, _) in zip(arg_exprs, procedure.signature.params, strict=True)
        }
        with_bindings.update(
            {
                name: value
                for name, value in _render_callee_private_exec_context_call_bindings(
                    lowered_callee=callee,
                    imported_bundle=None,
                    authored_bindings=call_arg_bindings,
                    local_values=local_values,
                ).items()
                if name not in with_bindings
            }
        )
        with_bindings.update(
            _carry_callee_private_exec_context_bindings(
                context=context,
                source_expr=expr,
                lowered_callee=callee,
                imported_bundle=None,
                already_bound=set(with_bindings),
            )
        )
        with_bindings.update(
            _carry_callee_runtime_context_inputs(
                context=context,
                source_expr=expr,
                lowered_callee=callee,
                imported_bundle=None,
                already_bound=set(with_bindings),
            )
        )
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
            [
                *projection_binding_steps,
                *binding_steps,
                {
                    "name": step_name,
                    "id": step_id,
                    "call": procedure.generated_workflow_name,
                    "with": with_bindings,
                },
            ],
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
    child_locals = inline_procedure_bindings(
        procedure, caller_values=local_values, actual_values=tuple(
            _resolve_inline_expr_value(arg, local_values=local_values) for arg in arg_exprs
        ),
    )
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
        output_target_dsl_version=context.output_target_dsl_version,
        lowering_session=context.lowering_session,
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
            compiler_prompt_dependency_contracts=(
                context.compiler_prompt_dependency_contracts
            ),
            prompt_dependency_lineages=context.prompt_dependency_lineages,
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
        effect_boundary_observer=context.effect_boundary_observer,
        lower_expression=context.lower_expression,
        lower_call_expr=context.lower_call_expr,
        record_step_origin=context.record_step_origin,
        normalize_generated_step_id=context.normalize_generated_step_id,
        source_read_trace=context.source_read_trace,
    )
    output_refs = (
        _inline_output_refs_for_expr(
            procedure.typed_body.expr,
            type_ref=procedure.typed_body.type_ref,
            local_values=child_locals,
            context=child_context,
        )
        if isinstance(procedure.typed_body.expr, NameExpr)
        and not isinstance(
            procedure.typed_body.type_ref,
            (RecordTypeRef, UnionTypeRef),
        )
        else None
    )
    if output_refs is not None:
        steps, terminal = [], _TerminalResult(
            step_name=child_context.step_name_prefix,
            step_id=child_context.normalize_generated_step_id(
                child_context.step_name_prefix
            ),
            output_refs=output_refs,
            output_kind="projection",
            hidden_inputs={},
        )
    else:
        steps, terminal = _lower_expression(
            procedure.typed_body,
            context=child_context,
            local_values=child_locals,
        )
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
        return_spec=procedure.definition.return_spec,
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
    from .values import (
        rewrite_typed_union_projection_references,
        rewrite_typed_union_prompt_source_references,
    )

    def rewrite(ref: str) -> str:
        for step_name in sibling_names:
            prefix = f"root.steps.{step_name}."
            if ref.startswith(prefix):
                return "self.steps." + ref.removeprefix("root.steps.")
        return ref

    protected = rewrite_typed_union_projection_references(value, rewrite)
    if protected is not None:
        return protected
    if isinstance(value, MaterializeViewBindingReference):
        return replace(
            value,
            ref=_rewrite_refs_in_sibling_scope(value.ref, sibling_names),
        )
    if isinstance(value, str):
        return rewrite(value)
    if isinstance(value, list):
        return [_rewrite_refs_in_sibling_scope(item, sibling_names) for item in value]
    if isinstance(value, Mapping):
        rewritten: dict[Any, Any] = {}
        for key, item in value.items():
            if key == "__typed_union_prompt_source__":
                rewritten[key] = rewrite_typed_union_prompt_source_references(item, rewrite)
                continue
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
