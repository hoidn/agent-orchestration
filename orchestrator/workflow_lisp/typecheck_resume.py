"""Resume-or-start typecheck ownership for Workflow Lisp."""

from __future__ import annotations

from dataclasses import replace

from .effects import (
    UsesCommandEffect,
    effect_summary_from_direct,
    merge_effect_summaries,
)
from .expressions import CallExpr, CommandResultExpr, ResumeOrStartExpr
from .phase_stdlib import ReusableStateValidationSpec
from .spans import SourceSpan
from .type_env import PathTypeRef, RecordTypeRef, UnionTypeRef
from .typecheck_context import (
    TypedExpr,
    _require_normative_phase_ctx_type,
    _require_phase_scope_name_match,
    get_session_state,
    raise_error,
)


def typecheck_resume_or_start_expr(
    expr: ResumeOrStartExpr,
    *,
    context,
    recurse,
    typed_factory,
) -> TypedExpr:
    type_env = context.type_env
    workflow_catalog = context.workflow_catalog
    command_boundary_environment = context.command_boundary_environment
    active_phase_scope = context.active_phase_scope

    return_type = type_env.resolve_type(
        expr.returns_type_name,
        span=expr.span,
        form_path=expr.form_path,
    )
    if not isinstance(return_type, (RecordTypeRef, UnionTypeRef)):
        raise_error(
            "`resume-or-start :returns` must resolve to a record or union",
            code="resume_or_start_contract_invalid",
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
        active_phase_scope,
        authored_name=expr.resume_name,
        form_name="resume-or-start",
        span=expr.span,
        form_path=expr.form_path,
    )
    typed_resume_from = recurse(expr.resume_from_expr)
    if not isinstance(typed_resume_from.type_ref, PathTypeRef) or typed_resume_from.type_ref.definition.under != "state":
        raise_error(
            "`resume-or-start :resume-from` must be a canonical state relpath",
            code="resume_or_start_resume_path_invalid",
            span=expr.resume_from_expr.span,
            form_path=expr.resume_from_expr.form_path,
        )
    if isinstance(expr.start_expr, CallExpr):
        start_signature = workflow_catalog.signatures_by_name.get(expr.start_expr.callee_name) if workflow_catalog is not None else None
        if start_signature is not None and isinstance(start_signature.return_type_ref, UnionTypeRef):
            if start_signature.return_type_ref != return_type:
                raise_error(
                    "`resume-or-start :start` workflow call must return the declared union `:returns` type",
                    code="resume_or_start_contract_invalid",
                    span=expr.start_expr.span,
                    form_path=expr.start_expr.form_path,
                )
    typed_start = recurse(expr.start_expr)
    if typed_start.type_ref != return_type:
        raise_error(
            "`resume-or-start :start` must typecheck to the declared `:returns` type",
            code="resume_or_start_contract_invalid",
            span=expr.start_expr.span,
            form_path=expr.start_expr.form_path,
        )
    valid_variants = expr.valid_when
    if isinstance(return_type, UnionTypeRef):
        if not valid_variants:
            raise_error(
                "`resume-or-start` union returns require non-empty `:valid-when`",
                code="resume_or_start_contract_invalid",
                span=expr.span,
                form_path=expr.form_path,
            )
        declared_variants = {variant.name for variant in return_type.definition.variants}
        for variant_name in valid_variants:
            if variant_name not in declared_variants:
                raise_error(
                    f"`resume-or-start :valid-when` includes unknown variant `{variant_name}`",
                    code="resume_or_start_reusable_variant_invalid",
                    span=expr.span,
                    form_path=expr.form_path,
                )
    elif valid_variants:
        raise_error(
            "`resume-or-start :valid-when` is valid only for union return types",
            code="resume_or_start_record_valid_when_invalid",
            span=expr.span,
            form_path=expr.form_path,
        )
    validator_binding_name = "validate_reusable_phase_state"
    writer_binding_name = "write_reusable_phase_state_v1"
    loader_binding_name = f"load_canonical_phase_result__{expr.returns_type_name}"
    _require_resume_binding(
        command_boundary_environment=command_boundary_environment,
        binding_name=validator_binding_name,
        expected_output_type_name="ResumeReuseDecision",
        span=expr.span,
        form_path=expr.form_path,
    )
    _require_resume_binding(
        command_boundary_environment=command_boundary_environment,
        binding_name=writer_binding_name,
        expected_output_type_name="ReusablePhaseStateWriteAck",
        span=expr.span,
        form_path=expr.form_path,
    )
    _require_resume_binding(
        command_boundary_environment=command_boundary_environment,
        binding_name=loader_binding_name,
        expected_output_type_name=expr.returns_type_name,
        span=expr.span,
        form_path=expr.form_path,
    )
    if isinstance(expr.start_expr, CommandResultExpr) and expr.start_expr.step_name.startswith("load_canonical_phase_result__"):
        raise_error(
            "`resume-or-start` may not author loader adapter calls directly",
            code="resume_or_start_contract_invalid",
            span=expr.start_expr.span,
            form_path=expr.start_expr.form_path,
        )
    (
        structured_contract_kind,
        expected_contract_fingerprint,
        artifact_requirements,
        _,
    ) = _derive_resume_metadata(
        return_type,
        target_dsl_version="2.14",
        workflow_name="resume_or_start",
        step_id=expr.resume_name,
        reusable_variants=valid_variants,
        span=expr.span,
        form_path=expr.form_path,
    )
    public_input_hash_basis = _derive_resume_public_input_hash_basis()
    producer_fingerprint_basis = _derive_resume_producer_fingerprint_basis(
        return_type_name=expr.returns_type_name,
        structured_contract_kind=structured_contract_kind,
        expected_contract_fingerprint=expected_contract_fingerprint,
        target_dsl_version="2.14",
        reusable_variants=valid_variants,
    )
    validation_spec = ReusableStateValidationSpec(
        resume_from_expr=expr.resume_from_expr,
        return_type_ref=return_type,
        summary_schema="ReusablePhaseState.v1",
        summary_version="v1",
        sidecar_suffix=".reusable_state.json",
        structured_contract_kind=structured_contract_kind,
        expected_contract_fingerprint=expected_contract_fingerprint,
        reusable_variants=valid_variants,
        public_input_hash_basis=public_input_hash_basis,
        producer_fingerprint_basis=producer_fingerprint_basis,
        artifact_requirements=artifact_requirements,
        canonical_bundle_digest_field="canonical_bundle_sha256",
        validator_binding_name=validator_binding_name,
        writer_binding_name=writer_binding_name,
        loader_binding_name=loader_binding_name,
        source_map_behavior="step",
    )
    return typed_factory(
        expr=replace(expr, validation_spec=validation_spec),
        type_ref=return_type,
        effect=merge_effect_summaries(
            typed_ctx.effect_summary,
            typed_resume_from.effect_summary,
            typed_start.effect_summary,
            effect_summary_from_direct(
                direct_effects=(UsesCommandEffect(subject=(validator_binding_name,)),),
            ),
        ),
    )


