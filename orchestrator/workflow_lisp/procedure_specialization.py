"""Procedure specialization ownership for Workflow Lisp stage-3 compilation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal
from types import MappingProxyType

from .contracts import derive_workflow_boundary_fields
from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .effects import EMPTY_EFFECT_SUMMARY
from .expression_traversal import _rebuild_with_replacements, iter_child_exprs
from .expressions import (
    BindProcExpr,
    GeneratedRelpathSeedExpr,
    LoopStateSeedExpr,
    LoopStateUpdateExpr,
    PhaseTargetExpr,
    ProcRefLiteralExpr,
    ProviderBundlePathExpr,
    CallExpr,
    FieldAccessExpr,
    ExprNode,
    EnumMemberExpr,
    IfExpr,
    LetStarExpr,
    LiteralExpr,
    ListExpr,
    NameExpr,
    ProcedureCallExpr,
    RecordExpr,
    UnionVariantExpr,
    WorkflowRefLiteralExpr,
)
from .procedure_refs import ResolvedProcRefValue, resolve_proc_ref_value
from .procedures import (
    ProcedureCallableSpecialization,
    ProcedureCatalog,
    ProcedureLoweringMode,
    ProcedureParam,
    TypedProcedureDef,
    parametric_specialization_name,
    proc_ref_specialization_name as proc_ref_call_specialization_name,
    procedure_type_env_for,
)
from .result_guidance import validate_result_guidance_example
from .type_env import (
    FrontendTypeEnvironment,
    ProcRefTypeRef,
    RecordTypeRef,
    TypeRef,
    UnionTypeRef,
    WorkflowRefTypeRef,
    render_type_ref,
    substitute_type_params,
)
from .workflow_refs import (
    ResolvedWorkflowRef,
    collision_specialization_name,
    resolve_workflow_ref_expr,
    specialization_name,
    workflow_ref_binding_identity,
)
from .workflows import TypedWorkflowDef


@dataclass(frozen=True)
class ProcedureSpecializationRequest:
    """Compile-time-only specialization inputs for one procedure materialization."""

    procedure: TypedProcedureDef
    type_bindings: Mapping[str, TypeRef]
    workflow_ref_bindings: Mapping[str, ResolvedWorkflowRef]
    proc_ref_bindings: Mapping[str, ResolvedProcRefValue]
    value_bindings: Mapping[str, Any]
    shared_union_field_capabilities: tuple[object, ...]
    remaining_params: tuple[tuple[str, TypeRef], ...]
    workflow_path: Path
    typed_procedures_by_name: Mapping[str, TypedProcedureDef]
    specialized_name: str | None = None
    origin_span: object | None = None
    origin_form_path: tuple[str, ...] | None = None


def procedure_catalog_with_specializations(
    procedure_catalog: ProcedureCatalog,
    typed_procedures: tuple[TypedProcedureDef, ...],
) -> ProcedureCatalog:
    signatures_by_name = dict(procedure_catalog.signatures_by_name)
    definitions_by_name = dict(procedure_catalog.definitions_by_name)
    for procedure in typed_procedures:
        signatures_by_name[procedure.signature.name] = procedure.signature
        definitions_by_name[procedure.definition.name] = procedure.definition
    return ProcedureCatalog(
        signatures_by_name=signatures_by_name,
        definitions_by_name=definitions_by_name,
        call_graph=procedure_catalog.call_graph,
    )


def materialized_specialization_rows(
    procedure: TypedProcedureDef,
    *,
    workflow_ref_bindings: Mapping[str, ResolvedWorkflowRef],
    proc_ref_bindings: Mapping[str, ResolvedProcRefValue],
    typed_procedures: Mapping[str, TypedProcedureDef],
) -> tuple[TypedProcedureDef, ...]:
    """Select exact compiler-owned rows without reconstructing their keys."""

    existing = procedure.specialization
    base_name = existing.base_name if existing is not None else procedure.signature.name
    expected_workflow_bindings = {
        **dict(getattr(existing, "workflow_ref_bindings", {})),
        **dict(workflow_ref_bindings),
    }
    expected_proc_bindings = {
        **dict(getattr(existing, "proc_ref_bindings", {})),
        **dict(proc_ref_bindings),
    }
    expected_proc_identity = tuple(
        sorted(
            (param_name, resolved.call_target_name)
            for param_name, resolved in expected_proc_bindings.items()
        )
    )
    matches: list[TypedProcedureDef] = []
    for candidate in typed_procedures.values():
        specialization = candidate.specialization
        if specialization is None or specialization.base_name != base_name:
            continue
        if workflow_ref_binding_identity(
            specialization.workflow_ref_bindings
        ) != workflow_ref_binding_identity(expected_workflow_bindings):
            continue
        candidate_proc_identity = tuple(
            sorted(
                (param_name, resolved.call_target_name)
                for param_name, resolved in specialization.proc_ref_bindings.items()
            )
        )
        if candidate_proc_identity != expected_proc_identity:
            continue
        if dict(specialization.type_bindings) != dict(
            getattr(existing, "type_bindings", {})
        ):
            continue
        if dict(specialization.value_bindings) != dict(
            getattr(existing, "value_bindings", {})
        ):
            continue
        matches.append(candidate)
    return tuple(matches)


def _substitute_capture_origin_types(
    expr: ExprNode,
    type_bindings: Mapping[str, TypeRef],
) -> ExprNode:
    """Specialize retained creator types without changing their lexical owners."""

    if not type_bindings:
        return expr

    bindings = dict(type_bindings)
    rewritten_by_id: dict[int, ExprNode] = {}

    def origin_type(origin):
        if origin is None:
            return None
        identity, original_type = origin
        substituted = substitute_type_params(original_type, bindings)
        return origin if substituted == original_type else (identity, substituted)

    def rewrite(node: ExprNode) -> ExprNode:
        known = rewritten_by_id.get(id(node))
        if known is not None:
            return known
        # Field bases are leaves for ordinary traversal, but carry retained
        # creator facts just like standalone lexical references.
        children = (node.base,) if isinstance(node, FieldAccessExpr) else iter_child_exprs(node)
        if isinstance(node, LetStarExpr) and node.condition_normalization_input is not None:
            children = (*children, node.condition_normalization_input)
        replacements = {id(child): rewrite(child) for child in children}
        rewritten = (
            _rebuild_with_replacements(node, replacements)
            if any(replacements[id(child)] is not child for child in children)
            else node
        )
        if isinstance(rewritten, ListExpr):
            rewritten = replace(rewritten,
                element_type_ref=(substitute_type_params(rewritten.element_type_ref, bindings)
                    if rewritten.element_type_ref is not None else None),
                item_type_refs=tuple(substitute_type_params(ref, bindings) for ref in rewritten.item_type_refs))
        if isinstance(rewritten, NameExpr):
            origin = origin_type(rewritten.capture_origin)
            if origin is not rewritten.capture_origin:
                rewritten = replace(rewritten, capture_origin=origin)
        elif isinstance(rewritten, LetStarExpr):
            sources = tuple(origin_type(source) for source in rewritten.binding_capture_sources)
            if any(new is not old for new, old in zip(sources, rewritten.binding_capture_sources, strict=True)):
                rewritten = replace(rewritten, binding_capture_sources=sources)
        rewritten_by_id[id(node)] = rewritten
        return rewritten

    return rewrite(expr)


def specialize_typed_procedure(
    procedure: TypedProcedureDef,
    *,
    type_bindings: Mapping[str, TypeRef] | None = None,
    workflow_ref_bindings: Mapping[str, ResolvedWorkflowRef] | None = None,
    proc_ref_bindings: Mapping[str, ResolvedProcRefValue] | None = None,
    value_bindings: Mapping[str, Any] | None = None,
    shared_union_field_capabilities: tuple[object, ...] = (),
    remaining_params: tuple[tuple[str, TypeRef], ...],
    workflow_path: Path,
    type_env: FrontendTypeEnvironment,
    typed_procedures_by_name: Mapping[str, TypedProcedureDef],
    procedure_type_envs: Mapping[str, FrontendTypeEnvironment] | None = None,
    specialized_name: str | None = None,
    origin_span=None,
    origin_form_path: tuple[str, ...] | None = None,
    defer_lowering_resolution: bool = False,
    preserve_inherited_bound_params: bool = False,
) -> TypedProcedureDef:
    existing_specialization = getattr(procedure, "specialization", None)
    merged_type_bindings = {
        **dict(getattr(existing_specialization, "type_bindings", {})),
        **dict(type_bindings or {}),
    }
    merged_workflow_ref_bindings = {
        **dict(getattr(existing_specialization, "workflow_ref_bindings", {})),
        **dict(workflow_ref_bindings or {}),
    }
    merged_proc_ref_bindings = {
        **dict(getattr(existing_specialization, "proc_ref_bindings", {})),
        **dict(proc_ref_bindings or {}),
    }
    merged_value_bindings = {
        **dict(getattr(existing_specialization, "value_bindings", {})),
        **dict(value_bindings or {}),
    }
    request = ProcedureSpecializationRequest(
        procedure=procedure,
        type_bindings=merged_type_bindings,
        workflow_ref_bindings=merged_workflow_ref_bindings,
        proc_ref_bindings=merged_proc_ref_bindings,
        value_bindings=merged_value_bindings,
        shared_union_field_capabilities=shared_union_field_capabilities,
        remaining_params=remaining_params,
        workflow_path=workflow_path,
        typed_procedures_by_name=typed_procedures_by_name,
        specialized_name=specialized_name,
        origin_span=origin_span,
        origin_form_path=origin_form_path,
    )
    substituted_signature_params = tuple(
        (
            name,
            substitute_type_params(type_ref, dict(request.type_bindings)),
        )
        for name, type_ref in request.procedure.signature.params
    )
    bound_param_types = {
        name: type_ref
        for name, type_ref in substituted_signature_params
        if (
            name in request.workflow_ref_bindings
            or name in request.proc_ref_bindings
            or name in request.value_bindings
        )
    }
    # A residual-reference specialization retains the static creator facts
    # of its already-bound parent row, whose params no longer list them.
    bound_param_types = {
        **dict(getattr(existing_specialization, "bound_param_types", {})),
        **bound_param_types,
    }
    bound_names = set(bound_param_types)
    if request.specialized_name is None:
        specialized_name = (
            parametric_specialization_name(request.procedure.signature.name, request.type_bindings)
            if request.type_bindings
            else request.procedure.signature.name
        )
        if request.workflow_ref_bindings:
            specialized_name = specialization_name(specialized_name, request.workflow_ref_bindings)
        if request.proc_ref_bindings:
            specialized_name = proc_ref_call_specialization_name(specialized_name, request.proc_ref_bindings)
    else:
        specialized_name = request.specialized_name
    substituted_return_type = substitute_type_params(
        request.procedure.signature.return_type_ref,
        dict(request.type_bindings),
    )
    specialization = ProcedureCallableSpecialization(
        base_name=getattr(existing_specialization, "base_name", request.procedure.signature.name),
        specialization_key=specialized_name,
        type_bindings=request.type_bindings,
        workflow_ref_bindings=request.workflow_ref_bindings,
        proc_ref_bindings=request.proc_ref_bindings,
        value_bindings=request.value_bindings,
        bound_param_types=bound_param_types,
        shared_union_field_capabilities=request.shared_union_field_capabilities,
        specialized_name=specialized_name,
        origin_span=request.origin_span or request.procedure.definition.span,
        origin_form_path=request.origin_form_path or request.procedure.definition.form_path,
    )
    specialized = TypedProcedureDef(
        definition=replace(
            request.procedure.definition,
            name=specialized_name,
            params=tuple(
                ProcedureParam(
                    name=param.name,
                    type_name=render_type_ref(
                        substitute_type_params(
                            next(
                                type_ref
                                for param_name, type_ref in request.procedure.signature.params
                                if param_name == param.name
                            ),
                            dict(request.type_bindings),
                        )
                    ),
                    span=param.span,
                    form_path=param.form_path,
                    expansion_stack=param.expansion_stack,
                    binding_label=param.binding_label,
                )
                for param in request.procedure.definition.params
                if param.name not in bound_names
            ),
            return_spec=replace(
                request.procedure.definition.return_spec,
                type_name=render_type_ref(substituted_return_type),
            ),
            return_type_name=render_type_ref(substituted_return_type),
            type_params=(),
            where_clauses=(),
        ),
        signature=replace(
            request.procedure.signature,
            name=specialized_name,
            params=request.remaining_params,
            return_type_ref=substituted_return_type,
            type_params=(),
            where_clauses=(),
        ),
        typed_body=replace(
            request.procedure.typed_body,
            expr=_substitute_capture_origin_types(
                request.procedure.typed_body.expr, request.type_bindings,
            ),
        ),
        # Deferred objects are compiler-owned re-typecheck targets, not
        # completed specializations. Non-deferred specializations are still
        # consumed on the lowering compatibility path, so preserve their
        # conservative carrier until that path also moves before lowering.
        direct_effect_summary=(
            EMPTY_EFFECT_SUMMARY
            if defer_lowering_resolution
            else request.procedure.direct_effect_summary
        ),
        transitive_effect_summary=(
            EMPTY_EFFECT_SUMMARY
            if defer_lowering_resolution
            else request.procedure.transitive_effect_summary
        ),
        resolved_lowering_mode=ProcedureLoweringMode.INLINE,
        generated_workflow_name=None,
        specialization=specialization,
    )
    if (
        request.procedure.signature.type_params
        and all(
            type_param.name in request.type_bindings
            for type_param in request.procedure.signature.type_params
        )
        and request.procedure.definition.return_spec.guidance is not None
        and request.procedure.definition.return_spec.guidance.example_expr is not None
    ):
        validate_result_guidance_example(
            specialized.definition.return_spec.guidance,
            expected_type=substituted_return_type,
            type_env=type_env,
        )
    return replace(
        specialized,
        resolved_lowering_mode=ProcedureLoweringMode.INLINE,
        generated_workflow_name=None,
    )


def bound_proc_ref_request(
    resolved: ResolvedProcRefValue,
    *,
    typed_procedures_by_name: Mapping[str, TypedProcedureDef],
    procedure_catalog: ProcedureCatalog,
    proc_ref_env: Mapping[str, ResolvedProcRefValue],
    type_env: FrontendTypeEnvironment,
    procedure_type_envs: Mapping[str, FrontendTypeEnvironment] | None = None,
    origin_span=None,
    origin_form_path: tuple[str, ...] | None = None,
    workflow_catalog=None,
    workflow_ref_env=None,
    typed_workflows_by_name=None,
) -> TypedProcedureDef | None:
    if not resolved.bound_args:
        return None
    base_procedure = typed_procedures_by_name.get(resolved.procedure_name)
    if base_procedure is None:
        return None
    proc_ref_bindings: dict[str, ResolvedProcRefValue] = {}
    value_bindings: dict[str, object] = {}
    workflow_ref_bindings = {}
    for binding in resolved.bound_args:
        if isinstance(binding.type_ref, ProcRefTypeRef):
            resolved_binding = resolve_proc_ref_value(
                binding.value_expr,
                procedure_catalog=procedure_catalog,
                proc_ref_env=proc_ref_env,
                expected_type=binding.type_ref,
            )
            if resolved_binding is not None:
                proc_ref_bindings[binding.name] = resolved_binding
            continue
        if isinstance(binding.type_ref, WorkflowRefTypeRef):
            expression = binding.value_expr
            if isinstance(expression, NameExpr) and expression.name in (workflow_ref_env or {}):
                reference = workflow_ref_env[expression.name]
                if reference is None:
                    return None
            else:
                reference = resolve_workflow_ref_expr(expression, workflow_catalog=workflow_catalog,
                    span=expression.span, form_path=expression.form_path,
                    expansion_stack=expression.expansion_stack, expected_type=binding.type_ref,
                    typed_workflows_by_name=typed_workflows_by_name, allow_extern_rebinding=True)
            workflow_ref_bindings[binding.name] = reference
            continue
        value_bindings[binding.name] = binding.value_expr
    return specialize_typed_procedure(
        base_procedure,
        proc_ref_bindings=proc_ref_bindings,
        workflow_ref_bindings=workflow_ref_bindings,
        value_bindings=value_bindings,
        remaining_params=resolved.residual_params,
        workflow_path=Path(base_procedure.definition.span.start.path),
        type_env=procedure_type_env_for(
            base_procedure,
            procedure_type_envs=procedure_type_envs,
            default=type_env,
        ),
        typed_procedures_by_name=typed_procedures_by_name,
        procedure_type_envs=procedure_type_envs,
        specialized_name=resolved.call_target_name,
        origin_span=origin_span,
        origin_form_path=origin_form_path,
        # Discovery products are inserted into the compiler's procedure-target
        # fixed point and authoritatively re-typechecked before lowering.  Do
        # not validate private-workflow eligibility or retain stale effects on
        # this provisional object.
        defer_lowering_resolution=True,
    )


def discover_proc_ref_specializations(
    *,
    typed_procedures: tuple[TypedProcedureDef, ...],
    typed_workflows: tuple[TypedWorkflowDef, ...],
    procedure_catalog: ProcedureCatalog,
    type_env: FrontendTypeEnvironment,
    visible_typed_procedures_by_name: Mapping[str, TypedProcedureDef] | None = None,
    procedure_type_envs: Mapping[str, FrontendTypeEnvironment] | None = None,
    workflow_catalog=None,
) -> tuple[TypedProcedureDef, ...]:
    from .expressions import LetStarExpr, ProcedureCallExpr

    discovered: dict[str, TypedProcedureDef] = {}
    typed_procedures_by_name = {
        **dict(visible_typed_procedures_by_name or {}),
        **{procedure.definition.name: procedure for procedure in typed_procedures},
    }

    def record_specialization(
        specialized: TypedProcedureDef | None,
    ) -> None:
        if specialized is None:
            return
        if specialized.definition.name in typed_procedures_by_name:
            return
        discovered.setdefault(specialized.definition.name, specialized)

    def walk(node: object, proc_ref_env: Mapping[str, ResolvedProcRefValue], workflow_ref_env) -> None:
        if isinstance(node, ProcedureCallExpr):
            bound_proc_ref = proc_ref_env.get(node.callee_name)
            if bound_proc_ref is not None:
                record_specialization(
                    bound_proc_ref_request(
                        bound_proc_ref,
                        typed_procedures_by_name=typed_procedures_by_name,
                        procedure_catalog=procedure_catalog,
                        proc_ref_env=proc_ref_env,
                        type_env=type_env,
                        procedure_type_envs=procedure_type_envs,
                        origin_span=node.span,
                        origin_form_path=node.form_path,
                        workflow_catalog=workflow_catalog,
                        workflow_ref_env=workflow_ref_env,
                        typed_workflows_by_name={row.definition.name: row for row in typed_workflows},
                    )
                )
            # A bound consumer can still receive reference-valued residual
            # arguments. Its static row is discovered above; once settled,
            # use that same ordinary specialization path for the actuals.
            callee_name = (bound_proc_ref.call_target_name
                           if bound_proc_ref is not None else node.callee_name)
            signature = procedure_catalog.signatures_by_name.get(callee_name)
            if signature is not None:
                if len(node.args) != len(signature.params):
                    for arg in node.args:
                        walk(arg, proc_ref_env, workflow_ref_env)
                    return
                proc_ref_bindings: dict[str, ResolvedProcRefValue] = {}
                for arg_expr, (param_name, param_type) in zip(node.args, signature.params, strict=True):
                    if not isinstance(param_type, ProcRefTypeRef):
                        continue
                    resolved_binding = resolve_proc_ref_value(
                        arg_expr,
                        procedure_catalog=procedure_catalog,
                        proc_ref_env=proc_ref_env,
                        expected_type=param_type,
                    )
                    if resolved_binding is not None:
                        proc_ref_bindings[param_name] = resolved_binding
                if proc_ref_bindings:
                    base_procedure = typed_procedures_by_name.get(callee_name)
                    if base_procedure is not None:
                        record_specialization(
                            specialize_typed_procedure(
                                base_procedure,
                                proc_ref_bindings=proc_ref_bindings,
                                remaining_params=tuple(
                                    (param_name, param_type)
                                    for param_name, param_type in signature.params
                                    if param_name not in proc_ref_bindings
                                ),
                                workflow_path=Path(base_procedure.definition.span.start.path),
                                type_env=procedure_type_env_for(
                                    base_procedure,
                                    procedure_type_envs=procedure_type_envs,
                                    default=type_env,
                                ),
                                typed_procedures_by_name=typed_procedures_by_name,
                                procedure_type_envs=procedure_type_envs,
                                specialized_name=proc_ref_call_specialization_name(
                                    signature.name,
                                    proc_ref_bindings,
                                ),
                                origin_span=node.span,
                                origin_form_path=node.form_path,
                                # The compiler records this discovery
                                # product, continues the fixed point, and
                                # re-typechecks it before lowering.
                                defer_lowering_resolution=True,
                                preserve_inherited_bound_params=bound_proc_ref is not None,
                            )
                        )
            for arg in node.args:
                walk(arg, proc_ref_env, workflow_ref_env)
            return
        if isinstance(node, LetStarExpr):
            child_env = dict(proc_ref_env)
            child_workflow_env = dict(workflow_ref_env)
            for binding_name, binding_expr in node.bindings:
                walk(binding_expr, child_env, child_workflow_env)
                resolved_binding = resolve_proc_ref_value(
                    binding_expr,
                    procedure_catalog=procedure_catalog,
                    proc_ref_env=child_env,
                )
                if resolved_binding is not None:
                    child_env[binding_name] = resolved_binding
                if isinstance(binding_expr, NameExpr) and binding_expr.name in child_workflow_env:
                    child_workflow_env[binding_name] = child_workflow_env[binding_expr.name]
                elif isinstance(binding_expr, WorkflowRefLiteralExpr):
                    child_workflow_env[binding_name] = resolve_workflow_ref_expr(binding_expr,
                        workflow_catalog=workflow_catalog, span=binding_expr.span,
                        form_path=binding_expr.form_path, expansion_stack=binding_expr.expansion_stack,
                        typed_workflows_by_name={row.definition.name: row for row in typed_workflows},
                        allow_extern_rebinding=True)
            walk(node.body, child_env, child_workflow_env)
            return
        for child in iter_child_exprs(node):
            walk(child, proc_ref_env, workflow_ref_env)

    for procedure in typed_procedures:
        proc_ref_env = dict(getattr(procedure.specialization, "proc_ref_bindings", {}))
        workflow_ref_env = {formal: None for formal, ref in procedure.signature.params
            if isinstance(ref, WorkflowRefTypeRef)}
        workflow_ref_env.update(getattr(procedure.specialization, "workflow_ref_bindings", {}))
        walk(procedure.typed_body.expr, proc_ref_env, workflow_ref_env)
    for workflow in typed_workflows:
        walk(workflow.typed_body.expr, {}, {})
    return tuple(discovered.values())


def _same_specialization_bindings(
    left: TypedProcedureDef,
    right: TypedProcedureDef,
) -> bool:
    """Compare every compile-time binding carried by two specialization rows."""

    left_specialization = left.specialization
    right_specialization = right.specialization
    if left_specialization is None or right_specialization is None:
        return left_specialization is right_specialization
    return (
        left_specialization.base_name == right_specialization.base_name
        and dict(left_specialization.type_bindings)
        == dict(right_specialization.type_bindings)
        and workflow_ref_binding_identity(left_specialization.workflow_ref_bindings)
        == workflow_ref_binding_identity(right_specialization.workflow_ref_bindings)
        and tuple(
            sorted(
                (param_name, resolved.call_target_name)
                for param_name, resolved in left_specialization.proc_ref_bindings.items()
            )
        )
        == tuple(
            sorted(
                (param_name, resolved.call_target_name)
                for param_name, resolved in right_specialization.proc_ref_bindings.items()
            )
        )
        and dict(left_specialization.value_bindings)
        == dict(right_specialization.value_bindings)
    )


def _walk_workflow_ref_bindings(node, workflow_ref_env, *, resolve_alias,
    on_procedure_call=None, on_workflow_call=None):
    """Share discovery's lexical reference scopes with read-only call inspection."""
    def walk(child, env):
        _walk_workflow_ref_bindings(child, env, resolve_alias=resolve_alias,
            on_procedure_call=on_procedure_call, on_workflow_call=on_workflow_call)

    if isinstance(node, ProcedureCallExpr):
        if on_procedure_call is not None:
            on_procedure_call(node, workflow_ref_env)
        for arg in node.args:
            walk(arg, workflow_ref_env)
        return
    if isinstance(node, CallExpr) and on_workflow_call is not None:
        on_workflow_call(node, workflow_ref_env)
    if isinstance(node, LetStarExpr):
        child_env = dict(workflow_ref_env)
        for name, binding in node.bindings:
            walk(binding, child_env)
            if isinstance(binding, NameExpr) and binding.name in child_env:
                child_env[name] = child_env[binding.name]
            elif isinstance(binding, (WorkflowRefLiteralExpr, NameExpr, EnumMemberExpr)):
                resolved = resolve_alias(binding)
                if resolved is not None:
                    child_env[name] = resolved
        walk(node.body, child_env)
        return
    for child in iter_child_exprs(node):
        walk(child, workflow_ref_env)


