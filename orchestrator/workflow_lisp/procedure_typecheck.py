"""Procedure typing ownership for Workflow Lisp."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from .definitions import SyntaxNode
from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .effects import (
    EMPTY_EFFECT_SUMMARY,
    EffectSummary,
    ProcedureCallEdge,
    effect_summary_from_direct,
    merge_effect_summaries,
)
from .expressions import ProcedureCallExpr
from .phase_stdlib import (
    DEFAULT_REVIEW_LOOP_LEGACY_BRIDGE_POLICY,
    ReviewLoopLegacyBridgePolicy,
)
from .procedures import ProcedureCatalog, ProcedureDef, TypedProcedureDef, proc_ref_specialization_name
from .procedure_refs import ResolvedProcRefValue
from .type_env import FrontendTypeEnvironment, ProcRefTypeRef, TypeRef, WorkflowRefTypeRef


@dataclass(frozen=True)
class ProcedureTypecheckContext:
    """Internal procedure-typing seam for generated helpers and procedure calls."""

    value_env: Mapping[str, TypeRef]
    workflow_catalog: object | None
    procedure_catalog: ProcedureCatalog | None
    extern_environment: object | None
    command_boundary_environment: object | None
    procedure_effects_by_name: Mapping[str, EffectSummary]
    workflow_effects_by_name: Mapping[str, EffectSummary]
    proc_ref_resolution_context: object | None
    active_proc_ref_value_env: Mapping[str, ResolvedProcRefValue]
    generated_local_procedure_state: object | None = None


def typecheck_procedure_definitions(
    procedure_defs: tuple[ProcedureDef | TypedProcedureDef, ...],
    *,
    type_env: FrontendTypeEnvironment,
    workflow_catalog: object,
    procedure_catalog: ProcedureCatalog,
    function_catalog=None,
    extern_environment: object,
    command_boundary_environment: object,
    procedure_effects_by_name: Mapping[str, EffectSummary] | None = None,
    workflow_effects_by_name: Mapping[str, EffectSummary] | None = None,
    function_name_resolver=None,
    procedure_name_resolver=None,
    workflow_name_resolver=None,
    proc_ref_resolution_context=None,
    review_loop_legacy_bridge_policy: ReviewLoopLegacyBridgePolicy = DEFAULT_REVIEW_LOOP_LEGACY_BRIDGE_POLICY,
) -> tuple[TypedProcedureDef, ...]:
    from .typecheck import typecheck_expression
    from .workflows import ExternEnvironment, ProviderExtern
    from .expressions import elaborate_expression

    externs = extern_environment or ExternEnvironment(bindings_by_name={})
    typed_procedures: list[TypedProcedureDef] = []
    for procedure_target in procedure_defs:
        if isinstance(procedure_target, TypedProcedureDef):
            procedure_def = procedure_target.definition
            signature = procedure_target.signature
            specialization = procedure_target.specialization
        else:
            procedure_def = procedure_target
            signature = procedure_catalog.signatures_by_name[procedure_def.name]
            specialization = None
        value_env = {name: type_ref for name, type_ref in signature.params}
        proc_ref_value_env = {}
        if specialization is not None:
            value_env.update(dict(getattr(specialization, "bound_param_types", {})))
            proc_ref_value_env.update(dict(getattr(specialization, "proc_ref_bindings", {})))
        for extern_name, binding in externs.bindings_by_name.items():
            if isinstance(binding, ProviderExtern):
                value_env[extern_name] = type_env.resolve_type(
                    "Provider",
                    span=procedure_def.span,
                    form_path=procedure_def.form_path,
                )
            else:
                value_env[extern_name] = type_env.resolve_type(
                    "Prompt",
                    span=procedure_def.span,
                    form_path=procedure_def.form_path,
                )
        if isinstance(procedure_def.body, SyntaxNode):
            body_expr = elaborate_expression(
                procedure_def.body,
                bound_names=frozenset(value_env),
                procedure_names=frozenset(procedure_catalog.signatures_by_name),
                function_names=(
                    frozenset()
                    if function_catalog is None
                    else frozenset(function_catalog.signatures_by_name)
                ),
                function_name_resolver=function_name_resolver,
                procedure_name_resolver=procedure_name_resolver,
                workflow_name_resolver=workflow_name_resolver,
                review_loop_legacy_bridge_policy=review_loop_legacy_bridge_policy,
            )
        else:
            body_expr = procedure_def.body
        typed_body = typecheck_expression(
            body_expr,
            type_env=type_env,
            value_env=value_env,
            workflow_catalog=workflow_catalog,
            procedure_catalog=procedure_catalog,
            function_catalog=function_catalog,
            extern_environment=externs,
            command_boundary_environment=command_boundary_environment,
            procedure_effects_by_name=procedure_effects_by_name,
            workflow_effects_by_name=workflow_effects_by_name,
            proc_ref_resolution_context=proc_ref_resolution_context,
            proc_ref_value_env=proc_ref_value_env,
            review_loop_legacy_bridge_policy=review_loop_legacy_bridge_policy,
        )
        if typed_body.type_ref != signature.return_type_ref:
            raise LispFrontendCompileError(
                (
                    LispFrontendDiagnostic(
                        code="procedure_return_type_invalid",
                        message=(
                            f"procedure `{procedure_def.name}` declared return type "
                            f"`{procedure_def.return_type_name}` but body returned a different type"
                        ),
                        span=procedure_def.body.span,
                        form_path=procedure_def.body.form_path,
                        expansion_stack=procedure_def.body.expansion_stack,
                    ),
                )
            )
        typed_procedures.append(
            TypedProcedureDef(
                definition=procedure_def,
                signature=signature,
                typed_body=typed_body,
                direct_effect_summary=typed_body.effect_summary,
                transitive_effect_summary=typed_body.effect_summary,
                specialization=specialization,
            )
        )
    return tuple(typed_procedures)


def typecheck_procedure_call_expr(
    expr: ProcedureCallExpr,
    *,
    context: ProcedureTypecheckContext,
    recurse: Callable[[object], object],
    typecheck_workflow_ref_argument: Callable[[object, WorkflowRefTypeRef], object],
    typecheck_proc_ref_argument: Callable[[object, ProcRefTypeRef], tuple[object, ResolvedProcRefValue | None]],
    typed_factory: Callable[..., object],
    raise_error: Callable[..., None],
    type_label: Callable[[TypeRef], str],
) -> object:
    if context.procedure_catalog is None:
        raise TypeError("procedure_catalog is required for ProcedureCallExpr typechecking")
    bound_proc_ref = context.active_proc_ref_value_env.get(expr.callee_name)
    if bound_proc_ref is not None:
        if len(expr.args) != len(bound_proc_ref.residual_params):
            raise_error(
                f"procedure `{expr.callee_name}` expected {len(bound_proc_ref.residual_params)} positional arguments but got {len(expr.args)}",
                code="procedure_arity_mismatch",
                span=expr.span,
                form_path=expr.form_path,
            )
        arg_summaries: list[EffectSummary] = []
        for arg_expr, (param_name, expected_type) in zip(expr.args, bound_proc_ref.residual_params, strict=True):
            typed_arg = recurse(arg_expr)
            arg_summaries.append(typed_arg.effect_summary)
            if typed_arg.type_ref != expected_type:
                raise_error(
                    f"procedure argument `{param_name}` expected `{type_label(expected_type)}`"
                    f" but got `{type_label(typed_arg.type_ref)}`",
                    code="type_mismatch",
                    span=arg_expr.span,
                    form_path=arg_expr.form_path,
                )
        callee_summary = context.procedure_effects_by_name.get(bound_proc_ref.call_target_name, EMPTY_EFFECT_SUMMARY)
        procedure_summary = effect_summary_from_direct(
            direct_effects=callee_summary.transitive_effects,
            procedure_edges=(
                ProcedureCallEdge(
                    callee_name=bound_proc_ref.call_target_name,
                    span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
            ),
        )
        return typed_factory(
            expr=expr,
            type_ref=bound_proc_ref.return_type_ref,
            effect=merge_effect_summaries(*arg_summaries, procedure_summary),
        )
    generic_proc_ref_type = context.value_env.get(expr.callee_name)
    if isinstance(generic_proc_ref_type, ProcRefTypeRef):
        if len(expr.args) != len(generic_proc_ref_type.param_type_refs):
            raise_error(
                f"procedure `{expr.callee_name}` expected {len(generic_proc_ref_type.param_type_refs)} positional arguments but got {len(expr.args)}",
                code="procedure_arity_mismatch",
                span=expr.span,
                form_path=expr.form_path,
            )
        arg_summaries: list[EffectSummary] = []
        for arg_expr, expected_type in zip(expr.args, generic_proc_ref_type.param_type_refs, strict=True):
            typed_arg = recurse(arg_expr)
            arg_summaries.append(typed_arg.effect_summary)
            if typed_arg.type_ref != expected_type:
                raise_error(
                    f"procedure argument expected `{type_label(expected_type)}`"
                    f" but got `{type_label(typed_arg.type_ref)}`",
                    code="type_mismatch",
                    span=arg_expr.span,
                    form_path=arg_expr.form_path,
                )
        return typed_factory(
            expr=expr,
            type_ref=generic_proc_ref_type.return_type_ref,
            effect=merge_effect_summaries(*arg_summaries),
        )
    signature = context.procedure_catalog.signatures_by_name.get(expr.callee_name)
    if signature is None:
        if expr.callee_name in context.value_env:
            raise_error(
                f"bound name `{expr.callee_name}` is not a callable proc-ref",
                code="procedure_call_unknown",
                span=expr.span,
                form_path=expr.form_path,
            )
        raise_error(
            f"unknown procedure callee `{expr.callee_name}`",
            code="procedure_call_unknown",
            span=expr.span,
            form_path=expr.form_path,
        )
    if len(expr.args) != len(signature.params):
        raise_error(
            f"procedure `{expr.callee_name}` expected {len(signature.params)} positional arguments but got {len(expr.args)}",
            code="procedure_arity_mismatch",
            span=expr.span,
            form_path=expr.form_path,
        )
    arg_summaries: list[EffectSummary] = []
    proc_ref_bindings: dict[str, ResolvedProcRefValue] = {}
    for arg_expr, (param_name, expected_type) in zip(expr.args, signature.params, strict=True):
        if isinstance(expected_type, WorkflowRefTypeRef):
            typed_arg = typecheck_workflow_ref_argument(arg_expr, expected_type)
            arg_summaries.append(typed_arg.effect_summary)
            if typed_arg.type_ref != expected_type:
                raise_error(
                    f"workflow ref argument `{param_name}` does not match `{expected_type.name}`",
                    code="workflow_ref_signature_invalid",
                    span=arg_expr.span,
                    form_path=arg_expr.form_path,
                )
            continue
        if isinstance(expected_type, ProcRefTypeRef):
            typed_arg, resolved_proc_ref = typecheck_proc_ref_argument(arg_expr, expected_type)
            arg_summaries.append(typed_arg.effect_summary)
            if resolved_proc_ref is not None:
                proc_ref_bindings[param_name] = resolved_proc_ref
            if typed_arg.type_ref != expected_type:
                raise_error(
                    f"procedure ref argument `{param_name}` does not match `{expected_type.name}`",
                    code="proc_ref_signature_invalid",
                    span=arg_expr.span,
                    form_path=arg_expr.form_path,
                )
            continue
        typed_arg = recurse(arg_expr)
        arg_summaries.append(typed_arg.effect_summary)
        if typed_arg.type_ref != expected_type:
            raise_error(
                f"procedure argument `{param_name}` expected `{type_label(expected_type)}`"
                f" but got `{type_label(typed_arg.type_ref)}`",
                code="type_mismatch",
                span=arg_expr.span,
                form_path=arg_expr.form_path,
            )
    callee_name = (
        proc_ref_specialization_name(signature.name, proc_ref_bindings)
        if proc_ref_bindings
        else signature.name
    )
    callee_summary = context.procedure_effects_by_name.get(
        callee_name,
        context.procedure_effects_by_name.get(signature.name, EMPTY_EFFECT_SUMMARY),
    )
    procedure_summary = effect_summary_from_direct(
        direct_effects=callee_summary.transitive_effects,
        procedure_edges=(
            ProcedureCallEdge(
                callee_name=callee_name,
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            ),
        ),
    )
    return typed_factory(
        expr=expr,
        type_ref=signature.return_type_ref,
        effect=merge_effect_summaries(*arg_summaries, procedure_summary),
    )


def typecheck_generated_procedure(
    definition,
    signature,
    *,
    type_env: FrontendTypeEnvironment,
    context: ProcedureTypecheckContext,
) -> TypedProcedureDef:
    from .typecheck import typecheck_expression
    from .workflows import ProviderExtern

    local_value_env = {name: type_ref for name, type_ref in signature.params}
    if context.extern_environment is not None:
        for extern_name, binding in context.extern_environment.bindings_by_name.items():
            local_value_env[extern_name] = (
                type_env.resolve_type("Provider", span=definition.span, form_path=definition.form_path)
                if isinstance(binding, ProviderExtern)
                else type_env.resolve_type("Prompt", span=definition.span, form_path=definition.form_path)
            )
    typed_body = typecheck_expression(
        definition.body,
        type_env=type_env,
        value_env=local_value_env,
        workflow_catalog=context.workflow_catalog,
        procedure_catalog=context.procedure_catalog,
        extern_environment=context.extern_environment,
        command_boundary_environment=context.command_boundary_environment,
        procedure_effects_by_name=context.procedure_effects_by_name,
        workflow_effects_by_name=context.workflow_effects_by_name,
        proc_ref_resolution_context=context.proc_ref_resolution_context,
    )
    return TypedProcedureDef(
        definition=definition,
        signature=signature,
        typed_body=typed_body,
        direct_effect_summary=typed_body.effect_summary,
        transitive_effect_summary=typed_body.effect_summary,
        resolved_lowering_mode=signature.requested_lowering_mode,
    )
