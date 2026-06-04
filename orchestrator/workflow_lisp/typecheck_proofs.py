"""Variant-proof typing ownership for Workflow Lisp."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .effects import EMPTY_EFFECT_SUMMARY, merge_effect_summaries
from .expressions import FieldAccessExpr, MatchExpr, NameExpr
from .loops import LoopControlTypeRef
from .type_env import (
    FrontendTypeEnvironment,
    RecordTypeRef,
    TypeRef,
    UnionTypeRef,
    VariantCaseTypeRef,
)


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


def _variant_has_field(variant_type: VariantCaseTypeRef, field_name: str) -> bool:
    return any(field.name == field_name for field in variant_type.definition.fields)


def _union_has_any_field(union_type: UnionTypeRef, field_name: str) -> bool:
    return any(field.name == field_name for variant in union_type.definition.variants for field in variant.fields)


def resolve_field_access(
    base_type: TypeRef,
    *,
    base_name: str,
    field_name: str,
    span,
    form_path: tuple[str, ...],
    type_env: FrontendTypeEnvironment,
    proof_scope: ProofScope,
) -> TypeRef:
    from . import typecheck as compat

    if isinstance(base_type, RecordTypeRef):
        return type_env.record_field(base_type, field_name, span=span, form_path=form_path)
    if isinstance(base_type, VariantCaseTypeRef):
        if _variant_has_field(base_type, field_name):
            return type_env.record_field(base_type, field_name, span=span, form_path=form_path)
        if type_env.field_exists_in_other_variant(base_type, field_name):
            compat._raise_error(
                f"field `{field_name}` is not available under proven variant `{base_type.variant_name}`",
                code="variant_ref_wrong_variant",
                span=span,
                form_path=form_path,
            )
        compat._raise_error(
            f"unknown field `{field_name}`",
            code="record_field_unknown",
            span=span,
            form_path=form_path,
        )
    if isinstance(base_type, UnionTypeRef):
        proof_fact = proof_scope.facts.get(base_name)
        if proof_fact is None:
            if _union_has_any_field(base_type, field_name):
                compat._raise_error(
                    f"field `{field_name}` requires variant proof for `{base_type.name}`",
                    code="variant_ref_unproved",
                    span=span,
                    form_path=form_path,
                )
            compat._raise_error(
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
            compat._raise_error(
                f"field `{field_name}` is not available under proven variant `{proof_fact.variant_name}`",
                code="variant_ref_wrong_variant",
                span=span,
                form_path=form_path,
            )
        compat._raise_error(
            f"unknown field `{field_name}`",
            code="record_field_unknown",
            span=span,
            form_path=form_path,
        )
    compat._raise_error(
        f"type `{compat._type_label(base_type)}` does not support field access",
        code="record_field_unknown",
        span=span,
        form_path=form_path,
    )


def typecheck_field_access_expr(
    expr: FieldAccessExpr,
    *,
    context,
    recurse,
    typed_factory,
):
    typed_base = recurse(expr.base)
    current_type = typed_base.type_ref
    base_name = expr.base.name if isinstance(expr.base, NameExpr) else ""
    for field_name in expr.fields:
        current_type = resolve_field_access(
            current_type,
            base_name=base_name,
            field_name=field_name,
            span=expr.span,
            form_path=expr.form_path,
            type_env=context.type_env,
            proof_scope=context.proof_scope,
        )
    return typed_factory(expr=expr, type_ref=current_type, effect=typed_base.effect_summary)


def typecheck_match_expr(
    expr: MatchExpr,
    *,
    context,
    recurse,
    typed_factory,
):
    from dataclasses import replace

    from . import typecheck as compat

    typed_subject = recurse(expr.subject)
    if not isinstance(typed_subject.type_ref, UnionTypeRef):
        compat._raise_error(
            "match subject must have a union type",
            code="match_subject_not_union",
            span=expr.subject.span,
            form_path=expr.subject.form_path,
        )
    union_type = typed_subject.type_ref
    seen_variants: set[str] = set()
    expected_variants = {variant.name for variant in union_type.definition.variants}
    arm_result_type: TypeRef | LoopControlTypeRef | None = None
    arm_summaries = [typed_subject.effect_summary]
    rewritten_arms = []
    for arm in expr.arms:
        if arm.variant_name in seen_variants:
            compat._raise_error(
                f"duplicate match arm `{arm.variant_name}`",
                code="union_match_non_exhaustive",
                span=arm.span,
                form_path=arm.form_path,
            )
        seen_variants.add(arm.variant_name)
        variant_type = context.type_env.union_variant(
            union_type,
            arm.variant_name,
            span=arm.span,
            form_path=arm.form_path,
        )
        arm_env = dict(context.value_env)
        arm_env[arm.binding_name] = variant_type
        arm_facts = dict(context.proof_scope.facts)
        if isinstance(expr.subject, NameExpr):
            arm_facts[expr.subject.name] = ProofFact(
                subject_name=expr.subject.name,
                variant_name=arm.variant_name,
                variant_type=variant_type,
            )
        typed_body = recurse(
            arm.body,
            value_env=arm_env,
            proof_scope=ProofScope(facts=arm_facts),
        )
        arm_summaries.append(typed_body.effect_summary)
        rewritten_arms.append(replace(arm, body=typed_body.expr))
        if arm_result_type is None:
            arm_result_type = typed_body.type_ref
            continue
        unified_loop_control = compat._unify_loop_control_types(arm_result_type, typed_body.type_ref)
        if unified_loop_control is not None:
            arm_result_type = unified_loop_control
            continue
        if isinstance(arm_result_type, LoopControlTypeRef) and isinstance(typed_body.type_ref, LoopControlTypeRef):
            compat._raise_error(
                f"`done` expected `{compat._type_label(arm_result_type.result_type_ref)}` but got `{compat._type_label(typed_body.type_ref.result_type_ref)}`",
                code="loop_recur_done_type_mismatch",
                span=arm.body.span,
                form_path=arm.body.form_path,
            )
        if typed_body.type_ref != arm_result_type:
            compat._raise_error(
                f"match arm for `{arm.variant_name}` returned `{compat._type_label(typed_body.type_ref)}`"
                f" but expected `{compat._type_label(arm_result_type)}`",
                code="type_mismatch",
                span=arm.body.span,
                form_path=arm.body.form_path,
            )
    if seen_variants != expected_variants:
        missing = sorted(expected_variants - seen_variants)
        compat._raise_error(
            f"match must cover every variant of `{union_type.name}`; missing `{missing[0]}`",
            code="union_match_non_exhaustive",
            span=expr.span,
            form_path=expr.form_path,
        )
    if arm_result_type is None:
        compat._raise_error(
            "match requires at least one arm",
            code="union_match_non_exhaustive",
            span=expr.span,
            form_path=expr.form_path,
        )
    return typed_factory(
        expr=replace(expr, arms=tuple(rewritten_arms)),
        type_ref=arm_result_type,
        effect=merge_effect_summaries(*arm_summaries),
    )
