"""Frontend-local type and proof checking for Workflow Lisp expressions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .effects import (
    EMPTY_EFFECT_SUMMARY,
    CallsWorkflowEffect,
    EffectSummary,
    ProcedureCallEdge,
    UsesCommandEffect,
    UsesProviderEffect,
    effect_summary_from_direct,
    merge_effect_summaries,
)
from .expressions import (
    CallExpr,
    CommandResultExpr,
    ExprNode,
    FieldAccessExpr,
    LetStarExpr,
    LiteralExpr,
    MatchExpr,
    NameExpr,
    PhaseTargetExpr,
    ProcedureCallExpr,
    ProviderResultExpr,
    RecordExpr,
    WithPhaseExpr,
)
from .phase import (
    PhaseScope,
    build_implementation_attempt_phase_scope,
    is_implementation_attempt_result_type,
    resolve_phase_target_type,
)
from .spans import SourceSpan
from .type_env import (
    FrontendTypeEnvironment,
    PrimitiveTypeRef,
    RecordTypeRef,
    TypeRef,
    UnionTypeRef,
    VariantCaseTypeRef,
)

if TYPE_CHECKING:
    from .workflows import (
        CertifiedAdapterBinding,
        CommandBoundaryEnvironment,
        ExternEnvironment,
        ExternalToolBinding,
        WorkflowCatalog,
    )
    from .procedures import ProcedureCatalog


@dataclass(frozen=True)
class TypedExpr:
    """One expression paired with its resolved frontend-local type."""

    expr: ExprNode
    type_ref: TypeRef
    span: SourceSpan
    form_path: tuple[str, ...]
    effect_summary: EffectSummary = EMPTY_EFFECT_SUMMARY


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
    workflow_catalog: "WorkflowCatalog | None" = None,
    procedure_catalog: "ProcedureCatalog | None" = None,
    extern_environment: "ExternEnvironment | None" = None,
    command_boundary_environment: "CommandBoundaryEnvironment | None" = None,
    active_phase_scope: PhaseScope | None = None,
    procedure_effects_by_name: Mapping[str, EffectSummary] | None = None,
    workflow_effects_by_name: Mapping[str, EffectSummary] | None = None,
) -> TypedExpr:
    """Typecheck one bounded Stage 2 expression."""

    active_proof = proof_scope or ProofScope(facts={})
    return _typecheck(
        expr,
        type_env=type_env,
        value_env=dict(value_env),
        proof_scope=active_proof,
        workflow_catalog=workflow_catalog,
        procedure_catalog=procedure_catalog,
        extern_environment=extern_environment,
        command_boundary_environment=command_boundary_environment,
        active_phase_scope=active_phase_scope,
        procedure_effects_by_name=procedure_effects_by_name or {},
        workflow_effects_by_name=workflow_effects_by_name or {},
    )


def _typecheck(
    expr: ExprNode,
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
) -> TypedExpr:
    if isinstance(expr, LiteralExpr):
        return _typed(
            expr=expr,
            type_ref=PrimitiveTypeRef(name=_literal_type_name(expr.literal_kind)),
            effect=EMPTY_EFFECT_SUMMARY,
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
                expansion_stack=expr.expansion_stack,
            )
        return _typed(expr=expr, type_ref=type_ref, effect=EMPTY_EFFECT_SUMMARY)
    if isinstance(expr, FieldAccessExpr):
        typed_base = _typecheck(
            expr.base,
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
        )
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
        return _typed(expr=expr, type_ref=current_type, effect=typed_base.effect_summary)
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
        field_summaries: list[EffectSummary] = []
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
                workflow_catalog=workflow_catalog,
                procedure_catalog=procedure_catalog,
                extern_environment=extern_environment,
                command_boundary_environment=command_boundary_environment,
                active_phase_scope=active_phase_scope,
                procedure_effects_by_name=procedure_effects_by_name,
                workflow_effects_by_name=workflow_effects_by_name,
            )
            field_summaries.append(typed_field.effect_summary)
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
        return _typed(
            expr=expr,
            type_ref=record_type,
            effect=merge_effect_summaries(*field_summaries),
        )
    if isinstance(expr, LetStarExpr):
        local_env = dict(value_env)
        seen_names: set[str] = set()
        binding_summaries: list[EffectSummary] = []
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
                workflow_catalog=workflow_catalog,
                procedure_catalog=procedure_catalog,
                extern_environment=extern_environment,
                command_boundary_environment=command_boundary_environment,
                active_phase_scope=active_phase_scope,
                procedure_effects_by_name=procedure_effects_by_name,
                workflow_effects_by_name=workflow_effects_by_name,
            )
            binding_summaries.append(typed_binding.effect_summary)
            seen_names.add(name)
            local_env[name] = typed_binding.type_ref
        typed_body = _typecheck(
            expr.body,
            type_env=type_env,
            value_env=local_env,
            proof_scope=proof_scope,
            workflow_catalog=workflow_catalog,
            procedure_catalog=procedure_catalog,
            extern_environment=extern_environment,
            command_boundary_environment=command_boundary_environment,
            active_phase_scope=active_phase_scope,
            procedure_effects_by_name=procedure_effects_by_name,
            workflow_effects_by_name=workflow_effects_by_name,
        )
        return _typed(
            expr=expr,
            type_ref=typed_body.type_ref,
            effect=merge_effect_summaries(*binding_summaries, typed_body.effect_summary),
        )
    if isinstance(expr, MatchExpr):
        typed_subject = _typecheck(
            expr.subject,
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
        )
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
        arm_summaries: list[EffectSummary] = []
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
                workflow_catalog=workflow_catalog,
                procedure_catalog=procedure_catalog,
                extern_environment=extern_environment,
                command_boundary_environment=command_boundary_environment,
                active_phase_scope=active_phase_scope,
                procedure_effects_by_name=procedure_effects_by_name,
                workflow_effects_by_name=workflow_effects_by_name,
            )
            arm_summaries.append(typed_body.effect_summary)
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
        return _typed(
            expr=expr,
            type_ref=arm_result_type,
            effect=merge_effect_summaries(typed_subject.effect_summary, *arm_summaries),
        )
    if isinstance(expr, CallExpr):
        if workflow_catalog is None:
            raise TypeError("workflow_catalog is required for CallExpr typechecking")
        signature = workflow_catalog.signatures_by_name.get(expr.callee_name)
        if signature is None:
            _raise_error(
                f"unknown workflow callee `{expr.callee_name}`",
                code="workflow_call_unknown",
                span=expr.span,
                form_path=expr.form_path,
            )
        expected_bindings = dict(signature.params)
        seen_bindings: set[str] = set()
        binding_summaries: list[EffectSummary] = []
        for binding_name, binding_expr in expr.bindings:
            if binding_name in seen_bindings:
                _raise_error(
                    f"duplicate call binding `{binding_name}`",
                    code="workflow_signature_mismatch",
                    span=binding_expr.span,
                    form_path=binding_expr.form_path,
                )
            seen_bindings.add(binding_name)
            expected_type = expected_bindings.get(binding_name)
            if expected_type is None:
                _raise_error(
                    f"call binding `{binding_name}` does not match the callee signature",
                    code="workflow_signature_mismatch",
                    span=binding_expr.span,
                    form_path=binding_expr.form_path,
                )
            typed_binding = _typecheck(
                binding_expr,
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
            )
            binding_summaries.append(typed_binding.effect_summary)
            if typed_binding.type_ref != expected_type:
                _raise_error(
                    f"call binding `{binding_name}` expected `{_type_label(expected_type)}`"
                    f" but got `{_type_label(typed_binding.type_ref)}`",
                    code="type_mismatch",
                    span=binding_expr.span,
                    form_path=binding_expr.form_path,
                )
        missing_bindings = [name for name, _ in signature.params if name not in seen_bindings]
        if missing_bindings:
            _raise_error(
                f"call is missing required binding `{missing_bindings[0]}`",
                code="workflow_signature_mismatch",
                span=expr.span,
                form_path=expr.form_path,
            )
        call_summary = effect_summary_from_direct(
            direct_effects=(CallsWorkflowEffect(subject=(expr.callee_name,)),),
        )
        return _typed(
            expr=expr,
            type_ref=signature.return_type_ref,
            effect=merge_effect_summaries(
                *binding_summaries,
                call_summary,
                workflow_effects_by_name.get(expr.callee_name, EMPTY_EFFECT_SUMMARY),
            ),
        )
    if isinstance(expr, ProcedureCallExpr):
        if procedure_catalog is None:
            raise TypeError("procedure_catalog is required for ProcedureCallExpr typechecking")
        signature = procedure_catalog.signatures_by_name.get(expr.callee_name)
        if signature is None:
            _raise_error(
                f"unknown procedure callee `{expr.callee_name}`",
                code="procedure_call_unknown",
                span=expr.span,
                form_path=expr.form_path,
            )
        if len(expr.args) != len(signature.params):
            _raise_error(
                f"procedure `{expr.callee_name}` expected {len(signature.params)} positional arguments but got {len(expr.args)}",
                code="procedure_arity_mismatch",
                span=expr.span,
                form_path=expr.form_path,
            )
        arg_summaries: list[EffectSummary] = []
        for arg_expr, (param_name, expected_type) in zip(expr.args, signature.params, strict=True):
            typed_arg = _typecheck(
                arg_expr,
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
            )
            arg_summaries.append(typed_arg.effect_summary)
            if typed_arg.type_ref != expected_type:
                _raise_error(
                    f"procedure argument `{param_name}` expected `{_type_label(expected_type)}`"
                    f" but got `{_type_label(typed_arg.type_ref)}`",
                    code="type_mismatch",
                    span=arg_expr.span,
                    form_path=arg_expr.form_path,
                )
        callee_summary = procedure_effects_by_name.get(expr.callee_name, EMPTY_EFFECT_SUMMARY)
        procedure_summary = effect_summary_from_direct(
            direct_effects=callee_summary.transitive_effects,
            procedure_edges=(ProcedureCallEdge(callee_name=expr.callee_name),),
        )
        return _typed(
            expr=expr,
            type_ref=signature.return_type_ref,
            effect=merge_effect_summaries(*arg_summaries, procedure_summary),
        )
    if isinstance(expr, WithPhaseExpr):
        if active_phase_scope is not None:
            _raise_error(
                "nested `with-phase` scopes are not supported in this slice",
                code="phase_scope_nested_unsupported",
                span=expr.span,
                form_path=expr.form_path,
            )
        typed_context = _typecheck(
            expr.ctx_expr,
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
        )
        phase_scope = build_implementation_attempt_phase_scope(
            typed_context.type_ref,
            phase_name=expr.phase_name,
            type_env=type_env,
            span=expr.ctx_expr.span,
            form_path=expr.ctx_expr.form_path,
        )
        typed_body = _typecheck(
            expr.body,
            type_env=type_env,
            value_env=value_env,
            proof_scope=proof_scope,
            workflow_catalog=workflow_catalog,
            procedure_catalog=procedure_catalog,
            extern_environment=extern_environment,
            command_boundary_environment=command_boundary_environment,
            active_phase_scope=phase_scope,
            procedure_effects_by_name=procedure_effects_by_name,
            workflow_effects_by_name=workflow_effects_by_name,
        )
        return _typed(
            expr=expr,
            type_ref=typed_body.type_ref,
            effect=merge_effect_summaries(typed_context.effect_summary, typed_body.effect_summary),
        )
    if isinstance(expr, PhaseTargetExpr):
        if active_phase_scope is None:
            _raise_error(
                "`phase-target` is valid only inside an active `with-phase` scope",
                code="phase_target_outside_with_phase",
                span=expr.span,
                form_path=expr.form_path,
            )
        target_type = resolve_phase_target_type(
            active_phase_scope,
            expr.target_name,
            type_env=type_env,
            span=expr.span,
            form_path=expr.form_path,
        )
        return _typed(expr=expr, type_ref=target_type, effect=EMPTY_EFFECT_SUMMARY)
    if isinstance(expr, ProviderResultExpr):
        return_type = type_env.resolve_type(
            expr.returns_type_name,
            span=expr.span,
            form_path=expr.form_path,
        )
        if not isinstance(return_type, (RecordTypeRef, UnionTypeRef)):
            _raise_error(
                f"`provider-result` must return a record or union type, got `{expr.returns_type_name}`",
                code="provider_result_return_type_invalid",
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
        if active_phase_scope is not None and not is_implementation_attempt_result_type(return_type):
            _raise_error(
                "the bounded `with-phase` slice requires `provider-result` to return `ImplementationAttempt`",
                code="provider_result_return_type_invalid",
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
        typed_provider = _typecheck_expected_extern_operand(
            expr.provider,
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
        )
        typed_prompt = _typecheck_expected_extern_operand(
            expr.prompt,
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
        )
        if typed_provider.type_ref != PrimitiveTypeRef(name="Provider"):
            _raise_error(
                "`provider-result` provider operand must resolve to `Provider`",
                code="provider_result_provider_invalid",
                span=expr.provider.span,
                form_path=expr.provider.form_path,
                expansion_stack=expr.provider.expansion_stack,
            )
        if typed_prompt.type_ref != PrimitiveTypeRef(name="Prompt"):
            _raise_error(
                "`provider-result` prompt operand must resolve to `Prompt`",
                code="provider_result_prompt_invalid",
                span=expr.prompt.span,
                form_path=expr.prompt.form_path,
                expansion_stack=expr.prompt.expansion_stack,
            )
        if not isinstance(expr.provider, NameExpr) or extern_environment is None:
            _raise_error(
                "`provider-result` requires a compiler-known provider extern",
                code="provider_result_provider_invalid",
                span=expr.provider.span,
                form_path=expr.provider.form_path,
                expansion_stack=expr.provider.expansion_stack,
            )
        provider_binding = extern_environment.bindings_by_name.get(expr.provider.name)
        from .workflows import PromptExtern, ProviderExtern

        if not isinstance(provider_binding, ProviderExtern):
            _raise_error(
                f"`provider-result` provider `{expr.provider.name}` is not a declared provider extern",
                code="provider_result_provider_invalid",
                span=expr.provider.span,
                form_path=expr.provider.form_path,
                expansion_stack=expr.provider.expansion_stack,
            )
        if not isinstance(expr.prompt, NameExpr) or extern_environment is None:
            _raise_error(
                "`provider-result` requires a compiler-known prompt extern",
                code="provider_result_prompt_invalid",
                span=expr.prompt.span,
                form_path=expr.prompt.form_path,
                expansion_stack=expr.prompt.expansion_stack,
            )
        prompt_binding = extern_environment.bindings_by_name.get(expr.prompt.name)
        if not isinstance(prompt_binding, PromptExtern):
            _raise_error(
                f"`provider-result` prompt `{expr.prompt.name}` is not a declared prompt extern",
                code="provider_result_prompt_invalid",
                span=expr.prompt.span,
                form_path=expr.prompt.form_path,
                expansion_stack=expr.prompt.expansion_stack,
            )
        input_summaries: list[EffectSummary] = []
        for input_expr in expr.inputs:
            typed_input = _typecheck(
                input_expr,
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
            )
            input_summaries.append(typed_input.effect_summary)
        provider_name = expr.provider.name if isinstance(expr.provider, NameExpr) else "provider-result"
        provider_summary = effect_summary_from_direct(
            direct_effects=(
                UsesProviderEffect(subject=tuple(provider_name.split("."))),
            )
        )
        return _typed(
            expr=expr,
            type_ref=return_type,
            effect=merge_effect_summaries(
                typed_provider.effect_summary,
                typed_prompt.effect_summary,
                *input_summaries,
                provider_summary,
            ),
        )
    if isinstance(expr, CommandResultExpr):
        arg_summaries: list[EffectSummary] = []
        for arg_expr in expr.argv:
            typed_arg = _typecheck(
                arg_expr,
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
            )
            arg_summaries.append(typed_arg.effect_summary)
        command_binding = None
        if command_boundary_environment is not None:
            command_binding = command_boundary_environment.bindings_by_name.get(expr.step_name)
            if command_binding is None:
                _raise_error(
                    f"`command-result` `{expr.step_name}` is missing command boundary metadata",
                    code="command_adapter_missing_contract",
                    span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                )
            _validate_command_argv(expr, command_binding)
        else:
            _validate_command_argv(expr, None)
        return_type = type_env.resolve_type(
            expr.returns_type_name,
            span=expr.span,
            form_path=expr.form_path,
        )
        if not isinstance(return_type, (RecordTypeRef, UnionTypeRef)):
            _raise_error(
                f"`command-result` must return a record or union type, got `{expr.returns_type_name}`",
                code="command_result_return_type_invalid",
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
        from .workflows import CertifiedAdapterBinding

        if isinstance(command_binding, CertifiedAdapterBinding) and command_binding.output_type_name != expr.returns_type_name:
            _raise_error(
                f"`command-result` `{expr.step_name}` must return `{command_binding.output_type_name}`",
                code="command_result_return_type_invalid",
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
        command_summary = effect_summary_from_direct(
            direct_effects=(
                UsesCommandEffect(subject=(expr.step_name,)),
            )
        )
        return _typed(
            expr=expr,
            type_ref=return_type,
            effect=merge_effect_summaries(*arg_summaries, command_summary),
        )
    raise TypeError(f"unsupported expression node: {type(expr)!r}")


def _typed(*, expr: ExprNode, type_ref: TypeRef, effect: EffectSummary) -> TypedExpr:
    return TypedExpr(
        expr=expr,
        type_ref=type_ref,
        effect_summary=effect,
        span=expr.span,
        form_path=expr.form_path,
    )


def _typecheck_expected_extern_operand(
    expr: ExprNode,
    *,
    expected_primitive: str,
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
) -> TypedExpr:
    if isinstance(expr, NameExpr) and expr.name not in value_env:
        return _typed(
            expr=expr,
            type_ref=PrimitiveTypeRef(name=expected_primitive),
            effect=EMPTY_EFFECT_SUMMARY,
        )
    return _typecheck(
        expr,
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
    )


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


def _validate_command_argv(
    expr: CommandResultExpr,
    binding: "ExternalToolBinding | CertifiedAdapterBinding | None",
) -> None:
    argv = list(expr.argv)
    first = _literal_string(argv[0]) if argv else None
    if first:
        packed_head = first.split()
        if len(packed_head) >= 2:
            head = packed_head[0]
            flag = packed_head[1]
            if head.startswith("python") and flag in {"-c", "-"}:
                _raise_error(
                    "inline Python command glue is not allowed in `command-result`",
                    code="inline_python_command_in_workflow",
                    span=expr.span,
                    form_path=expr.form_path,
                )
            if head in {"bash", "sh"} and flag in {"-c", "-lc"}:
                _raise_error(
                    "one-string shell wrappers are not allowed in `command-result`",
                    code="command_result_argv_invalid",
                    span=expr.span,
                    form_path=expr.form_path,
                )
    if len(argv) >= 2:
        second = _literal_string(argv[1])
        if first and first.startswith("python") and second in {"-c", "-"}:
            _raise_error(
                "inline Python command glue is not allowed in `command-result`",
                code="inline_python_command_in_workflow",
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
        if first in {"bash", "sh"} and second in {"-c", "-lc"}:
            _raise_error(
                "inline shell command glue is not allowed in `command-result`",
                code="inline_shell_command_in_workflow",
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
    if not argv:
        _raise_error(
            "`command-result` requires a non-empty argv list",
            code="command_result_argv_invalid",
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    if binding is None:
        return
    stable_prefix = list(binding.stable_command)
    if len(argv) < len(stable_prefix):
        _raise_error(
            f"`command-result` `{expr.step_name}` must start with the stable command {' '.join(stable_prefix)!r}",
            code="command_result_argv_invalid",
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    for index, token in enumerate(stable_prefix):
        actual = _literal_string(argv[index])
        if actual != token:
            _raise_error(
                f"`command-result` `{expr.step_name}` must start with the stable command {' '.join(stable_prefix)!r}",
                code="command_result_argv_invalid",
                span=expr.argv[index].span,
                form_path=expr.argv[index].form_path,
                expansion_stack=expr.argv[index].expansion_stack,
            )
    if len(argv) == 1:
        only = _literal_string(argv[0])
        if only and (" " in only or ";" in only or "|" in only):
            _raise_error(
                "one-string shell wrappers are not allowed in `command-result`",
                code="command_result_argv_invalid",
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )


def _literal_string(expr: ExprNode) -> str | None:
    if isinstance(expr, LiteralExpr) and expr.literal_kind == "string" and isinstance(expr.value, str):
        return expr.value
    return None


def _variant_has_field(variant_type: VariantCaseTypeRef, field_name: str) -> bool:
    return any(field.name == field_name for field in variant_type.definition.fields)


def _union_has_any_field(union_type: UnionTypeRef, field_name: str) -> bool:
    return any(field.name == field_name for variant in union_type.definition.variants for field in variant.fields)


def _raise_error(
    message: str,
    *,
    code: str,
    span: SourceSpan,
    form_path: tuple[str, ...],
    expansion_stack: tuple[object, ...] = (),
) -> None:
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code=code,
                message=message,
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            ),
        )
    )