def _procedure_workflow_ref_bindings(procedure):
    return {**{name: None for name, ref in procedure.signature.params
        if isinstance(ref, WorkflowRefTypeRef)},
        **dict(getattr(procedure.specialization, "workflow_ref_bindings", {}))}


def unresolved_workflow_ref_calls(procedure) -> tuple[str, ...]:
    """Report actual calls through unbound roles using discovery's lexical walk."""
    pending = set()

    def inspect_call(node, env):
        if node.callee_name in env and env[node.callee_name] is None:
            pending.add(node.callee_name)

    # Only the unbound/concrete distinction is needed here; literals are opaque
    # concrete markers, so inspection neither resolves names nor creates rows.
    _walk_workflow_ref_bindings(procedure.typed_body.expr,
        _procedure_workflow_ref_bindings(procedure), resolve_alias=lambda expr: expr,
        on_workflow_call=inspect_call)
    return tuple(sorted(pending))


def discover_workflow_ref_specializations(
    *,
    typed_procedures: tuple[TypedProcedureDef, ...],
    typed_workflows: tuple[TypedWorkflowDef, ...],
    procedure_catalog: ProcedureCatalog,
    workflow_catalog: object,
    type_env: FrontendTypeEnvironment,
    visible_typed_procedures_by_name: Mapping[str, TypedProcedureDef] | None = None,
    procedure_type_envs: Mapping[str, FrontendTypeEnvironment] | None = None,
    on_reference_call=None,
) -> tuple[TypedProcedureDef, ...]:
    """Discover concrete WorkflowRef procedure calls for the Stage-3 fixed point."""

    candidates_by_legacy_name: dict[str, list[TypedProcedureDef]] = {}
    typed_procedures_by_name = {
        **dict(visible_typed_procedures_by_name or {}),
        **{
            procedure.definition.name: procedure
            for procedure in typed_procedures
        },
    }

    def record_specialization(specialized: TypedProcedureDef | None) -> None:
        if specialized is None:
            return
        candidates = candidates_by_legacy_name.setdefault(
            specialized.definition.name,
            [],
        )
        if any(
            _same_specialization_bindings(candidate, specialized)
            for candidate in candidates
        ):
            return
        candidates.append(specialized)

    def resolve_binding(
        arg_expr: object,
        *,
        expected_type: WorkflowRefTypeRef,
        workflow_ref_env: Mapping[str, ResolvedWorkflowRef],
    ) -> ResolvedWorkflowRef | None:
        if isinstance(arg_expr, NameExpr) and arg_expr.name in workflow_ref_env:
            return workflow_ref_env[arg_expr.name]
        if not isinstance(arg_expr, (WorkflowRefLiteralExpr, NameExpr, EnumMemberExpr)):
            return None
        return resolve_workflow_ref_expr(
            arg_expr,
            workflow_catalog=workflow_catalog,
            span=arg_expr.span,
            form_path=arg_expr.form_path,
            expansion_stack=arg_expr.expansion_stack,
            expected_type=expected_type,
            typed_workflows_by_name={
                workflow.definition.name: workflow for workflow in typed_workflows
            },
            allow_extern_rebinding=True,
        )

    def discover_call(node, workflow_ref_env):
        selected_reference_row = None
        bound_proc_ref = proc_ref_env.get(node.callee_name)
        callee_name = (
            bound_proc_ref.call_target_name
            if bound_proc_ref is not None
            else node.callee_name
        )
        procedure = typed_procedures_by_name.get(callee_name)
        signature = (
            procedure.signature
            if procedure is not None
            else procedure_catalog.signatures_by_name.get(callee_name)
        )
        if procedure is not None and signature is not None and len(node.args) == len(signature.params):
            workflow_ref_bindings: dict[str, ResolvedWorkflowRef] = {}
            proc_ref_bindings: dict[str, ResolvedProcRefValue] = {}
            remaining_params: list[tuple[str, TypeRef]] = []
            for arg_expr, (param_name, param_type) in zip(
                node.args,
                signature.params,
                strict=True,
            ):
                if isinstance(param_type, WorkflowRefTypeRef):
                    resolved = resolve_binding(
                        arg_expr,
                        expected_type=param_type,
                        workflow_ref_env=workflow_ref_env,
                    )
                    if resolved is not None:
                        workflow_ref_bindings[param_name] = resolved
                        continue
                if isinstance(param_type, ProcRefTypeRef):
                    resolved_proc_ref = resolve_proc_ref_value(
                        arg_expr,
                        procedure_catalog=procedure_catalog,
                        proc_ref_env=proc_ref_env,
                        expected_type=param_type,
                    )
                    if resolved_proc_ref is not None:
                        proc_ref_bindings[param_name] = resolved_proc_ref
                        continue
                remaining_params.append((param_name, param_type))
            if workflow_ref_bindings:
                record_specialization(
                    specialize_typed_procedure(
                        procedure,
                        workflow_ref_bindings=workflow_ref_bindings,
                        proc_ref_bindings=proc_ref_bindings,
                        remaining_params=tuple(remaining_params),
                        workflow_path=Path(procedure.definition.span.start.path),
                        type_env=procedure_type_env_for(
                            procedure,
                            procedure_type_envs=procedure_type_envs,
                            default=type_env,
                        ),
                        typed_procedures_by_name=typed_procedures_by_name,
                        procedure_type_envs=procedure_type_envs,
                        origin_span=node.span,
                        origin_form_path=node.form_path,
                        defer_lowering_resolution=True,
                    )
                )
            if on_reference_call is not None and any(
                isinstance(ref, WorkflowRefTypeRef) for _, ref in signature.params
            ):
                rows = materialized_specialization_rows(
                    procedure, workflow_ref_bindings=workflow_ref_bindings,
                    proc_ref_bindings=proc_ref_bindings,
                    typed_procedures=typed_procedures_by_name,
                )
                selected_reference_row = rows[0].definition.name if len(rows) == 1 else None
        if on_reference_call is not None:
            on_reference_call(owner, node, selected_reference_row)

    def retain_workflow_call(node, workflow_ref_env):
        if node.callee_name in workflow_ref_env:
            reference = workflow_ref_env[node.callee_name]
            on_reference_call(owner, node,
                reference.workflow_name if reference is not None else None)
        else:
            on_reference_call(owner, node, node.callee_name)

    def resolve_alias(binding_expr):
        try:
            return resolve_workflow_ref_expr(
                binding_expr, workflow_catalog=workflow_catalog,
                span=binding_expr.span, form_path=binding_expr.form_path,
                expansion_stack=binding_expr.expansion_stack,
                typed_workflows_by_name={row.definition.name: row for row in typed_workflows},
                allow_extern_rebinding=True,
            )
        except LispFrontendCompileError:
            return None

    for procedure in typed_procedures:
        owner = procedure.definition.name
        proc_ref_env = dict(getattr(procedure.specialization, "proc_ref_bindings", {}))
        _walk_workflow_ref_bindings(procedure.typed_body.expr,
            _procedure_workflow_ref_bindings(procedure), resolve_alias=resolve_alias,
            on_procedure_call=discover_call,
            on_workflow_call=retain_workflow_call if on_reference_call is not None else None)
    for workflow in typed_workflows:
        owner = workflow.definition.name
        proc_ref_env = {}
        _walk_workflow_ref_bindings(workflow.typed_body.expr, {}, resolve_alias=resolve_alias,
            on_procedure_call=discover_call,
            on_workflow_call=retain_workflow_call if on_reference_call is not None else None)

    discovered: dict[str, tuple[tuple[tuple[str, str], ...], TypedProcedureDef]] = {}
    for legacy_name, candidates in candidates_by_legacy_name.items():
        existing_legacy_row = typed_procedures_by_name.get(legacy_name)
        collision_group = len(candidates) > 1 or (
            existing_legacy_row is not None
            and not any(
                _same_specialization_bindings(existing_legacy_row, candidate)
                for candidate in candidates
            )
        )
        for candidate in candidates:
            if any(
                _same_specialization_bindings(existing, candidate)
                for existing in typed_procedures_by_name.values()
            ):
                # Fixed-point rediscovery reuses the exact compiler row even
                # when a later candidate turns its legacy key into a group.
                continue
            identity = workflow_ref_binding_identity(
                candidate.specialization.workflow_ref_bindings
            )
            final_name = (
                collision_specialization_name(
                    legacy_name,
                    candidate.specialization.workflow_ref_bindings,
                )
                if collision_group
                else legacy_name
            )
            if final_name != candidate.definition.name:
                candidate = replace(
                    candidate,
                    definition=replace(candidate.definition, name=final_name),
                    signature=replace(candidate.signature, name=final_name),
                    specialization=replace(
                        candidate.specialization,
                        specialized_name=final_name,
                        specialization_key=final_name,
                    ),
                )

            existing = typed_procedures_by_name.get(final_name)
            if existing is not None:
                if not _same_specialization_bindings(existing, candidate):
                    raise LispFrontendCompileError(
                        (
                            LispFrontendDiagnostic(
                                code="procedure_specialization_key_collision",
                                message=(
                                    "procedure specialization key "
                                    f"`{final_name}` has conflicting WorkflowRef bindings"
                                ),
                                span=candidate.definition.span,
                                form_path=candidate.definition.form_path,
                            ),
                        )
                    )
                continue

            prior = discovered.get(final_name)
            if prior is not None and not _same_specialization_bindings(
                prior[1],
                candidate,
            ):
                raise LispFrontendCompileError(
                    (
                        LispFrontendDiagnostic(
                            code="procedure_specialization_key_collision",
                            message=(
                                "procedure specialization key "
                                f"`{final_name}` has conflicting WorkflowRef bindings"
                            ),
                            span=candidate.definition.span,
                            form_path=candidate.definition.form_path,
                        ),
                    )
                )
            discovered[final_name] = (identity, candidate)
    return tuple(candidate for _, candidate in discovered.values())


