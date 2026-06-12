"""Frontend-local conditional classification and predicate rendering."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .expressions import ExprNode, FieldAccessExpr, IfExpr, LetStarExpr, LiteralExpr, NameExpr, PureOpExpr
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


def classify_condition_expr(expr: ExprNode, *, type_ref: TypeRef) -> ConditionShape:
    """Classify one authored `if` condition into the narrow lowering subset."""

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
    if _is_projectable_pure_bool_expr(expr):
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
