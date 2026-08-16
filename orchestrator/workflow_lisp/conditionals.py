"""Frontend-local conditional classification and predicate rendering."""

from __future__ import annotations

import dataclasses
import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .effects import EffectSummary
from .expression_traversal import _rebuild_with_replacements, iter_child_exprs
from .expressions import (
    BindProcExpr,
    CallExpr,
    CommandResultExpr,
    CompilerListNonemptyHeadExpr,
    CondExpr,
    ContinueExpr,
    DoneExpr,
    EnumMemberExpr,
    ExprNode,
    FieldAccessExpr,
    FinalizeSelectedItemExpr,
    FunctionCallExpr,
    GeneratedRelpathSeedExpr,
    IfExpr,
    LetProcExpr,
    LetStarExpr,
    ListExpr,
    ListMapEffectExpr,
    ListMapExpr,
    LiteralExpr,
    LoopRecurExpr,
    LoopStateSeedExpr,
    LoopStateUpdateExpr,
    MatchArm,
    MatchExpr,
    MaterializeViewExpr,
    NameExpr,
    PathJoinUnderExpr,
    PhaseTargetExpr,
    ProcRefLiteralExpr,
    ProcedureCallExpr,
    ProduceOneOfExpr,
    ProviderBundlePathExpr,
    ProviderResultExpr,
    PureOpExpr,
    RecordExpr,
    RecordUpdateExpr,
    ResourceTransitionExpr,
    ResumeOrStartExpr,
    RunProviderPhaseExpr,
    RunRefExpr,
    TrialExpr,
    UnionVariantExpr,
    UnionVariantTagExpr,
    WithLiveProviderPeersExpr,
    WithLiveProvidersExpr,
    WithPhaseExpr,
    WorkflowRefLiteralExpr,
)
from .type_env import PrimitiveTypeRef, TypeRef


@dataclass(frozen=True)
class LiteralBoolCondition:
    value: bool


@dataclass(frozen=True)
class BoolRefCondition:
    base_name: str
    fields: tuple[str, ...]


ConditionShape = LiteralBoolCondition | BoolRefCondition


@dataclass(frozen=True)
class PureExprCondition:
    expr: ExprNode


ConditionShape = LiteralBoolCondition | BoolRefCondition | PureExprCondition


def classify_condition_expr(
    expr: ExprNode,
    *,
    type_ref: TypeRef,
    allow_pure_projection: bool = False,
) -> ConditionShape:
    """Classify one `if` condition into the lowering subset.

    ``allow_pure_projection`` admits the broader pure-projection terminal
    surface (enum members, record/list values, nested pure ``if``) produced by
    the target-2.26 normalizer. It stays off so the legacy 2.25 projectability
    gate is byte-for-byte unchanged.
    """

    if type_ref != PrimitiveTypeRef(name="Bool"):
        _raise_condition_error(
            expr,
            code="if_condition_not_bool",
            message="`if` condition must resolve to exact `Bool`",
        )
    if isinstance(expr, LiteralExpr) and expr.literal_kind == "bool":
        return LiteralBoolCondition(value=bool(expr.value))
    if isinstance(expr, NameExpr):
        return BoolRefCondition(base_name=expr.name, fields=())
    if isinstance(expr, FieldAccessExpr):
        return BoolRefCondition(
            base_name=expr.base.name,
            fields=tuple(expr.fields),
        )
    if allow_pure_projection:
        from .lowering.pure_projection import is_pure_projection_expr

        if is_pure_projection_expr(expr):
            return PureExprCondition(expr=expr)
    elif _is_projectable_pure_bool_expr(expr):
        return PureExprCondition(expr=expr)
    _raise_condition_error(
        expr,
        code="if_condition_not_projectable",
        message="`if` condition must lower from a Bool literal or already-typed Bool ref",
    )


def render_condition_predicate(
    shape: ConditionShape,
    *,
    local_values: Mapping[str, Any],
) -> dict[str, Any]:
    """Render one classified condition as a shared typed predicate payload."""

    if isinstance(shape, LiteralBoolCondition):
        return {
            "compare": {
                "left": shape.value,
                "op": "eq",
                "right": True,
            }
        }
    resolved = _resolve_condition_ref(shape, local_values=local_values)
    if isinstance(resolved, bool):
        return {
            "compare": {
                "left": resolved,
                "op": "eq",
                "right": True,
            }
        }
    if isinstance(resolved, str):
        return {
            "artifact_bool": {
                "ref": resolved,
            }
        }
    if isinstance(shape, PureExprCondition):
        raise ValueError("pure boolean conditions require WCC pure-projection lowering")
    raise ValueError("Bool ref condition did not resolve to a shared ref or literal bool")


