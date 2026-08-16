"""Variant-proof typing ownership for Workflow Lisp."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .conditionals import classify_condition_expr, normalize_condition_expr
from .effects import EMPTY_EFFECT_SUMMARY, effect_summary_contains_runs_ref, merge_effect_summaries
from .expressions import (
    FieldAccessExpr,
    IfExpr,
    LetStarExpr,
    LiteralExpr,
    MatchExpr,
    NameExpr,
    PureOpExpr,
    UnionVariantTagExpr,
)
from .loops import LoopControlTypeRef
from .parametric_constraints import SharedUnionFieldCapability
from .syntax import target_dsl_supports_strict_boolean_control_flow
from .type_env import (
    DiscriminantTypeRef,
    FrontendTypeEnvironment,
    PrimitiveTypeRef,
    RecordTypeRef,
    TypeRef,
    TypeParamRef,
    UnionTypeRef,
    VariantCaseTypeRef,
    type_refs_compatible,
)
from .typecheck_context import (
    _type_label,
    _unify_loop_control_types,
    raise_error,
    raise_run_ref_placement_invalid,
)


@dataclass(frozen=True)
class BindingIdentity:
    """Stable identity for one lexical binding, independent of spelling.

    ``path`` is the enclosing authored form path, ``kind`` distinguishes the
    binder family (root, param, arm, let), ``name`` is the binder spelling, and
    ``ordinal`` disambiguates same-spelling binders in nested scopes. Shadowed
    binders receive distinct ordinals so facts keyed by identity never collide
    merely because two binders share a name.
    """

    path: tuple[str, ...]
    kind: str
    name: str
    ordinal: int = 0


@dataclass(frozen=True)
class PossibleVariants:
    """Closed set of variants still possible for one union binding.

    ``variants`` is the frozenset of variant names still reachable on this
    path. An empty set is unreachable; only a singleton authorizes a
    variant-only field. ``union_name`` preserves the owning union's identity so
    facts remain self-contained through WCC carriage and restore descriptors.
    """

    union_name: str
    variants: frozenset[str]


@dataclass(frozen=True)
class ProofScope:
    """Frontend-local proof facts for the current checking scope.

    Facts are keyed by stable lexical :class:`BindingIdentity`, never by
    identifier spelling. A binding absent from ``facts`` is unconstrained (all
    declared variants possible).
    """

    facts: Mapping[BindingIdentity, PossibleVariants]


class _Unreachable:
    """Sentinel marking a statically unreachable branch path."""


UNREACHABLE = _Unreachable()


def join_possible_variants(
    left: PossibleVariants | None,
    right: PossibleVariants | None,
) -> PossibleVariants | None:
    """Union two possible sets for the same binding identity.

    ``None`` means "no fact established" (all variants possible). The union of
    an unconstrained path and a narrowed path is unconstrained.
    """
    if left is None or right is None:
        return None
    if left.union_name != right.union_name:
        return None
    return PossibleVariants(
        union_name=left.union_name,
        variants=left.variants | right.variants,
    )


def join_fact_maps(
    left: Mapping[BindingIdentity, PossibleVariants],
    right: Mapping[BindingIdentity, PossibleVariants],
) -> dict[BindingIdentity, PossibleVariants]:
    """Join two fact maps per binding identity."""
    merged: dict[BindingIdentity, PossibleVariants] = {}
    for identity in set(left) | set(right):
        joined = join_possible_variants(left.get(identity), right.get(identity))
        if joined is not None:
            merged[identity] = joined
    return merged


def intersect_variant(
    current: PossibleVariants | None,
    *,
    union_name: str,
    variant: str,
) -> PossibleVariants:
    """Refine one binding's possible set to a single variant."""
    if current is None:
        return PossibleVariants(union_name=union_name, variants=frozenset({variant}))
    return PossibleVariants(
        union_name=current.union_name,
        variants=current.variants & frozenset({variant}),
    )


def exclude_variant(
    current: PossibleVariants | None,
    *,
    union_name: str,
    variant: str,
    full_variants: frozenset[str],
) -> PossibleVariants:
    """Refine one binding's possible set by excluding one variant."""
    if current is None:
        return PossibleVariants(union_name=union_name, variants=full_variants - {variant})
    return PossibleVariants(
        union_name=current.union_name,
        variants=current.variants - {variant},
    )