_PROVIDER_BUNDLE_PATH_REF_KEY = "__provider_bundle_path_ref__"


_PROVIDER_BUNDLE_PROJECTION_KEY = "__provider_bundle_projection__"


@dataclass(frozen=True)
class ProjectedPathRef:
    """Inline lowered ref plus projection metadata for public output provenance."""

    ref: str
    projection: Mapping[str, Any]


def _projected_provider_bundle_ref(value: Any) -> ProjectedPathRef | None:
    if not isinstance(value, Mapping):
        return None
    path_ref = value.get(_PROVIDER_BUNDLE_PATH_REF_KEY)
    projection = value.get(_PROVIDER_BUNDLE_PROJECTION_KEY)
    if not isinstance(path_ref, str) or not isinstance(projection, Mapping):
        return None
    return ProjectedPathRef(ref=path_ref, projection=dict(projection))


def _value_compile_error(*, code: str, message: str, span, form_path: tuple[str, ...]) -> LispFrontendCompileError:
    return LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code=code,
                message=message,
                span=span,
                form_path=form_path,
                phase="lowering",
            ),
        )
    )


def _resolve_nested_local_value(value: Any, field_path: tuple[str, ...]) -> Any:
    """Follow a flattened field path through a nested local-value mapping."""

    current = value
    for field_name in field_path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(field_name)
    return current


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


