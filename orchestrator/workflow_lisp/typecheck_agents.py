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
