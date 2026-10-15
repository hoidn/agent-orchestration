"""Typing of `agent` allocations and conservative provider-origin propagation.

Dependencies: `context` is a `typecheck_context.TypecheckContext`; origins of
`let*`-bound agents are kept in `context.session_state.agent_origins_by_binding`
keyed by the object identity of the binding's `BindingIdentity`, so a later
shadowing binder never inherits another binding's origins.
"""

from __future__ import annotations

from collections.abc import Mapping

from .effects import UsesProviderEffect, effect_summary_from_direct, merge_effect_summaries
from .expressions import AgentExpr, ExprNode, FieldAccessExpr, LiteralExpr, NameExpr
from .type_env import PrimitiveTypeRef, TypeRef
from .typecheck_context import raise_error
from .typecheck_effects import _extern_operand_name, typecheck_expected_extern_operand

AGENT_TYPE = PrimitiveTypeRef(name="Agent")
_STRING_TYPE = PrimitiveTypeRef(name="String")


def typecheck_agent_expr(expr: AgentExpr, *, context, recurse, typed_factory):
    """Type one allocation as `Agent` with a `uses-provider` effect on its extern."""

    from .workflows import ProviderExtern

    typed_provider = typecheck_expected_extern_operand(
        expr.provider, expected_primitive="Provider", context=context, recurse=recurse,
        typed_factory=typed_factory,
    )
    name = _extern_operand_name(expr.provider)
    binding = None if name is None or context.extern_environment is None \
        else context.extern_environment.bindings_by_name.get(name)
    if typed_provider.type_ref != PrimitiveTypeRef(name="Provider") or not isinstance(binding, ProviderExtern):
        raise_error(
            "`agent` requires a compiler-known provider extern",
            code="agent_provider_invalid",
            span=expr.provider.span,
            form_path=expr.provider.form_path,
            expansion_stack=expr.provider.expansion_stack,
        )
    summaries = [_typecheck_policy(field_name, policy_expr, recurse)
                 for field_name, policy_expr in (("model", expr.model), ("effort", expr.effort))
                 if policy_expr is not None]
    return typed_factory(
        expr=expr,
        type_ref=AGENT_TYPE,
        effect=merge_effect_summaries(
            *summaries,
            effect_summary_from_direct(direct_effects=(UsesProviderEffect(subject=tuple(name.split("."))),)),
        ),
    )


def _typecheck_policy(field_name: str, policy_expr: ExprNode, recurse):
    typed_policy = recurse(policy_expr)
    if typed_policy.type_ref != _STRING_TYPE:
        raise_error(
            f"`agent :{field_name}` must have type `String`",
            code=f"agent_{field_name}_type_invalid",
            span=policy_expr.span,
            form_path=policy_expr.form_path,
            expansion_stack=policy_expr.expansion_stack,
        )
    summary = typed_policy.effect_summary
    if not isinstance(policy_expr, (LiteralExpr, NameExpr, FieldAccessExpr)) \
            or summary.direct_effects or summary.transitive_effects:
        raise_error(
            f"`agent :{field_name}` must use an inline-lowerable String operand",
            code="agent_policy_operand_not_inline_lowerable",
            span=policy_expr.span,
            form_path=policy_expr.form_path,
            expansion_stack=policy_expr.expansion_stack,
        )
    return summary


def record_agent_origin(
    context,
    identity: object,
    value_expr: ExprNode,
    type_ref: TypeRef,
    binding_env: Mapping[str, object],
) -> None:
    """Remember the origins of one `let*` binding of type `Agent`, resolved in its RHS scope."""

    if type_ref == AGENT_TYPE:
        origins = _origins(value_expr, binding_env, context)
        context.session_state.agent_origins_by_binding[id(identity)] = (identity, origins)


def agent_origins(expr: ExprNode, context) -> frozenset[str]:
    """Provider-extern names an `Agent` operand may denote.

    Exact for an `agent` form and for names bound (directly or by alias) to one
    by a visible `let*`; every declared provider extern otherwise (parameters,
    fields, branch joins, loop and match binders).
    """

    return _origins(expr, context.binding_env, context)


def _origins(expr: ExprNode, binding_env: Mapping[str, object], context) -> frozenset[str]:
    if isinstance(expr, AgentExpr):
        return frozenset({_extern_operand_name(expr.provider)})
    if isinstance(expr, NameExpr):
        identity = binding_env.get(expr.name)
        entry = context.session_state.agent_origins_by_binding.get(id(identity))
        if entry is not None and entry[0] is identity:
            return entry[1]
    return all_provider_externs(context)


def all_provider_externs(context) -> frozenset[str]:
    """Every provider extern name declared for this build."""

    from .workflows import ProviderExtern

    if context.extern_environment is None:
        return frozenset()
    return frozenset(
        name for name, binding in context.extern_environment.bindings_by_name.items()
        if isinstance(binding, ProviderExtern)
    )