def _record_field_value(record_expr: RecordExpr, field_name: str) -> Any:
    for current_name, current_value in record_expr.fields:
        if current_name == field_name:
            return current_value
    return None


def _resolve_inline_field_value(
    value: Any,
    *,
    field_path: tuple[str, ...],
    local_values: Mapping[str, Any],
    retain_expression_facts: bool = False,
) -> Any:
    """Resolve a nested field path through inline mappings or record expressions."""


    current = value
    for field_name in field_path:
        if isinstance(current, RetainedExpressionFact):
            current = current.tag if current.form == "union" and field_name == "variant" else dict(current.fields).get(field_name)
            continue
        if current is not None and not isinstance(current, (Mapping, RecordExpr, UnionVariantExpr)):
            next_current = _resolve_inline_expr_value(current, local_values=local_values, retain_expression_facts=retain_expression_facts)
            if next_current is current:
                return None
            current = next_current
        if isinstance(current, Mapping):
            current = current.get(field_name)
            continue
        if isinstance(current, RecordExpr):
            current = _record_field_value(current, field_name)
            current = _resolve_inline_expr_value(current, local_values=local_values, retain_expression_facts=retain_expression_facts)
            continue
        if isinstance(current, UnionVariantExpr):
            current = _union_variant_expr_value_at_path(current, (field_name,), bound_record_fields=False)
            current = _resolve_inline_expr_value(current, local_values=local_values, retain_expression_facts=retain_expression_facts)
            continue
        return None
    return current


