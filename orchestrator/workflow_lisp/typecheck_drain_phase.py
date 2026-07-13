"""Drain/phase typecheck ownership for Workflow Lisp."""

from __future__ import annotations

from .effects import (
    EMPTY_EFFECT_SUMMARY,
    EffectSummary,
    UsesProviderEffect,
    effect_summary_from_direct,
    merge_effect_summaries,
)
from .expressions import (
    NameExpr,
    PhaseTargetExpr,
    ProduceOneOfExpr,
    RunProviderPhaseExpr,
)
from .phase import resolve_phase_target_type
from .type_env import PathTypeRef, PrimitiveTypeRef, RecordTypeRef, UnionTypeRef
from .typecheck_context import (
    raise_error,
    _require_normative_phase_ctx_type,
    _require_phase_scope_name_match,
)


def typecheck_phase_target_expr(
    expr: PhaseTargetExpr,
    *,
    context,
    recurse,
    typed_factory,
):
    if context.active_phase_scope is None:
        raise_error(
            "`phase-target` is valid only inside an active `with-phase` scope",
            code="phase_target_outside_with_phase",
            span=expr.span,
            form_path=expr.form_path,
        )
    target_type = resolve_phase_target_type(
        context.active_phase_scope,
        expr.target_name,
        type_env=context.type_env,
        span=expr.span,
        form_path=expr.form_path,
    )
    return typed_factory(expr=expr, type_ref=target_type, effect=EMPTY_EFFECT_SUMMARY)


def typecheck_run_provider_phase_expr(
    expr: RunProviderPhaseExpr,
    *,
    context,
    recurse,
    typed_factory,
):
    return_type = context.type_env.resolve_type(
        expr.returns_type_name,
        span=expr.span,
        form_path=expr.form_path,
    )
    if not isinstance(return_type, (RecordTypeRef, UnionTypeRef)):
        raise_error(
            "`run-provider-phase` requires a record or union `:returns` type",
            code="run_provider_phase_return_invalid",
            span=expr.span,
            form_path=expr.form_path,
        )
    typed_ctx = recurse(expr.ctx_expr)
    _require_normative_phase_ctx_type(
        typed_ctx.type_ref,
        span=expr.ctx_expr.span,
        form_path=expr.ctx_expr.form_path,
    )
    _require_phase_scope_name_match(
        context.active_phase_scope,
        authored_name=expr.phase_name,
        form_name="run-provider-phase",
        span=expr.span,
        form_path=expr.form_path,
    )
    typed_inputs = recurse(expr.inputs_expr)
    typed_provider = _expected_extern_operand(
        expr.provider,
        expected_primitive="Provider",
        context=context,
        recurse=recurse,
        typed_factory=typed_factory,
    )
    typed_prompt = _expected_extern_operand(
        expr.prompt,
        expected_primitive="Prompt",
        context=context,
        recurse=recurse,
        typed_factory=typed_factory,
    )
    if typed_provider.type_ref != PrimitiveTypeRef(name="Provider"):
        raise_error(
            "`run-provider-phase` provider operand must resolve to `Provider`",
            code="provider_result_provider_invalid",
            span=expr.provider.span,
            form_path=expr.provider.form_path,
        )
    if typed_prompt.type_ref != PrimitiveTypeRef(name="Prompt"):
        raise_error(
            "`run-provider-phase` prompt operand must resolve to `Prompt`",
            code="provider_result_prompt_invalid",
            span=expr.prompt.span,
            form_path=expr.prompt.form_path,
        )
    return typed_factory(
        expr=expr,
        type_ref=return_type,
        effect=merge_effect_summaries(
            typed_ctx.effect_summary,
            typed_inputs.effect_summary,
            typed_provider.effect_summary,
            typed_prompt.effect_summary,
            effect_summary_from_direct(
                direct_effects=(UsesProviderEffect(subject=(expr.phase_name,)),),
            ),
        ),
    )