def _resolve_condition_ref(
    shape: BoolRefCondition | PureExprCondition,
    *,
    local_values: Mapping[str, Any],
) -> str | bool | None:
    if isinstance(shape, PureExprCondition):
        return None
    current: Any = local_values.get(shape.base_name)
    if isinstance(current, LiteralExpr) and current.literal_kind == "bool":
        current = bool(current.value)
    for field_name in shape.fields:
        if isinstance(current, Mapping):
            current = current.get(field_name)
        else:
            return None
        if isinstance(current, LiteralExpr) and current.literal_kind == "bool":
            current = bool(current.value)
    if isinstance(current, (bool, str)):
        return current
    return None


def _is_projectable_pure_bool_expr(expr: ExprNode) -> bool:
    if isinstance(expr, (LiteralExpr, NameExpr, FieldAccessExpr)):
        return True
    if isinstance(expr, PureOpExpr):
        return all(_is_projectable_pure_bool_expr(arg) for arg in expr.args)
    if isinstance(expr, LetStarExpr):
        return all(_is_projectable_pure_bool_expr(binding_expr) for _, binding_expr in expr.bindings) and _is_projectable_pure_bool_expr(expr.body)
    if isinstance(expr, IfExpr):
        return (
            _is_projectable_pure_bool_expr(expr.condition_expr)
            and _is_projectable_pure_bool_expr(expr.then_expr)
            and _is_projectable_pure_bool_expr(expr.else_expr)
        )
    return False


def _raise_condition_error(expr: ExprNode, *, code: str, message: str) -> None:
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code=code,
                message=message,
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=getattr(expr, "expansion_stack", ()),
            ),
        )
    )


@dataclass(frozen=True)
class NormalizedCondition:
    """One normalized target-2.26 strict-Boolean `if` condition.

    ``bindings`` are compiler-owned ``let*`` bindings evaluated left-to-right
    before the pure ``terminal`` is routed. ``true_env``/``false_env`` are the
    branch path environments reserved for Task 3 proof refinement; Task 2
    carries them through unchanged.
    """

    bindings: tuple[tuple[str, ExprNode], ...]
    terminal: ExprNode
    type_ref: TypeRef
    effect_summary: EffectSummary
    true_env: object | None
    false_env: object | None


_EFFECT_EXPRS: tuple[type, ...] = (
    ProviderResultExpr,
    CommandResultExpr,
    RunRefExpr,
    RunProviderPhaseExpr,
    ProduceOneOfExpr,
    ResourceTransitionExpr,
    MaterializeViewExpr,
    FinalizeSelectedItemExpr,
    CallExpr,
    ProcedureCallExpr,
)

# Scope/lifecycle owners are handled by dedicated rebuilders below, never by
# the generic effect traversal: their body/arm/start bindings must stay inside
# the owner that supplies their names/lifecycle rather than hoist to the
# enclosing condition prefix. `TrialExpr`/`ResumeOrStartExpr` cannot be
# exact-``Bool`` (a generated trial-result record and a record/union,
# respectively), but their run-ref input and start-branch children may still
# contain condition-owned Bool projections and are rebuilt scope-preservingly.

# Effect expressions whose expression children are ordinary values that can
# themselves contain a nested strict-Boolean `and`/`or`; every effect is
# recursively normalized before it is bound once.
_EFFECT_EXPRS_WITH_ARG_CHILDREN: tuple[type, ...] = (
    CallExpr,
    ProcedureCallExpr,
    RunRefExpr,
)

# Composite value/call expressions traversed for nested `and`/`or`. Loop-control
# terminals (`continue`/`done`) are normalized in place: their state/result
# children fold any condition-owned Bool projection without binding the control
# form itself, which stays inside its loop body.
_COMPOSITE_VALUE_EXPRS: tuple[type, ...] = (
    FunctionCallExpr,
    RecordExpr,
    UnionVariantExpr,
    RecordUpdateExpr,
    ListExpr,
    CompilerListNonemptyHeadExpr,
    PathJoinUnderExpr,
    LoopStateSeedExpr,
    LoopStateUpdateExpr,
    BindProcExpr,
    ContinueExpr,
    DoneExpr,
)

# Closed expression variants that carry no condition-owned child and are safe
# terminals.
_LEAF_EXPRS: tuple[type, ...] = (
    NameExpr,
    LiteralExpr,
    EnumMemberExpr,
    UnionVariantTagExpr,
    FieldAccessExpr,
    PhaseTargetExpr,
    GeneratedRelpathSeedExpr,
    WorkflowRefLiteralExpr,
    ProcRefLiteralExpr,
    ProviderBundlePathExpr,
)


# Every node kind that can perform an effect. A post-expansion `and`/`or` whose
# subtree reaches any of these must not be folded without bindings (the fold
# would emit a raw effect condition that WCC's value consumer cannot route).
_EFFECT_NODE_TYPES: tuple[type, ...] = _EFFECT_EXPRS + (
    TrialExpr,
    ResumeOrStartExpr,
    WithLiveProvidersExpr,
    WithLiveProviderPeersExpr,
    LoopRecurExpr,
    ListMapEffectExpr,
)