def _variant_has_field(variant_type: VariantCaseTypeRef, field_name: str) -> bool:
    return any(field.name == field_name for field in variant_type.definition.fields)


def _union_has_any_field(union_type: UnionTypeRef, field_name: str) -> bool:
    return any(field.name == field_name for variant in union_type.definition.variants for field in variant.fields)


def _singleton_variant(possible: PossibleVariants | None) -> str | None:
    if possible is None or len(possible.variants) != 1:
        return None
    return next(iter(possible.variants))


def resolve_field_access(
    base_type: TypeRef,
    *,
    base_name: str,
    binding_identity: BindingIdentity | None,
    field_name: str,
    span,
    form_path: tuple[str, ...],
    type_env: FrontendTypeEnvironment,
    proof_scope: ProofScope,
    shared_union_field_capabilities: tuple[SharedUnionFieldCapability, ...] = (),
) -> TypeRef:
    capability_type = _shared_union_field_type(
        base_type=base_type,
        field_name=field_name,
        shared_union_field_capabilities=shared_union_field_capabilities,
    )
    if capability_type is not None:
        return capability_type
    if isinstance(base_type, UnionTypeRef) and field_name == "variant":
        return DiscriminantTypeRef(
            union_name=base_type.name,
            variant_names=tuple(variant.name for variant in base_type.definition.variants),
        )
    if isinstance(base_type, RecordTypeRef):
        return type_env.record_field(base_type, field_name, span=span, form_path=form_path)
    if isinstance(base_type, VariantCaseTypeRef):
        if _variant_has_field(base_type, field_name):
            return type_env.record_field(base_type, field_name, span=span, form_path=form_path)
        if type_env.field_exists_in_other_variant(base_type, field_name):
            raise_error(
                f"field `{field_name}` is not available under proven variant `{base_type.variant_name}`",
                code="variant_ref_wrong_variant",
                span=span,
                form_path=form_path,
            )
        raise_error(
            f"unknown field `{field_name}`",
            code="record_field_unknown",
            span=span,
            form_path=form_path,
        )
    if isinstance(base_type, UnionTypeRef):
        possible = proof_scope.facts.get(binding_identity) if binding_identity is not None else None
        variant_name = _singleton_variant(possible)
        if variant_name is None:
            if _union_has_any_field(base_type, field_name):
                raise_error(
                    f"field `{field_name}` requires variant proof for `{base_type.name}`",
                    code="variant_ref_unproved",
                    span=span,
                    form_path=form_path,
                )
            raise_error(
                f"unknown field `{field_name}`",
                code="record_field_unknown",
                span=span,
                form_path=form_path,
            )
        variant_type = type_env.union_variant(
            base_type,
            variant_name,
            span=span,
            form_path=form_path,
        )
        if _variant_has_field(variant_type, field_name):
            return type_env.record_field(
                variant_type,
                field_name,
                span=span,
                form_path=form_path,
            )
        if type_env.field_exists_in_other_variant(variant_type, field_name):
            raise_error(
                f"field `{field_name}` is not available under proven variant `{variant_name}`",
                code="variant_ref_wrong_variant",
                span=span,
                form_path=form_path,
            )
        raise_error(
            f"unknown field `{field_name}`",
            code="record_field_unknown",
            span=span,
            form_path=form_path,
        )
    raise_error(
        f"type `{_type_label(base_type)}` does not support field access",
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
    binding_identity = context.binding_env.get(base_name) if base_name else None
    for field_name in expr.fields:
        current_type = resolve_field_access(
            current_type,
            base_name=base_name,
            binding_identity=binding_identity,
            field_name=field_name,
            span=expr.span,
            form_path=expr.form_path,
            type_env=context.type_env,
            proof_scope=context.proof_scope,
            shared_union_field_capabilities=context.shared_union_field_capabilities,
        )
    return typed_factory(expr=expr, type_ref=current_type, effect=typed_base.effect_summary)


def _shared_union_field_type(
    *,
    base_type: TypeRef,
    field_name: str,
    shared_union_field_capabilities: tuple[SharedUnionFieldCapability, ...],
) -> TypeRef | None:
    for capability in shared_union_field_capabilities:
        if capability.field_name != field_name:
            continue
        if isinstance(base_type, UnionTypeRef) and capability.union_type_name == base_type.name:
            return capability.field_type_ref
        if isinstance(base_type, TypeParamRef) and capability.type_param_name == base_type.name:
            return capability.field_type_ref
    return None


def _allocate_binding_identity(
    binding_env: Mapping[str, BindingIdentity],
    *,
    form_path: tuple[str, ...],
    kind: str,
    name: str,
) -> BindingIdentity:
    """Allocate a stable identity for one new binder, shadow-aware."""
    parent = binding_env.get(name)
    ordinal = (parent.ordinal + 1) if parent is not None else 0
    return BindingIdentity(path=form_path, kind=kind, name=name, ordinal=ordinal)


def typecheck_match_expr(
    expr: MatchExpr,
    *,
    context,
    recurse,
    typed_factory,
    expected_type: TypeRef | None = None,
):
    from dataclasses import replace

    typed_subject = recurse(expr.subject)
    if effect_summary_contains_runs_ref(typed_subject.effect_summary):
        raise_run_ref_placement_invalid(
            typed_subject.expr,
            reason="is not permitted in a `match` discriminant",
            effect_summary=typed_subject.effect_summary,
        )
    if isinstance(typed_subject.type_ref, TypeParamRef):
        raise_error(
            f"match on type parameter `{typed_subject.type_ref.name}` requires declared `has-union-variant` capabilities",
            code="parametric_capability_undeclared",
            span=expr.subject.span,
            form_path=expr.subject.form_path,
        )
    if not isinstance(typed_subject.type_ref, UnionTypeRef):
        raise_error(
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
    subject_identity = (
        context.binding_env.get(expr.subject.name)
        if isinstance(expr.subject, NameExpr)
        else None
    )
    for arm in expr.arms:
        if arm.variant_name in seen_variants:
            raise_error(
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
        arm_binding_env = dict(context.binding_env)
        arm_binding_env[arm.binding_name] = _allocate_binding_identity(
            arm_binding_env,
            form_path=arm.form_path,
            kind="arm",
            name=arm.binding_name,
        )
        arm_facts = dict(context.proof_scope.facts)
        if subject_identity is not None:
            arm_facts[subject_identity] = PossibleVariants(
                union_name=union_type.name,
                variants=frozenset({arm.variant_name}),
            )
        typed_body = recurse(
            arm.body,
            value_env=arm_env,
            binding_env=arm_binding_env,
            proof_scope=ProofScope(facts=arm_facts),
            expected_type=expected_type,
        )
        arm_summaries.append(typed_body.effect_summary)
        rewritten_arms.append(replace(arm, body=typed_body.expr))
        if arm_result_type is None:
            arm_result_type = typed_body.type_ref
            continue
        unified_loop_control = _unify_loop_control_types(arm_result_type, typed_body.type_ref)
        if unified_loop_control is not None:
            arm_result_type = unified_loop_control
            continue
        if isinstance(arm_result_type, LoopControlTypeRef) and isinstance(typed_body.type_ref, LoopControlTypeRef):
            raise_error(
                f"`done` expected `{_type_label(arm_result_type.result_type_ref)}` but got `{_type_label(typed_body.type_ref.result_type_ref)}`",
                code="loop_recur_done_type_mismatch",
                span=arm.body.span,
                form_path=arm.body.form_path,
            )
        if not type_refs_compatible(arm_result_type, typed_body.type_ref):
            raise_error(
                f"match arm for `{arm.variant_name}` returned `{_type_label(typed_body.type_ref)}`"
                f" but expected `{_type_label(arm_result_type)}`",
                code="type_mismatch",
                span=arm.body.span,
                form_path=arm.body.form_path,
            )
    if seen_variants != expected_variants:
        missing = sorted(expected_variants - seen_variants)
        raise_error(
            f"match must cover every variant of `{union_type.name}`; missing `{missing[0]}`",
            code="union_match_non_exhaustive",
            span=expr.span,
            form_path=expr.form_path,
        )
    if arm_result_type is None:
        raise_error(
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


def typecheck_if_expr(
    expr: IfExpr,
    *,
    context,
    recurse,
    typed_factory,
    expected_type: TypeRef | None = None,
):
    from dataclasses import replace

    typed_condition = recurse(expr.condition_expr)
    supports_strict = target_dsl_supports_strict_boolean_control_flow(
        context.type_env.target_dsl_version or ""
    )
    true_proof_facts: dict | None = None
    false_proof_facts: dict | None = None
    if supports_strict:
        if typed_condition.type_ref != PrimitiveTypeRef(name="Bool"):
            raise_error(
                "`if` condition must resolve to exact `Bool`",
                code="if_condition_not_bool",
                span=expr.condition_expr.span,
                form_path=expr.condition_expr.form_path,
            )
        true_env, false_env = analyze_condition(
            typed_condition.expr,
            binding_env=context.binding_env,
            facts=context.proof_scope.facts,
        )
        true_proof_facts = dict(true_env) if true_env is not UNREACHABLE else {}
        false_proof_facts = dict(false_env) if false_env is not UNREACHABLE else {}
        normalized_condition = normalize_condition_expr(
            typed_condition.expr,
            type_ref=typed_condition.type_ref,
            effect_summary=typed_condition.effect_summary,
        )
    else:
        if effect_summary_contains_runs_ref(typed_condition.effect_summary):
            raise_run_ref_placement_invalid(
                typed_condition.expr,
                reason="is not permitted in an `if` condition",
                effect_summary=typed_condition.effect_summary,
            )
        if typed_condition.type_ref != PrimitiveTypeRef(name="Bool"):
            raise_error(
                "`if` condition must resolve to exact `Bool`",
                code="if_condition_not_bool",
                span=expr.condition_expr.span,
                form_path=expr.condition_expr.form_path,
            )
        if typed_condition.effect_summary != EMPTY_EFFECT_SUMMARY:
            raise_error(
                "`if` condition must be pure",
                code="if_condition_has_effect",
                span=expr.condition_expr.span,
                form_path=expr.condition_expr.form_path,
            )
        classify_condition_expr(
            typed_condition.expr,
            type_ref=typed_condition.type_ref,
        )
    then_proof_scope = (
        ProofScope(facts=true_proof_facts)
        if true_proof_facts is not None
        else context.proof_scope
    )
    else_proof_scope = (
        ProofScope(facts=false_proof_facts)
        if false_proof_facts is not None
        else context.proof_scope
    )
    typed_then = recurse(
        expr.then_expr,
        proof_scope=then_proof_scope,
        expected_type=expected_type,
    )
    typed_else = recurse(
        expr.else_expr,
        proof_scope=else_proof_scope,
        expected_type=expected_type,
    )
    result_type = _unify_loop_control_types(typed_then.type_ref, typed_else.type_ref)
    if result_type is None:
        if isinstance(typed_then.type_ref, LoopControlTypeRef) and isinstance(
            typed_else.type_ref,
            LoopControlTypeRef,
        ):
            raise_error(
                f"`done` expected `{_type_label(typed_then.type_ref.result_type_ref)}` but got `{_type_label(typed_else.type_ref.result_type_ref)}`",
                code="loop_recur_done_type_mismatch",
                span=expr.else_expr.span,
                form_path=expr.else_expr.form_path,
            )
        if typed_then.type_ref != typed_else.type_ref:
            raise_error(
                f"`if` branches must return the same type; got `{_type_label(typed_then.type_ref)}` and `{_type_label(typed_else.type_ref)}`",
                code="type_mismatch",
                span=expr.span,
                form_path=expr.form_path,
            )
        result_type = typed_then.type_ref
    if supports_strict:
        normalized_if = replace(
            expr,
            condition_expr=normalized_condition.terminal,
            then_expr=typed_then.expr,
            else_expr=typed_else.expr,
            true_proof_context=true_proof_facts,
            false_proof_context=false_proof_facts,
        )
        if normalized_condition.bindings:
            result_expr = LetStarExpr(
                bindings=normalized_condition.bindings,
                body=normalized_if,
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
        else:
            result_expr = normalized_if
        return typed_factory(
            expr=result_expr,
            type_ref=result_type,
            effect=merge_effect_summaries(
                normalized_condition.effect_summary,
                typed_then.effect_summary,
                typed_else.effect_summary,
            ),
        )
    return typed_factory(
        expr=replace(
            expr,
            condition_expr=typed_condition.expr,
            then_expr=typed_then.expr,
            else_expr=typed_else.expr,
        ),
        type_ref=result_type,
        effect=merge_effect_summaries(
            typed_condition.effect_summary,
            typed_then.effect_summary,
            typed_else.effect_summary,
        ),
    )


def analyze_condition(
    expr,
    *,
    binding_env: Mapping[str, BindingIdentity],
    facts: Mapping[BindingIdentity, PossibleVariants],
):
    """Return ``(when_true, when_false)`` proof environments for a condition.

    Each result is either ``UNREACHABLE`` or a fresh facts dict. Literals,
    ``=``/``!=`` discriminant comparisons, and ``and``/``or``/``not``
    composition refine the incoming facts. Any other Boolean expression routes
    without narrowing (``(facts, facts)``).
    """
    if isinstance(expr, LiteralExpr) and expr.literal_kind == "bool":
        if expr.value is True:
            return (dict(facts), UNREACHABLE)
        return (UNREACHABLE, dict(facts))
    if isinstance(expr, PureOpExpr):
        if expr.operator == "not":
            true_f, false_f = analyze_condition(
                expr.args[0], binding_env=binding_env, facts=facts
            )
            return (false_f, true_f)
        if expr.operator == "and":
            return _analyze_conjunction(expr.args, binding_env=binding_env, facts=facts)
        if expr.operator == "or":
            return _analyze_disjunction(expr.args, binding_env=binding_env, facts=facts)
        if expr.operator in {"=", "!="}:
            return _analyze_equality(expr, binding_env=binding_env, facts=facts)
    return (dict(facts), dict(facts))


def _analyze_conjunction(args, *, binding_env, facts):
    """``and``: analyze each later operand under the prior true environment."""
    true_env = dict(facts)
    false_envs: list = []
    for arg in args:
        if true_env is UNREACHABLE:
            break
        true_f, false_f = analyze_condition(arg, binding_env=binding_env, facts=true_env)
        false_envs.append(false_f)
        true_env = true_f
    return (true_env, _join_envs(false_envs))


def _analyze_disjunction(args, *, binding_env, facts):
    """``or``: analyze each later operand under the prior false environment."""
    false_env = dict(facts)
    true_envs: list = []
    for arg in args:
        if false_env is UNREACHABLE:
            break
        true_f, false_f = analyze_condition(arg, binding_env=binding_env, facts=false_env)
        true_envs.append(true_f)
        false_env = false_f
    return (_join_envs(true_envs), false_env)


def _join_envs(envs):
    """Conservatively join reachable fact maps; unreachable paths drop out."""
    merged = None
    reachable = False
    for env in envs:
        if env is UNREACHABLE:
            continue
        reachable = True
        merged = env if merged is None else join_fact_maps(merged, env)
    return merged if reachable else UNREACHABLE


def _analyze_equality(expr, *, binding_env, facts):
    left, right = expr.args
    if isinstance(left, UnionVariantTagExpr) and _is_variant_access(right):
        tag, discriminant = left, right
    elif isinstance(right, UnionVariantTagExpr) and _is_variant_access(left):
        tag, discriminant = right, left
    else:
        # Discriminant-to-discriminant equality proves no variant.
        return (dict(facts), dict(facts))

    identity = binding_env.get(discriminant.base.name)
    if identity is None:
        return (dict(facts), dict(facts))

    union_name = tag.union_name
    variant = tag.variant_name
    full_variants = frozenset(tag.variant_names)
    current = facts.get(identity)
    if expr.operator == "=":
        true_fact = intersect_variant(current, union_name=union_name, variant=variant)
        false_fact = exclude_variant(
            current, union_name=union_name, variant=variant, full_variants=full_variants
        )
    else:
        true_fact = exclude_variant(
            current, union_name=union_name, variant=variant, full_variants=full_variants
        )
        false_fact = intersect_variant(current, union_name=union_name, variant=variant)
    return (
        _reachable({**facts, identity: true_fact}),
        _reachable({**facts, identity: false_fact}),
    )


def _is_variant_access(expr) -> bool:
    return isinstance(expr, FieldAccessExpr) and expr.fields == ("variant",)


def _reachable(facts: dict):
    """Mark a fact map unreachable when any binding's possible set is empty."""
    for possible in facts.values():
        if len(possible.variants) == 0:
            return UNREACHABLE
    return facts
