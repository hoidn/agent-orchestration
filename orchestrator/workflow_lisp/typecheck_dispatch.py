"""Type and proof checking for Workflow Lisp expressions.

See `../../docs/design/workflow_lisp_type_catalog.md` for the type model and
`../../docs/design/workflow_lisp_proof_graph.md` for the planned variant-proof model.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass, replace
from typing import TYPE_CHECKING

from .conditionals import classify_condition_expr
from .definitions import RecordDef, RecordField, UnionDef, UnionVariant
from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .effects import (
    EMPTY_EFFECT_SUMMARY,
    MovesResourceEffect,
    UpdatesLedgerEffect,
    CallsWorkflowEffect,
    EffectSummary,
    ProcedureCallEdge,
    WriteEffect,
    UsesCommandEffect,
    UsesProviderEffect,
    effect_summary_from_direct,
    merge_effect_summaries,
)
from .expressions import (
    BacklogDrainExpr,
    BindProcBinding,
    BindProcExpr,
    CallExpr,
    CommandResultExpr,
    ContinueExpr,
    DoneExpr,
    EnumMemberExpr,
    ExprNode,
    FinalizeSelectedItemExpr,
    FieldAccessExpr,
    FunctionCallExpr,
    GeneratedRelpathSeedExpr,
    IfExpr,
    LetProcExpr,
    LetStarExpr,
    LiteralExpr,
    LoopStateSeedExpr,
    LoopStateUpdateExpr,
    LoopRecurExpr,
    MaterializeViewExpr,
    MatchArm,
    MatchExpr,
    NameExpr,
    PhaseTargetExpr,
    ProcRefLiteralExpr,
    ProduceOneOfExpr,
    PureOpExpr,
    ProcedureCallExpr,
    ProviderBundlePathExpr,
    ProviderResultExpr,
    RecordUpdateExpr,
    ResourceTransitionExpr,
    RecordExpr,
    ResumeOrStartExpr,
    RunProviderPhaseExpr,
    UnionVariantExpr,
    WorkflowRefLiteralExpr,
    elaborate_expression,
    WithPhaseExpr,
)
from .loops import LoopControlTypeRef, ensure_loop_projectable_type
from .loop_state import typecheck_loop_state_expr as typecheck_loop_state_expr_owner
from .procedure_refs import (
    BoundProcArg,
    ProcRefAuthoritySource,
    ProcRefResolutionContext,
    ResolvedProcRefValue,
    proc_ref_type_from_signature,
    resolve_proc_ref_value,
    resolve_proc_ref_name,
)
from .phase import (
    PhaseScope,
    PHASE_CONTEXT_NAME,
    RUN_CONTEXT_NAME,
    build_phase_scope,
    IMPLEMENTATION_ATTEMPT_PHASE_CONTEXT_NAME,
    is_implementation_attempt_result_type,
    is_record_definition_named,
    resolve_phase_target_type,
)
from .phase_stdlib import ReusableStateValidationSpec
from .parametric_constraints import SharedUnionFieldCapability
from .resource import (
    ensure_drain_context_type,
    ensure_finalize_selected_item_inputs,
    ensure_item_context_type,
    ensure_resource_transition_resource_type,
    ensure_resource_transition_members,
)
from .typecheck_calls import (
    typecheck_call_expr as _typecheck_call_expr,
    typecheck_function_call_expr as _typecheck_function_call_expr,
    typecheck_proc_ref_argument as _typecheck_proc_ref_argument,
    typecheck_workflow_ref_argument as _typecheck_workflow_ref_argument,
    validate_gap_drafter_workflow_ref as _validate_gap_drafter_workflow_ref,
    validate_run_item_workflow_ref as _validate_run_item_workflow_ref,
    validate_selector_workflow_ref as _validate_selector_workflow_ref,
    workflow_ref_signature as _workflow_ref_signature,
)
from .typecheck_context import (
    LoopTypecheckContext,
    TypecheckContext,
    TypedExpr,
    ValueEnvironment,
    get_session_state,
    raise_error as _raise_error,
    raise_required_lint as _raise_required_lint,
    restore_session_state,
    snapshot_session_state,
)
from .typecheck_effects import (
    is_macro_introduced_effect as _is_macro_introduced_effect,
    typecheck_command_result_expr as _typecheck_command_result_expr,
    typecheck_expected_extern_operand as _typecheck_expected_extern_operand,
    typecheck_provider_bundle_path_expr as _typecheck_provider_bundle_path_expr,
    typecheck_provider_result_expr as _typecheck_provider_result_expr,
    validate_command_argv as _validate_command_argv,
    validate_semantic_command_adapter_usage as _validate_semantic_command_adapter_usage,
)
from .typecheck_pure_ops import typecheck_pure_expr as _typecheck_pure_expr
from .typecheck_proofs import (
    ProofFact,
    ProofScope,
    resolve_field_access as _resolve_field_access_owner,
    typecheck_field_access_expr as _typecheck_field_access_expr,
    typecheck_match_expr as _typecheck_match_expr,
)
from .lints import required_lint_diagnostic
from .spans import SourceSpan
from .syntax import SyntaxNode
from .type_env import (
    FrontendTypeEnvironment,
    ListTypeRef,
    OptionalTypeRef,
    PathTypeRef,
    PrimitiveTypeRef,
    ProcRefTypeRef,
    RecordTypeRef,
    TypeRef,
    UnionTypeRef,
    VariantCaseTypeRef,
    WorkflowRefTypeRef,
    type_refs_compatible,
)
from .workflow_refs import (
    resolve_workflow_ref_name,
    workflow_ref_target_name,
    workflow_ref_type_from_signature,
)
from orchestrator.workflow.view_renderer import ViewRendererError, resolve_view_renderer

if TYPE_CHECKING:
    from .functions import FunctionCatalog
    from .procedures import ProcedureCatalog
    from .workflows import (
        CertifiedAdapterBinding,
        CommandBoundaryEnvironment,
        ExternEnvironment,
        ExternalToolBinding,
        WorkflowCatalog,
    )
from .procedures import (
    GeneratedLocalProcedure,
    ProcedureCatalog,
    ProcedureCallableSpecialization,
    ProcedureDef,
    ProcedureLoweringMode,
    ProcedureParam,
    ProcedureSignature,
    TypedProcedureDef,
    let_proc_generated_name,
    proc_ref_specialization_name as proc_ref_call_specialization_name,
)


def _effect_subject(value: str) -> tuple[str, ...]:
    return tuple(segment for segment in value.split(".") if segment)


def _first_transition_runtime_forbidden_type(type_ref: TypeRef) -> str | None:
    if isinstance(type_ref, WorkflowRefTypeRef):
        return "WorkflowRef"
    if isinstance(type_ref, ProcRefTypeRef):
        return "ProcRef"
    if isinstance(type_ref, PrimitiveTypeRef) and type_ref.name in {"Json", "Provider", "Prompt"}:
        return type_ref.name
    if isinstance(type_ref, OptionalTypeRef):
        return _first_transition_runtime_forbidden_type(type_ref.item_type_ref)
    if hasattr(type_ref, "item_type_ref"):
        return _first_transition_runtime_forbidden_type(type_ref.item_type_ref)
    if hasattr(type_ref, "key_type_ref") and hasattr(type_ref, "value_type_ref"):
        return _first_transition_runtime_forbidden_type(type_ref.key_type_ref) or _first_transition_runtime_forbidden_type(
            type_ref.value_type_ref
        )
    if isinstance(type_ref, RecordTypeRef):
        for field_type in type_ref.field_types.values():
            forbidden = _first_transition_runtime_forbidden_type(field_type)
            if forbidden is not None:
                return forbidden
        return None
    if isinstance(type_ref, UnionTypeRef):
        for field_types in type_ref.variant_field_types.values():
            for field_type in field_types.values():
                forbidden = _first_transition_runtime_forbidden_type(field_type)
                if forbidden is not None:
                    return forbidden
        return None
    return None


def _materialize_view_path_contracts_compatible(
    target_type: PathTypeRef,
    returns_type: PathTypeRef,
) -> bool:
    return (
        target_type.definition.kind == returns_type.definition.kind
        and target_type.definition.under == returns_type.definition.under
    )

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
    proc_ref_resolution_context: ProcRefResolutionContext | None = None,
    proc_ref_value_env: Mapping[str, ResolvedProcRefValue] | None = None,
    shared_union_field_capabilities: tuple[SharedUnionFieldCapability, ...] = (),
) -> TypedExpr:
    """Typecheck one supported Workflow Lisp expression."""

    active_proof = proof_scope or ProofScope(facts={})
    session_state = get_session_state()
    previous_session_state = snapshot_session_state()
    previous_generated_local_procedures = dict(previous_session_state.generated_local_procedures)
    session_state.function_catalog = function_catalog
    session_state.proc_ref_value_env = dict(proc_ref_value_env or {})
    session_state.value_expr_env = {}
    session_state.loop_context = []
    session_state.let_proc_rewrite_results = {}
    session_state.shared_union_field_capabilities = tuple(shared_union_field_capabilities)
    try:
        typed = _typecheck(
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
            proc_ref_resolution_context=proc_ref_resolution_context,
        )
        from .procedure_typecheck import _replace_eliminated_let_procs as _replace_eliminated_let_procs_owner

        return replace(
            typed,
            expr=_replace_eliminated_let_procs_owner(
                typed.expr,
                let_proc_rewrite_results=session_state.let_proc_rewrite_results,
            ),
        )
    finally:
        generated_local_procedures = dict(session_state.generated_local_procedures)
        restore_session_state(previous_session_state)
        session_state.generated_local_procedures = {
            **previous_generated_local_procedures,
            **generated_local_procedures,
        }


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
    proc_ref_resolution_context: ProcRefResolutionContext | None,
) -> TypedExpr:
    session_state = get_session_state()
    context = TypecheckContext(
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
        shared_union_field_capabilities=session_state.shared_union_field_capabilities,
        session_state=session_state,
    )

    def recurse(
        node: ExprNode,
        **overrides,
    ) -> TypedExpr:
        recurse_value_env = overrides.pop("value_env", value_env)
        recurse_proof_scope = overrides.pop("proof_scope", proof_scope)
        recurse_workflow_catalog = overrides.pop("workflow_catalog", workflow_catalog)
        recurse_procedure_catalog = overrides.pop("procedure_catalog", procedure_catalog)
        recurse_extern_environment = overrides.pop("extern_environment", extern_environment)
        recurse_command_boundary_environment = overrides.pop(
            "command_boundary_environment",
            command_boundary_environment,
        )
        recurse_active_phase_scope = overrides.pop("active_phase_scope", active_phase_scope)
        recurse_procedure_effects = overrides.pop(
            "procedure_effects_by_name",
            procedure_effects_by_name,
        )
        recurse_workflow_effects = overrides.pop(
            "workflow_effects_by_name",
            workflow_effects_by_name,
        )
        recurse_proc_ref_resolution_context = overrides.pop(
            "proc_ref_resolution_context",
            proc_ref_resolution_context,
        )
        recurse_proc_ref_value_env = overrides.pop("proc_ref_value_env", None)
        recurse_value_expr_env = overrides.pop("value_expr_env", None)
        if overrides:
            raise TypeError(f"unexpected recurse overrides: {sorted(overrides)}")
        previous_proc_ref_env = session_state.proc_ref_value_env
        previous_value_expr_env = session_state.value_expr_env
        if recurse_proc_ref_value_env is not None:
            session_state.proc_ref_value_env = recurse_proc_ref_value_env
        if recurse_value_expr_env is not None:
            session_state.value_expr_env = recurse_value_expr_env
        try:
            return _typecheck(
                node,
                type_env=type_env,
                value_env=dict(recurse_value_env),
                proof_scope=recurse_proof_scope,
                workflow_catalog=recurse_workflow_catalog,
                procedure_catalog=recurse_procedure_catalog,
                extern_environment=recurse_extern_environment,
                command_boundary_environment=recurse_command_boundary_environment,
                active_phase_scope=recurse_active_phase_scope,
                procedure_effects_by_name=recurse_procedure_effects,
                workflow_effects_by_name=recurse_workflow_effects,
                proc_ref_resolution_context=recurse_proc_ref_resolution_context,
            )
        finally:
            session_state.proc_ref_value_env = previous_proc_ref_env
            session_state.value_expr_env = previous_value_expr_env

    if isinstance(expr, LiteralExpr):
        return _typed(
            expr=expr,
            type_ref=PrimitiveTypeRef(name=_literal_type_name(expr.literal_kind)),
            effect=EMPTY_EFFECT_SUMMARY,
        )
    if isinstance(expr, GeneratedRelpathSeedExpr):
        seed_type = expr.target_type_ref
        if isinstance(seed_type, str):
            seed_type = type_env.resolve_type(
                seed_type,
                span=expr.span,
                form_path=expr.form_path,
            )
            expr = GeneratedRelpathSeedExpr(
                target_type_ref=seed_type,
                literal_path=expr.literal_path,
                seed_role=expr.seed_role,
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
        if not isinstance(seed_type, PathTypeRef) or seed_type.definition.kind != "relpath":
            _raise_error(
                f"generated relpath seed `{expr.seed_role}` requires a relpath type, got `{_type_label(seed_type)}`",
                code="type_mismatch",
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
        return _typed(expr=expr, type_ref=seed_type, effect=EMPTY_EFFECT_SUMMARY)
    if isinstance(expr, EnumMemberExpr):
        try:
            enum_type = type_env.resolve_type(
                expr.enum_name,
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
        except LispFrontendCompileError as exc:
            if exc.diagnostics and exc.diagnostics[0].code == "type_unknown":
                _raise_error(
                    f"unknown name `{expr.enum_name}.{expr.member_name}`",
                    code="name_unknown",
                    span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                )
            raise
        if not isinstance(enum_type, PrimitiveTypeRef) or not enum_type.allowed_values:
            _raise_error(
                f"unknown name `{expr.enum_name}.{expr.member_name}`",
                code="name_unknown",
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
        if expr.member_name not in enum_type.allowed_values:
            _raise_error(
                f"unknown enum member `{expr.member_name}` for `{expr.enum_name}`",
                code="enum_member_unknown",
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
        return _typed(expr=expr, type_ref=enum_type, effect=EMPTY_EFFECT_SUMMARY)
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
    if isinstance(expr, WorkflowRefLiteralExpr):
        if workflow_catalog is None:
            raise TypeError("workflow_catalog is required for workflow-ref literals")
        resolved_ref = resolve_workflow_ref_name(
            expr.target_name,
            workflow_catalog=workflow_catalog,
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
            allow_extern_rebinding=True,
        )
        return _typed(
            expr=expr,
            type_ref=workflow_ref_type_from_signature(
                type(
                    "WorkflowRefSignature",
                    (),
                    {
                        "params": resolved_ref.signature_params,
                        "return_type_ref": resolved_ref.return_type_ref,
                    },
                )()
            ),
            effect=EMPTY_EFFECT_SUMMARY,
        )
    if isinstance(expr, ProcRefLiteralExpr):
        if procedure_catalog is None:
            raise TypeError("procedure_catalog is required for proc-ref literals")
        resolved_ref = resolve_proc_ref_name(
            expr.target_name,
            procedure_catalog=procedure_catalog,
            span=expr.span,
            form_path=expr.form_path,
            authored_name=expr.authored_name,
            expansion_stack=expr.expansion_stack,
            resolution_context=proc_ref_resolution_context,
        )
        return _typed(
            expr=expr,
            type_ref=proc_ref_type_from_signature(
                type(
                    "ProcRefSignature",
                    (),
                    {
                        "params": resolved_ref.signature_params,
                        "return_type_ref": resolved_ref.return_type_ref,
                        "name": resolved_ref.procedure_name,
                    },
                )()
            ),
            effect=EMPTY_EFFECT_SUMMARY,
        )
    if isinstance(expr, BindProcExpr):
        if procedure_catalog is None:
            raise TypeError("procedure_catalog is required for bind-proc expressions")
        base_typed = recurse(expr.base_expr)
        if not isinstance(base_typed.type_ref, ProcRefTypeRef):
            _raise_error(
                "`bind-proc` requires a proc-ref value",
                code="proc_ref_literal_required",
                span=expr.base_expr.span,
                form_path=expr.base_expr.form_path,
                expansion_stack=expr.base_expr.expansion_stack,
            )
        base_value = resolve_proc_ref_value(
            expr.base_expr,
            procedure_catalog=procedure_catalog,
            proc_ref_env=session_state.proc_ref_value_env,
            resolution_context=proc_ref_resolution_context,
        )
        if base_value is None:
            _raise_error(
                "`bind-proc` requires a proc-ref value",
                code="proc_ref_literal_required",
                span=expr.base_expr.span,
                form_path=expr.base_expr.form_path,
                expansion_stack=expr.base_expr.expansion_stack,
            )
        expected_bindings = dict(base_value.signature_params)
        seen_bindings: set[str] = {binding.name for binding in base_value.bound_args}
        for binding in expr.bindings:
            expected_type = expected_bindings.get(binding.name)
            if expected_type is None:
                _raise_error(
                    f"unknown `bind-proc` keyword `:{binding.name}`",
                    code="proc_ref_binding_unknown",
                    span=binding.keyword_span,
                    form_path=binding.keyword_form_path,
                    expansion_stack=binding.keyword_expansion_stack,
                )
            if binding.name in seen_bindings:
                _raise_error(
                    f"duplicate `bind-proc` keyword `:{binding.name}`",
                    code="proc_ref_binding_duplicate",
                    span=binding.keyword_span,
                    form_path=binding.keyword_form_path,
                    expansion_stack=binding.keyword_expansion_stack,
                )
            seen_bindings.add(binding.name)
            typed_binding = recurse(binding.value_expr)
            if typed_binding.type_ref != expected_type:
                _raise_error(
                    f"`bind-proc` argument `:{binding.name}` expected `{_type_label(expected_type)}`"
                    f" but got `{_type_label(typed_binding.type_ref)}`",
                    code="proc_ref_binding_type_invalid",
                    span=binding.value_expr.span,
                    form_path=binding.value_expr.form_path,
                    expansion_stack=binding.value_expr.expansion_stack,
                )
        resolved = resolve_proc_ref_value(
            expr,
            procedure_catalog=procedure_catalog,
            proc_ref_env=session_state.proc_ref_value_env,
            resolution_context=proc_ref_resolution_context,
        )
        assert resolved is not None
        return _typed(
            expr=expr,
            type_ref=resolved.residual_type_ref,
            effect=EMPTY_EFFECT_SUMMARY,
        )
    if isinstance(expr, (PureOpExpr, RecordUpdateExpr)):
        return _typecheck_pure_expr(
            expr,
            context=context,
            recurse=recurse,
            typed_factory=_typed,
        )
    if type(expr) is FieldAccessExpr:
        typed_base = recurse(expr.base)
        if isinstance(typed_base.type_ref, OptionalTypeRef):
            _raise_error(
                f"field `{expr.fields[0]}` requires `some?` or `or-else` before optional access",
                code="pure_expr_optional_access_unproved",
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
        return _typecheck_field_access_expr(
            expr,
            context=context,
            recurse=recurse,
            typed_factory=_typed,
        )
    if isinstance(expr, (LoopStateSeedExpr, LoopStateUpdateExpr)):
        return typecheck_loop_state_expr_owner(
            expr,
            context=context,
            recurse=recurse,
            typed_factory=_typed,
            raise_error=_raise_error,
            type_label=_type_label,
        )
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
        rewritten_fields: list[tuple[str, ExprNode]] = []
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
                proc_ref_resolution_context=proc_ref_resolution_context,
            )
            if typed_field.effect_summary != EMPTY_EFFECT_SUMMARY:
                _raise_error(
                    "record field expressions must be pure; bind effectful work in `let*` first",
                    code="effect_not_permitted",
                    span=field_expr.span,
                    form_path=field_expr.form_path,
                )
            field_summaries.append(typed_field.effect_summary)
            rewritten_fields.append((field_name, typed_field.expr))
            expected_type = record_type.field_types.get(field_name)
            if expected_type is None:
                expected_type = type_env.resolve_type(
                    expected_field.type_name,
                    span=field_expr.span,
                    form_path=field_expr.form_path,
                )
            if not _type_refs_compatible(expected_type, typed_field.type_ref):
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
            expr=replace(expr, fields=tuple(rewritten_fields)),
            type_ref=record_type,
            effect=merge_effect_summaries(*field_summaries),
        )
    if isinstance(expr, UnionVariantExpr):
        union_type = type_env.resolve_type(expr.type_name, span=expr.span, form_path=expr.form_path)
        if not isinstance(union_type, UnionTypeRef):
            _raise_error(
                f"`{expr.type_name}` is not a union type",
                code="type_mismatch",
                span=expr.span,
                form_path=expr.form_path,
            )
        variant_type = type_env.union_variant(
            union_type,
            expr.variant_name,
            span=expr.span,
            form_path=expr.form_path,
        )
        expected_fields = {field.name: field for field in variant_type.definition.fields}
        seen_fields: set[str] = set()
        field_summaries: list[EffectSummary] = []
        rewritten_fields: list[tuple[str, ExprNode]] = []
        for field_name, field_expr in expr.fields:
            if field_name in seen_fields:
                _raise_error(
                    f"duplicate field `{field_name}` in union variant expression",
                    code="record_field_duplicate",
                    span=field_expr.span,
                    form_path=field_expr.form_path,
                )
            seen_fields.add(field_name)
            expected_field = expected_fields.get(field_name)
            if expected_field is None:
                _raise_error(
                    f"unknown field `{field_name}` for variant `{expr.variant_name}` in union `{union_type.name}`",
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
                proc_ref_resolution_context=proc_ref_resolution_context,
            )
            if typed_field.effect_summary != EMPTY_EFFECT_SUMMARY:
                _raise_error(
                    "union variant field expressions must be pure; bind effectful work in `let*` first",
                    code="effect_not_permitted",
                    span=field_expr.span,
                    form_path=field_expr.form_path,
                )
            field_summaries.append(typed_field.effect_summary)
            rewritten_fields.append((field_name, typed_field.expr))
            expected_type = union_type.variant_field_types.get(expr.variant_name, {}).get(field_name)
            if expected_type is None:
                expected_type = type_env.resolve_type(
                    expected_field.type_name,
                    span=field_expr.span,
                    form_path=field_expr.form_path,
                )
            if not _type_refs_compatible(expected_type, typed_field.type_ref):
                _raise_error(
                    f"union field `{field_name}` expected `{_type_label(expected_type)}`"
                    f" but got `{_type_label(typed_field.type_ref)}`",
                    code="type_mismatch",
                    span=field_expr.span,
                    form_path=field_expr.form_path,
                )
        missing_fields = [field.name for field in variant_type.definition.fields if field.name not in seen_fields]
        if missing_fields:
            _raise_error(
                f"missing required field `{missing_fields[0]}` for variant `{expr.variant_name}` in union `{union_type.name}`",
                code="record_field_missing",
                span=expr.span,
                form_path=expr.form_path,
            )
        return _typed(
            expr=replace(expr, fields=tuple(rewritten_fields)),
            type_ref=union_type,
            effect=merge_effect_summaries(*field_summaries),
        )
    if isinstance(expr, ContinueExpr):
        if not session_state.loop_context:
            _raise_error(
                "`continue` is valid only inside `loop/recur`",
                code="loop_recur_continue_outside_loop",
                span=expr.span,
                form_path=expr.form_path,
            )
        loop_context = session_state.loop_context[-1]
        typed_state = recurse(expr.state_expr)
        if typed_state.type_ref != loop_context.state_type_ref:
            _raise_error(
                f"`continue` expected `{_type_label(loop_context.state_type_ref)}` but got `{_type_label(typed_state.type_ref)}`",
                code="loop_recur_continue_type_mismatch",
                span=expr.state_expr.span,
                form_path=expr.state_expr.form_path,
            )
        return _typed(
            expr=expr,
            type_ref=LoopControlTypeRef(
                state_type_ref=loop_context.state_type_ref,
                result_type_ref=loop_context.result_type_ref,
            ),
            effect=typed_state.effect_summary,
        )
    if isinstance(expr, DoneExpr):
        if not session_state.loop_context:
            _raise_error(
                "`done` is valid only inside `loop/recur`",
                code="loop_recur_done_outside_loop",
                span=expr.span,
                form_path=expr.form_path,
            )
        loop_context = session_state.loop_context[-1]
        typed_result = recurse(expr.result_expr)
        if loop_context.result_type_ref is not None and typed_result.type_ref != loop_context.result_type_ref:
            _raise_error(
                f"`done` expected `{_type_label(loop_context.result_type_ref)}` but got `{_type_label(typed_result.type_ref)}`",
                code="loop_recur_done_type_mismatch",
                span=expr.result_expr.span,
                form_path=expr.result_expr.form_path,
            )
        return _typed(
            expr=expr,
            type_ref=LoopControlTypeRef(
                state_type_ref=loop_context.state_type_ref,
                result_type_ref=typed_result.type_ref,
            ),
            effect=typed_result.effect_summary,
        )
    if isinstance(expr, LetStarExpr):
        local_env = dict(value_env)
        local_proc_ref_env = dict(session_state.proc_ref_value_env)
        local_value_expr_env = dict(session_state.value_expr_env)
        seen_names: set[str] = set()
        binding_summaries: list[EffectSummary] = []
        rewritten_bindings: list[tuple[str, ExprNode]] = []
        for name, binding_expr in expr.bindings:
            if name in seen_names:
                _raise_error(
                    f"duplicate let* binding `{name}`",
                    code="binding_duplicate",
                    span=binding_expr.span,
                    form_path=binding_expr.form_path,
                )
            typed_binding = recurse(
                binding_expr,
                value_env=local_env,
                proc_ref_value_env=local_proc_ref_env,
                value_expr_env=local_value_expr_env,
            )
            binding_summaries.append(typed_binding.effect_summary)
            seen_names.add(name)
            local_env[name] = typed_binding.type_ref
            local_value_expr_env[name] = typed_binding.expr
            rewritten_bindings.append((name, typed_binding.expr))
            if isinstance(typed_binding.type_ref, ProcRefTypeRef):
                resolved_binding = resolve_proc_ref_value(
                    binding_expr,
                    procedure_catalog=procedure_catalog,
                    proc_ref_env=local_proc_ref_env,
                    resolution_context=proc_ref_resolution_context,
                )
                if resolved_binding is not None:
                    local_proc_ref_env[name] = resolved_binding
        typed_body = recurse(
            expr.body,
            value_env=local_env,
            proc_ref_value_env=local_proc_ref_env,
            value_expr_env=local_value_expr_env,
        )
        rewritten_expr = LetStarExpr(
            bindings=tuple(rewritten_bindings),
            body=typed_body.expr,
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
        return _typed(
            expr=rewritten_expr,
            type_ref=typed_body.type_ref,
            effect=merge_effect_summaries(*binding_summaries, typed_body.effect_summary),
        )
    if type(expr) is LetProcExpr:
        from .procedure_typecheck import typecheck_let_proc_expr

        return typecheck_let_proc_expr(
            expr,
            context=context,
            recurse=recurse,
            typed_factory=_typed,
            raise_error=_raise_error,
            type_label=_type_label,
        )
    if isinstance(expr, IfExpr):
        typed_condition = _typecheck(
            expr.condition_expr,
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
        if typed_condition.type_ref != PrimitiveTypeRef(name="Bool"):
            _raise_error(
                "`if` condition must resolve to exact `Bool`",
                code="if_condition_not_bool",
                span=expr.condition_expr.span,
                form_path=expr.condition_expr.form_path,
            )
        if typed_condition.effect_summary != EMPTY_EFFECT_SUMMARY:
            _raise_error(
                "`if` condition must be pure",
                code="if_condition_has_effect",
                span=expr.condition_expr.span,
                form_path=expr.condition_expr.form_path,
            )
        classify_condition_expr(
            typed_condition.expr,
            type_ref=typed_condition.type_ref,
        )
        typed_then = _typecheck(
            expr.then_expr,
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
        typed_else = _typecheck(
            expr.else_expr,
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
        result_type = _unify_loop_control_types(typed_then.type_ref, typed_else.type_ref)
        if result_type is None:
            if isinstance(typed_then.type_ref, LoopControlTypeRef) and isinstance(
                typed_else.type_ref,
                LoopControlTypeRef,
            ):
                _raise_error(
                    f"`done` expected `{_type_label(typed_then.type_ref.result_type_ref)}` but got `{_type_label(typed_else.type_ref.result_type_ref)}`",
                    code="loop_recur_done_type_mismatch",
                    span=expr.else_expr.span,
                    form_path=expr.else_expr.form_path,
                )
            if typed_then.type_ref != typed_else.type_ref:
                _raise_error(
                    f"`if` branches must return the same type; got `{_type_label(typed_then.type_ref)}` and `{_type_label(typed_else.type_ref)}`",
                    code="type_mismatch",
                    span=expr.span,
                    form_path=expr.form_path,
                )
            result_type = typed_then.type_ref
        return _typed(
            expr=expr,
            type_ref=result_type,
            effect=merge_effect_summaries(
                typed_then.effect_summary,
                typed_else.effect_summary,
            ),
        )
    if type(expr) is MatchExpr:
        return _typecheck_match_expr(
            expr,
            context=context,
            recurse=recurse,
            typed_factory=_typed,
        )
    if isinstance(expr, LoopRecurExpr):
        typed_max = recurse(expr.max_iterations_expr)
        if typed_max.type_ref != PrimitiveTypeRef(name="Int"):
            _raise_error(
                "`loop/recur :max` must resolve to `Int`",
                code="loop_recur_max_invalid",
                span=expr.max_iterations_expr.span,
                form_path=expr.max_iterations_expr.form_path,
            )
        typed_state = recurse(expr.initial_state_expr)
        ensure_loop_projectable_type(
            typed_state.type_ref,
            code="loop_recur_state_type_invalid",
            span=expr.initial_state_expr.span,
            form_path=expr.initial_state_expr.form_path,
        )
        session_state.loop_context.append(LoopTypecheckContext(state_type_ref=typed_state.type_ref))
        try:
            typed_body = recurse(
                expr.body_expr,
                value_env={**value_env, expr.binding_name: typed_state.type_ref},
                proof_scope=ProofScope(facts={}),
            )
        finally:
            loop_context = session_state.loop_context.pop()
        if not isinstance(typed_body.type_ref, LoopControlTypeRef):
            _raise_error(
                "`loop/recur` body must terminate with `continue` or `done`",
                code="loop_recur_missing_done",
                span=expr.body_expr.span,
                form_path=expr.body_expr.form_path,
            )
        if typed_body.type_ref.result_type_ref is None:
            _raise_error(
                "`loop/recur` body must contain at least one reachable `done`",
                code="loop_recur_missing_done",
                span=expr.body_expr.span,
                form_path=expr.body_expr.form_path,
            )
        ensure_loop_projectable_type(
            typed_body.type_ref.result_type_ref,
            code="loop_recur_result_type_invalid",
            span=expr.body_expr.span,
            form_path=expr.body_expr.form_path,
        )
        exhaustion_summaries: list[EffectSummary] = []
        if expr.on_exhausted_result_expr is not None:
            typed_exhausted = _typecheck(
                expr.on_exhausted_result_expr,
                type_env=type_env,
                value_env={**value_env, expr.binding_name: typed_state.type_ref},
                proof_scope=ProofScope(facts={}),
                workflow_catalog=workflow_catalog,
                procedure_catalog=procedure_catalog,
                extern_environment=extern_environment,
                command_boundary_environment=command_boundary_environment,
                active_phase_scope=active_phase_scope,
                procedure_effects_by_name=procedure_effects_by_name,
                workflow_effects_by_name=workflow_effects_by_name,
                proc_ref_resolution_context=proc_ref_resolution_context,
            )
            if typed_exhausted.type_ref != typed_body.type_ref.result_type_ref:
                _raise_error(
                    f"`loop/recur` exhaustion result expected `{_type_label(typed_body.type_ref.result_type_ref)}`"
                    f" but got `{_type_label(typed_exhausted.type_ref)}`",
                    code="loop_recur_done_type_mismatch",
                    span=expr.on_exhausted_result_expr.span,
                    form_path=expr.on_exhausted_result_expr.form_path,
                )
            if typed_exhausted.effect_summary != EMPTY_EFFECT_SUMMARY:
                _raise_error(
                    "`loop/recur` exhaustion projection must be pure",
                    code="loop_recur_contract_invalid",
                    span=expr.on_exhausted_result_expr.span,
                    form_path=expr.on_exhausted_result_expr.form_path,
                )
            exhaustion_summaries.append(typed_exhausted.effect_summary)
        return _typed(
            expr=expr,
            type_ref=typed_body.type_ref.result_type_ref,
            effect=merge_effect_summaries(
                typed_max.effect_summary,
                typed_state.effect_summary,
                typed_body.effect_summary,
                *exhaustion_summaries,
            ),
        )
    if type(expr) is CallExpr:
        return _typecheck_call_expr(
            expr,
            context=context,
            recurse=recurse,
            typed_factory=_typed,
        )
    if isinstance(expr, ProcedureCallExpr):
        from .procedure_typecheck import ProcedureTypecheckContext, typecheck_procedure_call_expr

        return typecheck_procedure_call_expr(
            expr,
            context=ProcedureTypecheckContext(
                type_env=type_env,
                value_env=value_env,
                workflow_catalog=workflow_catalog,
                procedure_catalog=procedure_catalog,
                extern_environment=extern_environment,
                command_boundary_environment=command_boundary_environment,
                procedure_effects_by_name=procedure_effects_by_name,
                workflow_effects_by_name=workflow_effects_by_name,
                proc_ref_resolution_context=proc_ref_resolution_context,
                active_proc_ref_value_env=session_state.proc_ref_value_env,
                generated_local_procedure_state=session_state.let_proc_rewrite_results,
                session_state=session_state,
            ),
            recurse=recurse,
            typecheck_workflow_ref_argument=lambda arg_expr, expected_type: _typecheck_workflow_ref_argument(
                arg_expr,
                expected_type=expected_type,
                value_env=dict(value_env),
                workflow_catalog=workflow_catalog,
                typed_factory=_typed,
            ),
            typecheck_proc_ref_argument=lambda arg_expr, expected_type: _typecheck_proc_ref_argument(
                arg_expr,
                expected_type=expected_type,
                value_env=dict(value_env),
                procedure_catalog=procedure_catalog,
                proc_ref_resolution_context=proc_ref_resolution_context,
                active_proc_ref_value_env=session_state.proc_ref_value_env,
                typed_factory=_typed,
            ),
            typed_factory=_typed,
            raise_error=_raise_error,
            type_label=_type_label,
        )
    if type(expr) is FunctionCallExpr:
        return _typecheck_function_call_expr(
            expr,
            context=context,
            recurse=recurse,
            typed_factory=_typed,
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
            proc_ref_resolution_context=proc_ref_resolution_context,
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
            proc_ref_resolution_context=proc_ref_resolution_context,
        )
        return _typed(
            expr=WithPhaseExpr(
                ctx_expr=typed_context.expr,
                phase_name=expr.phase_name,
                body=typed_body.expr,
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            ),
            type_ref=typed_body.type_ref,
            effect=merge_effect_summaries(typed_context.effect_summary, typed_body.effect_summary),
        )
    if isinstance(expr, ResourceTransitionExpr):
        if expr.spec.mode == "declared_transition":
            transition_def = type_env.resolve_transition_declaration(
                expr.spec.transition_ref_name or "",
                code="transition_unknown",
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
            resource_def = type_env.resolve_resource_declaration(
                expr.spec.resource_ref_name or "",
                code="transition_resource_unknown",
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
            declared_resource = type_env.resolve_resource_declaration(
                transition_def.resource_name,
                code="transition_declaration_invalid",
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
            if declared_resource != resource_def:
                _raise_error(
                    "declared transition resource does not match `resource-transition :resource`",
                    code="transition_resource_kind_mismatch",
                    span=expr.span,
                    form_path=expr.form_path,
                )
            resource_state_type = type_env.resolve_type(
                resource_def.state_type_name,
                span=resource_def.span,
                form_path=resource_def.form_path,
            )
            if not isinstance(resource_state_type, RecordTypeRef):
                _raise_error(
                    "declared transition resources require record state types",
                    code="transition_declaration_invalid",
                    span=resource_def.span,
                    form_path=resource_def.form_path,
                )
            forbidden = _first_transition_runtime_forbidden_type(resource_state_type)
            if forbidden is not None:
                _raise_error(
                    f"declared transition resource state cannot carry runtime-forbidden type `{forbidden}`",
                    code="transition_declaration_invalid",
                    span=resource_def.span,
                    form_path=resource_def.form_path,
                )
            request_type = type_env.resolve_type(
                transition_def.request_type_name,
                span=transition_def.span,
                form_path=transition_def.form_path,
            )
            forbidden = _first_transition_runtime_forbidden_type(request_type)
            if forbidden is not None:
                _raise_error(
                    f"declared transition request type cannot carry runtime-forbidden type `{forbidden}`",
                    code="transition_declaration_invalid",
                    span=transition_def.span,
                    form_path=transition_def.form_path,
                )
            result_type = type_env.resolve_type(
                transition_def.result_type_name,
                span=transition_def.span,
                form_path=transition_def.form_path,
            )
            typed_request = _typecheck(
                expr.spec.request_expr,
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
            if typed_request.type_ref != request_type:
                _raise_error(
                    f"`resource-transition :request` expected `{_type_label(request_type)}` but got `{_type_label(typed_request.type_ref)}`",
                    code="transition_request_type_mismatch",
                    span=expr.spec.request_expr.span,
                    form_path=expr.spec.request_expr.form_path,
                )
            typed_expected_version = None
            if expr.spec.expected_version_expr is not None:
                typed_expected_version = _typecheck(
                    expr.spec.expected_version_expr,
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
                if typed_expected_version.type_ref != PrimitiveTypeRef(name="String"):
                    _raise_error(
                        "`resource-transition :expect-version` must resolve to `String`",
                        code="transition_declaration_invalid",
                        span=expr.spec.expected_version_expr.span,
                        form_path=expr.spec.expected_version_expr.form_path,
                    )
            transition_value_env = {
                "state": resource_state_type,
                "request": request_type,
            }
            for precondition_expr in transition_def.preconditions:
                typed_precondition = _typecheck(
                    precondition_expr,
                    type_env=type_env,
                    value_env=transition_value_env,
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
                if typed_precondition.type_ref != PrimitiveTypeRef(name="Bool"):
                    _raise_error(
                        "declared transition preconditions must resolve to `Bool`",
                        code="transition_declaration_invalid",
                        span=precondition_expr.span,
                        form_path=precondition_expr.form_path,
                    )
            for update in transition_def.updates:
                target_type = resource_state_type.field_types.get(update.target)
                if target_type is None:
                    _raise_error(
                        f"unknown transition update target `{update.target}`",
                        code="transition_update_target_unknown",
                        span=update.span,
                        form_path=update.form_path,
                    )
                if update.op == "clear_field":
                    if not isinstance(target_type, OptionalTypeRef):
                        _raise_error(
                            f"`clear-field {update.target}` requires an `Optional` state field",
                            code="transition_declaration_invalid",
                            span=update.span,
                            form_path=update.form_path,
                        )
                    continue
                assert update.value_expr is not None
                typed_value = _typecheck(
                    update.value_expr,
                    type_env=type_env,
                    value_env=transition_value_env,
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
                expected_type = target_type.item_type_ref if update.op == "append_item" and isinstance(target_type, ListTypeRef) else target_type
                if typed_value.type_ref != expected_type:
                    _raise_error(
                        f"transition update `{update.target}` expected `{_type_label(expected_type)}` but got `{_type_label(typed_value.type_ref)}`",
                        code="transition_declaration_invalid",
                        span=update.value_expr.span,
                        form_path=update.value_expr.form_path,
                    )
            typed_result_expr = _typecheck(
                transition_def.result_expr,
                type_env=type_env,
                value_env=transition_value_env,
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
            if typed_result_expr.type_ref != result_type:
                _raise_error(
                    f"declared transition result projection expected `{_type_label(result_type)}` but got `{_type_label(typed_result_expr.type_ref)}`",
                    code="transition_result_projection_type_mismatch",
                    span=transition_def.span,
                    form_path=transition_def.form_path,
                )
            _typecheck(
                transition_def.audit_expr,
                type_env=type_env,
                value_env=transition_value_env,
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
            return _typed(
                expr=expr,
                type_ref=result_type,
                effect=merge_effect_summaries(
                    typed_request.effect_summary,
                    typed_expected_version.effect_summary if typed_expected_version is not None else EMPTY_EFFECT_SUMMARY,
                    effect_summary_from_direct(
                        direct_effects=(
                            UsesCommandEffect(subject=("apply_resource_transition",)),
                        ),
                    ),
                ),
            )
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
            proc_ref_resolution_context=proc_ref_resolution_context,
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
            proc_ref_resolution_context=proc_ref_resolution_context,
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
            proc_ref_resolution_context=proc_ref_resolution_context,
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
            proc_ref_resolution_context=proc_ref_resolution_context,
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
        if (
            transition_binding is None
            or getattr(transition_binding, "output_type_name", None) != "ResourceTransitionResult"
            or getattr(transition_binding, "effects", ()) != ("resource_transition", "ledger_update")
        ):
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
                    direct_effects=(
                        UsesCommandEffect(subject=("apply_resource_transition",)),
                        MovesResourceEffect(
                            subject=_effect_subject(expr.spec.transition_name),
                            from_queue=_effect_subject(expr.spec.from_queue_name),
                            to_queue=_effect_subject(expr.spec.to_queue_name),
                        ),
                        UpdatesLedgerEffect(
                            subject=_effect_subject(expr.spec.transition_name),
                            event_name=_effect_subject(expr.spec.event_name),
                        ),
                    ),
                ),
            ),
        )
    if isinstance(expr, MaterializeViewExpr):
        typed_value = _typecheck(
            expr.value_expr,
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
        returns_type = type_env.resolve_type(
            expr.returns_type_name,
            span=expr.span,
            form_path=expr.form_path,
        )
        if not isinstance(returns_type, PathTypeRef):
            _raise_error(
                "`materialize-view :returns` must resolve to a path type",
                code="materialize_view_target_contract_invalid",
                span=expr.span,
                form_path=expr.form_path,
            )
        try:
            descriptor = resolve_view_renderer(expr.renderer_id, expr.renderer_version)
        except ViewRendererError:
            _raise_error(
                f"unknown materialize-view renderer `{expr.renderer_id}` v{expr.renderer_version}",
                code="materialize_view_renderer_unknown",
                span=expr.span,
                form_path=expr.form_path,
            )
        forbidden = _first_transition_runtime_forbidden_type(typed_value.type_ref)
        if forbidden is not None:
            _raise_error(
                f"`materialize-view :value` cannot carry runtime-forbidden type `{forbidden}`",
                code="materialize_view_value_type_invalid",
                span=expr.value_expr.span,
                form_path=expr.value_expr.form_path,
            )
        if descriptor.accepted_shape == "path_value" and not isinstance(typed_value.type_ref, PathTypeRef):
            _raise_error(
                "`materialize-view` path-line rendering requires a path-typed value",
                code="materialize_view_value_type_invalid",
                span=expr.value_expr.span,
                form_path=expr.value_expr.form_path,
            )
        typed_target = None
        if expr.target_expr is not None:
            typed_target = _typecheck(
                expr.target_expr,
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
            if not isinstance(typed_target.type_ref, PathTypeRef) or not _materialize_view_path_contracts_compatible(
                typed_target.type_ref,
                returns_type,
            ):
                _raise_error(
                    "`materialize-view :target` must be a compatible path contract for `:returns`",
                    code="materialize_view_target_contract_invalid",
                    span=expr.target_expr.span,
                    form_path=expr.target_expr.form_path,
                )
        return _typed(
            expr=expr,
            type_ref=returns_type,
            effect=merge_effect_summaries(
                typed_value.effect_summary,
                typed_target.effect_summary if typed_target is not None else EMPTY_EFFECT_SUMMARY,
                effect_summary_from_direct(
                    direct_effects=(
                        WriteEffect(subject=_effect_subject(expr.view_name)),
                    ),
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
            proc_ref_resolution_context=proc_ref_resolution_context,
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
            proc_ref_resolution_context=proc_ref_resolution_context,
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
            proc_ref_resolution_context=proc_ref_resolution_context,
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
            proc_ref_resolution_context=proc_ref_resolution_context,
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
            proc_ref_resolution_context=proc_ref_resolution_context,
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
            proc_ref_resolution_context=proc_ref_resolution_context,
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
            proc_ref_resolution_context=proc_ref_resolution_context,
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
            proc_ref_resolution_context=proc_ref_resolution_context,
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
            proc_ref_resolution_context=proc_ref_resolution_context,
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
        if not isinstance(return_type, (RecordTypeRef, UnionTypeRef)):
            _raise_error(
                "`run-provider-phase` requires a record or union `:returns` type",
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
            proc_ref_resolution_context=proc_ref_resolution_context,
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
            proc_ref_resolution_context=proc_ref_resolution_context,
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
            proc_ref_resolution_context=proc_ref_resolution_context,
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
            proc_ref_resolution_context=proc_ref_resolution_context,
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
            proc_ref_resolution_context=proc_ref_resolution_context,
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
            proc_ref_resolution_context=proc_ref_resolution_context,
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
            proc_ref_resolution_context=proc_ref_resolution_context,
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
            proc_ref_resolution_context=proc_ref_resolution_context,
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
            proc_ref_resolution_context=proc_ref_resolution_context,
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
            proc_ref_resolution_context=proc_ref_resolution_context,
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
            proc_ref_resolution_context=proc_ref_resolution_context,
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
            proc_ref_resolution_context=proc_ref_resolution_context,
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
    if type(expr) is ProviderResultExpr:
        return _typecheck_provider_result_expr(
            expr,
            context=context,
            recurse=recurse,
            typed_factory=_typed,
        )
    if type(expr) is ProviderBundlePathExpr:
        return _typecheck_provider_bundle_path_expr(
            expr,
            context=context,
            recurse=recurse,
            typed_factory=_typed,
        )
    if type(expr) is CommandResultExpr:
        return _typecheck_command_result_expr(
            expr,
            context=context,
            recurse=recurse,
            typed_factory=_typed,
        )
    raise TypeError(f"unsupported expression node: {type(expr)!r}")


def _require_normative_phase_ctx_type(
    type_ref: TypeRef,
    *,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> None:
    if is_record_definition_named(type_ref, IMPLEMENTATION_ATTEMPT_PHASE_CONTEXT_NAME):
        _raise_error(
            "generic phase stdlib forms require `PhaseCtx`; the legacy bridge is reserved for the Stage 4 implementation-attempt regression",
            code="phase_ctx_legacy_bridge_invalid",
            span=span,
            form_path=form_path,
        )
    if not is_record_definition_named(type_ref, PHASE_CONTEXT_NAME):
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

























def _generated_procedure_signature(
    *,
    name: str,
    params: tuple[tuple[str, TypeRef], ...],
    return_type: TypeRef,
    requested_lowering_mode: ProcedureLoweringMode,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> ProcedureSignature:
    return ProcedureSignature(
        name=name,
        params=params,
        return_type_ref=return_type,
        declared_effects=frozenset(),
        requested_lowering_mode=requested_lowering_mode,
        span=span,
        form_path=form_path,
        type_params=(),
        where_clauses=(),
    )


def _type_name(type_ref: TypeRef) -> str:
    return type_ref.name


def _generated_procedure_definition(
    *,
    name: str,
    signature: ProcedureSignature,
    body: ExprNode,
    span: SourceSpan,
    form_path: tuple[str, ...],
    expansion_stack,
) -> ProcedureDef:
    return ProcedureDef(
        name=name,
        params=tuple(
            ProcedureParam(
                name=param_name,
                type_name=_type_name(param_type),
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            )
            for param_name, param_type in signature.params
        ),
        return_type_name=_type_name(signature.return_type_ref),
        declared_effects=frozenset(),
        requested_lowering_mode=signature.requested_lowering_mode,
        body=body,
        span=span,
        form_path=form_path,
        expansion_stack=expansion_stack,
        type_params=(),
        where_clauses=(),
    )


def _typecheck_generated_procedure(
    definition: ProcedureDef,
    signature: ProcedureSignature,
    *,
    type_env: FrontendTypeEnvironment,
    workflow_catalog: "WorkflowCatalog | None",
    procedure_catalog: ProcedureCatalog,
    extern_environment: "ExternEnvironment | None",
    command_boundary_environment: "CommandBoundaryEnvironment | None",
    procedure_effects_by_name: Mapping[str, EffectSummary],
    workflow_effects_by_name: Mapping[str, EffectSummary],
    proc_ref_resolution_context: ProcRefResolutionContext | None,
) -> TypedProcedureDef:
    from .procedure_typecheck import ProcedureTypecheckContext, typecheck_generated_procedure

    return typecheck_generated_procedure(
        definition,
        signature,
        type_env=type_env,
        context=ProcedureTypecheckContext(
            type_env=type_env,
            value_env={},
            workflow_catalog=workflow_catalog,
            procedure_catalog=procedure_catalog,
            extern_environment=extern_environment,
            command_boundary_environment=command_boundary_environment,
            procedure_effects_by_name=procedure_effects_by_name,
            workflow_effects_by_name=workflow_effects_by_name,
            proc_ref_resolution_context=proc_ref_resolution_context,
            active_proc_ref_value_env=get_session_state().proc_ref_value_env,
            generated_local_procedure_state=get_session_state().let_proc_rewrite_results,
            session_state=get_session_state(),
        ),
    )


def _register_generated_record_type(
    type_env: FrontendTypeEnvironment,
    *,
    name: str,
    fields: tuple[tuple[str, TypeRef], ...],
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> None:
    if type_env._type_refs.get(name) is not None:
        return
    definition = RecordDef(
        name=name,
        fields=tuple(
            RecordField(
                name=field_name,
                type_name=_type_name(field_type),
                span=span,
            )
            for field_name, field_type in fields
        ),
        span=span,
    )
    type_env._type_refs[name] = RecordTypeRef(
        name=name,
        definition=definition,
        field_types={field_name: field_type for field_name, field_type in fields},
    )


def _register_generated_union_type(
    type_env: FrontendTypeEnvironment,
    *,
    name: str,
    variants: tuple[tuple[str, tuple[tuple[str, TypeRef], ...]], ...],
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> None:
    if type_env._type_refs.get(name) is not None:
        return
    definition = UnionDef(
        name=name,
        variants=tuple(
            UnionVariant(
                name=variant_name,
                fields=tuple(
                    RecordField(
                        name=field_name,
                        type_name=_type_name(field_type),
                        span=span,
                    )
                    for field_name, field_type in fields
                ),
                span=span,
            )
            for variant_name, fields in variants
        ),
        span=span,
    )
    type_env._type_refs[name] = UnionTypeRef(
        name=name,
        definition=definition,
        variant_field_types={
            variant_name: {field_name: field_type for field_name, field_type in fields}
            for variant_name, fields in variants
        },
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


def _typed(*, expr: ExprNode, type_ref: TypeRef, effect: EffectSummary) -> TypedExpr:
    from .typecheck_context import TypedExpr as FacadeTypedExpr

    return FacadeTypedExpr(
        expr=expr,
        type_ref=type_ref,
        effect_summary=effect,
        span=expr.span,
        form_path=expr.form_path,
    )


def _generated_relpath_seed_expr(
    *,
    type_ref: TypeRef,
    literal_path: str,
    seed_role: str,
    span: SourceSpan,
    form_path: tuple[str, ...],
    expansion_stack,
) -> GeneratedRelpathSeedExpr:
    if not isinstance(type_ref, PathTypeRef) or type_ref.definition.kind != "relpath":
        _raise_error(
            f"generated relpath seed `{seed_role}` requires a relpath type, got `{_type_label(type_ref)}`",
            code="type_mismatch",
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
    return GeneratedRelpathSeedExpr(
        target_type_ref=type_ref,
        literal_path=literal_path,
        seed_role=seed_role,
        span=span,
        form_path=form_path,
        expansion_stack=expansion_stack,
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
    proc_ref_resolution_context: ProcRefResolutionContext | None,
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
        proc_ref_resolution_context=proc_ref_resolution_context,
    )


def _resolve_field_access_impl(
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


def _type_refs_compatible(expected: TypeRef, actual: TypeRef) -> bool:
    return type_refs_compatible(expected, actual)


def _unify_loop_control_types(
    left: TypeRef | LoopControlTypeRef,
    right: TypeRef | LoopControlTypeRef,
) -> LoopControlTypeRef | None:
    """Unify loop-control payloads across match arms when possible."""

    if not isinstance(left, LoopControlTypeRef) or not isinstance(right, LoopControlTypeRef):
        return None
    if left.state_type_ref != right.state_type_ref:
        return None
    if left.result_type_ref is None:
        return LoopControlTypeRef(
            state_type_ref=left.state_type_ref,
            result_type_ref=right.result_type_ref,
        )
    if right.result_type_ref is None:
        return LoopControlTypeRef(
            state_type_ref=left.state_type_ref,
            result_type_ref=left.result_type_ref,
        )
    if left.result_type_ref != right.result_type_ref:
        return None
    return LoopControlTypeRef(
        state_type_ref=left.state_type_ref,
        result_type_ref=left.result_type_ref,
    )


def _type_label(type_ref: TypeRef | LoopControlTypeRef) -> str:
    if isinstance(type_ref, LoopControlTypeRef):
        result_label = (
            "?"
            if type_ref.result_type_ref is None
            else _type_label(type_ref.result_type_ref)
        )
        return f"LoopControl[{_type_label(type_ref.state_type_ref)} -> {result_label}]"
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
    transition_binding = getattr(binding, "transition_binding", None)
    allow_migration_backend_call = (
        transition_binding is not None
        and getattr(transition_binding, "contract_role", None) == "migration_backend"
    )
    if (
        (
            "resource_transition" in effects
            or "ledger_update" in effects
            or binding.behavior_class == "resource_transition"
        )
        and not allow_migration_backend_call
    ):
        _raise_error(
            "resource movement must use `resource-transition` or a certified resource_transition adapter",
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
    try:
        resolved_ref = resolve_workflow_ref_name(
            workflow_name,
            workflow_catalog=workflow_catalog,
            span=span,
            form_path=form_path,
            allow_extern_rebinding=True,
        )
    except LispFrontendCompileError as exc:
        diagnostic = exc.diagnostics[0]
        _raise_required_lint(
            diagnostic.message,
            code=diagnostic.code,
            span=span,
            form_path=form_path,
        )
    return type(
        "WorkflowRefSignature",
        (),
        {
            "name": resolved_ref.workflow_name,
            "params": resolved_ref.signature_params,
            "return_type_ref": resolved_ref.return_type_ref,
        },
    )()


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
    _require_union_variant_exact_type(
        signature.return_type_ref,
        "BLOCKED",
        "reason",
        expected_type=PrimitiveTypeRef(name="String"),
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




def _temporary_procedure_catalog(
    procedure_catalog: ProcedureCatalog,
    *,
    definition: ProcedureDef,
    signature: ProcedureSignature,
) -> ProcedureCatalog:
    signatures_by_name = dict(procedure_catalog.signatures_by_name)
    definitions_by_name = dict(procedure_catalog.definitions_by_name)
    signatures_by_name[signature.name] = signature
    definitions_by_name[definition.name] = definition
    return ProcedureCatalog(
        signatures_by_name=signatures_by_name,
        definitions_by_name=definitions_by_name,
        call_graph=procedure_catalog.call_graph,
    )




















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
