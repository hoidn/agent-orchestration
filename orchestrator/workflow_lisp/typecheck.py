"""Type and proof checking for Workflow Lisp expressions.

See `../../docs/design/workflow_lisp_type_catalog.md` for the type model and
`../../docs/design/workflow_lisp_proof_graph.md` for the planned variant-proof model.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
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
    BacklogDrainExpr,
    CallExpr,
    CommandResultExpr,
    ExprNode,
    FinalizeSelectedItemExpr,
    FieldAccessExpr,
    FunctionCallExpr,
    LetStarExpr,
    LiteralExpr,
    MatchExpr,
    NameExpr,
    PhaseTargetExpr,
    ProduceOneOfExpr,
    ProcedureCallExpr,
    ProviderResultExpr,
    ResourceTransitionExpr,
    RecordExpr,
    ResumeOrStartExpr,
    ReviewReviseLoopExpr,
    RunProviderPhaseExpr,
    WithPhaseExpr,
)
from .phase import (
    PhaseScope,
    PHASE_CONTEXT_NAME,
    build_phase_scope,
    IMPLEMENTATION_ATTEMPT_PHASE_CONTEXT_NAME,
    is_implementation_attempt_result_type,
    resolve_phase_target_type,
)
from .phase_stdlib import ReusableStateValidationSpec
from .resource import (
    ensure_drain_context_type,
    ensure_finalize_selected_item_inputs,
    ensure_item_context_type,
    ensure_resource_transition_resource_type,
    ensure_resource_transition_members,
)
from .lints import required_lint_diagnostic
from .spans import SourceSpan
from .type_env import (
    FrontendTypeEnvironment,
    PathTypeRef,
    PrimitiveTypeRef,
    RecordTypeRef,
    TypeRef,
    UnionTypeRef,
    VariantCaseTypeRef,
)

if TYPE_CHECKING:
    from .functions import FunctionCatalog
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
    """One expression paired with its resolved Workflow Lisp type."""

    expr: ExprNode
    type_ref: TypeRef
    span: SourceSpan
    form_path: tuple[str, ...]
    effect_summary: EffectSummary = EMPTY_EFFECT_SUMMARY


ValueEnvironment = Mapping[str, TypeRef]
_ACTIVE_FUNCTION_CATALOG = None


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
    function_catalog: "FunctionCatalog | None" = None,
    extern_environment: "ExternEnvironment | None" = None,
    command_boundary_environment: "CommandBoundaryEnvironment | None" = None,
    active_phase_scope: PhaseScope | None = None,
    procedure_effects_by_name: Mapping[str, EffectSummary] | None = None,
    workflow_effects_by_name: Mapping[str, EffectSummary] | None = None,
) -> TypedExpr:
    """Typecheck one supported Workflow Lisp expression."""

    global _ACTIVE_FUNCTION_CATALOG

    active_proof = proof_scope or ProofScope(facts={})
    previous_function_catalog = _ACTIVE_FUNCTION_CATALOG
    _ACTIVE_FUNCTION_CATALOG = function_catalog
    try:
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
    finally:
        _ACTIVE_FUNCTION_CATALOG = previous_function_catalog


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
            direct_effects=(CallsWorkflowEffect(subject=(signature.name,)),),
        )
        return _typed(
            expr=expr,
            type_ref=signature.return_type_ref,
            effect=merge_effect_summaries(
                *binding_summaries,
                call_summary,
                workflow_effects_by_name.get(signature.name, EMPTY_EFFECT_SUMMARY),
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
        callee_summary = procedure_effects_by_name.get(signature.name, EMPTY_EFFECT_SUMMARY)
        procedure_summary = effect_summary_from_direct(
            direct_effects=callee_summary.transitive_effects,
            procedure_edges=(ProcedureCallEdge(callee_name=signature.name),),
        )
        return _typed(
            expr=expr,
            type_ref=signature.return_type_ref,
            effect=merge_effect_summaries(*arg_summaries, procedure_summary),
        )
    if isinstance(expr, FunctionCallExpr):
        if _ACTIVE_FUNCTION_CATALOG is None:
            raise TypeError("function_catalog is required for FunctionCallExpr typechecking")
        signature = _ACTIVE_FUNCTION_CATALOG.signatures_by_name.get(expr.callee_name)
        if signature is None:
            _raise_error(
                f"unknown function callee `{expr.callee_name}`",
                code="function_call_unknown",
                span=expr.span,
                form_path=expr.form_path,
            )
        if len(expr.args) != len(signature.params):
            _raise_error(
                f"function `{expr.callee_name}` expected {len(signature.params)} positional arguments but got {len(expr.args)}",
                code="function_arity_mismatch",
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
                    f"function argument `{param_name}` expected `{_type_label(expected_type)}`"
                    f" but got `{_type_label(typed_arg.type_ref)}`",
                    code="type_mismatch",
                    span=arg_expr.span,
                    form_path=arg_expr.form_path,
                )
        return _typed(
            expr=expr,
            type_ref=signature.return_type_ref,
            effect=merge_effect_summaries(*arg_summaries),
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
        phase_scope = build_phase_scope(
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
    if isinstance(expr, ResourceTransitionExpr):
        resource_result = type_env.resolve_type(
            "ResourceTransitionResult",
            span=expr.span,
            form_path=expr.form_path,
        )
        if not isinstance(resource_result, RecordTypeRef):
            _raise_error(
                "`resource-transition` requires a record `ResourceTransitionResult` type",
                code="resource_transition_contract_invalid",
                span=expr.span,
                form_path=expr.form_path,
            )
        typed_ctx = _typecheck(
            expr.spec.ctx_expr,
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
        ensure_item_context_type(
            typed_ctx.type_ref,
            span=expr.spec.ctx_expr.span,
            form_path=expr.spec.ctx_expr.form_path,
        )
        typed_resource = _typecheck(
            expr.spec.resource_expr,
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
        ensure_resource_transition_resource_type(
            typed_resource.type_ref,
            span=expr.spec.resource_expr.span,
            form_path=expr.spec.resource_expr.form_path,
        )
        typed_ledger = _typecheck(
            expr.spec.ledger_expr,
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
        typed_when = None
        if expr.spec.when_expr is not None:
            typed_when = _typecheck(
                expr.spec.when_expr,
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
            if typed_when.type_ref != PrimitiveTypeRef(name="Bool"):
                _raise_error(
                    "`resource-transition :when` must resolve to `Bool`",
                    code="type_mismatch",
                    span=expr.spec.when_expr.span,
                    form_path=expr.spec.when_expr.form_path,
                )
        if not isinstance(typed_ledger.type_ref, PathTypeRef) or typed_ledger.type_ref.definition.under != "state":
            _raise_error(
                "`resource-transition :ledger` must be a relpath under `state`",
                code="resource_transition_contract_invalid",
                span=expr.spec.ledger_expr.span,
                form_path=expr.spec.ledger_expr.form_path,
            )
        transition_binding = (
            None
            if command_boundary_environment is None
            else command_boundary_environment.bindings_by_name.get("apply_resource_transition")
        )
        if transition_binding is None or getattr(transition_binding, "output_type_name", None) != "ResourceTransitionResult":
            _raise_error(
                "`resource-transition` requires the certified `apply_resource_transition` adapter",
                code="command_adapter_missing_contract",
                span=expr.span,
                form_path=expr.form_path,
            )
        ensure_resource_transition_members(
            resource_result,
            type_env=type_env,
            from_queue_name=expr.spec.from_queue_name,
            to_queue_name=expr.spec.to_queue_name,
            event_name=expr.spec.event_name,
            span=expr.span,
            form_path=expr.form_path,
        )
        return _typed(
            expr=expr,
            type_ref=resource_result,
            effect=merge_effect_summaries(
                typed_ctx.effect_summary,
                typed_resource.effect_summary,
                typed_ledger.effect_summary,
                typed_when.effect_summary if typed_when is not None else EMPTY_EFFECT_SUMMARY,
                effect_summary_from_direct(
                    direct_effects=(UsesCommandEffect(subject=("apply_resource_transition",)),),
                ),
            ),
        )
    if isinstance(expr, FinalizeSelectedItemExpr):
        selected_item_result = type_env.resolve_type(
            "SelectedItemResult",
            span=expr.span,
            form_path=expr.form_path,
        )
        if not isinstance(selected_item_result, UnionTypeRef):
            _raise_error(
                "`finalize-selected-item` requires a union `SelectedItemResult` type",
                code="finalize_selected_item_contract_invalid",
                span=expr.span,
                form_path=expr.form_path,
            )
        typed_ctx = _typecheck(
            expr.spec.ctx_expr,
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
        ensure_item_context_type(
            typed_ctx.type_ref,
            span=expr.spec.ctx_expr.span,
            form_path=expr.spec.ctx_expr.form_path,
        )
        typed_selected = _typecheck(
            expr.spec.selected_expr,
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
        typed_queue_transition = _typecheck(
            expr.spec.queue_transition_expr,
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
        expected_transition = type_env.resolve_type(
            "ResourceTransitionResult",
            span=expr.span,
            form_path=expr.form_path,
        )
        if typed_queue_transition.type_ref != expected_transition:
            _raise_error(
                "`finalize-selected-item :queue-transition` must resolve to `ResourceTransitionResult`",
                code="finalize_selected_item_contract_invalid",
                span=expr.spec.queue_transition_expr.span,
                form_path=expr.spec.queue_transition_expr.form_path,
            )
        typed_roadmap = _typecheck(
            expr.spec.roadmap_expr,
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
        typed_plan = _typecheck(
            expr.spec.plan_expr,
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
        typed_implementation = _typecheck(
            expr.spec.implementation_expr,
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
        if not isinstance(typed_plan.type_ref, UnionTypeRef) or not isinstance(typed_implementation.type_ref, UnionTypeRef):
            _raise_error(
                "`finalize-selected-item` requires union plan and implementation results",
                code="finalize_selected_item_contract_invalid",
                span=expr.span,
                form_path=expr.form_path,
            )
        ensure_finalize_selected_item_inputs(
            type_env=type_env,
            selected_type=typed_selected.type_ref,
            roadmap_type=typed_roadmap.type_ref,
            plan_type=typed_plan.type_ref,
            implementation_type=typed_implementation.type_ref,
            span=expr.span,
            form_path=expr.form_path,
        )
        return _typed(
            expr=expr,
            type_ref=selected_item_result,
            effect=merge_effect_summaries(
                typed_ctx.effect_summary,
                typed_selected.effect_summary,
                typed_queue_transition.effect_summary,
                typed_roadmap.effect_summary,
                typed_plan.effect_summary,
                typed_implementation.effect_summary,
            ),
        )
    if isinstance(expr, BacklogDrainExpr):
        drain_result = type_env.resolve_type(
            "DrainResult",
            span=expr.span,
            form_path=expr.form_path,
        )
        if not isinstance(drain_result, UnionTypeRef):
            _raise_error(
                "`backlog-drain` requires a union `DrainResult` type",
                code="workflow_ref_return_type_invalid",
                span=expr.span,
                form_path=expr.form_path,
            )
        typed_ctx = _typecheck(
            expr.spec.ctx_expr,
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
        ensure_drain_context_type(
            typed_ctx.type_ref,
            span=expr.spec.ctx_expr.span,
            form_path=expr.spec.ctx_expr.form_path,
        )
        typed_max = _typecheck(
            expr.spec.max_iterations_expr,
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
        if typed_max.type_ref != PrimitiveTypeRef(name="Int"):
            _raise_error(
                "`backlog-drain :max-iterations` must resolve to `Int`",
                code="type_mismatch",
                span=expr.spec.max_iterations_expr.span,
                form_path=expr.spec.max_iterations_expr.form_path,
            )
        if not isinstance(typed_max.expr, LiteralExpr):
            _raise_error(
                "`backlog-drain :max-iterations` must be a literal `Int` in this Stage 6 slice",
                code="backlog_drain_contract_invalid",
                span=expr.spec.max_iterations_expr.span,
                form_path=expr.spec.max_iterations_expr.form_path,
            )
        selector_signature = _workflow_ref_signature(
            workflow_catalog,
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
            workflow_catalog,
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
            workflow_catalog,
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
        typed_providers = None
        if expr.spec.providers_expr is not None:
            typed_providers = _typecheck(
                expr.spec.providers_expr,
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
        return _typed(
            expr=expr,
            type_ref=drain_result,
            effect=merge_effect_summaries(
                typed_ctx.effect_summary,
                typed_max.effect_summary,
                typed_providers.effect_summary if typed_providers is not None else EMPTY_EFFECT_SUMMARY,
            ),
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
    if isinstance(expr, RunProviderPhaseExpr):
        return_type = type_env.resolve_type(
            expr.returns_type_name,
            span=expr.span,
            form_path=expr.form_path,
        )
        if not isinstance(return_type, UnionTypeRef):
            _raise_error(
                "`run-provider-phase` requires a union `:returns` type",
                code="run_provider_phase_return_invalid",
                span=expr.span,
                form_path=expr.form_path,
            )
        typed_ctx = _typecheck(
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
        _require_normative_phase_ctx_type(
            typed_ctx.type_ref,
            span=expr.ctx_expr.span,
            form_path=expr.ctx_expr.form_path,
        )
        _require_phase_scope_name_match(
            active_phase_scope,
            authored_name=expr.phase_name,
            form_name="run-provider-phase",
            span=expr.span,
            form_path=expr.form_path,
        )
        typed_inputs = _typecheck(
            expr.inputs_expr,
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
                "`run-provider-phase` provider operand must resolve to `Provider`",
                code="provider_result_provider_invalid",
                span=expr.provider.span,
                form_path=expr.provider.form_path,
            )
        if typed_prompt.type_ref != PrimitiveTypeRef(name="Prompt"):
            _raise_error(
                "`run-provider-phase` prompt operand must resolve to `Prompt`",
                code="provider_result_prompt_invalid",
                span=expr.prompt.span,
                form_path=expr.prompt.form_path,
            )
        return _typed(
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
    if isinstance(expr, ProduceOneOfExpr):
        return_type = type_env.resolve_type(
            expr.returns_type_name,
            span=expr.span,
            form_path=expr.form_path,
        )
        if not isinstance(return_type, UnionTypeRef):
            _raise_error(
                "`produce-one-of` requires a union return type",
                code="produce_one_of_candidate_invalid",
                span=expr.span,
                form_path=expr.form_path,
            )
        typed_ctx = _typecheck(
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
        _require_normative_phase_ctx_type(
            typed_ctx.type_ref,
            span=expr.ctx_expr.span,
            form_path=expr.ctx_expr.form_path,
        )
        candidate_variants = {candidate.variant_name for candidate in expr.candidates}
        declared_variants = {variant.name for variant in return_type.definition.variants}
        if candidate_variants != declared_variants:
            _raise_error(
                "`produce-one-of` candidates must cover the declared union variants exactly",
                code="produce_one_of_candidate_invalid",
                span=expr.span,
                form_path=expr.form_path,
            )
        input_summaries: list[EffectSummary] = [typed_ctx.effect_summary]
        if expr.producer.provider_expr is None or expr.producer.prompt_expr is None:
            _raise_error(
                "`produce-one-of` currently requires a provider producer",
                code="produce_one_of_candidate_invalid",
                span=expr.span,
                form_path=expr.form_path,
            )
        typed_provider = _typecheck_expected_extern_operand(
            expr.producer.provider_expr,
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
            expr.producer.prompt_expr,
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
        input_summaries.extend((typed_provider.effect_summary, typed_prompt.effect_summary))
        for producer_input in expr.producer.inputs:
            typed_input = _typecheck(
                producer_input,
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
                    _raise_error(
                        f"`produce-one-of` field `{field_spec.field_name}` is not part of variant `{candidate.variant_name}`",
                        code="produce_one_of_candidate_invalid",
                        span=expr.span,
                        form_path=expr.form_path,
                    )
                if field_spec.target_expr is not None:
                    typed_target = _typecheck(
                        field_spec.target_expr,
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
                    if not isinstance(typed_target.type_ref, PathTypeRef):
                        _raise_error(
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
                            _raise_error(
                                f"`produce-one-of` schema `{field_spec.schema_type_name}` must be a relpath contract",
                                code="produce_one_of_candidate_invalid",
                                span=expr.span,
                                form_path=expr.form_path,
                            )
        return _typed(
            expr=expr,
            type_ref=return_type,
            effect=merge_effect_summaries(*input_summaries),
        )
    if isinstance(expr, ReviewReviseLoopExpr):
        return_type = type_env.resolve_type(
            expr.returns_type_name,
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
        typed_ctx = _typecheck(
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
        _require_normative_phase_ctx_type(
            typed_ctx.type_ref,
            span=expr.ctx_expr.span,
            form_path=expr.ctx_expr.form_path,
        )
        _require_phase_scope_name_match(
            active_phase_scope,
            authored_name=expr.loop_name,
            form_name="review-revise-loop",
            span=expr.span,
            form_path=expr.form_path,
        )
        typed_completed = _typecheck(
            expr.completed_expr,
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
        typed_inputs = _typecheck(
            expr.inputs_expr,
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
        typed_review_provider = _typecheck_expected_extern_operand(
            expr.review_provider,
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
        typed_fix_provider = _typecheck_expected_extern_operand(
            expr.fix_provider,
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
        typed_review_prompt = _typecheck_expected_extern_operand(
            expr.review_prompt,
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
        typed_fix_prompt = _typecheck_expected_extern_operand(
            expr.fix_prompt,
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
        typed_max = _typecheck(
            expr.max_expr,
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
        if typed_max.type_ref != PrimitiveTypeRef(name="Int"):
            _raise_error(
                "`review-revise-loop :max` must resolve to `Int`",
                code="type_mismatch",
                span=expr.max_expr.span,
                form_path=expr.max_expr.form_path,
            )
        _validate_review_loop_result_contract(return_type, type_env=type_env, span=expr.span, form_path=expr.form_path)
        return _typed(
            expr=expr,
            type_ref=return_type,
            effect=merge_effect_summaries(
                typed_ctx.effect_summary,
                typed_completed.effect_summary,
                typed_inputs.effect_summary,
                typed_review_provider.effect_summary,
                typed_fix_provider.effect_summary,
                typed_review_prompt.effect_summary,
                typed_fix_prompt.effect_summary,
                typed_max.effect_summary,
            ),
        )
    if isinstance(expr, ResumeOrStartExpr):
        return_type = type_env.resolve_type(
            expr.returns_type_name,
            span=expr.span,
            form_path=expr.form_path,
        )
        if not isinstance(return_type, (RecordTypeRef, UnionTypeRef)):
            _raise_error(
                "`resume-or-start :returns` must resolve to a record or union",
                code="resume_or_start_contract_invalid",
                span=expr.span,
                form_path=expr.form_path,
            )
        typed_ctx = _typecheck(
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
        typed_resume_from = _typecheck(
            expr.resume_from_expr,
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
        if not isinstance(typed_resume_from.type_ref, PathTypeRef) or typed_resume_from.type_ref.definition.under != "state":
            _raise_error(
                "`resume-or-start :resume-from` must be a canonical state relpath",
                code="resume_or_start_resume_path_invalid",
                span=expr.resume_from_expr.span,
                form_path=expr.resume_from_expr.form_path,
            )
        if isinstance(expr.start_expr, CallExpr):
            start_signature = workflow_catalog.signatures_by_name.get(expr.start_expr.callee_name) if workflow_catalog is not None else None
            if start_signature is not None and isinstance(start_signature.return_type_ref, UnionTypeRef):
                if start_signature.return_type_ref != return_type:
                    _raise_error(
                        "`resume-or-start :start` workflow call must return the declared union `:returns` type",
                        code="resume_or_start_contract_invalid",
                        span=expr.start_expr.span,
                        form_path=expr.start_expr.form_path,
                    )
        typed_start = _typecheck(
            expr.start_expr,
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
        if typed_start.type_ref != return_type:
            _raise_error(
                "`resume-or-start :start` must typecheck to the declared `:returns` type",
                code="resume_or_start_contract_invalid",
                span=expr.start_expr.span,
                form_path=expr.start_expr.form_path,
            )
        valid_variants = expr.valid_when
        if isinstance(return_type, UnionTypeRef):
            if not valid_variants:
                _raise_error(
                    "`resume-or-start` union returns require non-empty `:valid-when`",
                    code="resume_or_start_contract_invalid",
                    span=expr.span,
                    form_path=expr.form_path,
                )
            declared_variants = {variant.name for variant in return_type.definition.variants}
            for variant_name in valid_variants:
                if variant_name not in declared_variants:
                    _raise_error(
                        f"`resume-or-start :valid-when` includes unknown variant `{variant_name}`",
                        code="resume_or_start_reusable_variant_invalid",
                        span=expr.span,
                        form_path=expr.form_path,
                    )
        elif valid_variants:
            _raise_error(
                "`resume-or-start :valid-when` is valid only for union return types",
                code="resume_or_start_record_valid_when_invalid",
                span=expr.span,
                form_path=expr.form_path,
            )
        validator_binding_name = "validate_reusable_phase_state"
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
            binding_name=loader_binding_name,
            expected_output_type_name=expr.returns_type_name,
            span=expr.span,
            form_path=expr.form_path,
        )
        if isinstance(expr.start_expr, CommandResultExpr) and expr.start_expr.step_name.startswith("load_canonical_phase_result__"):
            _raise_error(
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
        validation_spec = ReusableStateValidationSpec(
            resume_from_expr=expr.resume_from_expr,
            return_type_ref=return_type,
            structured_contract_kind=structured_contract_kind,
            expected_contract_fingerprint=expected_contract_fingerprint,
            reusable_variants=valid_variants,
            artifact_requirements=artifact_requirements,
            validator_binding_name=validator_binding_name,
            loader_binding_name=loader_binding_name,
            source_map_behavior="step",
        )
        return _typed(
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
    if isinstance(expr, ProviderResultExpr):
        if _is_macro_introduced_effect(expr.span, expr.expansion_stack):
            _raise_required_lint(
                "macro expansion introduced a hidden provider effect; move the `provider-result` to authored workflow code",
                code="macro_hidden_effect",
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
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
        if _is_macro_introduced_effect(expr.span, expr.expansion_stack):
            _raise_required_lint(
                "macro expansion introduced a hidden command effect; move the `command-result` to authored workflow code",
                code="macro_hidden_effect",
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
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

        if isinstance(command_binding, CertifiedAdapterBinding):
            _validate_semantic_command_adapter_usage(expr, command_binding)
            if command_binding.output_type_name != expr.returns_type_name:
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


def _require_normative_phase_ctx_type(
    type_ref: TypeRef,
    *,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> None:
    if isinstance(type_ref, RecordTypeRef) and type_ref.name == IMPLEMENTATION_ATTEMPT_PHASE_CONTEXT_NAME:
        _raise_error(
            "generic phase stdlib forms require `PhaseCtx`; the legacy bridge is reserved for the Stage 4 implementation-attempt regression",
            code="phase_ctx_legacy_bridge_invalid",
            span=span,
            form_path=form_path,
        )
    if not isinstance(type_ref, RecordTypeRef) or type_ref.name != PHASE_CONTEXT_NAME:
        _raise_error(
            "generic phase stdlib forms require `PhaseCtx`",
            code="phase_context_invalid",
            span=span,
            form_path=form_path,
        )


def _require_phase_scope_name_match(
    active_phase_scope: PhaseScope | None,
    *,
    authored_name: str,
    form_name: str,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> None:
    if active_phase_scope is None or active_phase_scope.phase_name == authored_name:
        return
    _raise_error(
        f"`{form_name}` name `{authored_name}` must match the active `with-phase` scope `{active_phase_scope.phase_name}`",
        code="phase_scope_name_mismatch",
        span=span,
        form_path=form_path,
    )


def _validate_review_loop_result_contract(
    return_type: UnionTypeRef,
    *,
    type_env: FrontendTypeEnvironment,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> None:
    required_variants = {
        "APPROVED": {"checks_report", "review_report", "review_decision"},
        "BLOCKED": {"progress_report", "blocker_class"},
        "EXHAUSTED": {"last_review_report", "reason"},
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
        _raise_error(
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


def _validate_semantic_command_adapter_usage(
    expr: CommandResultExpr,
    binding: "CertifiedAdapterBinding",
) -> None:
    effects = set(binding.effects)
    if "resource_transition" in effects or "ledger_update" in effects:
        _raise_error(
            "resource movement must use `resource-transition` instead of a raw `command-result` adapter call",
            code="resource_move_without_transition",
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    if "resume_state_reuse" in effects:
        _raise_error(
            "reusable-state gating must use `resume-or-start` instead of a raw `command-result` adapter call",
            code="recovery_gate_without_resume_or_start",
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


def _workflow_ref_signature(
    workflow_catalog: "WorkflowCatalog | None",
    *,
    workflow_name: str,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> "WorkflowSignature":
    if workflow_catalog is None:
        raise TypeError("workflow_catalog is required for workflow ref validation")
    signature = workflow_catalog.signatures_by_name.get(workflow_name)
    if signature is None:
        _raise_required_lint(
            f"unknown workflow ref `{workflow_name}`",
            code="workflow_call_signature_erased",
            span=span,
            form_path=form_path,
        )
    return signature


def _validate_selector_workflow_ref(
    signature: "WorkflowSignature",
    *,
    type_env: FrontendTypeEnvironment,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> tuple[RecordTypeRef, RecordTypeRef]:
    if len(signature.params) != 1:
        _raise_error(
            f"workflow ref `{signature.name}` must accept exactly one `DrainCtx` parameter for `selector`",
            code="backlog_drain_contract_invalid",
            span=span,
            form_path=form_path,
        )
    ensure_drain_context_type(signature.params[0][1], span=span, form_path=form_path)
    if not isinstance(signature.return_type_ref, UnionTypeRef):
        _raise_required_lint(
            f"workflow ref `{signature.name}` must return `SelectionResult`-shaped union output",
            code="workflow_call_signature_erased",
            span=span,
            form_path=form_path,
        )
    _require_union_variant_path_field(
        signature.return_type_ref,
        "EMPTY",
        "run-state",
        expected_under="state",
        span=span,
        form_path=form_path,
    )
    gap_payload_type = _require_union_variant_record_field(
        signature.return_type_ref,
        "GAP",
        "gap",
        span=span,
        form_path=form_path,
    )
    selected_payload_type = _require_union_variant_record_field(
        signature.return_type_ref,
        "SELECTED",
        "selection",
        span=span,
        form_path=form_path,
    )
    return selected_payload_type, gap_payload_type


def _validate_run_item_workflow_ref(
    signature: "WorkflowSignature",
    *,
    type_env: FrontendTypeEnvironment,
    selected_payload_type: RecordTypeRef,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> None:
    if len(signature.params) != 2:
        _raise_error(
            f"workflow ref `{signature.name}` must accept `ItemCtx` and the selector payload for `run-item`",
            code="backlog_drain_contract_invalid",
            span=span,
            form_path=form_path,
        )
    ensure_item_context_type(signature.params[0][1], span=span, form_path=form_path)
    if signature.params[1][1] != selected_payload_type:
        _raise_required_lint(
            f"workflow ref `{signature.name}` second parameter must match the selector `SELECTED.selection` payload",
            code="workflow_call_signature_erased",
            span=span,
            form_path=form_path,
        )
    if not isinstance(signature.return_type_ref, UnionTypeRef):
        _raise_required_lint(
            f"workflow ref `{signature.name}` must return a union for `run-item`",
            code="workflow_call_signature_erased",
            span=span,
            form_path=form_path,
        )
    blocker_class = type_env.resolve_type(
        "BlockerClass",
        span=span,
        form_path=form_path,
    )
    _require_union_variant_path_field(
        signature.return_type_ref,
        "CONTINUE",
        "summary-path",
        expected_under="artifacts/work",
        span=span,
        form_path=form_path,
    )
    _require_union_variant_path_field(
        signature.return_type_ref,
        "CONTINUE",
        "run-state",
        expected_under="state",
        span=span,
        form_path=form_path,
    )
    _require_union_variant_path_field(
        signature.return_type_ref,
        "BLOCKED",
        "summary-path",
        expected_under="artifacts/work",
        span=span,
        form_path=form_path,
    )
    _require_union_variant_exact_type(
        signature.return_type_ref,
        "BLOCKED",
        "blocker-class",
        expected_type=blocker_class,
        span=span,
        form_path=form_path,
    )
    _require_union_variant_path_field(
        signature.return_type_ref,
        "BLOCKED",
        "run-state",
        expected_under="state",
        span=span,
        form_path=form_path,
    )


def _validate_gap_drafter_workflow_ref(
    signature: "WorkflowSignature",
    *,
    type_env: FrontendTypeEnvironment,
    gap_payload_type: RecordTypeRef,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> None:
    if len(signature.params) != 2:
        _raise_error(
            f"workflow ref `{signature.name}` must accept `DrainCtx` and the selector gap payload for `gap-drafter`",
            code="backlog_drain_contract_invalid",
            span=span,
            form_path=form_path,
        )
    ensure_drain_context_type(signature.params[0][1], span=span, form_path=form_path)
    if signature.params[1][1] != gap_payload_type:
        _raise_required_lint(
            f"workflow ref `{signature.name}` second parameter must match the selector `GAP.gap` payload",
            code="workflow_call_signature_erased",
            span=span,
            form_path=form_path,
        )
    if isinstance(signature.return_type_ref, RecordTypeRef):
        return
    if not isinstance(signature.return_type_ref, UnionTypeRef):
        _raise_required_lint(
            f"workflow ref `{signature.name}` must return a record or union for `gap-drafter`",
            code="workflow_call_signature_erased",
            span=span,
            form_path=form_path,
        )
    blocker_class = type_env.resolve_type(
        "BlockerClass",
        span=span,
        form_path=form_path,
    )
    _require_union_variant_path_field(
        signature.return_type_ref,
        "CONTINUE",
        "run-state",
        expected_under="state",
        span=span,
        form_path=form_path,
    )
    _require_union_variant_path_field(
        signature.return_type_ref,
        "BLOCKED",
        "progress-report-path",
        expected_under="artifacts/work",
        span=span,
        form_path=form_path,
    )
    _require_union_variant_exact_type(
        signature.return_type_ref,
        "BLOCKED",
        "blocker-class",
        expected_type=blocker_class,
        span=span,
        form_path=form_path,
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
        _raise_required_lint(
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
        _raise_required_lint(
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
        _raise_required_lint(
            (
                f"workflow ref return union `{union_type.name}` must expose `{variant_name}.{field_name}` "
                f"as `{getattr(expected_type, 'name', type(expected_type).__name__)}`"
            ),
            code="workflow_call_signature_erased",
            span=span,
            form_path=form_path,
        )
    return field_type


def _require_union_variant_record_field(
    union_type: UnionTypeRef,
    variant_name: str,
    field_name: str,
    *,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> RecordTypeRef:
    field_type = _require_union_variant_field(
        union_type,
        variant_name,
        field_name,
        span=span,
        form_path=form_path,
    )
    if not isinstance(field_type, RecordTypeRef):
        _raise_required_lint(
            f"workflow ref return union `{union_type.name}` must expose record field `{variant_name}.{field_name}`",
            code="workflow_call_signature_erased",
            span=span,
            form_path=form_path,
        )
    return field_type


def _is_macro_introduced_effect(
    span: SourceSpan,
    expansion_stack: tuple[object, ...],
) -> bool:
    for frame in expansion_stack:
        definition_span = getattr(frame, "definition_span", None)
        if _span_contains(definition_span, span):
            return True
    return False


def _span_contains(outer: SourceSpan | None, inner: SourceSpan) -> bool:
    if outer is None:
        return False
    if outer.start.path != inner.start.path or outer.end.path != inner.end.path:
        return False
    return outer.start.offset <= inner.start.offset and inner.end.offset <= outer.end.offset


def _raise_required_lint(
    message: str,
    *,
    code: str,
    span: SourceSpan,
    form_path: tuple[str, ...],
    expansion_stack: tuple[object, ...] = (),
) -> None:
    raise LispFrontendCompileError(
        (
            required_lint_diagnostic(
                code,
                message=message,
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            ),
        )
    )


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
                phase="typecheck",
            ),
        )
    )