# Control/value spine forms inside a loop body. In the loop-body normalizer
# these are rebuilt in place (never bound) so the `done`/`continue` terminals
# stay directly reachable by loop lowering.
_LOOP_SPINE_EXPRS: tuple[type, ...] = (
    IfExpr,
    LetStarExpr,
    MatchExpr,
    LoopRecurExpr,
    TrialExpr,
    ResumeOrStartExpr,
    WithLiveProvidersExpr,
    WithLiveProviderPeersExpr,
)


def _contains_effect(expr: ExprNode) -> bool:
    """Return whether one expression subtree contains any effect node."""

    if isinstance(expr, _EFFECT_NODE_TYPES):
        return True
    return any(_contains_effect(child) for child in iter_child_exprs(expr))


def _is_helper_expanded(expr: ExprNode) -> bool:
    """Return whether one expression was inserted by helper expansion."""

    from .syntax import HelperExpansionFrame

    return any(
        isinstance(frame, HelperExpansionFrame)
        for frame in getattr(expr, "expansion_stack", ())
    )

def normalize_condition_expr(
    expr: ExprNode,
    *,
    type_ref: TypeRef,
    effect_summary: EffectSummary,
) -> NormalizedCondition:
    """Normalize one exact-``Bool`` condition into bindings plus pure terminal.

    Every target-2.26 ``and``/``or`` (including pure and literal operands)
    becomes a nested short-circuit ``IfExpr``, effects are bound exactly once
    in left-to-right order, ``not`` evaluates once and inverts, nested
    ``if``/``match`` values reuse the existing non-tail control join, and the
    terminal is a literal, ref, or existing pure projection.
    """

    bindings, terminal = _normalize_operand(expr, path=())
    return NormalizedCondition(
        bindings=bindings,
        terminal=terminal,
        type_ref=type_ref,
        effect_summary=effect_summary,
        true_env=None,
        false_env=None,
    )


def _normalize_operand(
    expr: ExprNode,
    *,
    path: tuple[int, ...],
) -> tuple[tuple[tuple[str, ExprNode], ...], ExprNode]:
    if isinstance(expr, PureOpExpr) and expr.operator in {"and", "or"}:
        return _normalize_short_circuit(expr, path=path)
    if isinstance(expr, PureOpExpr) and expr.operator == "not":
        return _normalize_not(expr, path=path)
    if isinstance(expr, PureOpExpr):
        return _normalize_pure_op(expr, path=path)
    if isinstance(expr, IfExpr):
        return _normalize_if_value(expr, path=path)
    if isinstance(expr, LetStarExpr):
        return _normalize_let_value(expr, path=path)
    if isinstance(expr, MatchExpr):
        return _normalize_match_value(expr, path=path)
    if isinstance(expr, (ListMapExpr, ListMapEffectExpr)):
        return _normalize_list_map(expr, path=path)
    if isinstance(expr, LoopRecurExpr):
        return _normalize_loop_recur(expr, path=path)
    if isinstance(expr, WithLiveProvidersExpr):
        return _normalize_with_live_providers(expr, path=path)
    if isinstance(expr, WithLiveProviderPeersExpr):
        return _normalize_with_live_provider_peers(expr, path=path)
    if isinstance(expr, TrialExpr):
        return _normalize_trial(expr, path=path)
    if isinstance(expr, ResumeOrStartExpr):
        return _normalize_resume_or_start(expr, path=path)
    if isinstance(expr, WithPhaseExpr):
        return _normalize_with_phase(expr, path=path)
    if isinstance(expr, LetProcExpr):
        return _normalize_let_proc(expr, path=path)
    if isinstance(expr, _EFFECT_EXPRS):
        return _normalize_effect_operand(expr, path=path)
    if isinstance(expr, _COMPOSITE_VALUE_EXPRS):
        return _normalize_composite(expr, path=path)
    if isinstance(expr, _LEAF_EXPRS):
        return (), expr
    raise TypeError(
        f"unhandled condition operand variant {type(expr).__name__}; "
        "add an explicit scope-preserving handler"
    )