def typecheck_produce_one_of_expr(
    expr: ProduceOneOfExpr,
    *,
    context,
    recurse,
    typed_factory,
):
    type_env = context.type_env
    return_type = type_env.resolve_type(
        expr.returns_type_name,
        span=expr.span,
        form_path=expr.form_path,
    )
    if not isinstance(return_type, UnionTypeRef):
        raise_error(
            "`produce-one-of` requires a union return type",
            code="produce_one_of_candidate_invalid",
            span=expr.span,
            form_path=expr.form_path,
        )
    typed_ctx = recurse(expr.ctx_expr)
    _require_normative_phase_ctx_type(
        typed_ctx.type_ref,
        span=expr.ctx_expr.span,
        form_path=expr.ctx_expr.form_path,
    )
    candidate_variants = {candidate.variant_name for candidate in expr.candidates}
    declared_variants = {variant.name for variant in return_type.definition.variants}
    if candidate_variants != declared_variants:
        raise_error(
            "`produce-one-of` candidates must cover the declared union variants exactly",
            code="produce_one_of_candidate_invalid",
            span=expr.span,
            form_path=expr.form_path,
        )
    input_summaries: list[EffectSummary] = [typed_ctx.effect_summary]
    if expr.producer.provider_expr is None or expr.producer.prompt_expr is None:
        raise_error(
            "`produce-one-of` currently requires a provider producer",
            code="produce_one_of_candidate_invalid",
            span=expr.span,
            form_path=expr.form_path,
        )
    typed_provider = _expected_extern_operand(
        expr.producer.provider_expr,
        expected_primitive="Provider",
        context=context,
        recurse=recurse,
        typed_factory=typed_factory,
    )
    typed_prompt = _expected_extern_operand(
        expr.producer.prompt_expr,
        expected_primitive="Prompt",
        context=context,
        recurse=recurse,
        typed_factory=typed_factory,
    )
    input_summaries.extend((typed_provider.effect_summary, typed_prompt.effect_summary))
    for producer_input in expr.producer.inputs:
        typed_input = recurse(producer_input)
        input_summaries.append(typed_input.effect_summary)
    for candidate in expr.candidates:
        variant = type_env.union_variant(
            return_type,
            candidate.variant_name,
            span=expr.span,
            form_path=expr.form_path,
        )
        variant_field_names = {field.name for field in variant.definition.fields}
        for field_spec in candidate.fields:
            if field_spec.field_name not in variant_field_names:
                raise_error(
                    f"`produce-one-of` field `{field_spec.field_name}` is not part of variant `{candidate.variant_name}`",
                    code="produce_one_of_candidate_invalid",
                    span=expr.span,
                    form_path=expr.form_path,
                )
            if field_spec.target_expr is not None:
                typed_target = recurse(field_spec.target_expr)
                if not isinstance(typed_target.type_ref, PathTypeRef):
                    raise_error(
                        f"`produce-one-of` target `{field_spec.field_name}` must resolve to a relpath contract",
                        code="produce_one_of_candidate_invalid",
                        span=expr.span,
                        form_path=expr.form_path,
                    )
                if field_spec.schema_type_name is not None:
                    schema_type = type_env.resolve_type(
                        field_spec.schema_type_name,
                        span=expr.span,
                        form_path=expr.form_path,
                    )
                    if not isinstance(schema_type, PathTypeRef):
                        raise_error(
                            f"`produce-one-of` schema `{field_spec.schema_type_name}` must be a relpath contract",
                            code="produce_one_of_candidate_invalid",
                            span=expr.span,
                            form_path=expr.form_path,
                        )
    return typed_factory(
        expr=expr,
        type_ref=return_type,
        effect=merge_effect_summaries(*input_summaries),
    )


def _expected_extern_operand(expr, *, expected_primitive, context, recurse, typed_factory):
    if isinstance(expr, NameExpr) and expr.name not in context.value_env:
        return typed_factory(
            expr=expr,
            type_ref=PrimitiveTypeRef(name=expected_primitive),
            effect=EMPTY_EFFECT_SUMMARY,
        )
    return recurse(expr)
