"""Procedure typing ownership for Workflow Lisp."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace

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
from .procedures import (
    ProcedureCatalog,
    ProcedureDef,
    TypedProcedureDef,
    parametric_specialization_name,
    proc_ref_specialization_name,
)
from .procedure_refs import ResolvedProcRefValue, resolve_proc_ref_value
from .type_env import (
    FrontendTypeEnvironment,
    ProcRefTypeRef,
    TypeParamRef,
    TypeRef,
    WorkflowRefTypeRef,
    ensure_no_type_params,
    substitute_type_params,
)


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


@dataclass(frozen=True)
class PendingParametricProcedureSpecialization:
    """One inferred generic procedure specialization request from typechecking."""

    base_name: str
    specialized_name: str
    type_bindings: Mapping[str, TypeRef]
    proc_ref_bindings: Mapping[str, ResolvedProcRefValue]
    remaining_params: tuple[tuple[str, TypeRef], ...]
    origin_span: object
    origin_form_path: tuple[str, ...]


_ACTIVE_PARAMETRIC_SPECIALIZATION_REQUESTS: dict[str, PendingParametricProcedureSpecialization] = {}


def consume_parametric_specialization_requests() -> tuple[PendingParametricProcedureSpecialization, ...]:
    global _ACTIVE_PARAMETRIC_SPECIALIZATION_REQUESTS

    requests = tuple(_ACTIVE_PARAMETRIC_SPECIALIZATION_REQUESTS.values())
    _ACTIVE_PARAMETRIC_SPECIALIZATION_REQUESTS = {}
    return requests


def reset_parametric_specialization_requests() -> None:
    global _ACTIVE_PARAMETRIC_SPECIALIZATION_REQUESTS

    _ACTIVE_PARAMETRIC_SPECIALIZATION_REQUESTS = {}


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
    if signature.type_params:
        return _typecheck_parametric_procedure_call(
            expr,
            signature=signature,
            context=context,
            recurse=recurse,
            typed_factory=typed_factory,
            raise_error=raise_error,
            type_label=type_label,
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


def _typecheck_parametric_procedure_call(
    expr: ProcedureCallExpr,
    *,
    signature,
    context: ProcedureTypecheckContext,
    recurse: Callable[[object], object],
    typed_factory: Callable[..., object],
    raise_error: Callable[..., None],
    type_label: Callable[[TypeRef], str],
) -> object:
    if len(expr.args) != len(signature.params):
        raise_error(
            f"procedure `{expr.callee_name}` expected {len(signature.params)} positional arguments but got {len(expr.args)}",
            code="procedure_arity_mismatch",
            span=expr.span,
            form_path=expr.form_path,
        )
    type_bindings: dict[str, TypeRef] = {}
    arg_summaries: list[EffectSummary] = []

    for arg_expr, (param_name, expected_type) in zip(expr.args, signature.params, strict=True):
        typed_arg = recurse(arg_expr)
        arg_summaries.append(typed_arg.effect_summary)
        _infer_parametric_type_bindings(
            expected_type,
            typed_arg.type_ref,
            bindings=type_bindings,
            raise_error=raise_error,
            span=arg_expr.span,
            form_path=arg_expr.form_path,
        )
    unresolved = [type_param.name for type_param in signature.type_params if type_param.name not in type_bindings]
    if unresolved:
        raise_error(
            f"procedure `{expr.callee_name}` could not infer concrete bindings for type parameters {', '.join(unresolved)}",
            code="parametric_type_binding_unresolved",
            span=expr.span,
            form_path=expr.form_path,
        )

    concrete_bindings = all(not _type_ref_contains_type_param(bound_type) for bound_type in type_bindings.values())

    if not concrete_bindings:
        return typed_factory(
            expr=expr,
            type_ref=substitute_type_params(signature.return_type_ref, type_bindings),
            effect=merge_effect_summaries(*arg_summaries),
        )

    if signature.where_clauses:
        raise_error(
            f"procedure `{expr.callee_name}` uses `:where`, but structural parametric constraints are not implemented yet",
            code="unsupported_parametric_constraint_surface",
            span=expr.span,
            form_path=expr.form_path,
        )

    concrete_return_type = substitute_type_params(signature.return_type_ref, type_bindings)
    ensure_no_type_params(
        concrete_return_type,
        span=expr.span,
        form_path=expr.form_path,
    )

    remaining_params: list[tuple[str, TypeRef]] = []
    for param_name, param_type in signature.params:
        concrete_param_type = substitute_type_params(param_type, type_bindings)
        ensure_no_type_params(
            concrete_param_type,
            span=expr.span,
            form_path=expr.form_path,
        )
        remaining_params.append((param_name, concrete_param_type))

    specialized_name = parametric_specialization_name(signature.name, type_bindings)
    _ACTIVE_PARAMETRIC_SPECIALIZATION_REQUESTS[specialized_name] = PendingParametricProcedureSpecialization(
        base_name=signature.name,
        specialized_name=specialized_name,
        type_bindings=dict(type_bindings),
        proc_ref_bindings={},
        remaining_params=tuple(remaining_params),
        origin_span=expr.span,
        origin_form_path=expr.form_path,
    )
    callee_summary = context.procedure_effects_by_name.get(
        specialized_name,
        context.procedure_effects_by_name.get(signature.name, EMPTY_EFFECT_SUMMARY),
    )
    procedure_summary = effect_summary_from_direct(
        direct_effects=callee_summary.transitive_effects,
        procedure_edges=(
            ProcedureCallEdge(
                callee_name=specialized_name,
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            ),
        ),
    )
    return typed_factory(
        expr=replace(expr, callee_name=specialized_name),
        type_ref=concrete_return_type,
        effect=merge_effect_summaries(*arg_summaries, procedure_summary),
    )


def _infer_parametric_type_bindings(
    expected_type: TypeRef,
    actual_type: TypeRef,
    *,
    bindings: dict[str, TypeRef],
    raise_error: Callable[..., None],
    span,
    form_path,
) -> None:
    if isinstance(expected_type, TypeParamRef):
        bound = bindings.get(expected_type.name)
        if bound is None:
            bindings[expected_type.name] = actual_type
            return
        if bound != actual_type:
            raise_error(
                f"type parameter `{expected_type.name}` inferred multiple incompatible concrete types",
                code="parametric_type_binding_ambiguous",
                span=span,
                form_path=form_path,
            )
        return
    if type(expected_type) is not type(actual_type):
        raise_error(
            f"procedure argument expected `{type_label_for_inference(expected_type)}` but got `{type_label_for_inference(actual_type)}`",
            code="type_mismatch",
            span=span,
            form_path=form_path,
        )
    if isinstance(expected_type, ProcRefTypeRef):
        if len(expected_type.param_type_refs) != len(actual_type.param_type_refs):
            raise_error(
                "procedure ref argument arity does not match parametric signature",
                code="proc_ref_signature_invalid",
                span=span,
                form_path=form_path,
            )
        for expected_param, actual_param in zip(expected_type.param_type_refs, actual_type.param_type_refs, strict=True):
            _infer_parametric_type_bindings(
                expected_param,
                actual_param,
                bindings=bindings,
                raise_error=raise_error,
                span=span,
                form_path=form_path,
            )
        _infer_parametric_type_bindings(
            expected_type.return_type_ref,
            actual_type.return_type_ref,
            bindings=bindings,
            raise_error=raise_error,
            span=span,
            form_path=form_path,
        )
        return
    if isinstance(expected_type, WorkflowRefTypeRef):
        if len(expected_type.param_type_refs) != len(actual_type.param_type_refs):
            raise_error(
                "workflow ref argument arity does not match parametric signature",
                code="workflow_ref_signature_invalid",
                span=span,
                form_path=form_path,
            )
        for expected_param, actual_param in zip(expected_type.param_type_refs, actual_type.param_type_refs, strict=True):
            _infer_parametric_type_bindings(
                expected_param,
                actual_param,
                bindings=bindings,
                raise_error=raise_error,
                span=span,
                form_path=form_path,
            )
        _infer_parametric_type_bindings(
            expected_type.return_type_ref,
            actual_type.return_type_ref,
            bindings=bindings,
            raise_error=raise_error,
            span=span,
            form_path=form_path,
        )
        return
    if hasattr(expected_type, "item_type_ref") and hasattr(actual_type, "item_type_ref"):
        _infer_parametric_type_bindings(
            expected_type.item_type_ref,
            actual_type.item_type_ref,
            bindings=bindings,
            raise_error=raise_error,
            span=span,
            form_path=form_path,
        )
        return
    if hasattr(expected_type, "key_type_ref") and hasattr(actual_type, "key_type_ref"):
        _infer_parametric_type_bindings(
            expected_type.key_type_ref,
            actual_type.key_type_ref,
            bindings=bindings,
            raise_error=raise_error,
            span=span,
            form_path=form_path,
        )
        _infer_parametric_type_bindings(
            expected_type.value_type_ref,
            actual_type.value_type_ref,
            bindings=bindings,
            raise_error=raise_error,
            span=span,
            form_path=form_path,
        )
        return
    if expected_type != actual_type:
        raise_error(
            f"procedure argument expected `{type_label_for_inference(expected_type)}` but got `{type_label_for_inference(actual_type)}`",
            code="type_mismatch",
            span=span,
            form_path=form_path,
        )


def type_label_for_inference(type_ref: TypeRef) -> str:
    return getattr(type_ref, "name", type(type_ref).__name__)


def _type_ref_contains_type_param(type_ref: TypeRef) -> bool:
    if isinstance(type_ref, TypeParamRef):
        return True
    if hasattr(type_ref, "item_type_ref"):
        return _type_ref_contains_type_param(type_ref.item_type_ref)
    if hasattr(type_ref, "key_type_ref"):
        return _type_ref_contains_type_param(type_ref.key_type_ref) or _type_ref_contains_type_param(
            type_ref.value_type_ref
        )
    if isinstance(type_ref, ProcRefTypeRef):
        return any(_type_ref_contains_type_param(param) for param in type_ref.param_type_refs) or _type_ref_contains_type_param(
            type_ref.return_type_ref
        )
    if isinstance(type_ref, WorkflowRefTypeRef):
        return any(_type_ref_contains_type_param(param) for param in type_ref.param_type_refs) or _type_ref_contains_type_param(
            type_ref.return_type_ref
        )
    return False


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
