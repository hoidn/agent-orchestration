"""Frontend-local conditional classification and predicate rendering."""

from __future__ import annotations

import dataclasses
import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .effects import EffectSummary
from .expression_traversal import iter_child_exprs
from .expressions import (
    CallExpr,
    CommandResultExpr,
    EnumMemberExpr,
    ExprNode,
    FieldAccessExpr,
    FinalizeSelectedItemExpr,
    IfExpr,
    LetStarExpr,
    LiteralExpr,
    MatchArm,
    MatchExpr,
    MaterializeViewExpr,
    NameExpr,
    PhaseTargetExpr,
    ProcedureCallExpr,
    ProduceOneOfExpr,
    ProviderResultExpr,
    PureOpExpr,
    ResourceTransitionExpr,
    RunProviderPhaseExpr,
    RunRefExpr,
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

_LEAF_EXPRS: tuple[type, ...] = (
    NameExpr,
    LiteralExpr,
    EnumMemberExpr,
    FieldAccessExpr,
    PhaseTargetExpr,
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
    ``if``/``match`` values reuse the existing non-linear control join, and the
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
    if isinstance(expr, _EFFECT_EXPRS):
        return _normalize_effect_operand(expr, path=path)
    if isinstance(expr, _LEAF_EXPRS):
        return (), expr
    return _normalize_composite(expr, path=path)


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
        inner: ExprNode = _literal_bool(True, expr)
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
    subject_bindings, subject_terminal = _normalize_operand(
        expr.subject,
        path=path + (0,),
    )
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


def _normalize_effect_operand(
    expr: ExprNode,
    *,
    path: tuple[int, ...],
) -> tuple[tuple[tuple[str, ExprNode], ...], ExprNode]:
    binding_name = _condition_binding_name(expr, role="effect", path=path)
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


def _rebuild_with_replacements(
    expr: ExprNode,
    replacements: Mapping[int, ExprNode],
) -> ExprNode:
    def _map_value(value: object) -> object:
        if isinstance(value, ExprNode):
            return replacements.get(id(value), value)
        if isinstance(value, tuple):
            return tuple(_map_value(item) for item in value)
        if isinstance(value, list):
            return [_map_value(item) for item in value]
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            return _map_node(value)
        return value

    def _map_node(node: object) -> object:
        updates = {
            field.name: _map_value(getattr(node, field.name))
            for field in dataclasses.fields(node)
            if field.init
        }
        return dataclasses.replace(node, **updates)

    return _map_node(expr)


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


def fold_pure_short_circuit(expr: PureOpExpr) -> IfExpr:
    """Fold one pure ``and``/``or`` into nested ``if`` without bindings.

    Used by WCC value elaboration to route an authored pure ``and``/``or`` in a
    value position through the same ``WccSelect`` path as an authored ``if``.
    """

    operator = expr.operator
    if operator == "and":
        inner: ExprNode = _literal_bool(True, expr)
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