def _retained_inline_child(value):
    from orchestrator.workflow_lisp.expressions import ExprNode
    from orchestrator.workflow_lisp.expression_traversal import is_pure_projection_expr

    if isinstance(value, ExprNode) and not isinstance(value, LiteralExpr):
        return RetainedExpressionFact("opaque", is_pure_projection_expr(value))
    return value


def _retained_inline_constructor(expr, *, local_values):
    from orchestrator.workflow_lisp.expression_traversal import is_pure_projection_expr

    fields = tuple((name, _retained_inline_child(_resolve_inline_expr_value(child,
        local_values=local_values, retain_expression_facts=True))) for name, child in expr.fields)
    tag = _union_variant_expr_value_at_path(expr, ("variant",), bound_record_fields=False)
    return RetainedExpressionFact("union", is_pure_projection_expr(expr), fields, tag)


def _resolve_inline_record(expr, *, local_values, retain_expression_facts):
    from orchestrator.workflow_lisp.expression_traversal import is_pure_projection_expr

    fields = []
    for name, child in expr.fields:
        value = _resolve_inline_expr_value(child, local_values=local_values,
            retain_expression_facts=retain_expression_facts)
        if value is None and not retain_expression_facts:
            return expr
        fields.append((name, _retained_inline_child(value) if retain_expression_facts else value))
    if any(value is None for _, value in fields):
        return RetainedExpressionFact("record", is_pure_projection_expr(expr), tuple(fields))
    return dict(fields)


