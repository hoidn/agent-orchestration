"""Procedure typing ownership for Workflow Lisp."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields, is_dataclass, replace

from .compiler_session import CompilerSession, TypecheckSessionState
from .definitions import RecordField, SyntaxNode, UnionDef, UnionVariant
from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .effects import (
    EMPTY_EFFECT_SUMMARY,
    EffectSummary,
    ProcedureCallEdge,
    effect_summary_from_procedure_call,
    merge_effect_summaries,
)
from .parametric_constraints import evaluate_parametric_constraints, provisional_shared_union_field_capabilities
from .generic_unions import bind_applied_union_arguments
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
    WithLiveProviderPeersExpr,
    WithLiveProvidersExpr,
    WithPhaseExpr,
    elaborate_expression,
)
from .expression_traversal import iter_child_exprs, walk_expr
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
from .phase import eligible_private_context_source_param_names
from .procedure_refs import (
    BoundProcArg,
    ProcRefAuthoritySource,
    ResolvedProcRefValue,
    resolve_proc_ref_value,
)
from .type_env import (
    FrontendTypeEnvironment,
    ProcRefTypeRef,
    RecordTypeRef,
    TypeParamRef,
    TypeRef,
    UnionTypeRef,
    WorkflowRefTypeRef,
    ensure_no_type_params,
    substitute_type_params,
    type_refs_compatible,
)
from .syntax import target_dsl_supports_local_hook_inference
from .typecheck_context import raise_error as _raise_error
from .typecheck_proofs import BindingIdentity, _allocate_binding_identity


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
    prompt_catalog: object | None
    active_proc_ref_value_env: Mapping[str, ResolvedProcRefValue]
    compiler_session: CompilerSession
    session_state: TypecheckSessionState
    generated_local_procedure_state: object | None = None


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


def consume_parametric_specialization_requests(
    session_state: TypecheckSessionState,
) -> tuple[PendingParametricProcedureSpecialization, ...]:
    requests = tuple(session_state.parametric_specialization_requests.values())
    session_state.parametric_specialization_requests = {}
    return requests


def reset_parametric_specialization_requests(
    session_state: TypecheckSessionState,
) -> None:
    session_state.parametric_specialization_requests = {}


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
    prompt_catalog: object | None = None,
    proc_ref_resolution_context=None,
    procedure_type_envs: Mapping[str, FrontendTypeEnvironment] | None = None,
    function_body_normalizer: Callable[[ExprNode], ExprNode] | None = None,
    allow_provisional_procedure_calls: bool = False,
    compiler_session: CompilerSession | None = None,
) -> tuple[TypedProcedureDef, ...]:
    from .typecheck import typecheck_expression
    from .workflows import ExternEnvironment, ProviderExtern
    from .expressions import elaborate_expression

    compiler_session = compiler_session or CompilerSession()
    session_state = compiler_session.typecheck
    externs = extern_environment or ExternEnvironment(bindings_by_name={})
    typed_procedures: list[TypedProcedureDef] = []
    for procedure_target in procedure_defs:
        current_type_env = (
            procedure_type_env_for(
                procedure_target,
                procedure_type_envs=procedure_type_envs,
                default=type_env,
                session_state=session_state,
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
        _validate_type_param_binding_coverage(procedure_def, signature)
        if isinstance(procedure_target, TypedProcedureDef):
            from .loop_state import register_all_known_carrier_types

            register_all_known_carrier_types(
                current_type_env,
                session_state=session_state,
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
        if specialization is None and signature.type_params:
            from .generic_unions import type_env_with_type_params

            current_type_env = type_env_with_type_params(
                current_type_env,
                {type_param.name: value_env[type_param.name] for type_param in signature.type_params},
            )
        if specialization is not None:
            value_env.update(dict(getattr(specialization, "type_bindings", {})))
            value_env.update(dict(getattr(specialization, "bound_param_types", {})))
            proc_ref_value_env.update(dict(getattr(specialization, "proc_ref_bindings", {})))
            shared_union_field_capabilities = tuple(
                getattr(specialization, "shared_union_field_capabilities", ())
            ) or shared_union_field_capabilities
        extern_names = frozenset(externs.bindings_by_name)
        lexical_names = frozenset(value_env) - extern_names
        w3 = target_dsl_supports_local_hook_inference(current_type_env.target_dsl_version)
        for extern_name, binding in externs.bindings_by_name.items():
            extern_type = current_type_env.resolve_type(
                "Provider" if isinstance(binding, ProviderExtern) else "Prompt",
                span=procedure_def.span,
                form_path=procedure_def.form_path,
            )
            if w3 and procedure_def.generated_local_procedure is not None:
                value_env.setdefault(extern_name, extern_type)
            else:
                value_env[extern_name] = extern_type
        if isinstance(procedure_target, TypedProcedureDef):
            body_expr = procedure_target.typed_body.expr
        elif isinstance(procedure_def.body, SyntaxNode):
            body_expr = elaborate_expression(
                procedure_def.body,
                bound_names=lexical_names if w3 else frozenset(value_env),
                extern_names=extern_names if w3 else frozenset(),
                procedure_names=frozenset(procedure_catalog.signatures_by_name),
                function_names=(
                    frozenset()
                    if function_catalog is None
                    else frozenset(function_catalog.signatures_by_name)
                ),
                function_name_resolver=function_name_resolver,
                procedure_name_resolver=procedure_name_resolver,
                workflow_name_resolver=workflow_name_resolver,
                target_dsl_version=(
                    current_type_env.target_dsl_version
                ),
                prompt_catalog=prompt_catalog,
                session_state=compiler_session.elaboration,
            )
        else:
            body_expr = procedure_def.body
        if function_body_normalizer is not None:
            body_expr = function_body_normalizer(body_expr)
        previous_hidden_context_signature = session_state.procedure_hidden_context_signature
        # A defproc body may omit a callee's hidden private phase context under
        # the same derived-private-child eligibility rules as a defworkflow
        # body exactly when the proc's params carry a structural private exec
        # context; procs without a private context source keep the plain
        # missing-binding failure (structural private-exec-context /
        # std/context contract,
        # docs/design/workflow_lisp_frontend_specification.md).
        session_state.procedure_hidden_context_signature = (
            signature
            if eligible_private_context_source_param_names(signature)
            else None
        )
        try:
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
                prompt_catalog=prompt_catalog,
                shared_union_field_capabilities=shared_union_field_capabilities,
                expected_type=signature.return_type_ref,
                compiler_session=compiler_session,
                allow_provisional_procedure_calls=allow_provisional_procedure_calls,
            )
        except LispFrontendCompileError as exc:
            if specialization is None:
                raise
            raise _annotate_specialization_body_error(exc, origin_span=specialization.origin_span) from exc
        finally:
            session_state.procedure_hidden_context_signature = previous_hidden_context_signature
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


def _validate_type_param_binding_coverage(
    procedure_def: ProcedureDef,
    signature: ProcedureSignature,
) -> None:
    if not signature.type_params:
        return

    bindable_type_params: set[str] = set()
    for _, type_ref in signature.params:
        bindable_type_params.update(_type_param_names_in_type_ref(type_ref))

    for type_param in signature.type_params:
        if type_param.name in bindable_type_params:
            continue
        raise LispFrontendCompileError(
            (
                LispFrontendDiagnostic(
                    code="procedure_type_param_unbindable",
                    message=(
                        f"procedure `{procedure_def.name}` declares type parameter `{type_param.name}` "
                        "but it appears in no parameter or ProcRef signature position; "
                        "it can never be inferred"
                    ),
                    span=procedure_def.span,
                    form_path=procedure_def.form_path,
                    expansion_stack=procedure_def.expansion_stack,
                    phase="typecheck",
                ),
            )
        )


def _type_param_names_in_type_ref(type_ref: TypeRef) -> frozenset[str]:
    if isinstance(type_ref, TypeParamRef):
        return frozenset({type_ref.name})
    if hasattr(type_ref, "item_type_ref"):
        return _type_param_names_in_type_ref(type_ref.item_type_ref)
    if hasattr(type_ref, "key_type_ref"):
        return _type_param_names_in_type_ref(type_ref.key_type_ref) | _type_param_names_in_type_ref(
            type_ref.value_type_ref
        )
    if isinstance(type_ref, ProcRefTypeRef):
        names: set[str] = set()
        for param_type in type_ref.param_type_refs:
            names.update(_type_param_names_in_type_ref(param_type))
        names.update(_type_param_names_in_type_ref(type_ref.return_type_ref))
        return frozenset(names)
    if isinstance(type_ref, WorkflowRefTypeRef):
        names: set[str] = set()
        for param_type in type_ref.param_type_refs:
            names.update(_type_param_names_in_type_ref(param_type))
        names.update(_type_param_names_in_type_ref(type_ref.return_type_ref))
        return frozenset(names)
    if isinstance(type_ref, UnionTypeRef):
        # Applied generic union arguments bind, phantom ones included.
        return frozenset(name for arg in type_ref.type_args for name in _type_param_names_in_type_ref(arg))
    if isinstance(type_ref, RecordTypeRef):
        from .context_types import is_contextual_type

        if is_contextual_type(type_ref):
            return frozenset(
                type_param_name
                for field_type in type_ref.field_types.values()
                for type_param_name in _type_param_names_in_type_ref(field_type)
            )
    return frozenset()


def _annotate_specialization_body_error(
    exc: LispFrontendCompileError,
    *,
    origin_span,
) -> LispFrontendCompileError:
    origin = origin_span.start
    note = f"instantiated from {origin.path}:{origin.line}:{origin.column}"
    return LispFrontendCompileError(
        tuple(
            diagnostic
            if note in diagnostic.notes
            else replace(diagnostic, notes=(*diagnostic.notes, note))
            for diagnostic in exc.diagnostics
        )
    )


def _apply_provisional_parametric_type(
    type_ref: TypeRef,
    provisional_match_types: Mapping[str, UnionTypeRef],
) -> TypeRef:
    if isinstance(type_ref, TypeParamRef):
        return provisional_match_types.get(type_ref.name, type_ref)
    if isinstance(type_ref, ProcRefTypeRef):
        # A ProcRef-typed hook parameter's invocation result is typed from the
        # ProcRef's return position, so the definition-scoped pass must apply
        # the same provisional `has-union-variant` capability union there that
        # a direct `TypeParamRef` parameter receives (provisional pass,
        # docs/design/workflow_lisp_parametric_type_system.md). Parameter
        # positions stay raw: they are inference sinks, not match subjects.
        rewritten_return = _apply_provisional_parametric_type(
            type_ref.return_type_ref,
            provisional_match_types,
        )
        if rewritten_return is type_ref.return_type_ref:
            return type_ref
        return replace(type_ref, return_type_ref=rewritten_return)
    return type_ref


def _provisional_parametric_match_types(
    *,
    signature: ProcedureSignature,
    type_env: FrontendTypeEnvironment,
) -> dict[str, UnionTypeRef]:
    type_param_names = frozenset(type_param.name for type_param in signature.type_params)
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
        # Constraint Vocabulary rule 3
        # (docs/design/workflow_lisp_parametric_type_system.md): a field
        # requirement's type may name another `:forall` parameter. The raw
        # (definition-scoped) pass has no concrete binding yet, so it types
        # such a field as the bare type-parameter placeholder rather than
        # eagerly resolving it against the type environment.
        variant_fields[clause.variant_name] = {
            requirement.field_name: (
                TypeParamRef(name=requirement.field_type_name)
                if requirement.field_type_name in type_param_names
                else type_env.resolve_type(
                    requirement.field_type_name,
                    span=requirement.span,
                    form_path=requirement.form_path,
                    expansion_stack=requirement.expansion_stack,
                )
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
    preparer = context.session_state.pending_local_hook_preparer
    if preparer is not None:
        prepared = preparer(expr, context=context, recurse=recurse)
        if prepared is not None:
            return prepared
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
        rewritten_args: list[ExprNode] = []
        for arg_expr, (param_name, expected_type) in zip(expr.args, bound_proc_ref.residual_params, strict=True):
            typed_arg = recurse(arg_expr, expected_type=expected_type)
            arg_summaries.append(typed_arg.effect_summary)
            rewritten_args.append(typed_arg.expr)
            if not type_refs_compatible(expected_type, typed_arg.type_ref):
                raise_error(
                    f"procedure argument `{param_name}` expected `{type_label(expected_type)}`"
                    f" but got `{type_label(typed_arg.type_ref)}`",
                    code="type_mismatch",
                    span=arg_expr.span,
                    form_path=arg_expr.form_path,
                )
        callee_summary = context.procedure_effects_by_name.get(bound_proc_ref.call_target_name, EMPTY_EFFECT_SUMMARY)
        procedure_summary = effect_summary_from_procedure_call(
            callee_effects=callee_summary.transitive_effects,
            edge=ProcedureCallEdge(
                callee_name=bound_proc_ref.call_target_name,
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            ),
        )
        return typed_factory(
            expr=replace(expr, args=tuple(rewritten_args)),
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
        rewritten_args = []
        for arg_expr, expected_type in zip(expr.args, generic_proc_ref_type.param_type_refs, strict=True):
            typed_arg = recurse(arg_expr, expected_type=expected_type)
            arg_summaries.append(typed_arg.effect_summary)
            rewritten_args.append(typed_arg.expr)
            if not type_refs_compatible(expected_type, typed_arg.type_ref):
                raise_error(
                    f"procedure argument expected `{type_label(expected_type)}`"
                    f" but got `{type_label(typed_arg.type_ref)}`",
                    code="type_mismatch",
                    span=arg_expr.span,
                    form_path=arg_expr.form_path,
                )
        return typed_factory(
            expr=replace(expr, args=tuple(rewritten_args)),
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
    rewritten_args: list[ExprNode] = []
    proc_ref_bindings: dict[str, ResolvedProcRefValue] = {}
    for arg_expr, (param_name, expected_type) in zip(expr.args, signature.params, strict=True):
        if isinstance(expected_type, WorkflowRefTypeRef):
            typed_arg = typecheck_workflow_ref_argument(arg_expr, expected_type)
            arg_summaries.append(typed_arg.effect_summary)
            rewritten_args.append(typed_arg.expr)
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
            rewritten_args.append(typed_arg.expr)
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
        typed_arg = recurse(arg_expr, expected_type=expected_type)
        arg_summaries.append(typed_arg.effect_summary)
        rewritten_args.append(typed_arg.expr)
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
    procedure_summary = effect_summary_from_procedure_call(
        callee_effects=callee_summary.transitive_effects,
        edge=ProcedureCallEdge(
            callee_name=callee_name,
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        ),
    )
    return typed_factory(
        expr=replace(expr, args=tuple(rewritten_args)),
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
        message = (
            f"procedure `{expr.callee_name}` expected {len(signature.params)} positional arguments "
            f"but got {len(expr.args)}"
        )
        if (
            signature.name == "std/improve::improve"
            and tuple(name for name, _type_ref in signature.params)
            == ("initial", "review", "revise", "limit")
            and len(expr.args) == 5
        ):
            message += (
                "; migrate this call by removing the `inputs` argument and capturing it "
                "in the local `review` and `revise` hooks"
            )
        raise_error(
            message,
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

    if context.compiler_session.closed_program:
        expr = replace(expr, args=tuple(argument.expr for argument in typed_args))
    else:
        expr = replace(expr, args=tuple(
            _retain_capture_metadata(original, argument.expr,
                procedure_catalog=context.procedure_catalog)
            for original, argument in zip(expr.args, typed_args, strict=True)
        ))

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
            owner_type_refs=dict(signature.constraint_type_refs),
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
    from .generic_unions import reject_untransportable_applied_unions

    for concrete_type in (
        concrete_return_type,
        *(substitute_type_params(param_type, type_bindings) for _, param_type in signature.params),
    ):
        reject_untransportable_applied_unions(concrete_type, span=expr.span, form_path=expr.form_path)

    remaining_params: list[tuple[str, TypeRef]] = []
    remaining_args: list[object] = []
    retained_reference_actuals = list(expr.retained_reference_actuals)
    for arg_expr, (param_name, param_type) in zip(expr.args, signature.params, strict=True):
        concrete_param_type = substitute_type_params(param_type, type_bindings)
        if isinstance(param_type, ProcRefTypeRef) and param_name in proc_ref_bindings:
            retained_reference_actuals.append((param_name, arg_expr))
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
    context.session_state.parametric_specialization_requests[
        specialized_name
    ] = PendingParametricProcedureSpecialization(
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
    procedure_summary = effect_summary_from_procedure_call(
        callee_effects=callee_summary.transitive_effects,
        edge=ProcedureCallEdge(
            callee_name=specialized_name,
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        ),
    )
    return typed_factory(
        expr=replace(expr, callee_name=specialized_name, args=tuple(remaining_args),
            retained_reference_actuals=tuple(retained_reference_actuals)),
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
    if isinstance(expected_type, UnionTypeRef) and expected_type.type_args:
        bind_applied_union_arguments(
            expected_type,
            actual_type,
            bind=lambda expected_arg, actual_arg: _infer_parametric_type_bindings(
                expected_arg,
                actual_arg,
                bindings=bindings,
                raise_error=raise_error,
                span=span,
                form_path=form_path,
            ),
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
    if isinstance(expected_type, RecordTypeRef) and isinstance(actual_type, RecordTypeRef):
        from .context_types import is_contextual_type

        if is_contextual_type(expected_type) and is_contextual_type(actual_type):
            for field_name in expected_type.field_types:
                _infer_parametric_type_bindings(
                    expected_type.field_types[field_name],
                    actual_type.field_types[field_name],
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
    if isinstance(type_ref, UnionTypeRef):
        return any(_type_ref_contains_type_param(arg) for arg in type_ref.type_args)
    return False


def calls_generic_procedure_through_type_dependent_hook(
    expr: ExprNode,
    *,
    procedure_catalog: ProcedureCatalog,
) -> bool:
    """Return whether ``expr`` calls a generic procedure whose hook type uses a type parameter.

    Proc-ref discovery checks the hook of such an authored call against the declared,
    unspecialized hook type and rejects it with ``proc_ref_signature_invalid``; only the
    specialized call that typechecking produces can be lowered.
    """
    for node in walk_expr(expr):
        signature = (
            procedure_catalog.signatures_by_name.get(node.callee_name)
            if isinstance(node, ProcedureCallExpr)
            else None
        )
        if signature is not None and signature.type_params and any(
            isinstance(param_type, ProcRefTypeRef) and _type_ref_contains_type_param(param_type)
            for _, param_type in signature.params
        ):
            return True
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
        prompt_catalog=context.prompt_catalog,
        compiler_session=context.compiler_session,
        expected_type=signature.return_type_ref,
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

    typed = _typecheck(*args, **kwargs)
    return replace(
        typed,
        binding_environment=dict(kwargs.get("binding_env", {})),
    )


def _temporary_procedure_catalog(
    procedure_catalog: ProcedureCatalog,
    *,
    definition: ProcedureDef,
    signature: ProcedureSignature,
) -> ProcedureCatalog:
    signatures_by_name = dict(procedure_catalog.signatures_by_name)
    definitions_by_name = dict(procedure_catalog.definitions_by_name)
    signatures_by_name[signature.name] = signature
    definitions_by_name[definition.name] = definition
    return ProcedureCatalog(
        signatures_by_name=signatures_by_name,
        definitions_by_name=definitions_by_name,
        call_graph=procedure_catalog.call_graph,
    )


@dataclass(frozen=True)
class LocalProcRewriteBinding:
    """How one lexical `let-proc` name rewrites during typechecking."""

    generated_name: str
    capture_bindings: tuple[tuple[str, ExprNode], ...]
    capture_binding_identities: tuple[object | None, ...]
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
        binding_env=context.binding_env,
        proof_scope=context.proof_scope,
        workflow_catalog=context.workflow_catalog,
        procedure_catalog=context.procedure_catalog,
        extern_environment=context.extern_environment,
        command_boundary_environment=context.command_boundary_environment,
        active_phase_scope=context.active_phase_scope,
        procedure_effects_by_name=context.procedure_effects_by_name,
        workflow_effects_by_name=context.workflow_effects_by_name,
        proc_ref_resolution_context=context.proc_ref_resolution_context,
        prompt_catalog=context.prompt_catalog,
        session_state=context.session_state,
        compiler_session=context.compiler_session,
    )


def _typecheck_let_proc_expr_impl(
    expr: LetProcExpr,
    *,
    type_env: FrontendTypeEnvironment,
    value_env: dict[str, TypeRef],
    binding_env: Mapping[str, BindingIdentity],
    proof_scope: ProofScope,
    workflow_catalog: "WorkflowCatalog | None",
    procedure_catalog: ProcedureCatalog | None,
    extern_environment: "ExternEnvironment | None",
    command_boundary_environment: "CommandBoundaryEnvironment | None",
    active_phase_scope: PhaseScope | None,
    procedure_effects_by_name: Mapping[str, EffectSummary],
    workflow_effects_by_name: Mapping[str, EffectSummary],
    proc_ref_resolution_context: ProcRefResolutionContext | None,
    prompt_catalog: object | None,
    session_state: TypecheckSessionState,
    compiler_session: CompilerSession,
    _prepared_local_body=None,
    _register_only=False,
) -> TypedExpr:

    if not _register_only and (expr.additional_bindings or expr.binding.return_type_name is None or any(param.type_name is None for param in expr.binding.params)):
        return _typecheck_local_hook_group(expr, type_env=type_env, value_env=value_env,
            binding_env=binding_env, proof_scope=proof_scope, workflow_catalog=workflow_catalog,
            procedure_catalog=procedure_catalog, extern_environment=extern_environment,
            command_boundary_environment=command_boundary_environment, active_phase_scope=active_phase_scope,
            procedure_effects_by_name=procedure_effects_by_name, workflow_effects_by_name=workflow_effects_by_name,
            proc_ref_resolution_context=proc_ref_resolution_context, prompt_catalog=prompt_catalog,
            session_state=session_state, compiler_session=compiler_session)

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
    capture_binding_identities: list[object | None] = []
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
        from .typecheck_agents import require_no_agent
        require_no_agent(capture_type, where=f"`let-proc` capture `{capture_name}`", span=expr.binding.span,
                         form_path=expr.binding.form_path, code="let_proc_capture_agent_forbidden")
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
        from .expression_traversal import stamp_capture_origin
        bound_capture_value = stamp_capture_origin(capture_value_expr, binding_env=binding_env, value_env=value_env)
        capture_identity = binding_env.get(capture_name)
        capture_bindings.append((capture_name, bound_capture_value))
        capture_binding_identities.append(capture_identity)
        bound_capture_args.append(
            BoundProcArg(
                name=capture_name,
                value_expr=bound_capture_value,
                type_ref=capture_type,
                source_identity=_expr_source_identity(capture_value_expr),
                keyword_span=expr.binding.span,
                keyword_form_path=expr.binding.form_path,
                keyword_expansion_stack=expr.binding.expansion_stack,
                source_binding_identity=capture_identity,
            )
        )

    local_body_expr = _rewrite_local_proc_references(
        expr.binding.local_body,
        local_bindings={
            expr.binding.local_name: LocalProcRewriteBinding(
                generated_name="",
                capture_bindings=tuple(capture_bindings),
                capture_binding_identities=tuple(capture_binding_identities),
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
        capture_binding_identities=tuple(capture_binding_identities),
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
    generated_catalog = _temporary_procedure_catalog(
        procedure_catalog,
        definition=generated_definition,
        signature=generated_signature,
    )
    if not _register_only and _expr_returns_local_proc_value(
        outer_body_expr,
        generated_name,
        procedure_catalog=generated_catalog,
        target_dsl_version=type_env.target_dsl_version,
        proc_ref_env=(session_state.proc_ref_value_env
            if target_dsl_supports_local_hook_inference(type_env.target_dsl_version) else None),
        compiler_session=compiler_session,
    ):
        _raise_error(
            f"`let-proc` local procedure `{expr.binding.local_name}` escaped its lexical scope",
            code="let_proc_scope_escape",
            span=expr.body.span,
            form_path=expr.body.form_path,
            expansion_stack=expr.body.expansion_stack,
        )

    local_value_env = {}
    if target_dsl_supports_local_hook_inference(type_env.target_dsl_version):
        from .workflows import ProviderExtern

        for name, binding in getattr(extern_environment, "bindings_by_name", {}).items():
            local_value_env[name] = type_env.resolve_type(
                "Provider" if isinstance(binding, ProviderExtern) else "Prompt",
                span=expr.binding.span, form_path=expr.binding.form_path,
            )
    local_value_env.update(dict(capture_signature_params))
    local_value_env.update(dict(residual_signature_params))
    local_binding_env = dict(binding_env)
    for name, _type_ref in residual_signature_params:
        local_binding_env[name] = _allocate_binding_identity(
            local_binding_env,
            form_path=expr.binding.form_path,
            kind="param",
            name=name,
        )
    previous_proc_ref_env = session_state.proc_ref_value_env
    session_state.proc_ref_value_env = local_proc_ref_env
    previous_workflow_signature = session_state.workflow_signature
    previous_hidden_context_signature = session_state.procedure_hidden_context_signature
    # A `let-proc` local's generated defproc-equivalent must typecheck under
    # the same hidden-context gate an authored top-level `defproc` body gets:
    # the generated signature's own params decide derived-private-child
    # eligibility, not whatever `defworkflow`/enclosing-`defproc` gate was
    # active at the `let-proc` call site (let-proc equivalence contract,
    # docs/design/workflow_lisp_let_proc_local_proc_refs.md; mirrors the
    # per-definition proc body gate above).
    session_state.workflow_signature = None
    session_state.procedure_hidden_context_signature = (
        generated_signature
        if eligible_private_context_source_param_names(generated_signature)
        else None
    )
    try:
        typed_local_body = _prepared_local_body
        if typed_local_body is None:
            typed_local_body = _typecheck_owner(
                local_body_expr,
                type_env=type_env,
                value_env=local_value_env,
                binding_env=local_binding_env,
                proof_scope=proof_scope,
                workflow_catalog=workflow_catalog,
                procedure_catalog=generated_catalog,
                extern_environment=extern_environment,
                command_boundary_environment=command_boundary_environment,
                active_phase_scope=active_phase_scope,
                procedure_effects_by_name=procedure_effects_by_name,
                workflow_effects_by_name=workflow_effects_by_name,
                proc_ref_resolution_context=proc_ref_resolution_context,
                prompt_catalog=prompt_catalog,
                session_state=session_state,
                compiler_session=compiler_session,
            )
    finally:
        session_state.proc_ref_value_env = previous_proc_ref_env
        session_state.workflow_signature = previous_workflow_signature
        session_state.procedure_hidden_context_signature = previous_hidden_context_signature
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
    if _register_only:
        return generated_catalog, rewrite_binding, bound_local_proc

    outer_proc_ref_env = dict(session_state.proc_ref_value_env)
    outer_proc_ref_env[expr.binding.local_name] = bound_local_proc
    previous_proc_ref_env = session_state.proc_ref_value_env
    session_state.proc_ref_value_env = outer_proc_ref_env
    try:
        typed_outer_body = _typecheck_owner(
            outer_body_expr,
            type_env=type_env,
            value_env=value_env,
            binding_env=binding_env,
            proof_scope=proof_scope,
            workflow_catalog=workflow_catalog,
            procedure_catalog=generated_catalog,
            extern_environment=extern_environment,
            command_boundary_environment=command_boundary_environment,
            active_phase_scope=active_phase_scope,
            procedure_effects_by_name=procedure_effects_by_name,
            workflow_effects_by_name=workflow_effects_by_name,
            proc_ref_resolution_context=proc_ref_resolution_context,
            prompt_catalog=prompt_catalog,
            session_state=session_state,
            compiler_session=compiler_session,
        )
    finally:
        session_state.proc_ref_value_env = previous_proc_ref_env
    retained_outer_body = (
        typed_outer_body.expr
        if compiler_session.closed_program
        and target_dsl_supports_local_hook_inference(type_env.target_dsl_version)
        else _retain_capture_metadata(
            outer_body_expr, typed_outer_body.expr, procedure_catalog=generated_catalog,
        )
    )
    session_state.let_proc_rewrite_results[id(expr)] = retained_outer_body
    return replace(typed_outer_body, expr=retained_outer_body)



def _local_hook_is_complete(binding):
    return binding.return_type_name is not None and all(
        param.type_name is not None for param in binding.params
    )


def _validate_local_hook_sites(consumer, bindings):
    """Count executable authored call paths within this lexical owner."""
    incomplete = {binding.local_name: binding for binding in bindings
                  if not _local_hook_is_complete(binding)}
    sites = {name: {} for name in incomplete}
    indirect = []

    def visit(node, path, direct_call=None):
        if isinstance(node, LetProcExpr):
            # This declaration/consumer has its own scoped local bindings.
            return
        if isinstance(node, ProcRefLiteralExpr):
            binding = incomplete.get(node.target_name)
            if binding is not None:
                if direct_call is None:
                    indirect.append((binding, node))
                else:
                    call_path, call = direct_call
                    sites[binding.local_name].setdefault(call_path, call)
            return
        if isinstance(node, ProcedureCallExpr):
            for index, arg in enumerate(node.args):
                visit(arg, path + (index,), (path, node))
            return
        for index, child in enumerate(iter_child_exprs(node)):
            visit(child, path + (index,))

    visit(consumer, ())
    if indirect:
        binding, use = indirect[0]
        _raise_error(
            "an incomplete local needs a direct ProcRef argument; annotate it for forwarding",
            code="let_proc_indirect_reference_unsupported", span=use.span,
            form_path=use.form_path, expansion_stack=use.expansion_stack,
            notes=(f"local `{binding.local_name}` declared at {binding.span.start.path}:{binding.span.start.line}",),
        )
    for name, binding in incomplete.items():
        if len(sites[name]) != 1:
            _raise_error(
                "an incomplete local requires exactly one authored consumer call; add explicit annotations",
                code="let_proc_consumer_site_invalid", span=binding.span,
                form_path=binding.form_path, expansion_stack=binding.expansion_stack,
                notes=tuple(f"consumer call at {call.span.start.path}:{call.span.start.line}"
                            for call in sites[name].values()),
            )
    return sites


def _prepare_local_hook_call(call, bindings, *, creator, signature, recurse):
    """Complete pending signatures at their one actual consumer call."""
    if signature is None:
        _raise_error("local hook consumer requires a resolved call signature",
            code="let_proc_expected_signature_missing", span=call.span, form_path=call.form_path)
    if len(call.args) != len(signature.params):
        _raise_error("local hook consumer arity differs from its signature",
            code="procedure_arity_mismatch", span=call.span, form_path=call.form_path)
    local_by_name = {binding.local_name: binding for binding in bindings}
    positions = {name: [] for name in local_by_name}
    type_bindings = {}
    for index, (arg, (_, expected)) in enumerate(zip(call.args, signature.params, strict=True)):
        if isinstance(arg, ProcRefLiteralExpr) and arg.target_name in local_by_name:
            if not isinstance(expected, ProcRefTypeRef):
                _raise_error("local hook requires ProcRef expectation",
                    code="let_proc_expected_signature_missing", span=arg.span, form_path=arg.form_path)
            positions[arg.target_name].append((index, expected))
        else:
            typed = recurse(arg)
            _infer_parametric_type_bindings(expected, typed.type_ref, bindings=type_bindings,
                raise_error=_raise_error, span=arg.span, form_path=arg.form_path)
    pending, completed = dict(local_by_name), {}
    while pending:
        # Gather every existing expected/authored constraint before asking which
        # bodies are ready. Later parameters and return annotations can ground
        # a variable used by an earlier omitted parameter.
        for binding in pending.values():
            occurrences = positions[binding.local_name]
            if not occurrences:
                _raise_error("incomplete local hook needs a direct consumer position",
                    code="let_proc_expected_signature_missing", span=binding.span, form_path=binding.form_path)
            if any(len(expected.param_type_refs) != len(binding.params) for _, expected in occurrences):
                _raise_error("local hook arity differs from expectation",
                    code="proc_ref_signature_invalid", span=binding.span, form_path=binding.form_path)
        previous_bindings = None
        while previous_bindings != type_bindings:
            previous_bindings = dict(type_bindings)
            for binding in pending.values():
                expectations = [expected for _, expected in positions[binding.local_name]]
                positions_to_unify = [
                    ([expected.param_type_refs[index] for expected in expectations],
                     param.type_name, param.span, param.form_path)
                    for index, param in enumerate(binding.params)
                ]
                positions_to_unify.append(([expected.return_type_ref for expected in expectations],
                    binding.return_type_name, binding.span, binding.form_path))
                for expected_positions, authored_name, span, form_path in positions_to_unify:
                    candidates = [substitute_type_params(item, type_bindings) for item in expected_positions]
                    if authored_name is not None:
                        candidates.append(creator["type_env"].resolve_type(
                            authored_name, span=span, form_path=form_path))
                    concrete = next((item for item in candidates if not _type_ref_contains_type_param(item)), None)
                    if concrete is not None:
                        for candidate in candidates:
                            _infer_parametric_type_bindings(candidate, concrete, bindings=type_bindings,
                                raise_error=_raise_error, span=span, form_path=form_path)
        progress = False
        for name, binding in tuple(pending.items()):
            occurrences = positions[name]
            expectations = [substitute_type_params(expected, type_bindings) for _, expected in occurrences]
            params = list(expectations[0].param_type_refs)
            if any(_type_ref_contains_type_param(item) for item in params):
                continue
            returns = [expected.return_type_ref for expected in expectations]
            authored_return = None
            if binding.return_type_name is not None:
                authored_return = creator["type_env"].resolve_type(
                    binding.return_type_name, span=binding.span, form_path=binding.form_path)
                returns.append(authored_return)
            expected_return = next((item for item in returns if not _type_ref_contains_type_param(item)), None)
            local_env = {capture: creator["value_env"][capture] for capture in binding.capture_names}
            local_env.update({param.name: typ for param, typ in zip(binding.params, params, strict=True)})
            local_ids = dict(creator["binding_env"])
            for param in binding.params:
                local_ids[param.name] = _allocate_binding_identity(
                    local_ids, form_path=binding.form_path, kind="param", name=param.name)
            session = creator["session_state"]
            previous = (session.workflow_signature, session.procedure_hidden_context_signature,
                        session.proc_ref_value_env, session.value_expr_env, session.pending_local_hook_preparer)
            local_signature = ProcedureSignature(name=name, params=tuple(local_env.items()),
                return_type_ref=expected_return or returns[0], declared_effects=frozenset(),
                requested_lowering_mode=ProcedureLoweringMode.AUTO,
                span=binding.span, form_path=binding.form_path, type_params=(), where_clauses=())
            session.workflow_signature = None
            session.procedure_hidden_context_signature = (
                local_signature if eligible_private_context_source_param_names(local_signature) else None)
            session.proc_ref_value_env = {capture: creator["creator_proc_refs"][capture]
                for capture in binding.capture_names if capture in creator["creator_proc_refs"]}
            session.value_expr_env = creator["creator_values"]
            session.pending_local_hook_preparer = None
            try:
                options = {key: value for key, value in creator.items()
                           if key not in {"creator_proc_refs", "creator_values"}}
                from .workflows import ProviderExtern

                body_env = {
                    extern_name: creator["type_env"].resolve_type(
                        "Provider" if isinstance(extern_binding, ProviderExtern) else "Prompt",
                        span=binding.span, form_path=binding.form_path,
                    )
                    for extern_name, extern_binding in getattr(
                        creator["extern_environment"], "bindings_by_name", {}
                    ).items()
                }
                body_env.update(local_env)
                options.update(value_env=body_env, binding_env=local_ids)
                if expected_return is not None:
                    options["expected_type"] = expected_return
                typed_body = _typecheck_owner(binding.local_body, **options)
            finally:
                (session.workflow_signature, session.procedure_hidden_context_signature,
                 session.proc_ref_value_env, session.value_expr_env, session.pending_local_hook_preparer) = previous
            if authored_return is not None and not type_refs_compatible(
                substitute_type_params(authored_return, type_bindings), typed_body.type_ref
            ):
                _raise_error("local body conflicts with its authored return type",
                    code="let_proc_return_type_invalid", span=binding.local_body.span,
                    form_path=binding.local_body.form_path, expansion_stack=binding.local_body.expansion_stack)
            actual = ProcRefTypeRef(name="ProcRef", param_type_refs=tuple(params), return_type_ref=typed_body.type_ref)
            for _, expected in occurrences:
                _infer_parametric_type_bindings(expected, actual, bindings=type_bindings,
                    raise_error=_raise_error, span=binding.span, form_path=binding.form_path)
            resolved = replace(binding,
                params=tuple(replace(param, type_name=typ.name) for param, typ in zip(binding.params, params, strict=True)),
                return_type_name=(substitute_type_params(authored_return, type_bindings).name
                                  if authored_return is not None else typed_body.type_ref.name))
            completed[name] = (resolved, typed_body)
            del pending[name]
            progress = True
        if not progress:
            binding = next(iter(pending.values()))
            _raise_error("local hook parameters are unresolved; add explicit annotations",
                code="let_proc_expected_signature_missing", span=binding.span, form_path=binding.form_path)
    return completed


def _typecheck_local_hook_group(expr, **creator):
    _validate_local_hook_sites(expr.body, expr.bindings)
    session = creator["session_state"]
    creator = dict(creator, value_env=dict(creator["value_env"]), binding_env=dict(creator["binding_env"]))
    creator_proc_refs, creator_values = dict(session.proc_ref_value_env), dict(session.value_expr_env)
    catalog = creator["procedure_catalog"]
    rewrites, resolved_refs, completed = {}, {}, set()

    def register(binding, typed_body):
        nonlocal catalog
        previous = session.proc_ref_value_env, session.value_expr_env, session.pending_local_hook_preparer
        session.proc_ref_value_env, session.value_expr_env = creator_proc_refs, creator_values
        session.pending_local_hook_preparer = None
        try:
            single = replace(expr, binding=binding, additional_bindings=())
            catalog, rewrite, resolved = _typecheck_let_proc_expr_impl(single,
                **dict(creator, procedure_catalog=catalog),
                _prepared_local_body=typed_body, _register_only=True)
        finally:
            session.proc_ref_value_env, session.value_expr_env, session.pending_local_hook_preparer = previous
        rewrites[binding.local_name] = rewrite
        resolved_refs[binding.local_name] = resolved
        completed.add(binding.local_name)

    for binding in expr.bindings:
        if _local_hook_is_complete(binding):
            register(binding, None)
    outer_body = _rewrite_local_proc_references(expr.body, local_bindings=rewrites)
    incomplete = {binding.local_name: binding for binding in expr.bindings if not _local_hook_is_complete(binding)}

    def prepare(call, *, context, recurse):
        names = {arg.target_name for arg in call.args
                 if isinstance(arg, ProcRefLiteralExpr) and arg.target_name in incomplete}
        if not names:
            return None
        pending = tuple(binding for binding in expr.bindings
                        if binding.local_name in names and binding.local_name not in completed)
        if pending:
            bound = context.active_proc_ref_value_env.get(call.callee_name)
            lexical_type = context.value_env.get(call.callee_name)
            signature = context.procedure_catalog.signatures_by_name.get(call.callee_name)
            if bound is not None or isinstance(lexical_type, ProcRefTypeRef):
                signature = ProcedureSignature(name=call.callee_name,
                    params=(bound.residual_params if bound is not None else tuple(
                        (str(index), typ) for index, typ in enumerate(lexical_type.param_type_refs))),
                    return_type_ref=(bound.return_type_ref if bound is not None else lexical_type.return_type_ref),
                    declared_effects=frozenset(), requested_lowering_mode=ProcedureLoweringMode.AUTO,
                    span=call.span, form_path=call.form_path, type_params=(), where_clauses=())
            prepared = _prepare_local_hook_call(call, pending,
                creator=dict(creator, creator_proc_refs=creator_proc_refs, creator_values=creator_values),
                signature=signature, recurse=recurse)
            for binding in pending:
                ready, body = prepared[binding.local_name]
                register(ready, body)
        rewritten = _rewrite_local_proc_references(call, local_bindings=rewrites)
        return recurse(rewritten, procedure_catalog=catalog,
                       proc_ref_value_env={**session.proc_ref_value_env, **resolved_refs})

    previous = session.proc_ref_value_env, session.pending_local_hook_preparer
    session.proc_ref_value_env = {**previous[0], **resolved_refs}
    session.pending_local_hook_preparer = prepare if incomplete else previous[1]
    try:
        typed = _typecheck_owner(outer_body, **dict(creator, procedure_catalog=catalog))
    finally:
        session.proc_ref_value_env, session.pending_local_hook_preparer = previous
    if incomplete.keys() - completed:
        binding = incomplete[next(iter(incomplete.keys() - completed))]
        _raise_error("local hook signature was not completed", code="let_proc_expected_signature_missing",
            span=binding.span, form_path=binding.form_path)
    final_body = _rewrite_local_proc_references(expr.body, local_bindings=rewrites)
    for rewrite in rewrites.values():
        if _expr_returns_local_proc_value(final_body, rewrite.generated_name,
            procedure_catalog=catalog, target_dsl_version=creator["type_env"].target_dsl_version,
            proc_ref_env=creator_proc_refs,
            compiler_session=creator["compiler_session"]):
            _raise_error("local procedure escaped its lexical scope", code="let_proc_scope_escape",
                span=expr.body.span, form_path=expr.body.form_path)
    retained = typed.expr if creator["compiler_session"].closed_program else _retain_capture_metadata(
        outer_body, typed.expr, procedure_catalog=catalog)
    session.let_proc_rewrite_results[id(expr)] = retained
    return replace(typed, expr=retained)


def _retain_capture_metadata(source, typed, *, procedure_catalog):
    """Keep the historical source tree, carrying only lexical capture facts."""
    metadata_fields = {
        "capture_origin", "binding_identity", "binding_identities",
        "binding_capture_sources", "source_binding_identity",
    }

    def retain(original, checked):
        if isinstance(original, TypeRef):
            return original
        if isinstance(original, tuple):
            if not isinstance(checked, tuple) or len(original) != len(checked):
                raise ValueError("capture metadata correspondence changed tuple topology")
            return tuple(retain(a, b) for a, b in zip(original, checked, strict=True))
        if not is_dataclass(original) or type(original).__module__ != NameExpr.__module__:
            return original
        if type(original) is not type(checked):
            raise ValueError("capture metadata correspondence changed expression kind")
        updates = {}
        if isinstance(original, NameExpr) and original.name != checked.name:
            raise ValueError("capture metadata correspondence changed value name")
        for field in fields(original):
            name = field.name
            if name in metadata_fields:
                updates[name] = getattr(checked, name)
                continue
            if isinstance(original, ProcedureCallExpr) and name == "args":
                checked_args = checked.args
                if len(original.args) != len(checked_args):
                    signature = procedure_catalog.signatures_by_name.get(original.callee_name)
                    if signature is None or len(signature.params) != len(original.args):
                        raise ValueError("capture metadata lacks authored procedure parameter slots")
                    retained = dict(checked.retained_reference_actuals)
                    prior_retained = dict(original.retained_reference_actuals)
                    new_retained = {k: v for k, v in retained.items() if k not in prior_retained}
                    parameter_names = {name for name, _ in signature.params}
                    if not set(new_retained).issubset(parameter_names):
                        raise ValueError("capture metadata retained reference has no authored slot")
                    residual = iter(checked_args)
                    aligned = []
                    for parameter_name, _ in signature.params:
                        if parameter_name in new_retained:
                            aligned.append(new_retained[parameter_name])
                        else:
                            try:
                                aligned.append(next(residual))
                            except StopIteration as error:
                                raise ValueError("capture metadata is missing a residual argument") from error
                    if next(residual, None) is not None:
                        raise ValueError("capture metadata has an unmatched residual argument")
                    checked_args = tuple(aligned)
                updates[name] = retain(original.args, checked_args)
                continue
            if name == "retained_reference_actuals":
                continue
            original_value = getattr(original, name)
            checked_value = getattr(checked, name)
            if isinstance(original_value, tuple) or (
                is_dataclass(original_value)
                and type(original_value).__module__ == NameExpr.__module__
            ):
                updates[name] = retain(original_value, checked_value)
        return replace(original, **updates)

    return retain(source, typed)


def _rewrite_local_proc_references(
    node: object,
    *,
    local_bindings: Mapping[str, LocalProcRewriteBinding],
):
    # Type references are resolved declaration owners, not expression trees.
    # Rebuilding their nested definition records loses the defining module
    # needed by canonical naming after source deletion.
    if isinstance(node, TypeRef):
        return node
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
            if field.name in {"run_ref_metadata", "run_ref_origin", "carrier_family", "owner_union", "discriminant_owner", "resolved_type_ref"}:
                continue
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
                source_binding_identity=binding_identity,
            )
            for (capture_name, capture_expr), binding_identity in zip(
                binding.capture_bindings,
                binding.capture_binding_identities,
                strict=True,
            )
        ),
        span=expr.span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )

def _expr_returns_local_proc_value(
    expr: ExprNode,
    generated_name: str,
    *,
    target_dsl_version: str,
    value_bindings: Mapping[str, bool] | None = None,
    procedure_catalog: ProcedureCatalog | None = None,
    proc_ref_env: Mapping[str, ResolvedProcRefValue] | None = None,
    visited_calls: frozenset[tuple[str, frozenset[str]]] = frozenset(),
    compiler_session: CompilerSession,
) -> bool:
    bindings = dict(value_bindings or {})
    active_proc_ref_env = dict(proc_ref_env or {})
    if isinstance(expr, ProcRefLiteralExpr):
        return expr.target_name == generated_name
    if isinstance(expr, BindProcExpr):
        if _expr_returns_local_proc_value(
            expr.base_expr,
            generated_name,
            target_dsl_version=target_dsl_version,
            value_bindings=bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=active_proc_ref_env,
            visited_calls=visited_calls,
            compiler_session=compiler_session,
        ):
            return True
        return any(
            _expr_returns_local_proc_value(
                binding.value_expr,
                generated_name,
                target_dsl_version=target_dsl_version,
                value_bindings=bindings,
                procedure_catalog=procedure_catalog,
                proc_ref_env=active_proc_ref_env,
                visited_calls=visited_calls,
                compiler_session=compiler_session,
            )
            for binding in expr.bindings
        )
    if isinstance(expr, NameExpr):
        return bindings.get(expr.name, False)
    if isinstance(expr, ProcedureCallExpr):
        return _procedure_call_returns_local_proc_value(
            expr,
            generated_name,
            target_dsl_version=target_dsl_version,
            value_bindings=bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=active_proc_ref_env,
            visited_calls=visited_calls,
            compiler_session=compiler_session,
        )
    if type(expr) is FunctionCallExpr:
        return _function_call_returns_local_proc_value(
            expr,
            generated_name,
            target_dsl_version=target_dsl_version,
            value_bindings=bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=active_proc_ref_env,
            visited_calls=visited_calls,
            compiler_session=compiler_session,
        )
    if isinstance(expr, RecordExpr):
        return any(
            _expr_returns_local_proc_value(
                field_expr,
                generated_name,
                target_dsl_version=target_dsl_version,
                value_bindings=bindings,
                procedure_catalog=procedure_catalog,
                proc_ref_env=active_proc_ref_env,
                visited_calls=visited_calls,
                compiler_session=compiler_session,
            )
            for _field_name, field_expr in expr.fields
        )
    if isinstance(expr, LetStarExpr):
        local_bindings = dict(bindings)
        local_proc_ref_env = dict(active_proc_ref_env)
        for binding_name, binding_expr in expr.bindings:
            local_bindings[binding_name] = _expr_returns_local_proc_value(
                binding_expr,
                generated_name,
                target_dsl_version=target_dsl_version,
                value_bindings=local_bindings,
                procedure_catalog=procedure_catalog,
                proc_ref_env=local_proc_ref_env,
                visited_calls=visited_calls,
                compiler_session=compiler_session,
            )
            if target_dsl_supports_local_hook_inference(target_dsl_version) and procedure_catalog is not None:
                resolved = resolve_proc_ref_value(binding_expr,
                    procedure_catalog=procedure_catalog, proc_ref_env=local_proc_ref_env)
                if resolved is None:
                    local_proc_ref_env.pop(binding_name, None)
                else:
                    local_proc_ref_env[binding_name] = resolved
        return _expr_returns_local_proc_value(
            expr.body,
            generated_name,
            target_dsl_version=target_dsl_version,
            value_bindings=local_bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=local_proc_ref_env,
            visited_calls=visited_calls,
            compiler_session=compiler_session,
        )
    if isinstance(expr, IfExpr):
        return _expr_returns_local_proc_value(
            expr.then_expr,
            generated_name,
            target_dsl_version=target_dsl_version,
            value_bindings=bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=active_proc_ref_env,
            visited_calls=visited_calls,
            compiler_session=compiler_session,
        ) or _expr_returns_local_proc_value(
            expr.else_expr,
            generated_name,
            target_dsl_version=target_dsl_version,
            value_bindings=bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=active_proc_ref_env,
            visited_calls=visited_calls,
            compiler_session=compiler_session,
        )
    if type(expr) is MatchExpr:
        for arm in expr.arms:
            arm_bindings = dict(bindings)
            arm_bindings[arm.binding_name] = False
            if _expr_returns_local_proc_value(
                arm.body,
                generated_name,
                target_dsl_version=target_dsl_version,
                value_bindings=arm_bindings,
                procedure_catalog=procedure_catalog,
                proc_ref_env=active_proc_ref_env,
                visited_calls=visited_calls,
                compiler_session=compiler_session,
            ):
                return True
        return False
    if isinstance(expr, WithPhaseExpr):
        return _expr_returns_local_proc_value(
            expr.body,
            generated_name,
            target_dsl_version=target_dsl_version,
            value_bindings=bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=active_proc_ref_env,
            visited_calls=visited_calls,
            compiler_session=compiler_session,
        )
    if isinstance(expr, (WithLiveProvidersExpr, WithLiveProviderPeersExpr)):
        return _expr_returns_local_proc_value(
            expr.body,
            generated_name,
            target_dsl_version=target_dsl_version,
            value_bindings=bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=active_proc_ref_env,
            visited_calls=visited_calls,
            compiler_session=compiler_session,
        )
    if isinstance(expr, ContinueExpr):
        return _expr_returns_local_proc_value(
            expr.state_expr,
            generated_name,
            target_dsl_version=target_dsl_version,
            value_bindings=bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=active_proc_ref_env,
            visited_calls=visited_calls,
            compiler_session=compiler_session,
        )
    if isinstance(expr, DoneExpr):
        result_returns_local = _expr_returns_local_proc_value(
            expr.result_expr,
            generated_name,
            target_dsl_version=target_dsl_version,
            value_bindings=bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=active_proc_ref_env,
            visited_calls=visited_calls,
            compiler_session=compiler_session,
        )
        if result_returns_local or expr.terminal_state_expr is None:
            return result_returns_local
        return _expr_returns_local_proc_value(
            expr.terminal_state_expr,
            generated_name,
            target_dsl_version=target_dsl_version,
            value_bindings=bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=active_proc_ref_env,
            visited_calls=visited_calls,
            compiler_session=compiler_session,
        )
    if isinstance(expr, LoopRecurExpr):
        loop_bindings = dict(bindings)
        loop_bindings[expr.binding_name] = False
        return _expr_returns_local_proc_value(
            expr.initial_state_expr,
            generated_name,
            target_dsl_version=target_dsl_version,
            value_bindings=bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=active_proc_ref_env,
            visited_calls=visited_calls,
            compiler_session=compiler_session,
        ) or _expr_returns_local_proc_value(
            expr.body_expr,
            generated_name,
            target_dsl_version=target_dsl_version,
            value_bindings=loop_bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=active_proc_ref_env,
            visited_calls=visited_calls,
            compiler_session=compiler_session,
        )
    if isinstance(expr, ResumeOrStartExpr):
        return _expr_returns_local_proc_value(
            expr.resume_from_expr,
            generated_name,
            target_dsl_version=target_dsl_version,
            value_bindings=bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=active_proc_ref_env,
            visited_calls=visited_calls,
            compiler_session=compiler_session,
        ) or _expr_returns_local_proc_value(
            expr.start_expr,
            generated_name,
            target_dsl_version=target_dsl_version,
            value_bindings=bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=active_proc_ref_env,
            visited_calls=visited_calls,
            compiler_session=compiler_session,
        )
    return False

def _procedure_call_returns_local_proc_value(
    expr: ProcedureCallExpr,
    generated_name: str,
    *,
    target_dsl_version: str,
    value_bindings: Mapping[str, bool],
    procedure_catalog: ProcedureCatalog | None,
    proc_ref_env: Mapping[str, ResolvedProcRefValue],
    visited_calls: frozenset[tuple[str, frozenset[str]]],
    compiler_session: CompilerSession,
) -> bool:
    if procedure_catalog is None:
        return False
    callee_value = proc_ref_env.get(expr.callee_name)
    if callee_value is not None:
        definition = procedure_catalog.definitions_by_name.get(callee_value.procedure_name)
        if definition is None and target_dsl_supports_local_hook_inference(target_dsl_version):
            return False
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
            target_dsl_version=target_dsl_version,
            value_bindings=value_bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=proc_ref_env,
            visited_calls=visited_calls,
            compiler_session=compiler_session,
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
            target_dsl_version=target_dsl_version,
            value_bindings=value_bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=proc_ref_env,
            visited_calls=visited_calls,
            compiler_session=compiler_session,
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
        function_catalog = compiler_session.typecheck.function_catalog
        body_expr = elaborate_expression(
            body_expr,
            bound_names=frozenset(name for name, _ in signature_params),
            procedure_names=frozenset(procedure_catalog.signatures_by_name),
            function_names=(
                frozenset()
                if function_catalog is None
                else frozenset(function_catalog.signatures_by_name)
            ),
            target_dsl_version=target_dsl_version,
            session_state=compiler_session.elaboration,
        )
    return _expr_returns_local_proc_value(
        body_expr,
        generated_name,
        target_dsl_version=target_dsl_version,
        value_bindings=local_bindings,
        procedure_catalog=procedure_catalog,
        proc_ref_env=local_proc_ref_env,
        visited_calls=visited_calls | {call_key},
        compiler_session=compiler_session,
    )

def _function_call_returns_local_proc_value(
    expr: FunctionCallExpr,
    generated_name: str,
    *,
    target_dsl_version: str,
    value_bindings: Mapping[str, bool],
    procedure_catalog: ProcedureCatalog | None,
    proc_ref_env: Mapping[str, ResolvedProcRefValue],
    visited_calls: frozenset[tuple[str, frozenset[str]]],
    compiler_session: CompilerSession,
) -> bool:
    function_catalog = compiler_session.typecheck.function_catalog
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
            target_dsl_version=target_dsl_version,
            value_bindings=value_bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=proc_ref_env,
            visited_calls=visited_calls,
            compiler_session=compiler_session,
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
            target_dsl_version=target_dsl_version,
            session_state=compiler_session.elaboration,
        )
    return _expr_returns_local_proc_value(
        body_expr,
        generated_name,
        target_dsl_version=target_dsl_version,
        value_bindings=local_bindings,
        procedure_catalog=procedure_catalog,
        proc_ref_env=proc_ref_env,
        visited_calls=visited_calls | {call_key},
        compiler_session=compiler_session,
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
            if field.name not in {
                "condition_normalization_input",
                "run_ref_metadata",
                "run_ref_origin",
                "carrier_family",
                "owner_union",
                "discriminant_owner",
                "resolved_type_ref",
            }
            for span in _collect_proc_ref_use_spans(getattr(node, field.name), authored_name=authored_name)
        )
    return ()

def _dataclass_semantic_identity(value):
    from .expressions import CommandResultExpr, ListMapEffectExpr

    identity_fields = tuple(
        item for item in fields(value)
        if item.name not in {"span", "form_path", "expansion_stack"}
        and not item.metadata.get("semantic_identity_omit")
        and not (isinstance(value, ListMapEffectExpr) and item.name in {"parallel_count", "workspace_expr"} and getattr(value, item.name) is None)
    )
    if isinstance(value, CommandResultExpr):
        identity_fields = tuple(
            item for item in identity_fields
            if not (item.name in {"inputs_present", "operand_order"} and not getattr(value, item.name))
        )
    return (f"{type(value).__name__}("
            + ",".join(f"{item.name}={_semantic_identity(getattr(value, item.name))}" for item in identity_fields)
            + ")")


def _semantic_identity(value: object) -> str:
    if is_dataclass(value):
        return _dataclass_semantic_identity(value)
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
        {} if let_proc_rewrite_results is None else let_proc_rewrite_results
    )
    replacement = rewrite_results.get(id(node))
    if replacement is not None:
        return _replace_eliminated_let_procs(
            replacement,
            let_proc_rewrite_results=rewrite_results,
        )
    # Checked TypeRefs carry the original nominal owner object.  Preserve that
    # identity while rewriting expression nodes around it.
    if isinstance(node, TypeRef):
        return node
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
            if field.name in {"run_ref_metadata", "run_ref_origin", "carrier_family", "owner_union", "discriminant_owner", "resolved_type_ref"}:
                continue
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