def _require_resume_binding(
    *,
    command_boundary_environment,
    binding_name: str,
    expected_output_type_name: str,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> None:
    from .workflows import CertifiedAdapterBinding

    binding = None
    if command_boundary_environment is not None:
        binding = command_boundary_environment.bindings_by_name.get(binding_name)
    if not isinstance(binding, CertifiedAdapterBinding) or binding.output_type_name != expected_output_type_name:
        raise_error(
            f"`resume-or-start` requires certified adapter binding `{binding_name}`",
            code="resume_or_start_uncertified_backend",
            span=span,
            form_path=form_path,
        )


def _derive_resume_metadata(
    return_type: RecordTypeRef | UnionTypeRef,
    *,
    target_dsl_version: str,
    workflow_name: str,
    step_id: str,
    reusable_variants: tuple[str, ...] = (),
    span: SourceSpan,
    form_path: tuple[str, ...],
):
    from .contracts import derive_reusable_state_contract_metadata

    return derive_reusable_state_contract_metadata(
        return_type,
        target_dsl_version=target_dsl_version,
        workflow_name=workflow_name,
        step_id=step_id,
        reusable_variants=reusable_variants,
        span=span,
        form_path=form_path,
    )


def _derive_resume_public_input_hash_basis() -> tuple[str, ...]:
    from .contracts import derive_reusable_state_public_input_hash_basis

    session_state = get_session_state()
    if session_state.workflow_signature is None:
        return ()
    return derive_reusable_state_public_input_hash_basis(session_state.workflow_signature)


def _derive_resume_producer_fingerprint_basis(
    *,
    return_type_name: str,
    structured_contract_kind: str,
    expected_contract_fingerprint: str,
    target_dsl_version: str,
    reusable_variants: tuple[str, ...],
):
    from .contracts import derive_reusable_state_producer_fingerprint_basis

    session_state = get_session_state()
    if session_state.workflow_signature is None:
        return {
            "workflow_name": "<unknown>",
            "return_type_name": return_type_name,
            "structured_contract_kind": structured_contract_kind,
            "expected_contract_fingerprint": expected_contract_fingerprint,
            "target_dsl_version": target_dsl_version,
            "compiler_version": "0.1.0",
            "reusable_variants": list(reusable_variants),
            "public_input_hash_basis": [],
            "source_file_digests": {},
            "provider_extern_bindings": {},
            "prompt_extern_bindings": {},
            "prompt_extern_source_bindings": {},
            "command_boundary_bindings": {},
            "imported_workflow_fingerprints": {},
            "compile_inputs_fingerprint": "<unknown>",
        }
    return derive_reusable_state_producer_fingerprint_basis(
        signature=session_state.workflow_signature,
        return_type_name=return_type_name,
        structured_contract_kind=structured_contract_kind,
        expected_contract_fingerprint=expected_contract_fingerprint,
        target_dsl_version=target_dsl_version,
        reusable_variants=reusable_variants,
        producer_context=session_state.reusable_state_producer_context,
    )