def _resolve_inline_expr_value(expr: Any, *, local_values: Mapping[str, Any], retain_expression_facts: bool = False) -> Any:
    """Resolve literals, names, fields, and record expressions for inline use."""

    if isinstance(expr, RetainedExpressionFact):
        return expr
    if retain_expression_facts and isinstance(expr, UnionVariantExpr):
        return _retained_inline_constructor(expr, local_values=local_values)


    if isinstance(expr, LiteralExpr | GeneratedRelpathSeedExpr | WorkflowRefLiteralExpr):
        return expr
    if isinstance(expr, EnumMemberExpr):
        return LiteralExpr(
            value=expr.member_name,
            literal_kind="string",
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    if isinstance(expr, ProcRefLiteralExpr | BindProcExpr):
        return expr
    if isinstance(expr, RecordExpr):
        return _resolve_inline_record(expr, local_values=local_values,
            retain_expression_facts=retain_expression_facts)
    if isinstance(expr, LoopStateSeedExpr):
        return _loop_state_seed_inline_value(expr, local_values=local_values, retain_expression_facts=retain_expression_facts)
    if isinstance(expr, LoopStateUpdateExpr):
        return _loop_state_update_inline_value(expr, local_values=local_values, retain_expression_facts=retain_expression_facts)
    if isinstance(expr, LetStarExpr):
        child_locals = _resolve_inline_let_bindings(expr.bindings, local_values=local_values, retain_expression_facts=retain_expression_facts)
        if child_locals is None:
            return expr
        return _resolve_inline_expr_value(expr.body, local_values=child_locals, retain_expression_facts=retain_expression_facts)
    if isinstance(expr, IfExpr):
        condition_value = _resolve_inline_expr_value(expr.condition_expr, local_values=local_values, retain_expression_facts=retain_expression_facts)
        if isinstance(condition_value, LiteralExpr) and condition_value.literal_kind == "bool":
            branch = expr.then_expr if condition_value.value else expr.else_expr
            return _resolve_inline_expr_value(branch, local_values=local_values, retain_expression_facts=retain_expression_facts)
        return expr
    if isinstance(expr, ProviderBundlePathExpr):
        source_value = _resolve_inline_expr_value(expr.source_expr, local_values=local_values, retain_expression_facts=retain_expression_facts)
        projected = _projected_provider_bundle_ref(source_value)
        if projected is None:
            return expr
        return projected
    resolved = _resolve_expr_local_value(expr, local_values=local_values)
    if retain_expression_facts and isinstance(resolved, (RecordExpr, UnionVariantExpr)):
        return _resolve_inline_expr_value(resolved, local_values=local_values, retain_expression_facts=True)
    if isinstance(resolved, (str, Mapping, LiteralExpr, RecordExpr, ProjectedPathRef)):
        return resolved
    if resolved is not None:
        if resolved is expr:
            return expr
        return _resolve_inline_expr_value(resolved, local_values=local_values, retain_expression_facts=retain_expression_facts)
    if isinstance(expr, NameExpr):
        bound = local_values.get(expr.name)
        if bound is None:
            return None
        if isinstance(bound, (str, Mapping)):
            return bound
        if bound is expr:
            return expr
        return _resolve_inline_expr_value(bound, local_values=local_values, retain_expression_facts=retain_expression_facts)
    if isinstance(expr, FieldAccessExpr):
        return _resolve_inline_field_value(
            local_values.get(expr.base.name),
            field_path=tuple(expr.fields),
            local_values=local_values, retain_expression_facts=retain_expression_facts,
        )
    return _retained_inline_child(expr) if retain_expression_facts else expr


def _resolve_inline_let_bindings(
    bindings: tuple[tuple[str, Any], ...], *, local_values: Mapping[str, Any],
    retain_expression_facts: bool = False,
) -> dict[str, Any] | None:
    """Resolve a suffix's aliases in order, without constructing another AST."""
    child_locals = dict(local_values)
    for name, expr in bindings:
        value = _resolve_inline_expr_value(expr, local_values=child_locals, retain_expression_facts=retain_expression_facts)
        if value is None:
            return None
        child_locals[name] = value
    return child_locals


def _loop_state_seed_inline_value(
    expr: LoopStateSeedExpr,
    *,
    local_values: Mapping[str, Any],
    retain_expression_facts: bool = False,
) -> Any:
    inline_value: dict[str, Any] = {}
    for field in expr.fields:
        resolved_value = _resolve_inline_expr_value(field.value_expr, local_values=local_values, retain_expression_facts=retain_expression_facts)
        if resolved_value is None:
            return expr
        inline_value[field.name] = resolved_value
    return inline_value


def _loop_state_update_inline_value(
    expr: LoopStateUpdateExpr,
    *,
    local_values: Mapping[str, Any],
    retain_expression_facts: bool = False,
) -> Any:
    base_value = _resolve_inline_expr_value(expr.base_expr, local_values=local_values, retain_expression_facts=retain_expression_facts)
    if not isinstance(base_value, Mapping):
        return expr
    updated_value = {name: _clone_inline_value(value) for name, value in base_value.items()}
    for field_name, field_expr in expr.overrides:
        resolved_value = _resolve_inline_expr_value(field_expr, local_values=local_values, retain_expression_facts=retain_expression_facts)
        if resolved_value is None:
            return expr
        updated_value[field_name] = resolved_value
    return updated_value


def _clone_inline_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _clone_inline_value(item)
            for key, item in value.items()
        }
    return value


def _build_output_step_local_value(
    output_refs: Mapping[str, str],
    *,
    type_ref: RecordTypeRef | UnionTypeRef | None = None,
    type_env: Any | None = None,
) -> dict[str, Any]:
    """Convert flattened terminal output refs into nested local-value shape."""

    field_paths = (
        dict(
            _flatten_boundary_leaf_paths(
                type_ref,
                generated_name="return",
                type_env=type_env,
            )
        )
        if type_ref is not None
        else {}
    )
    local_value: dict[str, Any] = {}
    for output_name, ref in output_refs.items():
        field_path = field_paths.get(
            output_name,
            tuple(output_name.removeprefix("return__").split("__")),
        )
        current = local_value
        for field_name in field_path[:-1]:
            next_current = current.get(field_name)
            if not isinstance(next_current, dict):
                next_current = {}
                current[field_name] = next_current
            current = next_current
        current[field_path[-1]] = ref
    return local_value


