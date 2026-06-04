"""Review-loop stdlib typecheck ownership and policy guards."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import Any

from .effects import EffectSummary, merge_effect_summaries
from .expressions import (
    CommandResultExpr,
    ContinueExpr,
    DoneExpr,
    ExprNode,
    FieldAccessExpr,
    LetStarExpr,
    LiteralExpr,
    LoopRecurExpr,
    MatchArm,
    MatchExpr,
    NameExpr,
    ProcedureCallExpr,
    ProviderResultExpr,
    RecordExpr,
    StdlibSpecializationExpr,
    UnionVariantExpr,
    WithPhaseExpr,
)
from .phase import PhaseScope
from .phase_stdlib import (
    ReviewLoopLegacyBridgePolicy,
    ensure_review_loop_legacy_bridge_allowed,
)
from .procedures import ProcedureLoweringMode
from .spans import SourceSpan
from .type_env import FrontendTypeEnvironment, PrimitiveTypeRef, RecordTypeRef, TypeRef, UnionTypeRef
from .typecheck_context import get_session_state, raise_error as _raise_error


def _typecheck_owner(*args, **kwargs):
    from .typecheck_dispatch import _typecheck

    return _typecheck(*args, **kwargs)


def _typecheck_expected_extern_operand_owner(*args, **kwargs):
    from types import SimpleNamespace

    from .typecheck_effects import typecheck_expected_extern_operand

    expr = args[0]
    expected_primitive = kwargs.pop("expected_primitive")
    recurse = lambda node: _typecheck_owner(node, **kwargs)
    typed_factory = lambda *, expr, type_ref, effect: SimpleNamespace(
        expr=expr,
        type_ref=type_ref,
        effect_summary=effect,
    )
    context = SimpleNamespace(value_env=kwargs["value_env"])
    return typecheck_expected_extern_operand(
        expr,
        expected_primitive=expected_primitive,
        context=context,
        recurse=recurse,
        typed_factory=typed_factory,
    )


def _require_normative_phase_ctx_type_owner(*args, **kwargs):
    from .typecheck_dispatch import _require_normative_phase_ctx_type

    return _require_normative_phase_ctx_type(*args, **kwargs)


def _require_phase_scope_name_match_owner(*args, **kwargs):
    from .typecheck_dispatch import _require_phase_scope_name_match

    return _require_phase_scope_name_match(*args, **kwargs)


def _generated_procedure_signature_owner(*args, **kwargs):
    from .typecheck_dispatch import _generated_procedure_signature

    return _generated_procedure_signature(*args, **kwargs)


def _generated_procedure_definition_owner(*args, **kwargs):
    from .typecheck_dispatch import _generated_procedure_definition

    return _generated_procedure_definition(*args, **kwargs)


def _typecheck_generated_procedure_owner(*args, **kwargs):
    from .typecheck_dispatch import _typecheck_generated_procedure

    return _typecheck_generated_procedure(*args, **kwargs)


def _register_generated_record_type_owner(*args, **kwargs):
    from .typecheck_dispatch import _register_generated_record_type

    return _register_generated_record_type(*args, **kwargs)


def _register_generated_union_type_owner(*args, **kwargs):
    from .typecheck_dispatch import _register_generated_union_type

    return _register_generated_union_type(*args, **kwargs)


def _temporary_procedure_catalog_owner(*args, **kwargs):
    from .typecheck_dispatch import _temporary_procedure_catalog

    return _temporary_procedure_catalog(*args, **kwargs)


def _generated_relpath_seed_expr_owner(*args, **kwargs):
    from .typecheck_dispatch import _generated_relpath_seed_expr

    return _generated_relpath_seed_expr(*args, **kwargs)


def validate_review_loop_result_contract(
    return_type: UnionTypeRef,
    *,
    type_env: FrontendTypeEnvironment,
    span: SourceSpan,
    form_path: tuple[str, ...],
    legacy_validator: Callable[..., None] | None = None,
) -> None:
    """Route review-loop result-contract validation through the stdlib owner seam."""

    (_phase_review_loop_result_contract_impl if legacy_validator is None else legacy_validator)(
        return_type,
        type_env=type_env,
        span=span,
        form_path=form_path,
    )


def typecheck_stdlib_specialization_expr(
    expr: StdlibSpecializationExpr,
    *,
    review_loop_legacy_bridge_policy: ReviewLoopLegacyBridgePolicy,
    legacy_typechecker: Callable[..., Any] | None = None,
    **kwargs: Any,
) -> Any:
    """Guard the legacy review-loop bridge before invoking the stdlib owner implementation."""

    ensure_review_loop_legacy_bridge_allowed(
        review_loop_legacy_bridge_policy=review_loop_legacy_bridge_policy,
        request_kind=expr.request_kind,
        span=expr.span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    handler = _phase_review_loop_typecheck_impl if legacy_typechecker is None else legacy_typechecker
    return handler(expr, **kwargs)


def _validate_phase_review_loop_result_contract(
    return_type: UnionTypeRef,
    *,
    type_env: FrontendTypeEnvironment,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> None:
    validate_review_loop_result_contract(
        return_type,
        type_env=type_env,
        span=span,
        form_path=form_path,
        legacy_validator=None,
    )


def _phase_review_loop_result_contract_impl(
    return_type: UnionTypeRef,
    *,
    type_env: FrontendTypeEnvironment,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> None:
    from .contracts import is_review_findings_type

    required_variants = {
        "APPROVED": {"checks_report", "review_report", "review_decision", "findings"},
        "BLOCKED": {"progress_report", "blocker_class", "findings"},
        "EXHAUSTED": {"last_review_report", "reason", "findings"},
    }
    declared_variants = {variant.name for variant in return_type.definition.variants}
    if set(required_variants) != declared_variants:
        _raise_error(
            "`review-revise-loop` requires `APPROVED`, `BLOCKED`, and `EXHAUSTED` variants exactly",
            code="review_loop_result_contract_invalid",
            span=span,
            form_path=form_path,
        )
    for variant_name, required_fields in required_variants.items():
        variant_type = type_env.union_variant(return_type, variant_name, span=span, form_path=form_path)
        declared_fields = {field.name for field in variant_type.definition.fields}
        missing = sorted(required_fields - declared_fields)
        if missing:
            _raise_error(
                f"`review-revise-loop` variant `{variant_name}` is missing `{missing[0]}`",
                code="review_loop_result_contract_invalid",
                span=span,
                form_path=form_path,
            )
        findings_type = return_type.variant_field_types.get(variant_name, {}).get("findings")
        if findings_type is None:
            continue
        if not is_review_findings_type(findings_type):
            _raise_error(
                f"`review-revise-loop` variant `{variant_name}` must use `std/phase.ReviewFindings` for `findings`",
                code="review_loop_result_contract_invalid",
                span=span,
                form_path=form_path,
            )


def _phase_review_loop_typecheck_impl(
    expr: StdlibSpecializationExpr,
    *,
    type_env: FrontendTypeEnvironment,
    value_env: dict[str, TypeRef],
    proof_scope: ProofScope,
    workflow_catalog: "WorkflowCatalog | None",
    procedure_catalog: "ProcedureCatalog | None",
    extern_environment: "ExternEnvironment | None",
    command_boundary_environment: "CommandBoundaryEnvironment | None",
    active_phase_scope: PhaseScope | None,
    procedure_effects_by_name: Mapping[str, EffectSummary],
    workflow_effects_by_name: Mapping[str, EffectSummary],
    proc_ref_resolution_context: ProcRefResolutionContext | None,
) -> TypedExpr:
    if expr.request_kind != "phase-review-loop":
        _raise_error(
            f"unknown stdlib specialization request `{expr.request_kind}`",
            span=expr.span,
            form_path=expr.form_path,
        )
    loop_name = _stdlib_specialization_symbol(expr, "loop-name")
    returns_type_name = _stdlib_specialization_symbol(expr, "returns")
    ctx_expr = _stdlib_specialization_operand(expr, "ctx")
    completed_expr = _stdlib_specialization_operand(expr, "completed")
    inputs_expr = _stdlib_specialization_operand(expr, "inputs")
    review_provider_expr = _stdlib_specialization_operand(expr, "review-provider")
    fix_provider_expr = _stdlib_specialization_operand(expr, "fix-provider")
    review_prompt_expr = _stdlib_specialization_operand(expr, "review-prompt")
    fix_prompt_expr = _stdlib_specialization_operand(expr, "fix-prompt")
    max_expr = _stdlib_specialization_operand(expr, "max")

    return_type = type_env.resolve_type(
        returns_type_name,
        span=expr.span,
        form_path=expr.form_path,
    )
    if not isinstance(return_type, UnionTypeRef):
        _raise_error(
            "`review-revise-loop` requires a union `:returns` type",
            code="review_loop_result_contract_invalid",
            span=expr.span,
            form_path=expr.form_path,
        )
    typed_ctx = _typecheck_owner(
        ctx_expr,
        type_env=type_env,
        value_env=value_env,
        proof_scope=proof_scope,
        workflow_catalog=workflow_catalog,
        procedure_catalog=procedure_catalog,
        extern_environment=extern_environment,
        command_boundary_environment=command_boundary_environment,
        active_phase_scope=active_phase_scope,
        procedure_effects_by_name=procedure_effects_by_name,
        workflow_effects_by_name=workflow_effects_by_name,
        proc_ref_resolution_context=proc_ref_resolution_context,
    )
    _require_normative_phase_ctx_type_owner(
        typed_ctx.type_ref,
        span=ctx_expr.span,
        form_path=ctx_expr.form_path,
    )
    _require_phase_scope_name_match_owner(
        active_phase_scope,
        authored_name=loop_name,
        form_name="review-revise-loop",
        span=expr.span,
        form_path=expr.form_path,
    )
    typed_completed = _typecheck_owner(
        completed_expr,
        type_env=type_env,
        value_env=value_env,
        proof_scope=proof_scope,
        workflow_catalog=workflow_catalog,
        procedure_catalog=procedure_catalog,
        extern_environment=extern_environment,
        command_boundary_environment=command_boundary_environment,
        active_phase_scope=active_phase_scope,
        procedure_effects_by_name=procedure_effects_by_name,
        workflow_effects_by_name=workflow_effects_by_name,
        proc_ref_resolution_context=proc_ref_resolution_context,
    )
    typed_inputs = _typecheck_owner(
        inputs_expr,
        type_env=type_env,
        value_env=value_env,
        proof_scope=proof_scope,
        workflow_catalog=workflow_catalog,
        procedure_catalog=procedure_catalog,
        extern_environment=extern_environment,
        command_boundary_environment=command_boundary_environment,
        active_phase_scope=active_phase_scope,
        procedure_effects_by_name=procedure_effects_by_name,
        workflow_effects_by_name=workflow_effects_by_name,
        proc_ref_resolution_context=proc_ref_resolution_context,
    )
    typed_review_provider = _typecheck_expected_extern_operand_owner(
        review_provider_expr,
        expected_primitive="Provider",
        type_env=type_env,
        value_env=value_env,
        proof_scope=proof_scope,
        workflow_catalog=workflow_catalog,
        procedure_catalog=procedure_catalog,
        extern_environment=extern_environment,
        command_boundary_environment=command_boundary_environment,
        active_phase_scope=active_phase_scope,
        procedure_effects_by_name=procedure_effects_by_name,
        workflow_effects_by_name=workflow_effects_by_name,
        proc_ref_resolution_context=proc_ref_resolution_context,
    )
    typed_fix_provider = _typecheck_expected_extern_operand_owner(
        fix_provider_expr,
        expected_primitive="Provider",
        type_env=type_env,
        value_env=value_env,
        proof_scope=proof_scope,
        workflow_catalog=workflow_catalog,
        procedure_catalog=procedure_catalog,
        extern_environment=extern_environment,
        command_boundary_environment=command_boundary_environment,
        active_phase_scope=active_phase_scope,
        procedure_effects_by_name=procedure_effects_by_name,
        workflow_effects_by_name=workflow_effects_by_name,
        proc_ref_resolution_context=proc_ref_resolution_context,
    )
    typed_review_prompt = _typecheck_expected_extern_operand_owner(
        review_prompt_expr,
        expected_primitive="Prompt",
        type_env=type_env,
        value_env=value_env,
        proof_scope=proof_scope,
        workflow_catalog=workflow_catalog,
        procedure_catalog=procedure_catalog,
        extern_environment=extern_environment,
        command_boundary_environment=command_boundary_environment,
        active_phase_scope=active_phase_scope,
        procedure_effects_by_name=procedure_effects_by_name,
        workflow_effects_by_name=workflow_effects_by_name,
        proc_ref_resolution_context=proc_ref_resolution_context,
    )
    typed_fix_prompt = _typecheck_expected_extern_operand_owner(
        fix_prompt_expr,
        expected_primitive="Prompt",
        type_env=type_env,
        value_env=value_env,
        proof_scope=proof_scope,
        workflow_catalog=workflow_catalog,
        procedure_catalog=procedure_catalog,
        extern_environment=extern_environment,
        command_boundary_environment=command_boundary_environment,
        active_phase_scope=active_phase_scope,
        procedure_effects_by_name=procedure_effects_by_name,
        workflow_effects_by_name=workflow_effects_by_name,
        proc_ref_resolution_context=proc_ref_resolution_context,
    )
    typed_max = _typecheck_owner(
        max_expr,
        type_env=type_env,
        value_env=value_env,
        proof_scope=proof_scope,
        workflow_catalog=workflow_catalog,
        procedure_catalog=procedure_catalog,
        extern_environment=extern_environment,
        command_boundary_environment=command_boundary_environment,
        active_phase_scope=active_phase_scope,
        procedure_effects_by_name=procedure_effects_by_name,
        workflow_effects_by_name=workflow_effects_by_name,
        proc_ref_resolution_context=proc_ref_resolution_context,
    )
    if typed_max.type_ref != PrimitiveTypeRef(name="Int"):
        _raise_error(
            "`review-revise-loop :max` must resolve to `Int`",
            code="type_mismatch",
            span=max_expr.span,
            form_path=max_expr.form_path,
        )
    _validate_phase_review_loop_result_contract(
        return_type,
        type_env=type_env,
        span=expr.span,
        form_path=expr.form_path,
    )
    if procedure_catalog is None:
        raise TypeError("procedure_catalog is required for stdlib specialization")
    rewritten = _specialize_phase_review_loop_request(
        expr,
        loop_name=loop_name,
        ctx_expr=ctx_expr,
        completed_expr=completed_expr,
        inputs_expr=inputs_expr,
        review_provider_expr=review_provider_expr,
        fix_provider_expr=fix_provider_expr,
        review_prompt_expr=review_prompt_expr,
        fix_prompt_expr=fix_prompt_expr,
        max_expr=max_expr,
        phase_ctx_type=typed_ctx.type_ref,
        completed_type=typed_completed.type_ref,
        inputs_type=typed_inputs.type_ref,
        return_type=return_type,
        type_env=type_env,
        value_env=value_env,
        proof_scope=proof_scope,
        workflow_catalog=workflow_catalog,
        procedure_catalog=procedure_catalog,
        extern_environment=extern_environment,
        command_boundary_environment=command_boundary_environment,
        active_phase_scope=active_phase_scope,
        procedure_effects_by_name=procedure_effects_by_name,
        workflow_effects_by_name=workflow_effects_by_name,
        proc_ref_resolution_context=proc_ref_resolution_context,
    )
    return replace(
        rewritten,
        effect_summary=merge_effect_summaries(
            typed_ctx.effect_summary,
            typed_completed.effect_summary,
            typed_inputs.effect_summary,
            typed_review_provider.effect_summary,
            typed_fix_provider.effect_summary,
            typed_review_prompt.effect_summary,
            typed_fix_prompt.effect_summary,
            typed_max.effect_summary,
            rewritten.effect_summary,
        ),
    )


def _specialize_phase_review_loop_request(
    expr: StdlibSpecializationExpr,
    *,
    loop_name: str,
    ctx_expr: ExprNode,
    completed_expr: ExprNode,
    inputs_expr: ExprNode,
    review_provider_expr: ExprNode,
    fix_provider_expr: ExprNode,
    review_prompt_expr: ExprNode,
    fix_prompt_expr: ExprNode,
    max_expr: ExprNode,
    phase_ctx_type: TypeRef,
    completed_type: TypeRef,
    inputs_type: TypeRef,
    return_type: UnionTypeRef,
    type_env: FrontendTypeEnvironment,
    value_env: dict[str, TypeRef],
    proof_scope: ProofScope,
    workflow_catalog: "WorkflowCatalog | None",
    procedure_catalog: ProcedureCatalog,
    extern_environment: "ExternEnvironment | None",
    command_boundary_environment: "CommandBoundaryEnvironment | None",
    active_phase_scope: PhaseScope | None,
    procedure_effects_by_name: Mapping[str, EffectSummary],
    workflow_effects_by_name: Mapping[str, EffectSummary],
    proc_ref_resolution_context: ProcRefResolutionContext | None,
) -> TypedExpr:
    generated_span = _generated_expr_span(expr)
    generated_prefix = _review_loop_generated_prefix(expr)
    type_prefix = f"{generated_prefix}__types"
    review_wrapper_name = _review_loop_generated_procedure_name(expr, "review")
    fix_wrapper_name = _review_loop_generated_procedure_name(expr, "fix")
    helper_name = _review_loop_generated_procedure_name(expr, "helper")
    approved_variant = type_env.union_variant(return_type, "APPROVED", span=expr.span, form_path=expr.form_path)
    blocked_variant = type_env.union_variant(return_type, "BLOCKED", span=expr.span, form_path=expr.form_path)
    exhausted_variant = type_env.union_variant(return_type, "EXHAUSTED", span=expr.span, form_path=expr.form_path)
    review_result_type_name = f"{type_prefix}__review_result"
    state_type_name = f"{type_prefix}__state"
    last_review_report_type = type_env.record_field(
        exhausted_variant,
        "last_review_report",
        span=expr.span,
        form_path=expr.form_path,
    )
    findings_type = _variant_field_type(type_env, approved_variant, "findings", expr)
    _register_generated_union_type_owner(
        type_env,
        name=review_result_type_name,
        variants=(
            (
                "APPROVED",
                (
                    ("checks_report", _variant_field_type(type_env, approved_variant, "checks_report", expr)),
                    ("review_report", _variant_field_type(type_env, approved_variant, "review_report", expr)),
                    ("review_decision", _variant_field_type(type_env, approved_variant, "review_decision", expr)),
                    ("findings", findings_type),
                ),
            ),
            (
                "BLOCKED",
                (
                    ("progress_report", _variant_field_type(type_env, blocked_variant, "progress_report", expr)),
                    ("blocker_class", _variant_field_type(type_env, blocked_variant, "blocker_class", expr)),
                    ("findings", findings_type),
                ),
            ),
            (
                "REVISE",
                (
                    ("revise_review_report", _variant_field_type(type_env, approved_variant, "review_report", expr)),
                    ("findings", findings_type),
                ),
            ),
        ),
        span=expr.span,
        form_path=expr.form_path,
    )
    _register_generated_record_type_owner(
        type_env,
        name=state_type_name,
        fields=(
            ("completed", completed_type),
            ("last_review_report", last_review_report_type),
            ("latest_findings", findings_type),
        ),
        span=expr.span,
        form_path=expr.form_path,
    )

    ctx_param = NameExpr(name="ctx", span=generated_span, form_path=expr.form_path, expansion_stack=expr.expansion_stack)
    completed_param = NameExpr(
        name="completed",
        span=generated_span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    inputs_param = NameExpr(
        name="inputs",
        span=generated_span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    max_param = NameExpr(name="max", span=generated_span, form_path=expr.form_path, expansion_stack=expr.expansion_stack)
    review_report_param = NameExpr(
        name="review_report",
        span=generated_span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    findings_param = NameExpr(
        name="findings",
        span=generated_span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    review_proc_param = NameExpr(
        name="review_proc",
        span=generated_span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    fix_proc_param = NameExpr(
        name="fix_proc",
        span=generated_span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    state_ref = NameExpr(
        name="__review_loop_state",
        span=generated_span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    review_ref = NameExpr(
        name="__review_loop_review",
        span=generated_span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    review_result_ref = NameExpr(
        name="__review_loop_review_result",
        span=generated_span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    fixed_ref = NameExpr(
        name="__review_loop_fixed",
        span=generated_span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    validated_findings_ref = NameExpr(
        name="__review_loop_validated_findings",
        span=generated_span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    revalidated_findings_ref = NameExpr(
        name="__review_loop_revalidated_findings",
        span=generated_span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    approved_ref = NameExpr(name="approved", span=generated_span, form_path=expr.form_path, expansion_stack=expr.expansion_stack)
    blocked_ref = NameExpr(name="blocked", span=generated_span, form_path=expr.form_path, expansion_stack=expr.expansion_stack)
    revise_ref = NameExpr(name="revise", span=generated_span, form_path=expr.form_path, expansion_stack=expr.expansion_stack)
    review_wrapper_approved_ref = NameExpr(
        name="review_wrapper_approved",
        span=generated_span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    review_wrapper_blocked_ref = NameExpr(
        name="review_wrapper_blocked",
        span=generated_span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    review_wrapper_revise_ref = NameExpr(
        name="review_wrapper_revise",
        span=generated_span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    state_completed_ref = FieldAccessExpr(
        base=state_ref,
        fields=("completed",),
        span=generated_span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    last_review_report_ref = FieldAccessExpr(
        base=state_ref,
        fields=("last_review_report",),
        span=generated_span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    latest_findings_ref = FieldAccessExpr(
        base=state_ref,
        fields=("latest_findings",),
        span=generated_span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    initial_last_review_report_expr = _initial_review_loop_report_expr(
        expr,
        completed_expr=completed_param,
        completed_type=completed_type,
        inputs_expr=inputs_param,
        inputs_type=inputs_type,
        last_review_report_type=last_review_report_type,
        generated_span=generated_span,
    )
    initial_findings_expr = RecordExpr(
        type_name=_type_name(findings_type),
        fields=(
            (
                "schema_version",
                LiteralExpr(
                    value="ReviewFindings.v1",
                    literal_kind="string",
                    span=generated_span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
            ),
            (
                "items_path",
                _generated_relpath_seed_expr_owner(
                    type_ref=findings_type.field_types["items_path"],
                    literal_path="artifacts/work/review-findings-seed.json",
                    seed_role="review_loop_findings_items_path_seed",
                    span=generated_span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
            ),
        ),
        span=generated_span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    findings_schema_version_param = FieldAccessExpr(
        base=validated_findings_ref,
        fields=("schema_version",),
        span=generated_span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    findings_items_path_param = FieldAccessExpr(
        base=validated_findings_ref,
        fields=("items_path",),
        span=generated_span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    revise_findings_schema_version_ref = FieldAccessExpr(
        base=revise_ref,
        fields=("findings", "schema_version"),
        span=generated_span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    revise_findings_items_path_ref = FieldAccessExpr(
        base=revise_ref,
        fields=("findings", "items_path"),
        span=generated_span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    approved_findings_schema_version_ref = FieldAccessExpr(
        base=review_wrapper_approved_ref,
        fields=("findings", "schema_version"),
        span=generated_span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    approved_findings_items_path_ref = FieldAccessExpr(
        base=review_wrapper_approved_ref,
        fields=("findings", "items_path"),
        span=generated_span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    blocked_findings_schema_version_ref = FieldAccessExpr(
        base=review_wrapper_blocked_ref,
        fields=("findings", "schema_version"),
        span=generated_span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    blocked_findings_items_path_ref = FieldAccessExpr(
        base=review_wrapper_blocked_ref,
        fields=("findings", "items_path"),
        span=generated_span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    revise_wrapper_findings_schema_version_ref = FieldAccessExpr(
        base=review_wrapper_revise_ref,
        fields=("findings", "schema_version"),
        span=generated_span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    revise_wrapper_findings_items_path_ref = FieldAccessExpr(
        base=review_wrapper_revise_ref,
        fields=("findings", "items_path"),
        span=generated_span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    review_findings_validator_argv = (
        LiteralExpr(
            value="python",
            literal_kind="string",
            span=generated_span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        ),
        LiteralExpr(
            value="-m",
            literal_kind="string",
            span=generated_span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        ),
        LiteralExpr(
            value="orchestrator.workflow_lisp.adapters.validate_review_findings_v1",
            literal_kind="string",
            span=generated_span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        ),
    )
    review_signature = _generated_procedure_signature_owner(
        name=review_wrapper_name,
        params=(
            ("completed", completed_type),
            ("inputs", inputs_type),
        ),
        return_type=type_env.resolve_type(review_result_type_name, span=expr.span, form_path=expr.form_path),
        requested_lowering_mode=ProcedureLoweringMode.PRIVATE_WORKFLOW,
        span=generated_span,
        form_path=expr.form_path,
    )
    review_definition = _generated_procedure_definition_owner(
        name=review_wrapper_name,
        signature=review_signature,
        body=LetStarExpr(
            bindings=(
                (
                    "__review_loop_review_result",
                    ProviderResultExpr(
                        provider=review_provider_expr,
                        prompt=review_prompt_expr,
                        inputs=(completed_param, inputs_param),
                        returns_type_name=review_result_type_name,
                        span=generated_span,
                        form_path=expr.form_path,
                        expansion_stack=expr.expansion_stack,
                    ),
                ),
            ),
            body=MatchExpr(
                subject=review_result_ref,
                arms=(
                    MatchArm(
                        variant_name="APPROVED",
                        binding_name="review_wrapper_approved",
                        body=LetStarExpr(
                            bindings=(
                                (
                                    "__review_loop_validated_findings",
                                    CommandResultExpr(
                                        step_name="validate_review_findings_v1",
                                        argv=(
                                            *review_findings_validator_argv,
                                            approved_findings_schema_version_ref,
                                            approved_findings_items_path_ref,
                                        ),
                                        returns_type_name=_type_name(findings_type),
                                        span=generated_span,
                                        form_path=expr.form_path,
                                        expansion_stack=expr.expansion_stack,
                                    ),
                                ),
                            ),
                            body=UnionVariantExpr(
                                type_name=review_result_type_name,
                                variant_name="APPROVED",
                                fields=(
                                    (
                                        "checks_report",
                                        _field_ref(review_wrapper_approved_ref, "checks_report", expr),
                                    ),
                                    (
                                        "review_report",
                                        _field_ref(review_wrapper_approved_ref, "review_report", expr),
                                    ),
                                    (
                                        "review_decision",
                                        _field_ref(review_wrapper_approved_ref, "review_decision", expr),
                                    ),
                                    (
                                        "findings",
                                        _review_findings_record_expr(
                                            findings_type=findings_type,
                                            base=validated_findings_ref,
                                            expr=expr,
                                        ),
                                    ),
                                ),
                                span=generated_span,
                                form_path=expr.form_path,
                                expansion_stack=expr.expansion_stack,
                            ),
                            span=generated_span,
                            form_path=expr.form_path,
                            expansion_stack=expr.expansion_stack,
                        ),
                        span=generated_span,
                        form_path=expr.form_path,
                        expansion_stack=expr.expansion_stack,
                    ),
                    MatchArm(
                        variant_name="BLOCKED",
                        binding_name="review_wrapper_blocked",
                        body=LetStarExpr(
                            bindings=(
                                (
                                    "__review_loop_validated_findings",
                                    CommandResultExpr(
                                        step_name="validate_review_findings_v1",
                                        argv=(
                                            *review_findings_validator_argv,
                                            blocked_findings_schema_version_ref,
                                            blocked_findings_items_path_ref,
                                        ),
                                        returns_type_name=_type_name(findings_type),
                                        span=generated_span,
                                        form_path=expr.form_path,
                                        expansion_stack=expr.expansion_stack,
                                    ),
                                ),
                            ),
                            body=UnionVariantExpr(
                                type_name=review_result_type_name,
                                variant_name="BLOCKED",
                                fields=(
                                    (
                                        "progress_report",
                                        _field_ref(review_wrapper_blocked_ref, "progress_report", expr),
                                    ),
                                    (
                                        "blocker_class",
                                        _field_ref(review_wrapper_blocked_ref, "blocker_class", expr),
                                    ),
                                    (
                                        "findings",
                                        _review_findings_record_expr(
                                            findings_type=findings_type,
                                            base=validated_findings_ref,
                                            expr=expr,
                                        ),
                                    ),
                                ),
                                span=generated_span,
                                form_path=expr.form_path,
                                expansion_stack=expr.expansion_stack,
                            ),
                            span=generated_span,
                            form_path=expr.form_path,
                            expansion_stack=expr.expansion_stack,
                        ),
                        span=generated_span,
                        form_path=expr.form_path,
                        expansion_stack=expr.expansion_stack,
                    ),
                    MatchArm(
                        variant_name="REVISE",
                        binding_name="review_wrapper_revise",
                        body=LetStarExpr(
                            bindings=(
                                (
                                    "__review_loop_validated_findings",
                                    CommandResultExpr(
                                        step_name="validate_review_findings_v1",
                                        argv=(
                                            *review_findings_validator_argv,
                                            revise_wrapper_findings_schema_version_ref,
                                            revise_wrapper_findings_items_path_ref,
                                        ),
                                        returns_type_name=_type_name(findings_type),
                                        span=generated_span,
                                        form_path=expr.form_path,
                                        expansion_stack=expr.expansion_stack,
                                    ),
                                ),
                            ),
                            body=UnionVariantExpr(
                                type_name=review_result_type_name,
                                variant_name="REVISE",
                                fields=(
                                    (
                                        "revise_review_report",
                                        _field_ref(
                                            review_wrapper_revise_ref,
                                            "revise_review_report",
                                            expr,
                                        ),
                                    ),
                                    (
                                        "findings",
                                        _review_findings_record_expr(
                                            findings_type=findings_type,
                                            base=validated_findings_ref,
                                            expr=expr,
                                        ),
                                    ),
                                ),
                                span=generated_span,
                                form_path=expr.form_path,
                                expansion_stack=expr.expansion_stack,
                            ),
                            span=generated_span,
                            form_path=expr.form_path,
                            expansion_stack=expr.expansion_stack,
                        ),
                        span=generated_span,
                        form_path=expr.form_path,
                        expansion_stack=expr.expansion_stack,
                    ),
                ),
                span=generated_span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            ),
            span=generated_span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        ),
        span=generated_span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    generated_catalog = _temporary_procedure_catalog_owner(
        procedure_catalog,
        definition=review_definition,
        signature=review_signature,
    )
    typed_review = _typecheck_generated_procedure_owner(
        review_definition,
        review_signature,
        type_env=type_env,
        workflow_catalog=workflow_catalog,
        procedure_catalog=generated_catalog,
        extern_environment=extern_environment,
        command_boundary_environment=command_boundary_environment,
        procedure_effects_by_name=procedure_effects_by_name,
        workflow_effects_by_name=workflow_effects_by_name,
        proc_ref_resolution_context=proc_ref_resolution_context,
    )
    fix_signature = _generated_procedure_signature_owner(
        name=fix_wrapper_name,
        params=(
            ("completed", completed_type),
            ("inputs", inputs_type),
            ("review_report", last_review_report_type),
            ("findings", findings_type),
        ),
        return_type=completed_type,
        requested_lowering_mode=ProcedureLoweringMode.PRIVATE_WORKFLOW,
        span=generated_span,
        form_path=expr.form_path,
    )
    fix_definition = _generated_procedure_definition_owner(
        name=fix_wrapper_name,
        signature=fix_signature,
        body=ProviderResultExpr(
            provider=fix_provider_expr,
            prompt=fix_prompt_expr,
            inputs=(completed_param, inputs_param, review_report_param, findings_param),
            returns_type_name=_type_name(completed_type),
            span=generated_span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        ),
        span=generated_span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    generated_catalog = _temporary_procedure_catalog_owner(
        generated_catalog,
        definition=fix_definition,
        signature=fix_signature,
    )
    typed_fix = _typecheck_generated_procedure_owner(
        fix_definition,
        fix_signature,
        type_env=type_env,
        workflow_catalog=workflow_catalog,
        procedure_catalog=generated_catalog,
        extern_environment=extern_environment,
        command_boundary_environment=command_boundary_environment,
        procedure_effects_by_name=procedure_effects_by_name,
        workflow_effects_by_name=workflow_effects_by_name,
        proc_ref_resolution_context=proc_ref_resolution_context,
    )

    helper_signature = _generated_procedure_signature_owner(
        name=helper_name,
        params=(
            ("ctx", phase_ctx_type),
            ("completed", completed_type),
            ("inputs", inputs_type),
            ("max", PrimitiveTypeRef(name="Int")),
        ),
        return_type=return_type,
        requested_lowering_mode=ProcedureLoweringMode.INLINE,
        span=generated_span,
        form_path=expr.form_path,
    )
    helper_definition = _generated_procedure_definition_owner(
        name=helper_name,
        signature=helper_signature,
        body=WithPhaseExpr(
            ctx_expr=ctx_param,
            phase_name=loop_name,
            body=LoopRecurExpr(
                max_iterations_expr=max_param,
                initial_state_expr=RecordExpr(
                    type_name=state_type_name,
                    fields=(
                        ("completed", completed_param),
                        ("last_review_report", initial_last_review_report_expr),
                        ("latest_findings", initial_findings_expr),
                    ),
                    span=generated_span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
                binding_name="__review_loop_state",
                body_expr=LetStarExpr(
                    bindings=(
                        (
                            "__review_loop_review",
                            ProcedureCallExpr(
                                callee_name=review_wrapper_name,
                                args=(state_completed_ref, inputs_param),
                                span=generated_span,
                                form_path=expr.form_path,
                                expansion_stack=expr.expansion_stack,
                            ),
                        ),
                    ),
                    body=MatchExpr(
                        subject=review_ref,
                        arms=(
                            MatchArm(
                                variant_name="APPROVED",
                                binding_name="approved",
                                body=DoneExpr(
                                    result_expr=UnionVariantExpr(
                                        type_name=return_type.name,
                                        variant_name="APPROVED",
                                        fields=(
                                            ("checks_report", _field_ref(approved_ref, "checks_report", expr)),
                                            ("review_report", _field_ref(approved_ref, "review_report", expr)),
                                            ("review_decision", _field_ref(approved_ref, "review_decision", expr)),
                                            (
                                                "findings",
                                                _review_findings_record_expr(
                                                    findings_type=findings_type,
                                                    base=_field_ref(approved_ref, "findings", expr),
                                                    expr=expr,
                                                ),
                                            ),
                                        ),
                                        span=generated_span,
                                        form_path=expr.form_path,
                                        expansion_stack=expr.expansion_stack,
                                    ),
                                    span=generated_span,
                                    form_path=expr.form_path,
                                    expansion_stack=expr.expansion_stack,
                                ),
                                span=generated_span,
                                form_path=expr.form_path,
                                expansion_stack=expr.expansion_stack,
                            ),
                            MatchArm(
                                variant_name="BLOCKED",
                                binding_name="blocked",
                                body=DoneExpr(
                                    result_expr=UnionVariantExpr(
                                        type_name=return_type.name,
                                        variant_name="BLOCKED",
                                        fields=(
                                            ("progress_report", _field_ref(blocked_ref, "progress_report", expr)),
                                            ("blocker_class", _field_ref(blocked_ref, "blocker_class", expr)),
                                            (
                                                "findings",
                                                _review_findings_record_expr(
                                                    findings_type=findings_type,
                                                    base=_field_ref(blocked_ref, "findings", expr),
                                                    expr=expr,
                                                ),
                                            ),
                                        ),
                                        span=generated_span,
                                        form_path=expr.form_path,
                                        expansion_stack=expr.expansion_stack,
                                    ),
                                    span=generated_span,
                                    form_path=expr.form_path,
                                    expansion_stack=expr.expansion_stack,
                                ),
                                span=generated_span,
                                form_path=expr.form_path,
                                expansion_stack=expr.expansion_stack,
                            ),
                            MatchArm(
                                variant_name="REVISE",
                                binding_name="revise",
                                body=LetStarExpr(
                                    bindings=(
                                        (
                                            "__review_loop_revalidated_findings",
                                            CommandResultExpr(
                                                step_name="validate_review_findings_v1",
                                                argv=(
                                                    *review_findings_validator_argv,
                                                    revise_findings_schema_version_ref,
                                                    revise_findings_items_path_ref,
                                                ),
                                                returns_type_name=_type_name(findings_type),
                                                span=generated_span,
                                                form_path=expr.form_path,
                                                expansion_stack=expr.expansion_stack,
                                            ),
                                        ),
                                        (
                                            "__review_loop_fixed",
                                            ProcedureCallExpr(
                                                callee_name=fix_wrapper_name,
                                                args=(
                                                    state_completed_ref,
                                                    inputs_param,
                                                    _field_ref(revise_ref, "revise_review_report", expr),
                                                    revalidated_findings_ref,
                                                ),
                                                span=generated_span,
                                                form_path=expr.form_path,
                                                expansion_stack=expr.expansion_stack,
                                            ),
                                        ),
                                    ),
                                    body=ContinueExpr(
                                        state_expr=RecordExpr(
                                            type_name=state_type_name,
                                            fields=(
                                                ("completed", fixed_ref),
                                                (
                                                    "last_review_report",
                                                    _field_ref(revise_ref, "revise_review_report", expr),
                                                ),
                                                (
                                                    "latest_findings",
                                                    _review_findings_record_expr(
                                                        findings_type=findings_type,
                                                        base=revalidated_findings_ref,
                                                        expr=expr,
                                                    ),
                                                ),
                                            ),
                                            span=generated_span,
                                            form_path=expr.form_path,
                                            expansion_stack=expr.expansion_stack,
                                        ),
                                        span=generated_span,
                                        form_path=expr.form_path,
                                        expansion_stack=expr.expansion_stack,
                                    ),
                                    span=generated_span,
                                    form_path=expr.form_path,
                                    expansion_stack=expr.expansion_stack,
                                ),
                                span=generated_span,
                                form_path=expr.form_path,
                                expansion_stack=expr.expansion_stack,
                            ),
                        ),
                        span=generated_span,
                        form_path=expr.form_path,
                        expansion_stack=expr.expansion_stack,
                    ),
                    span=generated_span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
                on_exhausted_result_expr=UnionVariantExpr(
                    type_name=return_type.name,
                    variant_name="EXHAUSTED",
                    fields=(
                        ("last_review_report", last_review_report_ref),
                        (
                            "findings",
                            RecordExpr(
                                type_name=_type_name(findings_type),
                                fields=(
                                    (
                                        "schema_version",
                                        LiteralExpr(
                                            value="ReviewFindings.v1",
                                            literal_kind="string",
                                            span=generated_span,
                                            form_path=expr.form_path,
                                            expansion_stack=expr.expansion_stack,
                                        ),
                                    ),
                                    (
                                        "items_path",
                                        FieldAccessExpr(
                                            base=latest_findings_ref,
                                            fields=("items_path",),
                                            span=generated_span,
                                            form_path=expr.form_path,
                                            expansion_stack=expr.expansion_stack,
                                        ),
                                    ),
                                ),
                                span=generated_span,
                                form_path=expr.form_path,
                                expansion_stack=expr.expansion_stack,
                            ),
                        ),
                        (
                            "reason",
                            LiteralExpr(
                                value="max_iterations_reached",
                                literal_kind="string",
                                span=generated_span,
                                form_path=expr.form_path,
                                expansion_stack=expr.expansion_stack,
                            ),
                        ),
                    ),
                    span=generated_span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
                span=generated_span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            ),
            span=generated_span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        ),
        span=generated_span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    generated_catalog = _temporary_procedure_catalog_owner(
        generated_catalog,
        definition=helper_definition,
        signature=helper_signature,
    )
    typed_helper = _typecheck_generated_procedure_owner(
        helper_definition,
        helper_signature,
        type_env=type_env,
        workflow_catalog=workflow_catalog,
        procedure_catalog=generated_catalog,
        extern_environment=extern_environment,
        command_boundary_environment=command_boundary_environment,
        procedure_effects_by_name=procedure_effects_by_name,
        workflow_effects_by_name=workflow_effects_by_name,
        proc_ref_resolution_context=proc_ref_resolution_context,
    )
    helper_effects = merge_effect_summaries(
        typed_helper.typed_body.effect_summary,
        typed_review.transitive_effect_summary,
        typed_fix.transitive_effect_summary,
    )
    typed_helper = replace(
        typed_helper,
        direct_effect_summary=helper_effects,
        transitive_effect_summary=helper_effects,
    )
    session_state = get_session_state()
    session_state.generated_local_procedures[review_wrapper_name] = typed_review
    session_state.generated_local_procedures[fix_wrapper_name] = typed_fix
    session_state.generated_local_procedures[helper_name] = typed_helper

    rewritten_expr = ProcedureCallExpr(
        callee_name=helper_name,
        args=(
            ctx_expr,
            completed_expr,
            inputs_expr,
            max_expr,
        ),
        span=generated_span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    generated_effects = dict(procedure_effects_by_name)
    generated_effects[review_wrapper_name] = typed_review.transitive_effect_summary
    generated_effects[fix_wrapper_name] = typed_fix.transitive_effect_summary
    generated_effects[helper_name] = typed_helper.transitive_effect_summary
    return _typecheck_owner(
        rewritten_expr,
        type_env=type_env,
        value_env=value_env,
        proof_scope=proof_scope,
        workflow_catalog=workflow_catalog,
        procedure_catalog=generated_catalog,
        extern_environment=extern_environment,
        command_boundary_environment=command_boundary_environment,
        active_phase_scope=active_phase_scope,
        procedure_effects_by_name=generated_effects,
        workflow_effects_by_name=workflow_effects_by_name,
        proc_ref_resolution_context=proc_ref_resolution_context,
    )


def _review_loop_generated_prefix(expr: StdlibSpecializationExpr) -> str:
    start = expr.span.start
    return f"rl{start.line}_{start.column}"


def _review_loop_generated_procedure_name(expr: StdlibSpecializationExpr, suffix: str) -> str:
    short_suffix = {
        "review": "r",
        "fix": "f",
        "helper": "h",
    }.get(suffix, suffix)
    return f"%rl.{_review_loop_generated_prefix(expr)}.{short_suffix}"


def _generated_expr_span(expr: StdlibSpecializationExpr) -> SourceSpan:
    for frame in expr.expansion_stack:
        call_span = getattr(frame, "call_span", None)
        if isinstance(call_span, SourceSpan):
            return call_span
    return expr.span


def _first_record_field_name_with_type(record_type: RecordTypeRef, target_type: TypeRef) -> str | None:
    for field in record_type.definition.fields:
        if record_type.field_types.get(field.name) == target_type:
            return field.name
    return None


def _type_name(type_ref: TypeRef) -> str:
    return type_ref.name


def _variant_field_type(
    type_env: FrontendTypeEnvironment,
    variant_type,
    field_name: str,
    expr: StdlibSpecializationExpr,
) -> TypeRef:
    return type_env.record_field(
        variant_type,
        field_name,
        span=expr.span,
        form_path=expr.form_path,
    )


def _field_ref(base: NameExpr, field_name: str, expr: StdlibSpecializationExpr) -> FieldAccessExpr:
    return FieldAccessExpr(
        base=base,
        fields=(field_name,),
        span=_generated_expr_span(expr),
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )


def _review_findings_record_expr(
    *,
    findings_type: TypeRef,
    base: ExprNode,
    expr: StdlibSpecializationExpr,
) -> RecordExpr:
    generated_span = _generated_expr_span(expr)
    return RecordExpr(
        type_name=_type_name(findings_type),
        fields=(
            (
                "schema_version",
                FieldAccessExpr(
                    base=base,
                    fields=("schema_version",),
                    span=generated_span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
            ),
            (
                "items_path",
                FieldAccessExpr(
                    base=base,
                    fields=("items_path",),
                    span=generated_span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
            ),
        ),
        span=generated_span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )


def _stdlib_specialization_symbol(expr: StdlibSpecializationExpr, name: str) -> str:
    symbols = dict(expr.symbol_operands)
    value = symbols.get(name)
    if value is None:
        _raise_error(
            f"missing stdlib specialization symbol operand `{name}`",
            span=expr.span,
            form_path=expr.form_path,
        )
    return value


def _stdlib_specialization_operand(expr: StdlibSpecializationExpr, name: str) -> ExprNode:
    operands = dict(expr.expr_operands)
    value = operands.get(name)
    if value is None:
        _raise_error(
            f"missing stdlib specialization operand `{name}`",
            span=expr.span,
            form_path=expr.form_path,
        )
    return value


def _initial_review_loop_report_expr(
    expr: StdlibSpecializationExpr,
    *,
    completed_expr: NameExpr,
    completed_type: TypeRef,
    inputs_expr: NameExpr,
    inputs_type: TypeRef,
    last_review_report_type: TypeRef,
    generated_span: SourceSpan,
) -> ExprNode:
    if isinstance(completed_type, RecordTypeRef) and (
        (
            "execution_report_path" in completed_type.field_types
            and completed_type.field_types["execution_report_path"] == last_review_report_type
        )
        or _first_record_field_name_with_type(completed_type, last_review_report_type) is not None
    ):
        field_name = (
            "execution_report_path"
            if completed_type.field_types.get("execution_report_path") == last_review_report_type
            else _first_record_field_name_with_type(completed_type, last_review_report_type)
        )
        assert field_name is not None
        return FieldAccessExpr(
            base=completed_expr,
            fields=(field_name,),
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    if isinstance(inputs_type, RecordTypeRef) and (
        field_name := _first_record_field_name_with_type(inputs_type, last_review_report_type)
    ) is not None:
        return FieldAccessExpr(
            base=inputs_expr,
            fields=(field_name,),
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    return _generated_relpath_seed_expr_owner(
        type_ref=last_review_report_type,
        literal_path="artifacts/review/last-review-report.md",
        seed_role="review_loop_last_review_report_seed",
        span=generated_span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