def typecheck_agent_turn(expr, *, context, recurse) -> tuple[str, ...] | None:
    """Return the sorted provider origins when `provider-result` targets an `Agent`, else None.

    An agent turn may not override the agent's pinned policy nor use options
    whose runtime is outside a native session turn.
    """

    if _extern_operand_name(expr.provider) is not None and expr.provider.name not in context.value_env:
        return None
    if recurse(expr.provider).type_ref != AGENT_TYPE:
        return None
    for field_name, value in (("model", expr.model), ("effort", expr.effort)):
        if value is not None:
            raise_error(
                f"an agent turn cannot override `:{field_name}`; change the `agent` constructor",
                code="agent_turn_policy_override_forbidden",
                span=value.span, form_path=value.form_path, expansion_stack=value.expansion_stack,
            )
    unsupported = [name for name, value in (
        ("session-artifact", expr.session_artifact), ("context", expr.context_expr),
        ("capture-context", expr.capture_context), ("materialization-attempts", expr.materialization_attempts),
        ("delivery :phased", getattr(expr.delivery, "value", None) == "phased" or None),
    ) if value is not None]
    if unsupported:
        raise_error(
            f"agent turns do not accept `:{unsupported[0]}`",
            code="agent_turn_option_unsupported",
            span=expr.span, form_path=expr.form_path, expansion_stack=expr.expansion_stack,
        )
    return tuple(sorted(agent_origins(expr.provider, context)))


def contains_agent(type_ref: TypeRef, seen: frozenset[str] = frozenset()) -> bool:
    """Whether `Agent` occurs anywhere inside one frontend type."""

    from .type_env import ListTypeRef, MapTypeRef, OptionalTypeRef, RecordTypeRef, UnionTypeRef

    if type_ref == AGENT_TYPE:
        return True
    if isinstance(type_ref, (OptionalTypeRef, ListTypeRef)):
        return contains_agent(type_ref.item_type_ref, seen)
    if isinstance(type_ref, MapTypeRef):
        return contains_agent(type_ref.key_type_ref, seen) or contains_agent(type_ref.value_type_ref, seen)
    if isinstance(type_ref, (RecordTypeRef, UnionTypeRef)) and type_ref.name not in seen:
        rows = [type_ref.field_types] if isinstance(type_ref, RecordTypeRef) \
            else list(type_ref.variant_field_types.values())
        inner = seen | {type_ref.name}
        return any(contains_agent(field, inner) for row in rows for field in row.values())
    return False


def require_no_agent(type_ref, *, where: str, span, form_path, expansion_stack=(),
                     code: str = "agent_transport_forbidden") -> None:
    """Refuse an `Agent` (at any depth) in a data position that leaves the run."""

    if contains_agent(type_ref):
        raise_error(
            f"an `Agent` cannot be passed as {where}; it is a run-local handle",
            code=code, span=span, form_path=form_path, expansion_stack=expansion_stack,
        )


def agent_return_boundary_diagnostic(workflow_def, return_type_ref: TypeRef):
    """A record/union workflow return carrying an `Agent` cannot cross the workflow boundary."""

    from .diagnostics import LispFrontendDiagnostic

    if not contains_agent(return_type_ref):
        return None
    return LispFrontendDiagnostic(
        code="workflow_boundary_type_invalid",
        message=f"workflow `{workflow_def.name}` return `{workflow_def.return_type_name}` carries an `Agent`",
        span=workflow_def.span, form_path=workflow_def.form_path, expansion_stack=workflow_def.expansion_stack,
    )


def check_parallel_body(expr, typed_body, context) -> None:
    """Refuse a parallel worker that receives, allocates, turns or returns an `Agent`.

    Allocation is searched in the typed body and, syntactically, in every
    procedure the body reaches through `context.procedure_catalog.call_graph`.
    """

    from .expression_traversal import free_expr_names, walk_expr
    from .expressions import ProcedureCallExpr, ProviderResultExpr

    free = free_expr_names(expr.body_expr, bound=frozenset({expr.binder_name}))
    nodes = list(walk_expr(typed_body.expr))
    callees = {node.callee_name for node in nodes if isinstance(node, ProcedureCallExpr)}
    if (
        contains_agent(typed_body.type_ref)
        or any(contains_agent(context.value_env[name]) for name in free if name in context.value_env)
        or any(isinstance(node, AgentExpr)
               or isinstance(node, ProviderResultExpr) and node.agent_origins is not None for node in nodes)
        or _procedures_allocate(callees, context.procedure_catalog)
    ):
        raise_error(
            "a parallel worker cannot receive, allocate, turn or return an `Agent`",
            code="parallel_agent_boundary",
            span=expr.span, form_path=expr.form_path, expansion_stack=expr.expansion_stack,
        )


def _procedures_allocate(names: set[str], catalog) -> bool:
    """Whether any procedure reachable from `names` writes an `agent` form."""

    if catalog is None:
        return False
    pending, seen = list(names), set()
    while pending:
        name = pending.pop()
        definition = catalog.definitions_by_name.get(name)
        if name in seen or definition is None:
            continue
        seen.add(name)
        if _datum_allocates(definition.body.datum):
            return True
        pending.extend(catalog.call_graph.get(name, ()))
    return False


def _datum_allocates(datum) -> bool:
    items = getattr(datum, "items", None)
    if items is None:
        return False
    head = items[0] if items else None
    if getattr(head, "display_name", getattr(head, "name", None)) == "agent":
        return True
    return any(_datum_allocates(item) for item in items)