def _flatten_boundary_leaf_paths(
    type_ref: RecordTypeRef | UnionTypeRef,
    *,
    generated_name: str,
    field_path: tuple[str, ...] = (),
    type_env: Any | None = None,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Return generated boundary names paired with frontend field paths."""

    if isinstance(type_ref, UnionTypeRef):
        return tuple(
            (field.generated_name, field_path + field.source_path[1:])
            for field in derive_workflow_boundary_fields(
                type_ref,
                generated_name=generated_name,
                source_path=(generated_name,),
                span=type_ref.definition.span,
                form_path=("workflow-lisp", "defunion", type_ref.name),
                type_env=type_env,
            )
        )
    flattened: list[tuple[str, tuple[str, ...]]] = []
    for field in type_ref.definition.fields:
        field_type = type_ref.field_types[field.name]
        next_generated_name = f"{generated_name}__{field.name}"
        next_field_path = field_path + (field.name,)
        if isinstance(field_type, (RecordTypeRef, UnionTypeRef)):
            flattened.extend(
                _flatten_boundary_leaf_paths(
                    field_type,
                    generated_name=next_generated_name,
                    field_path=next_field_path,
                    type_env=type_env,
                )
            )
            continue
        flattened.append((next_generated_name, next_field_path))
    return tuple(flattened)


def _record_expr_value_at_path(record_expr: RecordExpr, field_path: tuple[str, ...]) -> Any:
    """Read a nested field from an authored `record` expression."""

    current: Any = record_expr
    for field_name in field_path:
        if isinstance(current, RecordExpr):
            current = _record_field_value(current, field_name)
            continue
        if isinstance(current, UnionVariantExpr):
            current = _union_variant_expr_value_at_path(current, (field_name,), bound_record_fields=False)
            continue
        if not isinstance(current, RecordExpr):
            raise _value_compile_error(
                code="workflow_return_not_exportable",
                message=(
                    f"record return field `{'__'.join(field_path)}` must lower from nested record or variant expressions "
                    "when the workflow return type contains nested records"
                ),
                span=record_expr.span,
                form_path=record_expr.form_path,
            )
    return current


def _normalize_union_field_path(field_path: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    for segment in field_path:
        normalized.extend(part for part in segment.split("__") if part)
    return tuple(normalized)


def _union_variant_expr_value_at_path(
    union_expr: UnionVariantExpr,
    field_path: tuple[str, ...],
    *,
    bound_record_fields: bool,
) -> Any:
    """Read a field from one compiler-generated union variant literal.

    `bound_record_fields` (target 2.33+) lets a nested record field populated
    from a bound name lower as a field access; older targets reject it.
    """

    field_path = _normalize_union_field_path(field_path)
    if not field_path:
        return union_expr
    field_name = field_path[0]
    if field_name == "variant":
        return LiteralExpr(
            value=union_expr.variant_name,
            literal_kind="string",
            span=union_expr.span,
            form_path=union_expr.form_path,
            expansion_stack=union_expr.expansion_stack,
        )
    for current_name, current_value in union_expr.fields:
        if current_name != field_name:
            continue
        if len(field_path) == 1:
            return current_value
        if isinstance(current_value, (RecordExpr, UnionVariantExpr)):
            return _record_expr_value_at_path(current_value, field_path[1:])
        if bound_record_fields and isinstance(current_value, NameExpr):
            # A nested record populated from a bound value: read the leaf
            # through the same field access an author would write.
            return FieldAccessExpr(
                base=current_value,
                fields=field_path[1:],
                span=current_value.span,
                form_path=current_value.form_path,
                expansion_stack=current_value.expansion_stack,
            )
        if bound_record_fields and isinstance(current_value, FieldAccessExpr):
            return replace(
                current_value, fields=current_value.fields + field_path[1:],
                shared_field_types=(
                    current_value.shared_field_types + (None,) * len(field_path[1:])
                    if current_value.shared_field_types else ()
                ),
            )
        raise _value_compile_error(
            code="workflow_return_not_exportable",
            message=(
                f"union return field `{'__'.join(field_path)}` must lower from nested record expressions "
                "when the workflow return type contains nested records"
            ),
            span=union_expr.span,
            form_path=union_expr.form_path,
        )
    return None


def inline_expr_projection_source(
    expr: Any, *, field_path: tuple[str, ...], bound_record_fields: bool,
) -> Any:
    if isinstance(expr, RecordExpr):
        return _record_expr_value_at_path(expr, field_path)
    if isinstance(expr, UnionVariantExpr):
        return _union_variant_expr_value_at_path(
            expr, field_path, bound_record_fields=bound_record_fields,
        )
    return expr


def inline_expr_field_value(
    expr: Any, *, field_path: tuple[str, ...], local_values: Mapping[str, Any],
    bound_record_fields: bool, phase_target_values: Mapping[str, Any] | None,
    retain_expression_facts: bool = False,
) -> Any:
    """Pure projected-leaf resolution using explicit phase availability."""
    selected = inline_expr_projection_source(
        expr, field_path=field_path, bound_record_fields=bound_record_fields,
    )
    if isinstance(selected, PhaseTargetExpr) and phase_target_values is not None:
        return phase_target_values.get(selected.target_name)
    if isinstance(expr, LetStarExpr):
        return inline_let_field_value(
            expr.bindings, body=expr.body, field_path=field_path, local_values=local_values, retain_expression_facts=retain_expression_facts,
        )
    value = _resolve_inline_expr_value(selected, local_values=local_values, retain_expression_facts=retain_expression_facts)
    if isinstance(expr, (RecordExpr, UnionVariantExpr)):
        return value
    return _resolve_nested_local_value(value, field_path) if field_path else value


def inline_let_field_value(bindings: tuple[tuple[str, Any], ...], *, body: Any, field_path: tuple[str, ...], local_values: Mapping[str, Any], retain_expression_facts: bool = False) -> Any:
    """Project a complete suffix using the same resolved-value path as a Let node."""
    child_values = _resolve_inline_let_bindings(bindings, local_values=local_values, retain_expression_facts=retain_expression_facts)
    if child_values is None:
        return None
    value = _resolve_inline_expr_value(body, local_values=child_values, retain_expression_facts=retain_expression_facts)
    return _resolve_nested_local_value(value, field_path) if field_path else value


def _resolve_procedure_lowering(
    typed_procedures: tuple[TypedProcedureDef, ...],
    *,
    typed_workflows: tuple[TypedWorkflowDef, ...],
    workflow_path: Path,
    type_env: FrontendTypeEnvironment,
    procedure_type_envs: Mapping[str, FrontendTypeEnvironment] | None = None,
) -> Mapping[str, TypedProcedureDef]:
    """Every procedure lowers inline: a procedure has no call frame of its own."""

    return MappingProxyType({
        procedure.definition.name: replace(
            procedure, resolved_lowering_mode=ProcedureLoweringMode.INLINE, generated_workflow_name=None,
        )
        for procedure in typed_procedures
    })


def resolved_surface_proc_ref(
    value: Any, *, typed_procedures: Mapping[str, Any], local_values: Mapping[str, Any],
    procedure_catalog: Any = None, expected_type: Any = None,
) -> Any:
    from orchestrator.workflow_lisp.expressions import BindProcExpr, ProcRefLiteralExpr
    from orchestrator.workflow_lisp.procedure_refs import ResolvedProcRefValue, resolve_proc_ref_value
    from orchestrator.workflow_lisp.procedures import ProcedureCatalog

    if isinstance(value, ResolvedProcRefValue):
        return value
    if not isinstance(value, (NameExpr, ProcRefLiteralExpr, BindProcExpr)):
        return None
    if procedure_catalog is None:
        procedure_catalog = ProcedureCatalog(
            signatures_by_name={name: proc.signature for name, proc in typed_procedures.items()},
            definitions_by_name={name: proc.definition for name, proc in typed_procedures.items()},
            call_graph={},
        )
    return resolve_proc_ref_value(
        value, procedure_catalog=procedure_catalog,
        proc_ref_env={name: ref for name, ref in local_values.items() if isinstance(ref, ResolvedProcRefValue)},
        expected_type=expected_type,
    )


def resolved_surface_workflow_ref(
    value: Any, *, workflow_catalog: Any, typed_workflows: Mapping[str, Any],
    expected_type: Any = None,
) -> Any:
    from orchestrator.workflow_lisp.expressions import EnumMemberExpr, WorkflowRefLiteralExpr
    from orchestrator.workflow_lisp.workflow_refs import (
        ResolvedWorkflowRef, resolve_workflow_ref_literal, resolve_workflow_ref_name,
        workflow_ref_target_name,
    )
    from orchestrator.workflow_lisp.type_env import WorkflowRefTypeRef

    if isinstance(value, ResolvedWorkflowRef):
        return value
    if isinstance(value, WorkflowRefLiteralExpr):
        if expected_type is None:
            signature = workflow_catalog.signatures_by_name.get(value.target_name)
            if signature is None:
                raise _value_compile_error(
                    code="workflow_ref_unknown", message=f"unknown workflow ref `{value.target_name}`",
                    span=value.span, form_path=value.form_path,
                )
            expected_type = WorkflowRefTypeRef(
                name=f"WorkflowRef[{ ' '.join(type_ref.name for _, type_ref in signature.params) } -> {signature.return_type_ref.name}]",
                param_type_refs=tuple(type_ref for _, type_ref in signature.params),
                return_type_ref=signature.return_type_ref,
            )
        return resolve_workflow_ref_literal(
            value, expected_type=expected_type, workflow_catalog=workflow_catalog,
            typed_workflows_by_name=typed_workflows, allow_extern_rebinding=False,
        )
    if isinstance(value, (NameExpr, EnumMemberExpr)):
        return resolve_workflow_ref_name(
            workflow_ref_target_name(value), workflow_catalog=workflow_catalog,
            span=value.span, form_path=value.form_path, expansion_stack=value.expansion_stack,
            expected_type=expected_type, typed_workflows_by_name=typed_workflows,
            allow_extern_rebinding=False,
        )
    return None


def _surface_procedure_callee(
    call: Any, *, local_values: Mapping[str, Any], typed_procedures: Mapping[str, Any],
    procedure_catalog: Any,
) -> Any:

    if call.specialized_callee_name is not None:
        name = call.specialized_callee_name
        code = "procedure_lowering_unresolved"
        message = f"compiler-owned specialization row `{name}` is missing during lowering"
    else:
        bound = resolved_surface_proc_ref(
            local_values.get(call.callee_name), typed_procedures=typed_procedures,
            procedure_catalog=procedure_catalog, local_values=local_values,
        )
        if bound is not None:
            name = bound.call_target_name
            code = "procedure_lowering_unresolved"
            message = f"compiler-owned bound ProcRef specialization row `{name}` is missing during lowering"
        else:
            name = call.callee_name
            code = "procedure_call_unknown"
            message = f"unknown procedure callee `{name}` during lowering"
    procedure = typed_procedures.get(name)
    if procedure is None:
        raise _value_compile_error(code=code, message=message, span=call.span, form_path=call.form_path)
    return procedure


def _surface_procedure_actuals(
    procedure: Any, args: tuple[Any, ...], *, local_values: Mapping[str, Any],
    typed_procedures: Mapping[str, Any], procedure_catalog: Any,
    workflow_catalog: Any, typed_workflows: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], tuple[Any, ...]]:
    from orchestrator.workflow_lisp.expressions import EnumMemberExpr
    from orchestrator.workflow_lisp.type_env import ProcRefTypeRef, WorkflowRefTypeRef

    workflow_refs = {}
    proc_refs = {}
    residual = []
    for arg, (name, param_type) in zip(args, procedure.signature.params, strict=True):
        if isinstance(param_type, WorkflowRefTypeRef):
            candidate = arg if isinstance(arg, EnumMemberExpr) else _resolve_inline_expr_value(arg, local_values=local_values) or arg
            resolved = resolved_surface_workflow_ref(
                candidate, workflow_catalog=workflow_catalog, typed_workflows=typed_workflows,
                expected_type=param_type,
            )
            if resolved is None:
                raise _value_compile_error(
                    code="workflow_ref_literal_required",
                    message="workflow-ref arguments must be literals or forwarded workflow-ref bindings",
                    span=arg.span, form_path=arg.form_path,
                )
            workflow_refs[name] = resolved
            continue
        if isinstance(param_type, ProcRefTypeRef):
            resolved = resolved_surface_proc_ref(
                _resolve_inline_expr_value(arg, local_values=local_values) or arg,
                typed_procedures=typed_procedures, procedure_catalog=procedure_catalog,
                local_values=local_values, expected_type=param_type,
            )
            if resolved is not None:
                proc_refs[name] = resolved
                continue
        residual.append(arg)
    return workflow_refs, proc_refs, tuple(residual)


def select_surface_procedure_call(
    call: Any, *, local_values: Mapping[str, Any], typed_procedures: Mapping[str, Any],
    procedure_catalog: Any, workflow_catalog: Any, typed_workflows: Mapping[str, Any],
) -> tuple[Any, tuple[Any, ...]]:

    procedure = _surface_procedure_callee(
        call, local_values=local_values, typed_procedures=typed_procedures,
        procedure_catalog=procedure_catalog,
    )
    workflow_refs, proc_refs, residual = _surface_procedure_actuals(
        procedure, call.args, local_values=local_values, typed_procedures=typed_procedures,
        procedure_catalog=procedure_catalog, workflow_catalog=workflow_catalog,
        typed_workflows=typed_workflows,
    )
    if not (workflow_refs or proc_refs):
        return procedure, call.args
    rows = materialized_specialization_rows(
        procedure, workflow_ref_bindings=workflow_refs, proc_ref_bindings=proc_refs,
        typed_procedures=typed_procedures,
    )
    if len(rows) != 1:
        raise _value_compile_error(
            code="procedure_lowering_unresolved",
            message="compiler-owned procedure specialization row with exact compile-time bindings is missing or ambiguous during lowering",
            span=call.span, form_path=call.form_path,
        )
    return rows[0], residual


def inline_procedure_bindings(
    procedure: Any, *, caller_values: Mapping[str, Any], actual_values: tuple[Any, ...],
) -> dict[str, Any]:
    values = dict(caller_values)
    values.update(procedure_specialization_bindings(procedure))
    for value, (name, _) in zip(actual_values, procedure.signature.params, strict=True):
        values[name] = value
    return values


def procedure_specialization_bindings(procedure: Any) -> dict[str, Any]:
    values: dict[str, Any] = {}
    if procedure.specialization is not None:
        for kind in ("workflow_ref_bindings", "proc_ref_bindings", "value_bindings"):
            values.update(dict(getattr(procedure.specialization, kind, {})))
    return values


RUNTIME_REFERENCE = object()


@dataclass(frozen=True)
class RetainedExpressionFact:
    """Closed-only constructor facts selected under their creation locals."""

    form: Literal["record", "union", "opaque"]
    projection_candidate: bool
    fields: tuple[tuple[str, Any], ...] = ()
    tag: LiteralExpr | None = None