def _normalize_short_circuit(
    expr: PureOpExpr,
    *,
    path: tuple[int, ...],
) -> tuple[tuple[tuple[str, ExprNode], ...], ExprNode]:
    operator = expr.operator
    normalized = tuple(
        _normalize_operand(arg, path=path + (index,))
        for index, arg in enumerate(expr.args)
    )
    first_bindings, first_terminal = normalized[0]
    rest = normalized[1:]
    if operator == "and":
        inner = _literal_bool(True, expr)
        for bindings, terminal in reversed(rest):
            inner = _wrap_bindings(
                bindings,
                IfExpr(
                    condition_expr=terminal,
                    then_expr=inner,
                    else_expr=_literal_bool(False, expr),
                    span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
                expr,
            )
        terminal_if = IfExpr(
            condition_expr=first_terminal,
            then_expr=inner,
            else_expr=_literal_bool(False, expr),
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    else:
        inner = _literal_bool(False, expr)
        for bindings, terminal in reversed(rest):
            inner = _wrap_bindings(
                bindings,
                IfExpr(
                    condition_expr=terminal,
                    then_expr=_literal_bool(True, expr),
                    else_expr=inner,
                    span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
                expr,
            )
        terminal_if = IfExpr(
            condition_expr=first_terminal,
            then_expr=_literal_bool(True, expr),
            else_expr=inner,
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    binding_name = _condition_binding_name(expr, role="short_circuit", path=path)
    return (*first_bindings, (binding_name, terminal_if)), _name_expr(
        binding_name,
        expr,
    )


def _normalize_not(
    expr: PureOpExpr,
    *,
    path: tuple[int, ...],
) -> tuple[tuple[tuple[str, ExprNode], ...], ExprNode]:
    bindings, terminal = _normalize_operand(expr.args[0], path=path + (0,))
    return bindings, dataclasses.replace(expr, args=(terminal,))


def _normalize_pure_op(
    expr: PureOpExpr,
    *,
    path: tuple[int, ...],
) -> tuple[tuple[tuple[str, ExprNode], ...], ExprNode]:
    hoisted: list[tuple[str, ExprNode]] = []
    args: list[ExprNode] = []
    for index, arg in enumerate(expr.args):
        bindings, terminal = _normalize_operand(arg, path=path + (index,))
        hoisted.extend(bindings)
        args.append(terminal)
    return tuple(hoisted), dataclasses.replace(expr, args=tuple(args))


def _normalize_if_value(
    expr: IfExpr,
    *,
    path: tuple[int, ...],
) -> tuple[tuple[tuple[str, ExprNode], ...], ExprNode]:
    condition_bindings, condition_terminal = _normalize_operand(
        expr.condition_expr,
        path=path + (0,),
    )
    then_bindings, then_terminal = _normalize_operand(expr.then_expr, path=path + (1,))
    else_bindings, else_terminal = _normalize_operand(expr.else_expr, path=path + (2,))
    nested_if = IfExpr(
        condition_expr=condition_terminal,
        then_expr=_wrap_bindings(then_bindings, then_terminal, expr.then_expr),
        else_expr=_wrap_bindings(else_bindings, else_terminal, expr.else_expr),
        span=expr.span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    binding_name = _condition_binding_name(expr, role="value", path=path)
    return (*condition_bindings, (binding_name, nested_if)), _name_expr(
        binding_name,
        expr,
    )


def _normalize_let_value(
    expr: LetStarExpr,
    *,
    path: tuple[int, ...],
) -> tuple[tuple[tuple[str, ExprNode], ...], ExprNode]:
    # Keep each authored `let*` binding in its own lexical scope; normalize
    # binding expressions and the body but do not export authored names to the
    # enclosing condition prefix (that would break shadowing).
    new_bindings: list[tuple[str, ExprNode]] = []
    for index, (binding_name, binding_expr) in enumerate(expr.bindings):
        bindings, terminal = _normalize_operand(binding_expr, path=path + (index,))
        new_bindings.append(
            (binding_name, _wrap_bindings(bindings, terminal, binding_expr))
        )
    body_bindings, body_terminal = _normalize_operand(
        expr.body,
        path=path + (len(expr.bindings),),
    )
    nested_let = LetStarExpr(
        bindings=tuple(new_bindings),
        body=_wrap_bindings(body_bindings, body_terminal, expr.body),
        span=expr.span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    binding_name = _condition_binding_name(expr, role="value", path=path)
    return ((binding_name, nested_let),), _name_expr(binding_name, expr)


def _normalize_match_value(
    expr: MatchExpr,
    *,
    path: tuple[int, ...],
) -> tuple[tuple[tuple[str, ExprNode], ...], ExprNode]:
    subject_bindings, subject_terminal = _normalize_operand(expr.subject, path=path + (0,))
    arms: list[MatchArm] = []
    for index, arm in enumerate(expr.arms):
        arm_bindings, arm_terminal = _normalize_operand(arm.body, path=path + (1 + index,))
        arms.append(
            MatchArm(
                variant_name=arm.variant_name,
                binding_name=arm.binding_name,
                body=_wrap_bindings(arm_bindings, arm_terminal, arm.body),
                span=arm.span,
                form_path=arm.form_path,
                expansion_stack=arm.expansion_stack,
            )
        )
    nested_match = MatchExpr(
        subject=subject_terminal,
        arms=tuple(arms),
        span=expr.span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    binding_name = _condition_binding_name(expr, role="value", path=path)
    return (*subject_bindings, (binding_name, nested_match)), _name_expr(
        binding_name,
        expr,
    )


def _normalize_list_map(
    expr: ListMapExpr | ListMapEffectExpr,
    *,
    path: tuple[int, ...],
) -> tuple[tuple[tuple[str, ExprNode], ...], ExprNode]:
    # The source evaluates in the enclosing scope; body bindings stay inside
    # the binder/iteration scope so they never leave the per-item execution.
    source_bindings, source_terminal = _normalize_operand(expr.source_expr, path=path + (0,))
    body_bindings, body_terminal = _normalize_operand(expr.body_expr, path=path + (1,))
    rebuilt = dataclasses.replace(
        expr,
        source_expr=source_terminal,
        body_expr=_wrap_bindings(body_bindings, body_terminal, expr.body_expr),
    )
    if isinstance(expr, ListMapEffectExpr):
        binding_name = _condition_binding_name(expr, role="effect", path=path)
        return (*source_bindings, (binding_name, rebuilt)), _name_expr(binding_name, expr)
    return source_bindings, rebuilt


def _normalize_loop_recur(
    expr: LoopRecurExpr,
    *,
    path: tuple[int, ...],
) -> tuple[tuple[tuple[str, ExprNode], ...], ExprNode]:
    # Bounds/seed evaluate in the enclosing scope. The loop body normalizes in
    # its iteration scope (state-dependent `and`/`or` folds, the `done`/
    # `continue` spine stays intact); exhaustion bindings wrap inside the
    # exhaustion branch so they only execute on exhaustion.
    hoisted: list[tuple[str, ExprNode]] = []
    max_bindings, max_terminal = _normalize_operand(
        expr.max_iterations_expr,
        path=path + (0,),
    )
    hoisted.extend(max_bindings)
    init_bindings, init_terminal = _normalize_operand(
        expr.initial_state_expr,
        path=path + (1,),
    )
    hoisted.extend(init_bindings)
    body_bindings, body_terminal = _normalize_loop_body(
        expr.body_expr,
        path=path + (2,),
    )
    on_exhausted = expr.on_exhausted_result_expr
    if on_exhausted is not None:
        exhausted_bindings, exhausted_terminal = _normalize_operand(
            on_exhausted,
            path=path + (3,),
        )
        on_exhausted = _wrap_bindings(
            exhausted_bindings,
            exhausted_terminal,
            on_exhausted,
        )
    rebuilt = dataclasses.replace(
        expr,
        max_iterations_expr=max_terminal,
        initial_state_expr=init_terminal,
        body_expr=_wrap_bindings(body_bindings, body_terminal, expr.body_expr),
        on_exhausted_result_expr=on_exhausted,
    )
    binding_name = _condition_binding_name(expr, role="value", path=path)
    return (*hoisted, (binding_name, rebuilt)), _name_expr(binding_name, expr)


def _normalize_loop_body(
    expr: ExprNode,
    *,
    path: tuple[int, ...],
) -> tuple[tuple[tuple[str, ExprNode], ...], ExprNode]:
    """Normalize one loop body inside its iteration scope.

    Like ``_normalize_operand``, except control/value spine forms are rebuilt
    in place rather than bound, preserving the ``done``/``continue`` terminals
    loop lowering requires.
    """

    if isinstance(expr, PureOpExpr) and expr.operator in {"and", "or"}:
        return _normalize_short_circuit(expr, path=path)
    if isinstance(expr, PureOpExpr) and expr.operator == "not":
        return _normalize_not(expr, path=path)
    if isinstance(expr, PureOpExpr):
        return _normalize_pure_op(expr, path=path)
    if isinstance(expr, _EFFECT_EXPRS):
        return _normalize_effect_operand(expr, path=path)
    if isinstance(expr, _LEAF_EXPRS):
        return (), expr
    if isinstance(expr, IfExpr):
        return _normalize_loop_body_if(expr, path=path)
    if isinstance(expr, MatchExpr):
        return _normalize_loop_body_match(expr, path=path)
    if isinstance(expr, LetStarExpr):
        return _normalize_loop_body_let(expr, path=path)
    if isinstance(expr, _LOOP_SPINE_EXPRS) or isinstance(
        expr, _COMPOSITE_VALUE_EXPRS
    ):
        return _normalize_loop_body_composite(expr, path=path)


def _normalize_loop_body_if(
    expr: IfExpr,
    *,
    path: tuple[int, ...],
) -> tuple[tuple[tuple[str, ExprNode], ...], ExprNode]:
    condition_bindings, condition_terminal = _normalize_loop_body(
        expr.condition_expr,
        path=path + (0,),
    )
    then_bindings, then_terminal = _normalize_loop_body(expr.then_expr, path=path + (1,))
    else_bindings, else_terminal = _normalize_loop_body(expr.else_expr, path=path + (2,))
    rebuilt = IfExpr(
        condition_expr=condition_terminal,
        then_expr=_wrap_bindings(then_bindings, then_terminal, expr.then_expr),
        else_expr=_wrap_bindings(else_bindings, else_terminal, expr.else_expr),
        span=expr.span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    return condition_bindings, rebuilt


def _normalize_loop_body_match(
    expr: MatchExpr,
    *,
    path: tuple[int, ...],
) -> tuple[tuple[tuple[str, ExprNode], ...], ExprNode]:
    subject_bindings, subject_terminal = _normalize_loop_body(
        expr.subject,
        path=path + (0,),
    )
    arms: list[MatchArm] = []
    for index, arm in enumerate(expr.arms):
        arm_bindings, arm_terminal = _normalize_loop_body(arm.body, path=path + (1 + index,))
        arms.append(
            MatchArm(
                variant_name=arm.variant_name,
                binding_name=arm.binding_name,
                body=_wrap_bindings(arm_bindings, arm_terminal, arm.body),
                span=arm.span,
                form_path=arm.form_path,
                expansion_stack=arm.expansion_stack,
            )
        )
    rebuilt = MatchExpr(
        subject=subject_terminal,
        arms=tuple(arms),
        span=expr.span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    return subject_bindings, rebuilt


def _normalize_loop_body_let(
    expr: LetStarExpr,
    *,
    path: tuple[int, ...],
) -> tuple[tuple[tuple[str, ExprNode], ...], ExprNode]:
    new_bindings: list[tuple[str, ExprNode]] = []
    for index, (binding_name, binding_expr) in enumerate(expr.bindings):
        bindings, terminal = _normalize_loop_body(binding_expr, path=path + (index,))
        new_bindings.append(
            (binding_name, _wrap_bindings(bindings, terminal, binding_expr))
        )
    body_bindings, body_terminal = _normalize_loop_body(
        expr.body,
        path=path + (len(expr.bindings),),
    )
    rebuilt = LetStarExpr(
        bindings=tuple(new_bindings),
        body=_wrap_bindings(body_bindings, body_terminal, expr.body),
        span=expr.span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    return (), rebuilt


def _normalize_loop_body_composite(
    expr: ExprNode,
    *,
    path: tuple[int, ...],
) -> tuple[tuple[tuple[str, ExprNode], ...], ExprNode]:
    children = iter_child_exprs(expr)
    if not children:
        return (), expr
    hoisted: list[tuple[str, ExprNode]] = []
    replacements: dict[int, ExprNode] = {}
    for index, child in enumerate(children):
        if not isinstance(child, ExprNode):
            continue
        child_bindings, child_terminal = _normalize_loop_body(
            child,
            path=path + (index,),
        )
        hoisted.extend(child_bindings)
        replacements[id(child)] = child_terminal
    return tuple(hoisted), _rebuild_with_replacements(expr, replacements)


def _normalize_with_phase(
    expr: WithPhaseExpr,
    *,
    path: tuple[int, ...],
) -> tuple[tuple[tuple[str, ExprNode], ...], ExprNode]:
    # The phase context evaluates in the enclosing scope; the phase body
    # evaluates inside the phase scope, so its generated bindings stay inside
    # the body. The complete wrapper result is bound once through the generic
    # non-linear join like other control values.
    ctx_bindings, ctx_terminal = _normalize_operand(expr.ctx_expr, path=path + (0,))
    body_bindings, body_terminal = _normalize_operand(expr.body, path=path + (1,))
    rebuilt = dataclasses.replace(
        expr,
        ctx_expr=ctx_terminal,
        body=_wrap_bindings(body_bindings, body_terminal, expr.body),
    )
    binding_name = _condition_binding_name(expr, role="value", path=path)
    return (*ctx_bindings, (binding_name, rebuilt)), _name_expr(binding_name, expr)


def _normalize_let_proc(
    expr: LetProcExpr,
    *,
    path: tuple[int, ...],
) -> tuple[tuple[tuple[str, ExprNode], ...], ExprNode]:
    body_bindings, body_terminal = _normalize_operand(expr.body, path=path + (0,))
    nested = dataclasses.replace(
        expr,
        body=_wrap_bindings(body_bindings, body_terminal, expr.body),
    )
    binding_name = _condition_binding_name(expr, role="value", path=path)
    return ((binding_name, nested),), _name_expr(binding_name, expr)

def _normalize_live_provider_owner(
    expr: WithLiveProvidersExpr | WithLiveProviderPeersExpr,
    *,
    path: tuple[int, ...],
) -> tuple[tuple[tuple[str, ExprNode], ...], ExprNode]:
    # Member value expressions are provider performs owned by the group: keep
    # the provider node itself as the member (WCC validates the closed perform)
    # and wrap any generated member-child binding inside the member `value_expr`
    # so it executes within the live-provider lifecycle rather than acquiring
    # outer state ancestry. The settlement body evaluates inside the owner
    # where the member names are bound, so its bindings stay inside the body.
    new_bindings = []
    for index, binding in enumerate(expr.bindings):
        child_bindings, terminal = _normalize_composite(
            binding.value_expr,
            path=path + (index,),
        )
        new_bindings.append(
            dataclasses.replace(
                binding,
                value_expr=_wrap_bindings(
                    child_bindings,
                    terminal,
                    binding.value_expr,
                ),
            )
        )
    body_bindings, body_terminal = _normalize_operand(
        expr.body,
        path=path + (len(expr.bindings),),
    )
    rebuilt = dataclasses.replace(
        expr,
        bindings=tuple(new_bindings),
        body=_wrap_bindings(body_bindings, body_terminal, expr.body),
    )
    binding_name = _condition_binding_name(expr, role="effect", path=path)
    return ((binding_name, rebuilt),), _name_expr(binding_name, expr)


def _normalize_with_live_providers(
    expr: WithLiveProvidersExpr,
    *,
    path: tuple[int, ...],
) -> tuple[tuple[tuple[str, ExprNode], ...], ExprNode]:
    return _normalize_live_provider_owner(expr, path=path)


def _normalize_with_live_provider_peers(
    expr: WithLiveProviderPeersExpr,
    *,
    path: tuple[int, ...],
) -> tuple[tuple[tuple[str, ExprNode], ...], ExprNode]:
    return _normalize_live_provider_owner(expr, path=path)


def _normalize_trial(
    expr: TrialExpr,
    *,
    path: tuple[int, ...],
) -> tuple[tuple[tuple[str, ExprNode], ...], ExprNode]:
    # Each arm's run-ref is a lifecycle child owned by the trial: keep the
    # run-ref node itself as the arm (trial static config digests it), while
    # its input projections evaluate in the enclosing scope and fold any
    # condition-owned Bool `and`/`or` there.
    hoisted: list[tuple[str, ExprNode]] = []
    new_arms = []
    for index, arm in enumerate(expr.arms):
        arm_bindings, rebuilt_run_ref = _normalize_composite(
            arm.run_ref,
            path=path + (index,),
        )
        hoisted.extend(arm_bindings)
        new_arms.append(dataclasses.replace(arm, run_ref=rebuilt_run_ref))
    rebuilt = dataclasses.replace(expr, arms=tuple(new_arms))
    binding_name = _condition_binding_name(expr, role="effect", path=path)
    return (*hoisted, (binding_name, rebuilt)), _name_expr(binding_name, expr)


def _normalize_resume_or_start(
    expr: ResumeOrStartExpr,
    *,
    path: tuple[int, ...],
) -> tuple[tuple[tuple[str, ExprNode], ...], ExprNode]:
    # `ctx_expr` and `resume_from_expr` are always evaluated in the enclosing
    # scope; the `start_expr` branch runs only on a fresh start, so its
    # generated bindings stay wrapped inside the start branch.
    hoisted: list[tuple[str, ExprNode]] = []
    ctx_bindings, ctx_terminal = _normalize_operand(expr.ctx_expr, path=path + (0,))
    hoisted.extend(ctx_bindings)
    resume_bindings, resume_terminal = _normalize_operand(
        expr.resume_from_expr,
        path=path + (1,),
    )
    hoisted.extend(resume_bindings)
    start_bindings, start_terminal = _normalize_composite(
        expr.start_expr,
        path=path + (2,),
    )
    rebuilt = dataclasses.replace(
        expr,
        ctx_expr=ctx_terminal,
        resume_from_expr=resume_terminal,
        start_expr=_wrap_bindings(start_bindings, start_terminal, expr.start_expr),
    )
    binding_name = _condition_binding_name(expr, role="effect", path=path)
    return (*hoisted, (binding_name, rebuilt)), _name_expr(binding_name, expr)


def _normalize_effect_operand(
    expr: ExprNode,
    *,
    path: tuple[int, ...],
) -> tuple[tuple[tuple[str, ExprNode], ...], ExprNode]:
    binding_name = _condition_binding_name(expr, role="effect", path=path)
    # Normalize ordinary expression children (arguments/inputs) before binding
    # the parent; body-scoped children (live-provider settlement bodies) keep
    # their bindings inside the wrapper via _normalize_composite's guard.
    child_bindings, rebuilt = _normalize_composite(expr, path=path)
    return (*child_bindings, (binding_name, rebuilt)), _name_expr(binding_name, expr)


def _normalize_composite(
    expr: ExprNode,
    *,
    path: tuple[int, ...],
) -> tuple[tuple[tuple[str, ExprNode], ...], ExprNode]:
    children = iter_child_exprs(expr)
    if not children:
        return (), expr
    hoisted: list[tuple[str, ExprNode]] = []
    replacements: dict[int, ExprNode] = {}
    for index, child in enumerate(children):
        if not isinstance(child, ExprNode):
            continue
        child_bindings, child_terminal = _normalize_operand(child, path=path + (index,))
        hoisted.extend(child_bindings)
        replacements[id(child)] = child_terminal
    return tuple(hoisted), _rebuild_with_replacements(expr, replacements)


def normalize_expanded_conditions(
    expr: ExprNode,
    *,
    target_dsl_version: str | None,
) -> ExprNode:
    """Fold helper-inserted pure ``and``/``or`` after helper expansion.

    The frontend ``if`` typechecker already normalizes authored conditions
    (hoisting effects with the exact effect summary). Helper bodies are
    inlined later, so a pure ``and``/``or`` authored there re-enters the
    condition; this pass only folds those operators back into nested
    ``IfExpr`` and is idempotent (no effect hoisting, no new bindings).
    """

    from .syntax import target_dsl_supports_strict_boolean_control_flow

    if not target_dsl_supports_strict_boolean_control_flow(
        target_dsl_version or ""
    ):
        return expr
    if isinstance(expr, PureOpExpr) and expr.operator in {"and", "or"}:
        # Only fold exact helper-expansion clones (a `HelperExpansionFrame`
        # present in the expansion stack). Authored pure `and`/`or` in a value
        # position is folded later by WCC value elaboration, and authored
        # condition `and`/`or` is normalized by the `if` typechecker; folding
        # authored subtrees here would hoist/rewrite non-condition forms.
        if not _is_helper_expanded(expr) or _contains_effect(expr):
            return expr
        normalized_args = tuple(
            normalize_expanded_conditions(arg, target_dsl_version=target_dsl_version)
            for arg in expr.args
        )
        return fold_pure_short_circuit(
            dataclasses.replace(expr, args=normalized_args)
        )
    if isinstance(expr, PureOpExpr):
        return dataclasses.replace(
            expr,
            args=tuple(
                normalize_expanded_conditions(arg, target_dsl_version=target_dsl_version)
                for arg in expr.args
            ),
        )
    children = iter_child_exprs(expr)
    if not children:
        return expr
    replacements = {
        id(child): normalize_expanded_conditions(
            child, target_dsl_version=target_dsl_version
        )
        for child in children
        if isinstance(child, ExprNode)
    }
    if not replacements:
        return expr
    return _rebuild_with_replacements(expr, replacements)


def fold_pure_short_circuit(expr: PureOpExpr) -> IfExpr:
    """Fold one pure ``and``/``or`` into nested ``if`` without bindings."""

    operator = expr.operator
    if operator == "and":
        inner = _literal_bool(True, expr)
        for terminal in reversed(expr.args[1:]):
            inner = IfExpr(
                condition_expr=terminal,
                then_expr=inner,
                else_expr=_literal_bool(False, expr),
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
        return IfExpr(
            condition_expr=expr.args[0],
            then_expr=inner,
            else_expr=_literal_bool(False, expr),
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    inner = _literal_bool(False, expr)
    for terminal in reversed(expr.args[1:]):
        inner = IfExpr(
            condition_expr=terminal,
            then_expr=_literal_bool(True, expr),
            else_expr=inner,
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    return IfExpr(
        condition_expr=expr.args[0],
        then_expr=_literal_bool(True, expr),
        else_expr=inner,
        span=expr.span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )


def _wrap_bindings(
    bindings: tuple[tuple[str, ExprNode], ...],
    terminal: ExprNode,
    source_expr: ExprNode,
) -> ExprNode:
    if not bindings:
        return terminal
    return LetStarExpr(
        bindings=tuple(bindings),
        body=terminal,
        span=source_expr.span,
        form_path=source_expr.form_path,
        expansion_stack=source_expr.expansion_stack,
    )


def _name_expr(name: str, source_expr: ExprNode) -> NameExpr:
    return NameExpr(
        name=name,
        span=source_expr.span,
        form_path=source_expr.form_path,
        expansion_stack=source_expr.expansion_stack,
    )


def _literal_bool(value: bool, source_expr: ExprNode) -> LiteralExpr:
    return LiteralExpr(
        value=value,
        literal_kind="bool",
        span=source_expr.span,
        form_path=source_expr.form_path,
        expansion_stack=source_expr.expansion_stack,
    )


def _condition_binding_name(
    source_expr: ExprNode,
    *,
    role: str,
    path: tuple[int, ...],
) -> str:
    safe_role = "".join(char if char.isalnum() else "_" for char in role).strip("_")
    basis = repr(
        (
            tuple(source_expr.form_path),
            role,
            tuple(path),
            source_expr.span.start.offset,
            source_expr.span.end.offset,
        )
    )
    digest = hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]
    return f"__cond_{safe_role}_{digest}"
