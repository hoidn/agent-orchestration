"""Type and proof checking for Workflow Lisp expressions.

See `../../docs/design/workflow_lisp_type_catalog.md` for the type model and
`../../docs/design/workflow_lisp_proof_graph.md` for the planned variant-proof model.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import TYPE_CHECKING

from .conditionals import classify_condition_expr
from .diagnostics import LispFrontendCompileError
from .effects import (
    EMPTY_EFFECT_SUMMARY,
    EffectSummary,
    merge_effect_summaries,
)
from .expressions import (
    BacklogDrainExpr,
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
    WithPhaseExpr,
)
from .loops import LoopControlTypeRef, ensure_loop_projectable_type
from .loop_state import typecheck_loop_state_expr as typecheck_loop_state_expr_owner
from .procedure_refs import (
    ProcRefResolutionContext,
    ResolvedProcRefValue,
    proc_ref_type_from_signature,
    resolve_proc_ref_value,
    resolve_proc_ref_name,
)
from .phase import PhaseScope, build_phase_scope
from .parametric_constraints import SharedUnionFieldCapability
from .typecheck_calls import (
    typecheck_call_expr as _typecheck_call_expr,
    typecheck_function_call_expr as _typecheck_function_call_expr,
    typecheck_proc_ref_argument as _typecheck_proc_ref_argument,
    typecheck_workflow_ref_argument as _typecheck_workflow_ref_argument,
)
from .typecheck_context import (
    LoopTypecheckContext,
    TypecheckContext,
    TypedExpr,
    ValueEnvironment,
    get_session_state,
    raise_error as _raise_error,
    restore_session_state,
    snapshot_session_state,
    _literal_type_name,
    _type_label,
    _type_refs_compatible,
    _typed,
    _unify_loop_control_types,
)
from .typecheck_drain_phase import (
    typecheck_backlog_drain_expr,
    typecheck_phase_target_expr,
    typecheck_produce_one_of_expr,
    typecheck_run_provider_phase_expr,
)
from .typecheck_effects import (
    typecheck_command_result_expr as _typecheck_command_result_expr,
    typecheck_provider_bundle_path_expr as _typecheck_provider_bundle_path_expr,
    typecheck_provider_result_expr as _typecheck_provider_result_expr,
)
from .typecheck_pure_ops import typecheck_pure_expr as _typecheck_pure_expr
from .typecheck_resource_view import (
    typecheck_finalize_selected_item_expr,
    typecheck_materialize_view_expr,
    typecheck_resource_transition_expr,
)
from .typecheck_resume import typecheck_resume_or_start_expr
from .typecheck_proofs import (
    ProofScope,
    typecheck_field_access_expr as _typecheck_field_access_expr,
    typecheck_match_expr as _typecheck_match_expr,
)
from .type_env import (
    FrontendTypeEnvironment,
    OptionalTypeRef,
    PathTypeRef,
    PrimitiveTypeRef,
    ProcRefTypeRef,
    RecordTypeRef,
    TypeRef,
    UnionTypeRef,
)
from .workflow_refs import (
    resolve_workflow_ref_name,
    workflow_ref_type_from_signature,
)

if TYPE_CHECKING:
    from .functions import FunctionCatalog
    from .procedures import ProcedureCatalog
    from .workflows import (
        CommandBoundaryEnvironment,
        ExternEnvironment,
        WorkflowCatalog,
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
        return typecheck_resource_transition_expr(
            expr,
            context=context,
            recurse=recurse,
            typed_factory=_typed,
        )
    if isinstance(expr, MaterializeViewExpr):
        return typecheck_materialize_view_expr(
            expr,
            context=context,
            recurse=recurse,
            typed_factory=_typed,
        )
    if isinstance(expr, FinalizeSelectedItemExpr):
        return typecheck_finalize_selected_item_expr(
            expr,
            context=context,
            recurse=recurse,
            typed_factory=_typed,
        )
    if isinstance(expr, BacklogDrainExpr):
        return typecheck_backlog_drain_expr(
            expr,
            context=context,
            recurse=recurse,
            typed_factory=_typed,
        )
    if isinstance(expr, PhaseTargetExpr):
        return typecheck_phase_target_expr(
            expr,
            context=context,
            recurse=recurse,
            typed_factory=_typed,
        )
    if isinstance(expr, RunProviderPhaseExpr):
        return typecheck_run_provider_phase_expr(
            expr,
            context=context,
            recurse=recurse,
            typed_factory=_typed,
        )
    if isinstance(expr, ProduceOneOfExpr):
        return typecheck_produce_one_of_expr(
            expr,
            context=context,
            recurse=recurse,
            typed_factory=_typed,
        )
    if isinstance(expr, ResumeOrStartExpr):
        return typecheck_resume_or_start_expr(
            expr,
            context=context,
            recurse=recurse,
            typed_factory=_typed,
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
