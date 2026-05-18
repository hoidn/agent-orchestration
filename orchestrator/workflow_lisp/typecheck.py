"""Frontend-local type and proof checking for Workflow Lisp expressions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .expressions import ExprNode, FieldAccessExpr, LetStarExpr, LiteralExpr, MatchExpr, NameExpr, RecordExpr
from .spans import SourceSpan
from .type_env import (
    FrontendTypeEnvironment,
    PrimitiveTypeRef,
    RecordTypeRef,
    TypeRef,
    UnionTypeRef,
    VariantCaseTypeRef,
)


@dataclass(frozen=True)
class TypedExpr:
    """One expression paired with its resolved frontend-local type."""

    expr: ExprNode
    type_ref: TypeRef
    span: SourceSpan
    form_path: tuple[str, ...]


ValueEnvironment = Mapping[str, TypeRef]


@dataclass(frozen=True)
class ProofFact:
    """One proven union narrowing fact in scope."""

    subject_name: str
    variant_name: str
    variant_type: VariantCaseTypeRef


@dataclass(frozen=True)
class ProofScope:
    """Frontend-local proof facts for the current checking scope."""

    facts: Mapping[str, ProofFact]


def typecheck_expression(
    expr: ExprNode,
    *,
    type_env: FrontendTypeEnvironment,
    value_env: ValueEnvironment,
    proof_scope: ProofScope | None = None,
) -> TypedExpr:
    """Typecheck one bounded Stage 2 expression."""

    active_proof = proof_scope or ProofScope(facts={})
    return _typecheck(expr, type_env=type_env, value_env=dict(value_env), proof_scope=active_proof)


def _typecheck(
    expr: ExprNode,
    *,
    type_env: FrontendTypeEnvironment,
    value_env: dict[str, TypeRef],
    proof_scope: ProofScope,
) -> TypedExpr:
    if isinstance(expr, LiteralExpr):
        return TypedExpr(
            expr=expr,
            type_ref=PrimitiveTypeRef(name=_literal_type_name(expr.literal_kind)),
            span=expr.span,
            form_path=expr.form_path,
        )
    if isinstance(expr, NameExpr):
        try:
            type_ref = value_env[expr.name]
        except KeyError:
            _raise_error(
                f"unknown name `{expr.name}`",
                code="name_unknown",
                span=expr.span,
                form_path=expr.form_path,
            )
        return TypedExpr(expr=expr, type_ref=type_ref, span=expr.span, form_path=expr.form_path)
    if isinstance(expr, FieldAccessExpr):
        typed_base = _typecheck(expr.base, type_env=type_env, value_env=value_env, proof_scope=proof_scope)
        current_type = typed_base.type_ref
        for field_name in expr.fields:
            current_type = _resolve_field_access(
                current_type,
                base_name=expr.base.name,
                field_name=field_name,
                span=expr.span,
                form_path=expr.form_path,
                type_env=type_env,
                proof_scope=proof_scope,
            )
        return TypedExpr(expr=expr, type_ref=current_type, span=expr.span, form_path=expr.form_path)
    if isinstance(expr, RecordExpr):
        record_type = type_env.resolve_type(expr.type_name, span=expr.span, form_path=expr.form_path)
        if not isinstance(record_type, RecordTypeRef):
            _raise_error(
                f"`{expr.type_name}` is not a record type",
                code="type_mismatch",
                span=expr.span,
                form_path=expr.form_path,
            )
        expected_fields = {field.name: field for field in record_type.definition.fields}
        seen_fields: set[str] = set()
        for field_name, field_expr in expr.fields:
            if field_name in seen_fields:
                _raise_error(
                    f"duplicate field `{field_name}` in record expression",
                    code="record_field_duplicate",
                    span=field_expr.span,
                    form_path=field_expr.form_path,
                )
            seen_fields.add(field_name)
            expected_field = expected_fields.get(field_name)
            if expected_field is None:
                _raise_error(
                    f"unknown field `{field_name}` for record `{record_type.name}`",
                    code="record_field_unknown",
                    span=field_expr.span,
                    form_path=field_expr.form_path,
                )
            typed_field = _typecheck(
                field_expr,
                type_env=type_env,
                value_env=value_env,
                proof_scope=proof_scope,
            )
            expected_type = type_env.resolve_type(
                expected_field.type_name,
                span=field_expr.span,
                form_path=field_expr.form_path,
            )
            if typed_field.type_ref != expected_type:
                _raise_error(
                    f"record field `{field_name}` expected `{_type_label(expected_type)}`"
                    f" but got `{_type_label(typed_field.type_ref)}`",
                    code="type_mismatch",
                    span=field_expr.span,
                    form_path=field_expr.form_path,
                )
        missing_fields = [field.name for field in record_type.definition.fields if field.name not in seen_fields]
        if missing_fields:
            _raise_error(
                f"missing required field `{missing_fields[0]}` for record `{record_type.name}`",
                code="record_field_missing",
                span=expr.span,
                form_path=expr.form_path,
            )
        return TypedExpr(expr=expr, type_ref=record_type, span=expr.span, form_path=expr.form_path)
    if isinstance(expr, LetStarExpr):
        local_env = dict(value_env)
        seen_names: set[str] = set()
        for name, binding_expr in expr.bindings:
            if name in seen_names:
                _raise_error(
                    f"duplicate let* binding `{name}`",
                    code="binding_duplicate",
                    span=binding_expr.span,
                    form_path=binding_expr.form_path,
                )
            typed_binding = _typecheck(
                binding_expr,
                type_env=type_env,
                value_env=local_env,
                proof_scope=proof_scope,
            )
            seen_names.add(name)
            local_env[name] = typed_binding.type_ref
        typed_body = _typecheck(
            expr.body,
            type_env=type_env,
            value_env=local_env,
            proof_scope=proof_scope,
        )
        return TypedExpr(expr=expr, type_ref=typed_body.type_ref, span=expr.span, form_path=expr.form_path)
    if isinstance(expr, MatchExpr):
        typed_subject = _typecheck(expr.subject, type_env=type_env, value_env=value_env, proof_scope=proof_scope)
        if not isinstance(typed_subject.type_ref, UnionTypeRef):
            _raise_error(
                "match subject must have a union type",
                code="match_subject_not_union",
                span=expr.subject.span,
                form_path=expr.subject.form_path,
            )
        union_type = typed_subject.type_ref
        seen_variants: set[str] = set()
        expected_variants = {variant.name for variant in union_type.definition.variants}
        arm_result_type: TypeRef | None = None
        for arm in expr.arms:
            if arm.variant_name in seen_variants:
                _raise_error(
                    f"duplicate match arm `{arm.variant_name}`",
                    code="union_match_non_exhaustive",
                    span=arm.span,
                    form_path=arm.form_path,
                )
            seen_variants.add(arm.variant_name)
            variant_type = type_env.union_variant(
                union_type,
                arm.variant_name,
                span=arm.span,
                form_path=arm.form_path,
            )
            arm_env = dict(value_env)
            arm_env[arm.binding_name] = variant_type
            arm_facts = dict(proof_scope.facts)
            if isinstance(expr.subject, NameExpr):
                arm_facts[expr.subject.name] = ProofFact(
                    subject_name=expr.subject.name,
                    variant_name=arm.variant_name,
                    variant_type=variant_type,
                )
            typed_body = _typecheck(
                arm.body,
                type_env=type_env,
                value_env=arm_env,
                proof_scope=ProofScope(facts=arm_facts),
            )
            if arm_result_type is None:
                arm_result_type = typed_body.type_ref
            elif typed_body.type_ref != arm_result_type:
                _raise_error(
                    f"match arm for `{arm.variant_name}` returned `{_type_label(typed_body.type_ref)}`"
                    f" but expected `{_type_label(arm_result_type)}`",
                    code="type_mismatch",
                    span=arm.body.span,
                    form_path=arm.body.form_path,
                )
        if seen_variants != expected_variants:
            missing = sorted(expected_variants - seen_variants)
            _raise_error(
                f"match must cover every variant of `{union_type.name}`; missing `{missing[0]}`",
                code="union_match_non_exhaustive",
                span=expr.span,
                form_path=expr.form_path,
            )
        if arm_result_type is None:
            _raise_error(
                "match requires at least one arm",
                code="union_match_non_exhaustive",
                span=expr.span,
                form_path=expr.form_path,
            )
        return TypedExpr(expr=expr, type_ref=arm_result_type, span=expr.span, form_path=expr.form_path)
    raise TypeError(f"unsupported expression node: {type(expr)!r}")


def _resolve_field_access(
    base_type: TypeRef,
    *,
    base_name: str,
    field_name: str,
    span: SourceSpan,
    form_path: tuple[str, ...],
    type_env: FrontendTypeEnvironment,
    proof_scope: ProofScope,
) -> TypeRef:
    if isinstance(base_type, RecordTypeRef):
        return type_env.record_field(base_type, field_name, span=span, form_path=form_path)
    if isinstance(base_type, VariantCaseTypeRef):
        if _variant_has_field(base_type, field_name):
            return type_env.record_field(base_type, field_name, span=span, form_path=form_path)
        if type_env.field_exists_in_other_variant(base_type, field_name):
            _raise_error(
                f"field `{field_name}` is not available under proven variant `{base_type.variant_name}`",
                code="variant_ref_wrong_variant",
                span=span,
                form_path=form_path,
            )
        _raise_error(
            f"unknown field `{field_name}`",
            code="record_field_unknown",
            span=span,
            form_path=form_path,
        )
    if isinstance(base_type, UnionTypeRef):
        proof_fact = proof_scope.facts.get(base_name)
        if proof_fact is None:
            if _union_has_any_field(base_type, field_name):
                _raise_error(
                    f"field `{field_name}` requires variant proof for `{base_type.name}`",
                    code="variant_ref_unproved",
                    span=span,
                    form_path=form_path,
                )
            _raise_error(
                f"unknown field `{field_name}`",
                code="record_field_unknown",
                span=span,
                form_path=form_path,
            )
        if _variant_has_field(proof_fact.variant_type, field_name):
            return type_env.record_field(
                proof_fact.variant_type,
                field_name,
                span=span,
                form_path=form_path,
            )
        if type_env.field_exists_in_other_variant(proof_fact.variant_type, field_name):
            _raise_error(
                f"field `{field_name}` is not available under proven variant `{proof_fact.variant_name}`",
                code="variant_ref_wrong_variant",
                span=span,
                form_path=form_path,
            )
        _raise_error(
            f"unknown field `{field_name}`",
            code="record_field_unknown",
            span=span,
            form_path=form_path,
        )
    _raise_error(
        f"type `{_type_label(base_type)}` does not support field access",
        code="record_field_unknown",
        span=span,
        form_path=form_path,
    )


def _literal_type_name(literal_kind: str) -> str:
    if literal_kind == "string":
        return "String"
    if literal_kind == "int":
        return "Int"
    if literal_kind == "bool":
        return "Bool"
    raise ValueError(f"unsupported literal kind: {literal_kind}")


def _type_label(type_ref: TypeRef) -> str:
    if isinstance(type_ref, VariantCaseTypeRef):
        return f"{type_ref.union_name}.{type_ref.variant_name}"
    return type_ref.name


def _variant_has_field(variant_type: VariantCaseTypeRef, field_name: str) -> bool:
    return any(field.name == field_name for field in variant_type.definition.fields)


def _union_has_any_field(union_type: UnionTypeRef, field_name: str) -> bool:
    return any(field.name == field_name for variant in union_type.definition.variants for field in variant.fields)


def _raise_error(message: str, *, code: str, span: SourceSpan, form_path: tuple[str, ...]) -> None:
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code=code,
                message=message,
                span=span,
                form_path=form_path,
            ),
        )
    )
