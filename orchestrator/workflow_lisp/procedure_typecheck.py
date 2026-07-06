"""Procedure typing ownership for Workflow Lisp."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields, is_dataclass, replace

from .definitions import RecordField, SyntaxNode, UnionDef, UnionVariant
from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .effects import (
    EMPTY_EFFECT_SUMMARY,
    EffectSummary,
    ProcedureCallEdge,
    effect_summary_from_direct,
    merge_effect_summaries,
)
from .parametric_constraints import evaluate_parametric_constraints, provisional_shared_union_field_capabilities
from .expressions import (
    BindProcBinding,
    BindProcExpr,
    ContinueExpr,
    DoneExpr,
    ExprNode,
    FieldAccessExpr,
    FunctionCallExpr,
    IfExpr,
    LetProcExpr,
    LetStarExpr,
    LiteralExpr,
    LoopRecurExpr,
    MatchExpr,
    NameExpr,
    ProcRefLiteralExpr,
    ProcedureCallExpr,
    RecordExpr,
    ResumeOrStartExpr,
    WithPhaseExpr,
    elaborate_expression,
)
from .procedures import (
    GeneratedLocalProcedure,
    ProcedureCatalog,
    ProcedureDef,
    ProcedureLoweringMode,
    ProcedureParam,
    ProcedureSignature,
    TypedProcedureDef,
    let_proc_generated_name,
    parametric_specialization_name,
    proc_ref_specialization_name,
    procedure_type_env_for,
)
from .procedure_refs import (
    BoundProcArg,
    ProcRefAuthoritySource,
    ResolvedProcRefValue,
    resolve_proc_ref_value,
)
from .type_env import (
    FrontendTypeEnvironment,
    ProcRefTypeRef,
    TypeParamRef,
    TypeRef,
    UnionTypeRef,
    WorkflowRefTypeRef,
    ensure_no_type_params,
    substitute_type_params,
    type_refs_compatible,
)
from .typecheck_context import get_session_state, raise_error as _raise_error


@dataclass(frozen=True)
class ProcedureTypecheckContext:
    """Internal procedure-typing seam for generated helpers and procedure calls."""

    type_env: FrontendTypeEnvironment
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
    session_state: object | None = None


@dataclass(frozen=True)
class PendingParametricProcedureSpecialization:
    """One inferred generic procedure specialization request from typechecking."""

    base_name: str
    specialized_name: str
    type_bindings: Mapping[str, TypeRef]
    proc_ref_bindings: Mapping[str, ResolvedProcRefValue]
    shared_union_field_capabilities: tuple[object, ...]
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
    procedure_type_envs: Mapping[str, FrontendTypeEnvironment] | None = None,
) -> tuple[TypedProcedureDef, ...]:
    from .typecheck import typecheck_expression
    from .workflows import ExternEnvironment, ProviderExtern
    from .expressions import elaborate_expression

    externs = extern_environment or ExternEnvironment(bindings_by_name={})
    typed_procedures: list[TypedProcedureDef] = []
    for procedure_target in procedure_defs:
        current_type_env = (
            procedure_type_env_for(
                procedure_target,
                procedure_type_envs=procedure_type_envs,
                default=type_env,
            )
            if isinstance(procedure_target, TypedProcedureDef)
            else type_env
        )
        if isinstance(procedure_target, TypedProcedureDef):
            procedure_def = procedure_target.definition
            signature = procedure_target.signature
            specialization = procedure_target.specialization
        else:
            procedure_def = procedure_target
            signature = procedure_catalog.signatures_by_name[procedure_def.name]
            specialization = None
        if isinstance(procedure_target, TypedProcedureDef):
            from .loop_state import register_all_known_carrier_types

            register_all_known_carrier_types(
                current_type_env,
                span=procedure_def.span,
                form_path=procedure_def.form_path,
            )
        provisional_match_types = _provisional_parametric_match_types(
            signature=signature,
            type_env=current_type_env,
        )
        value_env = {
            name: _apply_provisional_parametric_type(type_ref, provisional_match_types)
            for name, type_ref in signature.params
        }
        proc_ref_value_env = {}
        shared_union_field_capabilities = provisional_shared_union_field_capabilities(
            where_clauses=signature.where_clauses,
            type_env=current_type_env,
            type_param_names=frozenset(type_param.name for type_param in signature.type_params),
        )
        value_env.update(
            {
                type_param.name: provisional_match_types.get(
                    type_param.name,
                    TypeParamRef(name=type_param.name),
                )
                for type_param in signature.type_params
            }
        )
        if specialization is not None:
            value_env.update(dict(getattr(specialization, "type_bindings", {})))
            value_env.update(dict(getattr(specialization, "bound_param_types", {})))
            proc_ref_value_env.update(dict(getattr(specialization, "proc_ref_bindings", {})))
            shared_union_field_capabilities = tuple(
                getattr(specialization, "shared_union_field_capabilities", ())
            ) or shared_union_field_capabilities
        for extern_name, binding in externs.bindings_by_name.items():
            if isinstance(binding, ProviderExtern):
                value_env[extern_name] = current_type_env.resolve_type(
                    "Provider",
                    span=procedure_def.span,
                    form_path=procedure_def.form_path,
                )
            else:
                value_env[extern_name] = current_type_env.resolve_type(
                    "Prompt",
                    span=procedure_def.span,
                    form_path=procedure_def.form_path,
                )
        if isinstance(procedure_target, TypedProcedureDef):
            body_expr = procedure_target.typed_body.expr
        elif isinstance(procedure_def.body, SyntaxNode):
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
            )
        else:
            body_expr = procedure_def.body
        typed_body = typecheck_expression(
            body_expr,
            type_env=current_type_env,
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
            shared_union_field_capabilities=shared_union_field_capabilities,
        )
        if not type_refs_compatible(signature.return_type_ref, typed_body.type_ref):
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


def _apply_provisional_parametric_type(
    type_ref: TypeRef,
    provisional_match_types: Mapping[str, UnionTypeRef],
) -> TypeRef:
    if isinstance(type_ref, TypeParamRef):
        return provisional_match_types.get(type_ref.name, type_ref)
    return type_ref


def _provisional_parametric_match_types(
    *,
    signature: ProcedureSignature,
    type_env: FrontendTypeEnvironment,
) -> dict[str, UnionTypeRef]:
    variants_by_type_param: dict[str, dict[str, UnionVariant]] = {}
    variant_fields_by_type_param: dict[str, dict[str, dict[str, TypeRef]]] = {}
    for clause in signature.where_clauses:
        if clause.constraint_name != "has-union-variant" or clause.variant_name is None:
            continue
        variants = variants_by_type_param.setdefault(clause.subject_name, {})
        variant_fields = variant_fields_by_type_param.setdefault(clause.subject_name, {})
        if clause.variant_name in variants:
            continue
        variants[clause.variant_name] = UnionVariant(
            name=clause.variant_name,
            fields=tuple(
                RecordField(
                    name=requirement.field_name,
                    type_name=requirement.field_type_name,
                    span=requirement.span,
                )
                for requirement in clause.field_requirements
            ),
            span=clause.span,
        )
        variant_fields[clause.variant_name] = {
            requirement.field_name: type_env.resolve_type(
                requirement.field_type_name,
                span=requirement.span,
                form_path=requirement.form_path,
                expansion_stack=requirement.expansion_stack,
            )
            for requirement in clause.field_requirements
        }
    return {
        type_param_name: UnionTypeRef(
            name=type_param_name,
            definition=UnionDef(
                name=type_param_name,
                variants=tuple(variants.values()),
                span=signature.span,
            ),
            variant_field_types=variant_fields_by_type_param[type_param_name],
        )
        for type_param_name, variants in variants_by_type_param.items()
        if variants
    }


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
            if not type_refs_compatible(expected_type, typed_arg.type_ref):
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
            if not type_refs_compatible(expected_type, typed_arg.type_ref):
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
            typecheck_workflow_ref_argument=typecheck_workflow_ref_argument,
            typecheck_proc_ref_argument=typecheck_proc_ref_argument,
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
            if not type_refs_compatible(expected_type, typed_arg.type_ref):
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
            if not type_refs_compatible(expected_type, typed_arg.type_ref):
                raise_error(
                    f"procedure ref argument `{param_name}` does not match `{expected_type.name}`",
                    code="proc_ref_signature_invalid",
                    span=arg_expr.span,
                    form_path=arg_expr.form_path,
                )
            continue
        typed_arg = recurse(arg_expr)
        arg_summaries.append(typed_arg.effect_summary)
        if not type_refs_compatible(expected_type, typed_arg.type_ref):
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
    typecheck_workflow_ref_argument: Callable[[object, WorkflowRefTypeRef], object],
    typecheck_proc_ref_argument: Callable[[object, ProcRefTypeRef], tuple[object, ResolvedProcRefValue | None]],
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
    typed_args: list[object] = []

    for arg_expr, (param_name, expected_type) in zip(expr.args, signature.params, strict=True):
        typed_arg = recurse(arg_expr)
        typed_args.append(typed_arg)
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

    proc_ref_bindings: dict[str, ResolvedProcRefValue] = {}
    for typed_arg, arg_expr, (param_name, expected_type) in zip(
        typed_args,
        expr.args,
        signature.params,
        strict=True,
    ):
        if isinstance(expected_type, WorkflowRefTypeRef):
            typecheck_workflow_ref_argument(
                arg_expr,
                substitute_type_params(expected_type, type_bindings),
            )
        elif isinstance(expected_type, ProcRefTypeRef):
            _, resolved_proc_ref = typecheck_proc_ref_argument(
                arg_expr,
                substitute_type_params(expected_type, type_bindings),
            )
            if resolved_proc_ref is not None:
                proc_ref_bindings[param_name] = resolved_proc_ref

    constraint_result = (
        evaluate_parametric_constraints(
            procedure_name=signature.name,
            where_clauses=signature.where_clauses,
            type_bindings=type_bindings,
            type_env=context.type_env,
            call_span=expr.span,
            call_form_path=expr.form_path,
            call_expansion_stack=expr.expansion_stack,
        )
        if signature.where_clauses
        else None
    )

    concrete_return_type = substitute_type_params(signature.return_type_ref, type_bindings)
    ensure_no_type_params(
        concrete_return_type,
        span=expr.span,
        form_path=expr.form_path,
    )

    remaining_params: list[tuple[str, TypeRef]] = []
    remaining_args: list[object] = []
    for arg_expr, (param_name, param_type) in zip(expr.args, signature.params, strict=True):
        concrete_param_type = substitute_type_params(param_type, type_bindings)
        if isinstance(param_type, ProcRefTypeRef) and param_name in proc_ref_bindings:
            continue
        ensure_no_type_params(
            concrete_param_type,
            span=expr.span,
            form_path=expr.form_path,
        )
        remaining_params.append((param_name, concrete_param_type))
        remaining_args.append(arg_expr)

    specialized_name = parametric_specialization_name(signature.name, type_bindings)
    if proc_ref_bindings:
        specialized_name = proc_ref_specialization_name(specialized_name, proc_ref_bindings)
    _ACTIVE_PARAMETRIC_SPECIALIZATION_REQUESTS[specialized_name] = PendingParametricProcedureSpecialization(
        base_name=signature.name,
        specialized_name=specialized_name,
        type_bindings=dict(type_bindings),
        proc_ref_bindings=dict(proc_ref_bindings),
        shared_union_field_capabilities=(
            ()
            if constraint_result is None
            else constraint_result.shared_union_field_capabilities
        ),
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
        expr=replace(expr, callee_name=specialized_name, args=tuple(remaining_args)),
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
        if not type_refs_compatible(bound, actual_type):
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
    if not type_refs_compatible(expected_type, actual_type):
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


def _typecheck_owner(*args, **kwargs):
    from .typecheck_dispatch import _typecheck

    return _typecheck(*args, **kwargs)


def _temporary_procedure_catalog_owner(*args, **kwargs):
    from .typecheck_dispatch import _temporary_procedure_catalog

    return _temporary_procedure_catalog(*args, **kwargs)


@dataclass(frozen=True)
class LocalProcRewriteBinding:
    """How one lexical `let-proc` name rewrites during typechecking."""

    generated_name: str
    capture_bindings: tuple[tuple[str, ExprNode], ...]
    allow_reference: bool


def typecheck_let_proc_expr(
    expr,
    *,
    context,
    recurse,
    typed_factory,
    raise_error,
    type_label,
):
    del recurse, typed_factory, raise_error, type_label
    return _typecheck_let_proc_expr_impl(
        expr,
        type_env=context.type_env,
        value_env=dict(context.value_env),
        proof_scope=context.proof_scope,
        workflow_catalog=context.workflow_catalog,
        procedure_catalog=context.procedure_catalog,
        extern_environment=context.extern_environment,
        command_boundary_environment=context.command_boundary_environment,
        active_phase_scope=context.active_phase_scope,
        procedure_effects_by_name=context.procedure_effects_by_name,
        workflow_effects_by_name=context.workflow_effects_by_name,
        proc_ref_resolution_context=context.proc_ref_resolution_context,
    )


def _typecheck_let_proc_expr_impl(
    expr: LetProcExpr,
    *,
    type_env: FrontendTypeEnvironment,
    value_env: dict[str, TypeRef],
    proof_scope: ProofScope,
    workflow_catalog: "WorkflowCatalog | None",
    procedure_catalog: ProcedureCatalog | None,
    extern_environment: "ExternEnvironment | None",
    command_boundary_environment: "CommandBoundaryEnvironment | None",
    active_phase_scope: PhaseScope | None,
    procedure_effects_by_name: Mapping[str, EffectSummary],
    workflow_effects_by_name: Mapping[str, EffectSummary],
    proc_ref_resolution_context: ProcRefResolutionContext | None,
) -> TypedExpr:
    session_state = get_session_state()

    if procedure_catalog is None:
        raise TypeError("procedure_catalog is required for let-proc expressions")

    if (
        expr.binding.local_name in value_env
        or expr.binding.local_name in procedure_catalog.signatures_by_name
    ):
        _raise_error(
            (
                f"`let-proc` local procedure `{expr.binding.local_name}` collides "
                "with an existing value or procedure binding"
            ),
            code="let_proc_name_collision",
            span=expr.binding.span,
            form_path=expr.binding.form_path,
            expansion_stack=expr.binding.expansion_stack,
        )

    capture_params: list[ProcedureParam] = []
    capture_signature_params: list[tuple[str, TypeRef]] = []
    bound_capture_args: list[BoundProcArg] = []
    capture_bindings: list[tuple[str, ExprNode]] = []
    local_proc_ref_env: dict[str, ResolvedProcRefValue] = {}
    seen_capture_names: set[str] = set()
    for capture_name in expr.binding.capture_names:
        capture_type = value_env.get(capture_name)
        if capture_type is None:
            _raise_error(
                f"unknown `let-proc` capture `{capture_name}`",
                code="let_proc_capture_unknown",
                span=expr.binding.span,
                form_path=expr.binding.form_path,
                expansion_stack=expr.binding.expansion_stack,
            )
        if capture_name in seen_capture_names:
            _raise_error(
                f"duplicate `let-proc` capture `{capture_name}`",
                code="let_proc_capture_duplicate",
                span=expr.binding.span,
                form_path=expr.binding.form_path,
                expansion_stack=expr.binding.expansion_stack,
            )
        seen_capture_names.add(capture_name)
        if any(param.name == capture_name for param in expr.binding.params):
            _raise_error(
                f"`let-proc` capture `{capture_name}` collides with a local parameter",
                code="let_proc_capture_duplicate",
                span=expr.binding.span,
                form_path=expr.binding.form_path,
                expansion_stack=expr.binding.expansion_stack,
            )
        capture_params.append(
            ProcedureParam(
                name=capture_name,
                type_name=capture_type.name,
                span=expr.binding.span,
                form_path=expr.binding.form_path,
                expansion_stack=expr.binding.expansion_stack,
            )
        )
        capture_signature_params.append((capture_name, capture_type))
        if isinstance(capture_type, ProcRefTypeRef):
            capture_value = session_state.proc_ref_value_env.get(capture_name)
            if capture_value is not None:
                local_proc_ref_env[capture_name] = capture_value
        capture_value_expr = session_state.value_expr_env.get(capture_name)
        if capture_value_expr is None:
            capture_value_expr = NameExpr(
                name=capture_name,
                span=expr.binding.span,
                form_path=expr.binding.form_path,
                expansion_stack=expr.binding.expansion_stack,
            )
        capture_bindings.append((capture_name, capture_value_expr))
        bound_capture_args.append(
            BoundProcArg(
                name=capture_name,
                value_expr=capture_value_expr,
                type_ref=capture_type,
                source_identity=_expr_source_identity(capture_value_expr),
                keyword_span=expr.binding.span,
                keyword_form_path=expr.binding.form_path,
                keyword_expansion_stack=expr.binding.expansion_stack,
            )
        )

    local_body_expr = _rewrite_local_proc_references(
        expr.binding.local_body,
        local_bindings={
            expr.binding.local_name: LocalProcRewriteBinding(
                generated_name="",
                capture_bindings=tuple(capture_bindings),
                allow_reference=False,
            ),
        },
    )
    generated_name = let_proc_generated_name(
        owner_callable_name=expr.form_path[-1],
        local_name=expr.binding.local_name,
        origin_span=expr.binding.span,
        param_type_names=tuple(
            [capture_type.name for _, capture_type in capture_signature_params]
            + [param.type_name for param in expr.binding.params]
        ),
        return_type_name=expr.binding.return_type_name,
        capture_names=expr.binding.capture_names,
        semantic_body_identity=_semantic_identity(local_body_expr),
    )
    generated_metadata = GeneratedLocalProcedure(
        authored_local_name=expr.binding.local_name,
        generated_name=generated_name,
        owner_callable_name=expr.form_path[-1],
        residual_params=tuple((param.name, param.type_name) for param in expr.binding.params),
        return_type_name=expr.binding.return_type_name,
        capture_names=expr.binding.capture_names,
        origin_span=expr.binding.span,
        consumer_proc_ref_spans=_collect_proc_ref_use_spans(
            expr.body,
            authored_name=expr.binding.local_name,
        ),
    )
    return_type_ref = type_env.resolve_type(
        expr.binding.return_type_name,
        span=expr.binding.span,
        form_path=expr.binding.form_path,
        expansion_stack=expr.binding.expansion_stack,
    )
    residual_signature_params = tuple(
        (
            param.name,
            type_env.resolve_type(
                param.type_name,
                span=param.span,
                form_path=param.form_path,
                expansion_stack=param.expansion_stack,
            ),
        )
        for param in expr.binding.params
    )
    generated_signature = ProcedureSignature(
        name=generated_name,
        params=tuple(capture_signature_params) + residual_signature_params,
        return_type_ref=return_type_ref,
        declared_effects=frozenset(),
        requested_lowering_mode=ProcedureLoweringMode.AUTO,
        span=expr.binding.span,
        form_path=expr.binding.form_path,
        type_params=(),
        where_clauses=(),
    )
    generated_definition = ProcedureDef(
        name=generated_name,
        params=tuple(capture_params) + expr.binding.params,
        return_type_name=expr.binding.return_type_name,
        declared_effects=frozenset(),
        requested_lowering_mode=generated_signature.requested_lowering_mode,
        body=expr.binding.local_body,
        span=expr.binding.span,
        form_path=expr.binding.form_path,
        expansion_stack=expr.binding.expansion_stack,
        type_params=(),
        where_clauses=(),
        generated_local_procedure=generated_metadata,
    )
    rewrite_binding = LocalProcRewriteBinding(
        generated_name=generated_name,
        capture_bindings=tuple(capture_bindings),
        allow_reference=True,
    )
    local_body_expr = _rewrite_local_proc_references(
        expr.binding.local_body,
        local_bindings={expr.binding.local_name: replace(rewrite_binding, allow_reference=False)},
    )
    outer_body_expr = _rewrite_local_proc_references(
        expr.body,
        local_bindings={expr.binding.local_name: rewrite_binding},
    )
    session_state.let_proc_rewrite_results[id(expr)] = outer_body_expr
    generated_catalog = _temporary_procedure_catalog_owner(
        procedure_catalog,
        definition=generated_definition,
        signature=generated_signature,
    )
    if _expr_returns_local_proc_value(
        outer_body_expr,
        generated_name,
        procedure_catalog=generated_catalog,
    ):
        _raise_error(
            f"`let-proc` local procedure `{expr.binding.local_name}` escaped its lexical scope",
            code="let_proc_scope_escape",
            span=expr.body.span,
            form_path=expr.body.form_path,
            expansion_stack=expr.body.expansion_stack,
        )

    local_value_env = {name: type_ref for name, type_ref in capture_signature_params}
    local_value_env.update(dict(residual_signature_params))
    previous_proc_ref_env = session_state.proc_ref_value_env
    session_state.proc_ref_value_env = local_proc_ref_env
    try:
        typed_local_body = _typecheck_owner(
            local_body_expr,
            type_env=type_env,
            value_env=local_value_env,
            proof_scope=proof_scope,
            workflow_catalog=workflow_catalog,
            procedure_catalog=generated_catalog,
            extern_environment=extern_environment,
            command_boundary_environment=command_boundary_environment,
            active_phase_scope=active_phase_scope,
            procedure_effects_by_name=procedure_effects_by_name,
            workflow_effects_by_name=workflow_effects_by_name,
            proc_ref_resolution_context=proc_ref_resolution_context,
        )
    finally:
        session_state.proc_ref_value_env = previous_proc_ref_env
    if not type_refs_compatible(return_type_ref, typed_local_body.type_ref):
        _raise_error(
            (
                f"`let-proc` local procedure `{expr.binding.local_name}` declared "
                f"`{expr.binding.return_type_name}` but returned `{getattr(typed_local_body.type_ref, 'name', type(typed_local_body.type_ref).__name__)}`"
            ),
            code="let_proc_return_type_invalid",
            span=expr.binding.local_body.span,
            form_path=expr.binding.local_body.form_path,
            expansion_stack=expr.binding.local_body.expansion_stack,
        )
    session_state.generated_local_procedures[generated_name] = TypedProcedureDef(
        definition=generated_definition,
        signature=generated_signature,
        typed_body=typed_local_body,
        direct_effect_summary=typed_local_body.effect_summary,
        transitive_effect_summary=typed_local_body.effect_summary,
    )

    bound_local_proc = ResolvedProcRefValue(
        procedure_name=generated_name,
        signature_params=generated_signature.params,
        return_type_ref=generated_signature.return_type_ref,
        authority_source=ProcRefAuthoritySource(
            kind="lexical_local_procedure",
            procedure_name=generated_name,
        ),
        bound_args=tuple(bound_capture_args),
    )
    outer_proc_ref_env = dict(session_state.proc_ref_value_env)
    outer_proc_ref_env[expr.binding.local_name] = bound_local_proc
    previous_proc_ref_env = session_state.proc_ref_value_env
    session_state.proc_ref_value_env = outer_proc_ref_env
    try:
        typed_outer_body = _typecheck_owner(
            outer_body_expr,
            type_env=type_env,
            value_env=value_env,
            proof_scope=proof_scope,
            workflow_catalog=workflow_catalog,
            procedure_catalog=generated_catalog,
            extern_environment=extern_environment,
            command_boundary_environment=command_boundary_environment,
            active_phase_scope=active_phase_scope,
            procedure_effects_by_name=procedure_effects_by_name,
            workflow_effects_by_name=workflow_effects_by_name,
            proc_ref_resolution_context=proc_ref_resolution_context,
        )
    finally:
        session_state.proc_ref_value_env = previous_proc_ref_env
    return replace(typed_outer_body, expr=outer_body_expr)


def _rewrite_local_proc_references(
    node: object,
    *,
    local_bindings: Mapping[str, LocalProcRewriteBinding],
):
    if isinstance(node, ProcRefLiteralExpr):
        binding = local_bindings.get(node.authored_name)
        if binding is None:
            return node
        if not binding.allow_reference:
            _raise_error(
                f"`let-proc` local procedure `{node.authored_name}` cannot reference itself",
                code="let_proc_recursive_unsupported",
                span=node.span,
                form_path=node.form_path,
                expansion_stack=node.expansion_stack,
            )
        return _bind_local_proc_reference(node, binding)
    if isinstance(node, LetProcExpr):
        return node
    if isinstance(node, tuple):
        return tuple(_rewrite_local_proc_references(item, local_bindings=local_bindings) for item in node)
    if isinstance(node, list):
        return [_rewrite_local_proc_references(item, local_bindings=local_bindings) for item in node]
    if is_dataclass(node):
        updates = {}
        for field in fields(node):
            current = getattr(node, field.name)
            rewritten = _rewrite_local_proc_references(current, local_bindings=local_bindings)
            if rewritten is not current:
                updates[field.name] = rewritten
        if updates:
            return replace(node, **updates)
    return node

def _bind_local_proc_reference(
    expr: ProcRefLiteralExpr,
    binding: LocalProcRewriteBinding,
) -> ExprNode:
    base_expr = ProcRefLiteralExpr(
        target_name=binding.generated_name,
        authored_name=expr.authored_name,
        span=expr.span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    if not binding.capture_bindings:
        return base_expr
    return BindProcExpr(
        base_expr=base_expr,
        bindings=tuple(
            BindProcBinding(
                name=capture_name,
                value_expr=capture_expr,
                keyword_span=expr.span,
                keyword_form_path=expr.form_path,
                keyword_expansion_stack=expr.expansion_stack,
            )
            for capture_name, capture_expr in binding.capture_bindings
        ),
        span=expr.span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )

def _expr_returns_local_proc_value(
    expr: ExprNode,
    generated_name: str,
    *,
    value_bindings: Mapping[str, bool] | None = None,
    procedure_catalog: ProcedureCatalog | None = None,
    proc_ref_env: Mapping[str, ResolvedProcRefValue] | None = None,
    visited_calls: frozenset[tuple[str, frozenset[str]]] = frozenset(),
) -> bool:
    bindings = dict(value_bindings or {})
    active_proc_ref_env = dict(proc_ref_env or {})
    if isinstance(expr, ProcRefLiteralExpr):
        return expr.target_name == generated_name
    if isinstance(expr, BindProcExpr):
        if _expr_returns_local_proc_value(
            expr.base_expr,
            generated_name,
            value_bindings=bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=active_proc_ref_env,
            visited_calls=visited_calls,
        ):
            return True
        return any(
            _expr_returns_local_proc_value(
                binding.value_expr,
                generated_name,
                value_bindings=bindings,
                procedure_catalog=procedure_catalog,
                proc_ref_env=active_proc_ref_env,
                visited_calls=visited_calls,
            )
            for binding in expr.bindings
        )
    if isinstance(expr, NameExpr):
        return bindings.get(expr.name, False)
    if isinstance(expr, ProcedureCallExpr):
        return _procedure_call_returns_local_proc_value(
            expr,
            generated_name,
            value_bindings=bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=active_proc_ref_env,
            visited_calls=visited_calls,
        )
    if type(expr) is FunctionCallExpr:
        return _function_call_returns_local_proc_value(
            expr,
            generated_name,
            value_bindings=bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=active_proc_ref_env,
            visited_calls=visited_calls,
        )
    if isinstance(expr, RecordExpr):
        return any(
            _expr_returns_local_proc_value(
                field_expr,
                generated_name,
                value_bindings=bindings,
                procedure_catalog=procedure_catalog,
                proc_ref_env=active_proc_ref_env,
                visited_calls=visited_calls,
            )
            for _field_name, field_expr in expr.fields
        )
    if isinstance(expr, LetStarExpr):
        local_bindings = dict(bindings)
        for binding_name, binding_expr in expr.bindings:
            local_bindings[binding_name] = _expr_returns_local_proc_value(
                binding_expr,
                generated_name,
                value_bindings=local_bindings,
                procedure_catalog=procedure_catalog,
                proc_ref_env=active_proc_ref_env,
                visited_calls=visited_calls,
            )
        return _expr_returns_local_proc_value(
            expr.body,
            generated_name,
            value_bindings=local_bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=active_proc_ref_env,
            visited_calls=visited_calls,
        )
    if isinstance(expr, IfExpr):
        return _expr_returns_local_proc_value(
            expr.then_expr,
            generated_name,
            value_bindings=bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=active_proc_ref_env,
            visited_calls=visited_calls,
        ) or _expr_returns_local_proc_value(
            expr.else_expr,
            generated_name,
            value_bindings=bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=active_proc_ref_env,
            visited_calls=visited_calls,
        )
    if type(expr) is MatchExpr:
        for arm in expr.arms:
            arm_bindings = dict(bindings)
            arm_bindings[arm.binding_name] = False
            if _expr_returns_local_proc_value(
                arm.body,
                generated_name,
                value_bindings=arm_bindings,
                procedure_catalog=procedure_catalog,
                proc_ref_env=active_proc_ref_env,
                visited_calls=visited_calls,
            ):
                return True
        return False
    if isinstance(expr, WithPhaseExpr):
        return _expr_returns_local_proc_value(
            expr.body,
            generated_name,
            value_bindings=bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=active_proc_ref_env,
            visited_calls=visited_calls,
        )
    if isinstance(expr, ContinueExpr):
        return _expr_returns_local_proc_value(
            expr.state_expr,
            generated_name,
            value_bindings=bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=active_proc_ref_env,
            visited_calls=visited_calls,
        )
    if isinstance(expr, DoneExpr):
        return _expr_returns_local_proc_value(
            expr.result_expr,
            generated_name,
            value_bindings=bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=active_proc_ref_env,
            visited_calls=visited_calls,
        )
    if isinstance(expr, LoopRecurExpr):
        loop_bindings = dict(bindings)
        loop_bindings[expr.binding_name] = False
        return _expr_returns_local_proc_value(
            expr.initial_state_expr,
            generated_name,
            value_bindings=bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=active_proc_ref_env,
            visited_calls=visited_calls,
        ) or _expr_returns_local_proc_value(
            expr.body_expr,
            generated_name,
            value_bindings=loop_bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=active_proc_ref_env,
            visited_calls=visited_calls,
        )
    if isinstance(expr, ResumeOrStartExpr):
        return _expr_returns_local_proc_value(
            expr.resume_from_expr,
            generated_name,
            value_bindings=bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=active_proc_ref_env,
            visited_calls=visited_calls,
        ) or _expr_returns_local_proc_value(
            expr.start_expr,
            generated_name,
            value_bindings=bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=active_proc_ref_env,
            visited_calls=visited_calls,
        )
    return False

def _procedure_call_returns_local_proc_value(
    expr: ProcedureCallExpr,
    generated_name: str,
    *,
    value_bindings: Mapping[str, bool],
    procedure_catalog: ProcedureCatalog | None,
    proc_ref_env: Mapping[str, ResolvedProcRefValue],
    visited_calls: frozenset[tuple[str, frozenset[str]]],
) -> bool:
    if procedure_catalog is None:
        return False
    callee_value = proc_ref_env.get(expr.callee_name)
    if callee_value is not None:
        definition = procedure_catalog.definitions_by_name.get(callee_value.procedure_name)
        signature_params = callee_value.signature_params
        bound_args = callee_value.bound_args
    else:
        definition = procedure_catalog.definitions_by_name.get(expr.callee_name)
        signature = procedure_catalog.signatures_by_name.get(expr.callee_name)
        if definition is None or signature is None:
            return False
        signature_params = signature.params
        bound_args = ()
    local_bindings = dict(value_bindings)
    local_proc_ref_env: dict[str, ResolvedProcRefValue] = {}
    for bound_arg in bound_args:
        local_bindings[bound_arg.name] = _expr_returns_local_proc_value(
            bound_arg.value_expr,
            generated_name,
            value_bindings=value_bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=proc_ref_env,
            visited_calls=visited_calls,
        )
        if isinstance(bound_arg.type_ref, ProcRefTypeRef):
            resolved_bound_arg = resolve_proc_ref_value(
                bound_arg.value_expr,
                procedure_catalog=procedure_catalog,
                proc_ref_env=proc_ref_env,
            )
            if resolved_bound_arg is not None:
                local_proc_ref_env[bound_arg.name] = resolved_bound_arg
    residual_params = [
        (param_name, param_type)
        for param_name, param_type in signature_params
        if param_name not in {bound_arg.name for bound_arg in bound_args}
    ]
    if len(expr.args) != len(residual_params):
        return False
    for arg_expr, (param_name, param_type) in zip(expr.args, residual_params, strict=True):
        local_bindings[param_name] = _expr_returns_local_proc_value(
            arg_expr,
            generated_name,
            value_bindings=value_bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=proc_ref_env,
            visited_calls=visited_calls,
        )
        if isinstance(param_type, ProcRefTypeRef):
            resolved_arg = resolve_proc_ref_value(
                arg_expr,
                procedure_catalog=procedure_catalog,
                proc_ref_env=proc_ref_env,
            )
            if resolved_arg is not None:
                local_proc_ref_env[param_name] = resolved_arg
    call_key = (definition.name, frozenset(name for name, escapes in local_bindings.items() if escapes))
    if call_key in visited_calls:
        return False
    body_expr = definition.body
    if isinstance(body_expr, SyntaxNode):
        body_expr = elaborate_expression(
            body_expr,
            bound_names=frozenset(name for name, _ in signature_params),
            procedure_names=frozenset(procedure_catalog.signatures_by_name),
        )
    return _expr_returns_local_proc_value(
        body_expr,
        generated_name,
        value_bindings=local_bindings,
        procedure_catalog=procedure_catalog,
        proc_ref_env=local_proc_ref_env,
        visited_calls=visited_calls | {call_key},
    )

def _function_call_returns_local_proc_value(
    expr: FunctionCallExpr,
    generated_name: str,
    *,
    value_bindings: Mapping[str, bool],
    procedure_catalog: ProcedureCatalog | None,
    proc_ref_env: Mapping[str, ResolvedProcRefValue],
    visited_calls: frozenset[tuple[str, frozenset[str]]],
) -> bool:
    session_state = get_session_state()
    function_catalog = session_state.function_catalog
    if function_catalog is None:
        return False
    definition = function_catalog.definitions_by_name.get(expr.callee_name)
    signature = function_catalog.signatures_by_name.get(expr.callee_name)
    if definition is None or signature is None or len(expr.args) != len(signature.params):
        return False
    local_bindings = dict(value_bindings)
    for arg_expr, (param_name, _param_type) in zip(expr.args, signature.params, strict=True):
        local_bindings[param_name] = _expr_returns_local_proc_value(
            arg_expr,
            generated_name,
            value_bindings=value_bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=proc_ref_env,
            visited_calls=visited_calls,
        )
    call_key = (
        f"function:{definition.name}",
        frozenset(name for name, escapes in local_bindings.items() if escapes),
    )
    if call_key in visited_calls:
        return False
    body_expr = definition.body
    if isinstance(body_expr, SyntaxNode):
        body_expr = elaborate_expression(
            body_expr,
            bound_names=frozenset(name for name, _ in signature.params),
            procedure_names=(
                frozenset()
                if procedure_catalog is None
                else frozenset(procedure_catalog.signatures_by_name)
            ),
            function_names=frozenset(function_catalog.signatures_by_name),
        )
    return _expr_returns_local_proc_value(
        body_expr,
        generated_name,
        value_bindings=local_bindings,
        procedure_catalog=procedure_catalog,
        proc_ref_env=proc_ref_env,
        visited_calls=visited_calls | {call_key},
    )

def _expr_source_identity(expr: ExprNode) -> str:
    if isinstance(expr, LiteralExpr):
        return f"literal:{expr.literal_kind}:{expr.value!r}"
    if type(expr) is FieldAccessExpr:
        return f"field:{expr.base.name}:{'.'.join(expr.fields)}"
    if isinstance(expr, NameExpr):
        return f"name:{expr.name}"
    start = expr.span.start
    return f"{start.path}:{start.line}:{start.column}"

def _collect_proc_ref_use_spans(
    node: object,
    *,
    authored_name: str,
) -> tuple[SourceSpan, ...]:
    if isinstance(node, ProcRefLiteralExpr):
        return (node.span,) if node.authored_name == authored_name else ()
    if isinstance(node, LetProcExpr):
        return ()
    if isinstance(node, tuple):
        return tuple(
            span
            for item in node
            for span in _collect_proc_ref_use_spans(item, authored_name=authored_name)
        )
    if isinstance(node, list):
        return tuple(
            span
            for item in node
            for span in _collect_proc_ref_use_spans(item, authored_name=authored_name)
        )
    if is_dataclass(node):
        return tuple(
            span
            for field in fields(node)
            for span in _collect_proc_ref_use_spans(getattr(node, field.name), authored_name=authored_name)
        )
    return ()

def _semantic_identity(value: object) -> str:
    if is_dataclass(value):
        return (
            f"{type(value).__name__}("
            + ",".join(
                f"{field.name}={_semantic_identity(getattr(value, field.name))}"
                for field in fields(value)
                if field.name not in {"span", "form_path", "expansion_stack"}
            )
            + ")"
        )
    if isinstance(value, tuple):
        return "(" + ",".join(_semantic_identity(item) for item in value) + ")"
    if isinstance(value, list):
        return "[" + ",".join(_semantic_identity(item) for item in value) + "]"
    if isinstance(value, Mapping):
        return (
            "{"
            + ",".join(
                f"{_semantic_identity(key)}:{_semantic_identity(value[key])}"
                for key in sorted(value, key=repr)
            )
            + "}"
        )
    if isinstance(value, frozenset):
        return "frozenset(" + ",".join(sorted(_semantic_identity(item) for item in value)) + ")"
    return repr(value)

def _replace_eliminated_let_procs(
    node: object,
    *,
    let_proc_rewrite_results: Mapping[int, ExprNode] | None = None,
):
    rewrite_results = (
        get_session_state().let_proc_rewrite_results
        if let_proc_rewrite_results is None
        else let_proc_rewrite_results
    )
    replacement = rewrite_results.get(id(node))
    if replacement is not None:
        return _replace_eliminated_let_procs(
            replacement,
            let_proc_rewrite_results=rewrite_results,
        )
    if isinstance(node, tuple):
        return tuple(
            _replace_eliminated_let_procs(
                item,
                let_proc_rewrite_results=rewrite_results,
            )
            for item in node
        )
    if isinstance(node, list):
        return [
            _replace_eliminated_let_procs(
                item,
                let_proc_rewrite_results=rewrite_results,
            )
            for item in node
        ]
    if is_dataclass(node):
        updates = {}
        for field in fields(node):
            current = getattr(node, field.name)
            rewritten = _replace_eliminated_let_procs(
                current,
                let_proc_rewrite_results=rewrite_results,
            )
            if rewritten is not current:
                updates[field.name] = rewritten
        if updates:
            return replace(node, **updates)
    return node
