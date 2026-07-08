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
    BacklogDrainExpr,
    LiteralExpr,
    PhaseTargetExpr,
    ProduceOneOfExpr,
    RunProviderPhaseExpr,
)
from .phase import resolve_phase_target_type
from .resource import ensure_drain_context_type
from .spans import SourceSpan
from .type_env import PathTypeRef, PrimitiveTypeRef, RecordTypeRef, TypeRef, UnionTypeRef
from .typecheck_calls import (
    _backlog_drain_blocker_class_type,
    validate_gap_drafter_workflow_ref as _validate_gap_drafter_workflow_ref,
    validate_run_item_workflow_ref as _validate_run_item_workflow_ref,
    validate_selector_workflow_ref as _validate_selector_workflow_ref,
    workflow_ref_signature as _workflow_ref_signature,
)
from .typecheck_context import (
    raise_error,
    raise_required_lint,
    _require_normative_phase_ctx_type,
    _require_phase_scope_name_match,
)
from .typecheck_effects import typecheck_expected_extern_operand


def typecheck_backlog_drain_expr(
    expr: BacklogDrainExpr,
    *,
    context,
    recurse,
    typed_factory,
):
    type_env = context.type_env
    drain_result = type_env.resolve_type(
        "DrainResult",
        span=expr.span,
        form_path=expr.form_path,
    )
    if not isinstance(drain_result, UnionTypeRef):
        raise_error(
            "`backlog-drain` requires a union `DrainResult` type",
            code="workflow_ref_return_type_invalid",
            span=expr.span,
            form_path=expr.form_path,
        )
    typed_ctx = recurse(expr.spec.ctx_expr)
    ensure_drain_context_type(
        typed_ctx.type_ref,
        span=expr.spec.ctx_expr.span,
        form_path=expr.spec.ctx_expr.form_path,
    )
    typed_max = recurse(expr.spec.max_iterations_expr)
    if typed_max.type_ref != PrimitiveTypeRef(name="Int"):
        raise_error(
            "`backlog-drain :max-iterations` must resolve to `Int`",
            code="type_mismatch",
            span=expr.spec.max_iterations_expr.span,
            form_path=expr.spec.max_iterations_expr.form_path,
        )
    if not isinstance(typed_max.expr, LiteralExpr):
        raise_error(
            "`backlog-drain :max-iterations` must be a literal `Int` in this Stage 6 slice",
            code="backlog_drain_contract_invalid",
            span=expr.spec.max_iterations_expr.span,
            form_path=expr.spec.max_iterations_expr.form_path,
        )
    selector_signature = _workflow_ref_signature(
        context.workflow_catalog,
        workflow_name=expr.spec.selector_name,
        span=expr.span,
        form_path=expr.form_path,
    )
    selected_payload_type, gap_payload_type = _validate_selector_workflow_ref(
        selector_signature,
        type_env=type_env,
        span=expr.span,
        form_path=expr.form_path,
    )
    run_item_signature = _workflow_ref_signature(
        context.workflow_catalog,
        workflow_name=expr.spec.run_item_name,
        span=expr.span,
        form_path=expr.form_path,
    )
    _validate_run_item_workflow_ref(
        run_item_signature,
        type_env=type_env,
        selected_payload_type=selected_payload_type,
        span=expr.span,
        form_path=expr.form_path,
    )
    gap_drafter_signature = _workflow_ref_signature(
        context.workflow_catalog,
        workflow_name=expr.spec.gap_drafter_name,
        span=expr.span,
        form_path=expr.form_path,
    )
    _validate_gap_drafter_workflow_ref(
        gap_drafter_signature,
        type_env=type_env,
        gap_payload_type=gap_payload_type,
        span=expr.span,
        form_path=expr.form_path,
    )
    blocker_class = _backlog_drain_blocker_class_type(
        type_env,
        span=expr.span,
        form_path=expr.form_path,
    )
    _require_union_variant_exact_field_names(
        drain_result,
        "EMPTY",
        expected_fields=(),
        span=expr.span,
        form_path=expr.form_path,
    )
    _require_union_variant_path_field(
        drain_result,
        "BLOCKED",
        "progress-report-path",
        expected_under="artifacts/work",
        span=expr.span,
        form_path=expr.form_path,
    )
    _require_union_variant_exact_type(
        drain_result,
        "BLOCKED",
        "blocker-class",
        expected_type=blocker_class,
        span=expr.span,
        form_path=expr.form_path,
    )
    _require_union_variant_exact_field_names(
        drain_result,
        "BLOCKED",
        expected_fields=("progress-report-path", "blocker-class"),
        span=expr.span,
        form_path=expr.form_path,
    )
    _require_union_variant_exact_type(
        drain_result,
        "COMPLETED",
        "items-processed",
        expected_type=PrimitiveTypeRef(name="Int"),
        span=expr.span,
        form_path=expr.form_path,
    )
    _require_union_variant_exact_field_names(
        drain_result,
        "COMPLETED",
        expected_fields=("items-processed",),
        span=expr.span,
        form_path=expr.form_path,
    )
    typed_providers = None
    if expr.spec.providers_expr is not None:
        typed_providers = recurse(expr.spec.providers_expr)
    return typed_factory(
        expr=expr,
        type_ref=drain_result,
        effect=merge_effect_summaries(
            typed_ctx.effect_summary,
            typed_max.effect_summary,
            typed_providers.effect_summary if typed_providers is not None else EMPTY_EFFECT_SUMMARY,
        ),
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
    typed_provider = typecheck_expected_extern_operand(
        expr.provider,
        expected_primitive="Provider",
        context=context,
        recurse=recurse,
        typed_factory=typed_factory,
    )
    typed_prompt = typecheck_expected_extern_operand(
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
    typed_provider = typecheck_expected_extern_operand(
        expr.producer.provider_expr,
        expected_primitive="Provider",
        context=context,
        recurse=recurse,
        typed_factory=typed_factory,
    )
    typed_prompt = typecheck_expected_extern_operand(
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


def _require_union_variant_field(
    union_type: UnionTypeRef,
    variant_name: str,
    field_name: str,
    *,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> TypeRef:
    variant_fields = union_type.variant_field_types.get(variant_name)
    if variant_fields is None or field_name not in variant_fields:
        raise_required_lint(
            f"workflow ref return union `{union_type.name}` must expose `{variant_name}.{field_name}`",
            code="workflow_call_signature_erased",
            span=span,
            form_path=form_path,
        )
    return variant_fields[field_name]


def _require_union_variant_path_field(
    union_type: UnionTypeRef,
    variant_name: str,
    field_name: str,
    *,
    expected_under: str,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> PathTypeRef:
    field_type = _require_union_variant_field(
        union_type,
        variant_name,
        field_name,
        span=span,
        form_path=form_path,
    )
    if not isinstance(field_type, PathTypeRef) or field_type.definition.under != expected_under:
        raise_required_lint(
            (
                f"workflow ref return union `{union_type.name}` must expose `{variant_name}.{field_name}` "
                f"as a relpath under `{expected_under}`"
            ),
            code="workflow_call_signature_erased",
            span=span,
            form_path=form_path,
        )
    return field_type


def _require_union_variant_exact_type(
    union_type: UnionTypeRef,
    variant_name: str,
    field_name: str,
    *,
    expected_type: TypeRef,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> TypeRef:
    field_type = _require_union_variant_field(
        union_type,
        variant_name,
        field_name,
        span=span,
        form_path=form_path,
    )
    if field_type != expected_type:
        raise_required_lint(
            (
                f"workflow ref return union `{union_type.name}` must expose `{variant_name}.{field_name}` "
                f"as `{getattr(expected_type, 'name', type(expected_type).__name__)}`"
            ),
            code="workflow_call_signature_erased",
            span=span,
            form_path=form_path,
        )
    return field_type


def _require_union_variant_exact_field_names(
    union_type: UnionTypeRef,
    variant_name: str,
    *,
    expected_fields: tuple[str, ...],
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> None:
    variant_fields = union_type.variant_field_types.get(variant_name)
    actual_fields = tuple(sorted(variant_fields)) if variant_fields is not None else ()
    if actual_fields != tuple(sorted(expected_fields)):
        raise_required_lint(
            (
                f"workflow ref return union `{union_type.name}` must expose `{variant_name}` "
                f"with exactly {expected_fields}"
            ),
            code="workflow_call_signature_erased",
            span=span,
            form_path=form_path,
        )
