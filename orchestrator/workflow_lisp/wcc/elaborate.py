"""Pure-subset elaboration from typed frontend expressions into WCC."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from ..expressions import FieldAccessExpr, LetStarExpr, LiteralExpr, NameExpr, RecordExpr, UnionVariantExpr
from ..spans import SourceSpan
from ..type_env import FrontendTypeEnvironment, PrimitiveTypeRef, RecordTypeRef, TypeRef, UnionTypeRef
from ..typecheck_context import TypedExpr
from ..workflows import TypedWorkflowDef
from .model import (
    WccBody,
    WccFieldAccessAtom,
    WccHalt,
    WccIdentityFactory,
    WccInject,
    WccLet,
    WccLiteralAtom,
    WccNameAtom,
    WccRecordAtom,
    WccValue,
)


def elaborate_typed_workflow_body(
    typed_body: TypedExpr,
    *,
    owner_name: str,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
) -> WccBody:
    """Elaborate one typed workflow body into the WCC M1 pure subset."""

    scope = WccIdentityFactory(owner_name=owner_name, lexical_owner_chain=("workflow",))
    return _elaborate_expr_to_body(
        typed_body.expr,
        scope=scope,
        type_env=type_env,
        value_env=dict(value_env),
    )


def elaborate_typed_workflow(
    typed_workflow: TypedWorkflowDef,
    *,
    type_env: FrontendTypeEnvironment,
) -> WccBody:
    """Convenience wrapper for elaborating one typed workflow definition."""

    return elaborate_typed_workflow_body(
        typed_workflow.typed_body,
        owner_name=typed_workflow.definition.name,
        type_env=type_env,
        value_env=dict(typed_workflow.signature.params),
    )


def _body_to_prefix_and_value(body: WccBody) -> tuple[tuple[WccLet, ...], WccValue]:
    prefix: list[WccLet] = []
    current = body
    while isinstance(current, WccLet):
        prefix.append(current)
        current = current.body
    return tuple(prefix), current.result


def _wrap_prefix_lets(prefix: tuple[WccLet, ...], tail: WccBody) -> WccBody:
    current = tail
    for let_node in reversed(prefix):
        current = replace(let_node, body=current)
    return current


def _elaborate_expr_to_body(
    expr,
    *,
    scope: WccIdentityFactory,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
) -> WccBody:
    if isinstance(expr, LetStarExpr):
        return _elaborate_let_star(expr, scope=scope, type_env=type_env, value_env=value_env)
    prefix, value = _elaborate_expr_to_value(
        expr,
        scope=scope,
        type_env=type_env,
        value_env=value_env,
    )
    halt = WccHalt(
        metadata=scope.body_metadata(
            role="halt:return",
            type_ref=_infer_expr_type(expr, type_env=type_env, value_env=value_env),
            source_span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        ),
        result=value,
    )
    return _wrap_prefix_lets(prefix, halt)


def _elaborate_let_star(
    expr: LetStarExpr,
    *,
    scope: WccIdentityFactory,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
) -> WccBody:
    result_type = _infer_expr_type(expr, type_env=type_env, value_env=value_env)

    def build(index: int, local_env: Mapping[str, TypeRef], local_scope: WccIdentityFactory) -> WccBody:
        if index >= len(expr.bindings):
            return _elaborate_expr_to_body(
                expr.body,
                scope=local_scope.child_scope("body", authored_binding_name="result"),
                type_env=type_env,
                value_env=local_env,
            )

        binding_name, binding_expr = expr.bindings[index]
        binding_type = _infer_expr_type(binding_expr, type_env=type_env, value_env=local_env)
        binding_scope = local_scope.child_scope("binding", authored_binding_name=binding_name)
        binding_body = _elaborate_expr_to_body(
            binding_expr,
            scope=binding_scope,
            type_env=type_env,
            value_env=local_env,
        )
        prefix, value = _body_to_prefix_and_value(binding_body)
        next_env = dict(local_env)
        next_env[binding_name] = binding_type
        tail = build(index + 1, next_env, local_scope.child_scope("body", authored_binding_name=binding_name))
        let_node = WccLet(
            metadata=local_scope.body_metadata(
                role=f"let:{binding_name}",
                type_ref=result_type,
                source_span=binding_expr.span,
                form_path=binding_expr.form_path,
                expansion_stack=binding_expr.expansion_stack,
            ),
            bound_name=binding_name,
            bound_type_ref=binding_type,
            bound_value=value,
            body=tail,
        )
        return _wrap_prefix_lets(prefix, let_node)

    return build(0, dict(value_env), scope)


def _elaborate_expr_to_value(
    expr,
    *,
    scope: WccIdentityFactory,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
) -> tuple[tuple[WccLet, ...], WccValue]:
    if isinstance(expr, LiteralExpr):
        return (
            (),
            WccLiteralAtom(
                metadata=scope.atom_metadata(
                    role=f"literal:{expr.literal_kind}",
                    type_ref=_infer_expr_type(expr, type_env=type_env, value_env=value_env),
                    source_span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
                value=expr.value,
                literal_kind=expr.literal_kind,
            ),
        )
    if isinstance(expr, NameExpr):
        return (
            (),
            WccNameAtom(
                metadata=scope.atom_metadata(
                    role=f"name:{expr.name}",
                    type_ref=_infer_expr_type(expr, type_env=type_env, value_env=value_env),
                    source_span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
                name=expr.name,
            ),
        )
    if isinstance(expr, FieldAccessExpr):
        base_type = value_env[expr.base.name]
        return (
            (),
            WccFieldAccessAtom(
                metadata=scope.atom_metadata(
                    role=f"field:{'.'.join((expr.base.name, *expr.fields))}",
                    type_ref=_infer_expr_type(expr, type_env=type_env, value_env=value_env),
                    source_span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
                base=WccNameAtom(
                    metadata=scope.atom_metadata(
                        role=f"name:{expr.base.name}",
                        type_ref=base_type,
                        source_span=expr.base.span,
                        form_path=expr.base.form_path,
                        expansion_stack=expr.base.expansion_stack,
                    ),
                    name=expr.base.name,
                ),
                fields=expr.fields,
            ),
        )
    if isinstance(expr, RecordExpr):
        record_type = _require_record_type(expr, type_env=type_env)
        prefix: list[WccLet] = []
        fields: list[tuple[str, WccValue]] = []
        for field_name, field_expr in expr.fields:
            field_body = _elaborate_expr_to_body(
                field_expr,
                scope=scope.child_scope("record-field", authored_binding_name=field_name),
                type_env=type_env,
                value_env=value_env,
            )
            field_prefix, field_value = _body_to_prefix_and_value(field_body)
            prefix.extend(field_prefix)
            fields.append((field_name, field_value))
        return (
            tuple(prefix),
            WccRecordAtom(
                metadata=scope.atom_metadata(
                    role=f"record:{expr.type_name}",
                    type_ref=record_type,
                    source_span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
                type_name=expr.type_name,
                fields=tuple(fields),
            ),
        )
    if isinstance(expr, UnionVariantExpr):
        union_type = _require_union_type(expr, type_env=type_env)
        prefix: list[WccLet] = []
        fields: list[tuple[str, WccValue]] = []
        for field_name, field_expr in expr.fields:
            field_body = _elaborate_expr_to_body(
                field_expr,
                scope=scope.child_scope("union-field", authored_binding_name=field_name),
                type_env=type_env,
                value_env=value_env,
            )
            field_prefix, field_value = _body_to_prefix_and_value(field_body)
            prefix.extend(field_prefix)
            fields.append((field_name, field_value))
        return (
            tuple(prefix),
            WccInject(
                metadata=scope.value_metadata(
                    role=f"inject:{expr.variant_name}",
                    type_ref=union_type,
                    source_span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
                union_name=expr.type_name,
                variant_name=expr.variant_name,
                fields=tuple(fields),
            ),
        )
    if isinstance(expr, LetStarExpr):
        prefix, value = _body_to_prefix_and_value(
            _elaborate_let_star(expr, scope=scope, type_env=type_env, value_env=value_env)
        )
        return prefix, value
    raise TypeError(f"unsupported WCC M1 elaboration node: {type(expr).__name__}")


def _require_record_type(expr: RecordExpr, *, type_env: FrontendTypeEnvironment) -> RecordTypeRef:
    resolved = type_env.resolve_type(
        expr.type_name,
        span=expr.span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    if not isinstance(resolved, RecordTypeRef):
        raise TypeError(f"expected record type for `{expr.type_name}`")
    return resolved


def _require_union_type(expr: UnionVariantExpr, *, type_env: FrontendTypeEnvironment) -> UnionTypeRef:
    resolved = type_env.resolve_type(
        expr.type_name,
        span=expr.span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    if not isinstance(resolved, UnionTypeRef):
        raise TypeError(f"expected union type for `{expr.type_name}`")
    return resolved


def _infer_expr_type(
    expr,
    *,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
) -> TypeRef:
    if isinstance(expr, LiteralExpr):
        return {
            "string": PrimitiveTypeRef(name="String"),
            "int": PrimitiveTypeRef(name="Int"),
            "bool": PrimitiveTypeRef(name="Bool"),
            "float": PrimitiveTypeRef(name="Float"),
        }[expr.literal_kind]
    if isinstance(expr, NameExpr):
        return value_env[expr.name]
    if isinstance(expr, FieldAccessExpr):
        current: TypeRef = value_env[expr.base.name]
        for field_name in expr.fields:
            current = type_env.record_field(
                current,
                field_name,
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
        return current
    if isinstance(expr, RecordExpr):
        return _require_record_type(expr, type_env=type_env)
    if isinstance(expr, UnionVariantExpr):
        return _require_union_type(expr, type_env=type_env)
    if isinstance(expr, LetStarExpr):
        local_env = dict(value_env)
        for binding_name, binding_expr in expr.bindings:
            local_env[binding_name] = _infer_expr_type(
                binding_expr,
                type_env=type_env,
                value_env=local_env,
            )
        return _infer_expr_type(expr.body, type_env=type_env, value_env=local_env)
    raise TypeError(f"unsupported WCC M1 type inference node: {type(expr).__name__}")
