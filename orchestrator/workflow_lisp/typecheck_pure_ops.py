"""Pure-expression typing ownership for Workflow Lisp."""

from __future__ import annotations

from dataclasses import replace

from .effects import EMPTY_EFFECT_SUMMARY, merge_effect_summaries
from orchestrator.workflow.pure_expr import PURE_EXPR_OPERATOR_CATALOG
from .expressions import PureOpExpr, RecordUpdateExpr
from .type_env import OptionalTypeRef, PathTypeRef, PrimitiveTypeRef, RecordTypeRef, TypeRef


def typecheck_pure_expr(
    expr: PureOpExpr | RecordUpdateExpr,
    *,
    context,
    recurse,
    typed_factory,
):
    from . import typecheck as compat

    if isinstance(expr, PureOpExpr):
        spec = PURE_EXPR_OPERATOR_CATALOG.get(expr.operator)
        if spec is None:
            compat._raise_error(
                f"unsupported pure operator `{expr.operator}`",
                code="pure_expr_operator_unsupported",
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
        arity = len(expr.args)
        if arity < spec.min_arity or (spec.max_arity is not None and arity > spec.max_arity):
            _raise_operand_mismatch(
                compat=compat,
                expr=expr,
                message=(
                    f"operator `{expr.operator}` requires between {spec.min_arity} and "
                    f"{spec.max_arity if spec.max_arity is not None else 'many'} operands"
                ),
            )
        typed_args = [recurse(arg) for arg in expr.args]
        rewritten = replace(expr, args=tuple(typed_arg.expr for typed_arg in typed_args))
        summaries = [typed_arg.effect_summary for typed_arg in typed_args]
        arg_types = [typed_arg.type_ref for typed_arg in typed_args]
        operator = expr.operator

        if operator in {"=", "!="}:
            left, right = arg_types
            if _is_union_like(left) or _is_union_like(right):
                compat._raise_error(
                    "union equality is forbidden in the pure expression core",
                    code="pure_expr_union_equality_forbidden",
                    span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                )
            if _is_primitive(left, "Float") or _is_primitive(right, "Float"):
                compat._raise_error(
                    "float equality is forbidden in the pure expression core",
                    code="pure_expr_float_equality_forbidden",
                    span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                )
            if left != right or not _supports_equality(left):
                _raise_operand_mismatch(
                    compat=compat,
                    expr=expr,
                    message=f"operator `{operator}` requires equal comparable operand types",
                )
            return typed_factory(
                expr=rewritten,
                type_ref=PrimitiveTypeRef(name="Bool"),
                effect=merge_effect_summaries(*summaries),
            )

        if operator in {"<", "<=", ">", ">="}:
            left, right = arg_types
            if left != right or not (_is_primitive(left, "Int") or _is_primitive(left, "Float")):
                _raise_operand_mismatch(
                    compat=compat,
                    expr=expr,
                    message=f"operator `{operator}` requires matching Int or Float operands",
                )
            return typed_factory(
                expr=rewritten,
                type_ref=PrimitiveTypeRef(name="Bool"),
                effect=merge_effect_summaries(*summaries),
            )

        if operator in {"and", "or"}:
            for arg_type in arg_types:
                _require_primitive(
                    compat=compat,
                    expr=expr,
                    type_ref=arg_type,
                    name="Bool",
                    operator=operator,
                )
            return typed_factory(
                expr=rewritten,
                type_ref=PrimitiveTypeRef(name="Bool"),
                effect=merge_effect_summaries(*summaries),
            )

        if operator == "not":
            _require_primitive(
                compat=compat,
                expr=expr,
                type_ref=arg_types[0],
                name="Bool",
                operator=operator,
            )
            return typed_factory(
                expr=rewritten,
                type_ref=PrimitiveTypeRef(name="Bool"),
                effect=merge_effect_summaries(*summaries),
            )

        if operator in {"+", "-", "*", "min", "max"}:
            for arg_type in arg_types:
                _require_primitive(
                    compat=compat,
                    expr=expr,
                    type_ref=arg_type,
                    name="Int",
                    operator=operator,
                )
            return typed_factory(
                expr=rewritten,
                type_ref=PrimitiveTypeRef(name="Int"),
                effect=merge_effect_summaries(*summaries),
            )

        if operator == "string/concat":
            if any(isinstance(arg_type, PathTypeRef) for arg_type in arg_types):
                compat._raise_error(
                    "path string concatenation is forbidden in the pure expression core",
                    code="pure_expr_path_string_concat_forbidden",
                    span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                )
            for arg_type in arg_types:
                _require_primitive(
                    compat=compat,
                    expr=expr,
                    type_ref=arg_type,
                    name="String",
                    operator=operator,
                )
            return typed_factory(
                expr=rewritten,
                type_ref=PrimitiveTypeRef(name="String"),
                effect=merge_effect_summaries(*summaries),
            )

        if operator == "string/empty?":
            _require_primitive(
                compat=compat,
                expr=expr,
                type_ref=arg_types[0],
                name="String",
                operator=operator,
            )
            return typed_factory(
                expr=rewritten,
                type_ref=PrimitiveTypeRef(name="Bool"),
                effect=merge_effect_summaries(*summaries),
            )

        if operator == "symbol/name":
            _require_primitive(
                compat=compat,
                expr=expr,
                type_ref=arg_types[0],
                name="Symbol",
                operator=operator,
            )
            return typed_factory(
                expr=rewritten,
                type_ref=PrimitiveTypeRef(name="String"),
                effect=merge_effect_summaries(*summaries),
            )

        if operator == "some?":
            if not isinstance(arg_types[0], OptionalTypeRef):
                _raise_operand_mismatch(
                    compat=compat,
                    expr=expr,
                    message="`some?` requires an Optional operand",
                )
            return typed_factory(
                expr=rewritten,
                type_ref=PrimitiveTypeRef(name="Bool"),
                effect=merge_effect_summaries(*summaries),
            )

        if operator == "or-else":
            optional_type = arg_types[0]
            if not isinstance(optional_type, OptionalTypeRef):
                _raise_operand_mismatch(
                    compat=compat,
                    expr=expr,
                    message="`or-else` requires an Optional first operand",
                )
            if optional_type.item_type_ref != arg_types[1]:
                _raise_operand_mismatch(
                    compat=compat,
                    expr=expr,
                    message="`or-else` fallback type must match the Optional item type",
                )
            return typed_factory(
                expr=rewritten,
                type_ref=optional_type.item_type_ref,
                effect=merge_effect_summaries(*summaries),
            )

        raise AssertionError(f"unhandled pure operator `{operator}`")

    typed_base = recurse(expr.base_expr)
    if not isinstance(typed_base.type_ref, RecordTypeRef):
        _raise_operand_mismatch(
            compat=compat,
            expr=expr,
            message="`record-update` requires a record base expression",
        )
    expected_fields = {field.name: field for field in typed_base.type_ref.definition.fields}
    seen_fields: set[str] = set()
    summaries = [typed_base.effect_summary]
    rewritten_overrides: list[tuple[str, object]] = []
    for field_name, field_expr in expr.overrides:
        if field_name in seen_fields:
            compat._raise_error(
                f"duplicate field `{field_name}` in record-update expression",
                code="record_field_duplicate",
                span=field_expr.span,
                form_path=field_expr.form_path,
                expansion_stack=field_expr.expansion_stack,
            )
        seen_fields.add(field_name)
        expected_field = expected_fields.get(field_name)
        if expected_field is None:
            compat._raise_error(
                f"unknown field `{field_name}` for record `{typed_base.type_ref.name}`",
                code="record_field_unknown",
                span=field_expr.span,
                form_path=field_expr.form_path,
                expansion_stack=field_expr.expansion_stack,
            )
        typed_value = recurse(field_expr)
        summaries.append(typed_value.effect_summary)
        expected_type = typed_base.type_ref.field_types.get(field_name)
        if expected_type is None:
            expected_type = context.type_env.resolve_type(
                expected_field.type_name,
                span=field_expr.span,
                form_path=field_expr.form_path,
                expansion_stack=field_expr.expansion_stack,
            )
        if expected_type != typed_value.type_ref:
            _raise_operand_mismatch(
                compat=compat,
                expr=field_expr,
                message=(
                    f"record-update field `{field_name}` expected `{compat._type_label(expected_type)}` "
                    f"but got `{compat._type_label(typed_value.type_ref)}`"
                ),
            )
        rewritten_overrides.append((field_name, typed_value.expr))
    return typed_factory(
        expr=replace(
            expr,
            base_expr=typed_base.expr,
            overrides=tuple(rewritten_overrides),
        ),
        type_ref=typed_base.type_ref,
        effect=merge_effect_summaries(*summaries) if summaries else EMPTY_EFFECT_SUMMARY,
    )


def _supports_equality(type_ref: TypeRef) -> bool:
    return (
        _is_primitive(type_ref, "String")
        or _is_primitive(type_ref, "Int")
        or _is_primitive(type_ref, "Bool")
        or _is_primitive(type_ref, "Symbol")
        or (isinstance(type_ref, PrimitiveTypeRef) and bool(type_ref.allowed_values))
    )


def _is_primitive(type_ref: TypeRef, name: str) -> bool:
    return isinstance(type_ref, PrimitiveTypeRef) and type_ref.name == name and not type_ref.allowed_values


def _is_union_like(type_ref: TypeRef) -> bool:
    return type(type_ref).__name__ in {"UnionTypeRef", "VariantCaseTypeRef"}


def _require_primitive(*, compat, expr, type_ref: TypeRef, name: str, operator: str) -> None:
    if not _is_primitive(type_ref, name):
        _raise_operand_mismatch(
            compat=compat,
            expr=expr,
            message=f"operator `{operator}` requires {name} operands",
        )


def _raise_operand_mismatch(*, compat, expr, message: str) -> None:
    compat._raise_error(
        message,
        code="pure_expr_operand_type_mismatch",
        span=expr.span,
        form_path=expr.form_path,
        expansion_stack=getattr(expr, "expansion_stack", ()),
    )
