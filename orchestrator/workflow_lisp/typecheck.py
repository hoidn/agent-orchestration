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
    ExprNode,
    FinalizeSelectedItemExpr,
    FieldAccessExpr,
    FunctionCallExpr,
    GeneratedRelpathSeedExpr,
    IfExpr,
    LetProcExpr,
    LetStarExpr,
    LiteralExpr,
    LoopRecurExpr,
    MatchArm,
    MatchExpr,
    NameExpr,
    PhaseTargetExpr,
    ProcRefLiteralExpr,
    ProduceOneOfExpr,
    ProcedureCallExpr,
    ProviderResultExpr,
    ResourceTransitionExpr,
    RecordExpr,
    ResumeOrStartExpr,
    RunProviderPhaseExpr,
    StdlibSpecializationExpr,
    UnionVariantExpr,
    WorkflowRefLiteralExpr,
    elaborate_expression,
    WithPhaseExpr,
)
from .loops import LoopControlTypeRef, ensure_loop_projectable_type
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
from .syntax import SyntaxNode
from .type_env import (
    FrontendTypeEnvironment,
    PathTypeRef,
    PrimitiveTypeRef,
    ProcRefTypeRef,
    RecordTypeRef,
    TypeRef,
    UnionTypeRef,
    VariantCaseTypeRef,
    WorkflowRefTypeRef,
)
from .workflow_refs import (
    resolve_workflow_ref_name,
    workflow_ref_target_name,
    workflow_ref_type_from_signature,
)

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


@dataclass(frozen=True)
class TypedExpr:
    """One expression paired with its resolved Workflow Lisp type."""

    expr: ExprNode
    type_ref: TypeRef | LoopControlTypeRef
    span: SourceSpan
    form_path: tuple[str, ...]
    effect_summary: EffectSummary = EMPTY_EFFECT_SUMMARY


ValueEnvironment = Mapping[str, TypeRef]
_ACTIVE_FUNCTION_CATALOG = None
_ACTIVE_PROC_REF_VALUE_ENV: Mapping[str, ResolvedProcRefValue] = {}
_ACTIVE_VALUE_EXPR_ENV: Mapping[str, ExprNode] = {}
_ACTIVE_LOOP_CONTEXT: list["LoopTypecheckContext"] = []
_ACTIVE_GENERATED_LOCAL_PROCEDURES: dict[str, TypedProcedureDef] = {}
_ACTIVE_LET_PROC_REWRITE_RESULTS: dict[int, ExprNode] = {}
_ACTIVE_WORKFLOW_SIGNATURE = None
_ACTIVE_REUSABLE_STATE_PRODUCER_CONTEXT: Mapping[str, object] | None = None
def consume_generated_local_procedures() -> tuple[TypedProcedureDef, ...]:
    """Return and clear generated `let-proc` procedures from the active pass."""

    global _ACTIVE_GENERATED_LOCAL_PROCEDURES

    procedures = tuple(_ACTIVE_GENERATED_LOCAL_PROCEDURES.values())
    _ACTIVE_GENERATED_LOCAL_PROCEDURES = {}
    return procedures


def reset_generated_local_procedure_state() -> None:
    """Clear compiler-pass-local `let-proc` generated state."""

    global _ACTIVE_GENERATED_LOCAL_PROCEDURES, _ACTIVE_LET_PROC_REWRITE_RESULTS

    _ACTIVE_GENERATED_LOCAL_PROCEDURES = {}
    _ACTIVE_LET_PROC_REWRITE_RESULTS = {}


def set_active_workflow_signature(signature) -> None:
    """Record the current workflow signature for nested typecheck helpers."""

    global _ACTIVE_WORKFLOW_SIGNATURE

    _ACTIVE_WORKFLOW_SIGNATURE = signature


def clear_active_workflow_signature() -> None:
    """Clear the active workflow signature after finishing one workflow body."""

    global _ACTIVE_WORKFLOW_SIGNATURE

    _ACTIVE_WORKFLOW_SIGNATURE = None


def set_active_reusable_state_producer_context(context: Mapping[str, object] | None) -> None:
    """Record compiler-owned reuse identity inputs for the active workflow body."""

    global _ACTIVE_REUSABLE_STATE_PRODUCER_CONTEXT

    _ACTIVE_REUSABLE_STATE_PRODUCER_CONTEXT = context


def clear_active_reusable_state_producer_context() -> None:
    """Clear the active compiler-owned reuse identity inputs."""

    global _ACTIVE_REUSABLE_STATE_PRODUCER_CONTEXT

    _ACTIVE_REUSABLE_STATE_PRODUCER_CONTEXT = None


def _effect_subject(value: str) -> tuple[str, ...]:
    return tuple(segment for segment in value.split(".") if segment)


def _hidden_context_omission_allowed(
    *,
    callee_signature,
    param_name: str,
    expected_type: TypeRef,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> bool:
    active_signature = _ACTIVE_WORKFLOW_SIGNATURE
    if (
        callee_signature is None
        or active_signature is None
        or not getattr(active_signature, "allow_hidden_context_binding", False)
    ):
        return False
    if not isinstance(expected_type, RecordTypeRef):
        return False
    if expected_type.name not in {RUN_CONTEXT_NAME, PHASE_CONTEXT_NAME}:
        return False

    ambiguities = getattr(callee_signature, "hidden_context_ambiguities", {})
    if param_name in ambiguities:
        phase_names = ambiguities[param_name]
        _raise_error(
            (
                f"promoted-entry hidden `{param_name}` binding is ambiguous across phases "
                f"`{phase_names[0]}` and `{phase_names[-1]}`"
            ),
            code="promoted_entry_hidden_phase_ctx_ambiguous",
            span=span,
            form_path=form_path,
        )

    requirements = getattr(callee_signature, "hidden_context_requirements", {})
    requirement = requirements.get(param_name) if isinstance(requirements, Mapping) else None
    if requirement is None:
        _raise_error(
            f"promoted-entry hidden binding for `{param_name}` is unavailable in this callee",
            code="promoted_entry_hidden_context_binding_invalid",
            span=span,
            form_path=form_path,
        )
    return True


@dataclass(frozen=True)
class LoopTypecheckContext:
    """Active loop typing contract for nested `continue` and `done` forms."""

    state_type_ref: TypeRef
    result_type_ref: TypeRef | None = None


@dataclass(frozen=True)
class ProofFact:
    """One proven union narrowing fact in scope."""

    subject_name: str
    variant_name: str
    variant_type: VariantCaseTypeRef


@dataclass(frozen=True)
class LocalProcRewriteBinding:
    """How one lexical `let-proc` name rewrites during typechecking."""

    generated_name: str
    capture_bindings: tuple[tuple[str, ExprNode], ...]
    allow_reference: bool


def _typecheck_workflow_ref_argument(
    expr: ExprNode,
    *,
    expected_type: WorkflowRefTypeRef,
    value_env: dict[str, TypeRef],
    workflow_catalog: "WorkflowCatalog | None",
) -> TypedExpr:
    if workflow_catalog is None:
        raise TypeError("workflow_catalog is required for workflow-ref arguments")
    if isinstance(expr, NameExpr):
        bound_type = value_env.get(expr.name)
        if isinstance(bound_type, WorkflowRefTypeRef):
            return _typed(expr=expr, type_ref=bound_type, effect=EMPTY_EFFECT_SUMMARY)
        if bound_type is not None:
            _raise_error(
                "workflow-ref arguments must be literals or forwarded workflow-ref bindings",
                code="workflow_ref_literal_required",
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
    if isinstance(expr, (WorkflowRefLiteralExpr, NameExpr)):
        resolved_ref = resolve_workflow_ref_name(
            workflow_ref_target_name(expr),
            workflow_catalog=workflow_catalog,
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=getattr(expr, "expansion_stack", ()),
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
    _raise_error(
        "workflow-ref arguments must be literals or forwarded workflow-ref bindings",
        code="workflow_ref_literal_required",
        span=expr.span,
        form_path=expr.form_path,
    )


def _typecheck_proc_ref_argument(
    expr: ExprNode,
    *,
    expected_type: ProcRefTypeRef,
    value_env: dict[str, TypeRef],
    procedure_catalog: "ProcedureCatalog | None",
    proc_ref_resolution_context: ProcRefResolutionContext | None,
) -> tuple[TypedExpr, ResolvedProcRefValue | None]:
    if procedure_catalog is None:
        raise TypeError("procedure_catalog is required for proc-ref arguments")
    resolved = resolve_proc_ref_value(
        expr,
        procedure_catalog=procedure_catalog,
        proc_ref_env=_ACTIVE_PROC_REF_VALUE_ENV,
        resolution_context=proc_ref_resolution_context,
        expected_type=expected_type,
    )
    if resolved is not None:
        bound_type = value_env.get(expr.name) if isinstance(expr, NameExpr) else resolved.residual_type_ref
        type_ref = bound_type if isinstance(bound_type, ProcRefTypeRef) else resolved.residual_type_ref
        return _typed(expr=expr, type_ref=type_ref, effect=EMPTY_EFFECT_SUMMARY), resolved
    if isinstance(expr, NameExpr):
        bound_type = value_env.get(expr.name)
        if isinstance(bound_type, ProcRefTypeRef):
            return _typed(expr=expr, type_ref=bound_type, effect=EMPTY_EFFECT_SUMMARY), None
    _raise_error(
        "proc-ref arguments must be literals or forwarded proc-ref bindings",
        code="proc_ref_literal_required",
        span=expr.span,
        form_path=expr.form_path,
    )


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
    proc_ref_resolution_context: ProcRefResolutionContext | None = None,
    proc_ref_value_env: Mapping[str, ResolvedProcRefValue] | None = None,
) -> TypedExpr:
    """Typecheck one supported Workflow Lisp expression."""

    global _ACTIVE_FUNCTION_CATALOG, _ACTIVE_PROC_REF_VALUE_ENV, _ACTIVE_VALUE_EXPR_ENV, _ACTIVE_LET_PROC_REWRITE_RESULTS

    active_proof = proof_scope or ProofScope(facts={})
    previous_function_catalog = _ACTIVE_FUNCTION_CATALOG
    previous_proc_ref_env = _ACTIVE_PROC_REF_VALUE_ENV
    previous_value_expr_env = _ACTIVE_VALUE_EXPR_ENV
    previous_let_proc_rewrites = _ACTIVE_LET_PROC_REWRITE_RESULTS
    _ACTIVE_FUNCTION_CATALOG = function_catalog
    _ACTIVE_PROC_REF_VALUE_ENV = proc_ref_value_env or {}
    _ACTIVE_VALUE_EXPR_ENV = {}
    _ACTIVE_LET_PROC_REWRITE_RESULTS = {}
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
        return replace(typed, expr=_replace_eliminated_let_procs(typed.expr))
    finally:
        _ACTIVE_FUNCTION_CATALOG = previous_function_catalog
        _ACTIVE_PROC_REF_VALUE_ENV = previous_proc_ref_env
        _ACTIVE_VALUE_EXPR_ENV = previous_value_expr_env
        _ACTIVE_LET_PROC_REWRITE_RESULTS = previous_let_proc_rewrites


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
    global _ACTIVE_PROC_REF_VALUE_ENV
    if isinstance(expr, LiteralExpr):
        return _typed(
            expr=expr,
            type_ref=PrimitiveTypeRef(name=_literal_type_name(expr.literal_kind)),
            effect=EMPTY_EFFECT_SUMMARY,
        )
    if isinstance(expr, GeneratedRelpathSeedExpr):
        seed_type = expr.target_type_ref
        if not isinstance(seed_type, PathTypeRef) or seed_type.definition.kind != "relpath":
            _raise_error(
                f"generated relpath seed `{expr.seed_role}` requires a relpath type, got `{_type_label(seed_type)}`",
                code="type_mismatch",
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
        return _typed(expr=expr, type_ref=seed_type, effect=EMPTY_EFFECT_SUMMARY)
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
        base_typed = _typecheck(
            expr.base_expr,
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
            proc_ref_env=_ACTIVE_PROC_REF_VALUE_ENV,
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
            typed_binding = _typecheck(
                binding.value_expr,
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
            proc_ref_env=_ACTIVE_PROC_REF_VALUE_ENV,
            resolution_context=proc_ref_resolution_context,
        )
        assert resolved is not None
        return _typed(
            expr=expr,
            type_ref=resolved.residual_type_ref,
            effect=EMPTY_EFFECT_SUMMARY,
        )
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
            proc_ref_resolution_context=proc_ref_resolution_context,
        )
        current_type = typed_base.type_ref
        base_name = expr.base.name if isinstance(expr.base, NameExpr) else ""
        for field_name in expr.fields:
            current_type = _resolve_field_access(
                current_type,
                base_name=base_name,
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
        if not _ACTIVE_LOOP_CONTEXT:
            _raise_error(
                "`continue` is valid only inside `loop/recur`",
                code="loop_recur_continue_outside_loop",
                span=expr.span,
                form_path=expr.form_path,
            )
        loop_context = _ACTIVE_LOOP_CONTEXT[-1]
        typed_state = _typecheck(
            expr.state_expr,
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
        if not _ACTIVE_LOOP_CONTEXT:
            _raise_error(
                "`done` is valid only inside `loop/recur`",
                code="loop_recur_done_outside_loop",
                span=expr.span,
                form_path=expr.form_path,
            )
        loop_context = _ACTIVE_LOOP_CONTEXT[-1]
        typed_result = _typecheck(
            expr.result_expr,
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
        global _ACTIVE_VALUE_EXPR_ENV
        local_env = dict(value_env)
        local_proc_ref_env = dict(_ACTIVE_PROC_REF_VALUE_ENV)
        local_value_expr_env = dict(_ACTIVE_VALUE_EXPR_ENV)
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
            previous_proc_ref_env = _ACTIVE_PROC_REF_VALUE_ENV
            _ACTIVE_PROC_REF_VALUE_ENV = local_proc_ref_env
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
                proc_ref_resolution_context=proc_ref_resolution_context,
            )
            _ACTIVE_PROC_REF_VALUE_ENV = previous_proc_ref_env
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
        previous_proc_ref_env = _ACTIVE_PROC_REF_VALUE_ENV
        previous_value_expr_env = _ACTIVE_VALUE_EXPR_ENV
        _ACTIVE_PROC_REF_VALUE_ENV = local_proc_ref_env
        _ACTIVE_VALUE_EXPR_ENV = local_value_expr_env
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
            proc_ref_resolution_context=proc_ref_resolution_context,
        )
        _ACTIVE_PROC_REF_VALUE_ENV = previous_proc_ref_env
        _ACTIVE_VALUE_EXPR_ENV = previous_value_expr_env
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
    if isinstance(expr, LetProcExpr):
        return _typecheck_let_proc(
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
            proc_ref_resolution_context=proc_ref_resolution_context,
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
                proc_ref_resolution_context=proc_ref_resolution_context,
            )
            arm_summaries.append(typed_body.effect_summary)
            if arm_result_type is None:
                arm_result_type = typed_body.type_ref
            else:
                unified_loop_control = _unify_loop_control_types(arm_result_type, typed_body.type_ref)
                if unified_loop_control is not None:
                    arm_result_type = unified_loop_control
                    continue
                if isinstance(arm_result_type, LoopControlTypeRef) and isinstance(
                    typed_body.type_ref,
                    LoopControlTypeRef,
                ):
                    _raise_error(
                        f"`done` expected `{_type_label(arm_result_type.result_type_ref)}` but got `{_type_label(typed_body.type_ref.result_type_ref)}`",
                        code="loop_recur_done_type_mismatch",
                        span=arm.body.span,
                        form_path=arm.body.form_path,
                    )
                if typed_body.type_ref != arm_result_type:
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
    if isinstance(expr, LoopRecurExpr):
        typed_max = _typecheck(
            expr.max_iterations_expr,
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
                "`loop/recur :max` must resolve to `Int`",
                code="loop_recur_max_invalid",
                span=expr.max_iterations_expr.span,
                form_path=expr.max_iterations_expr.form_path,
            )
        typed_state = _typecheck(
            expr.initial_state_expr,
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
        ensure_loop_projectable_type(
            typed_state.type_ref,
            code="loop_recur_state_type_invalid",
            span=expr.initial_state_expr.span,
            form_path=expr.initial_state_expr.form_path,
        )
        _ACTIVE_LOOP_CONTEXT.append(LoopTypecheckContext(state_type_ref=typed_state.type_ref))
        try:
            typed_body = _typecheck(
                expr.body_expr,
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
        finally:
            loop_context = _ACTIVE_LOOP_CONTEXT.pop()
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
    if isinstance(expr, CallExpr):
        if workflow_catalog is None:
            raise TypeError("workflow_catalog is required for CallExpr typechecking")
        workflow_ref_type = value_env.get(expr.callee_name)
        if isinstance(workflow_ref_type, WorkflowRefTypeRef):
            if len(expr.bindings) != len(workflow_ref_type.param_type_refs):
                _raise_error(
                    f"call is missing required binding for workflow ref `{expr.callee_name}`",
                    code="workflow_signature_mismatch",
                    span=expr.span,
                    form_path=expr.form_path,
                )
            expected_bindings = {
                binding_name: type_ref
                for (binding_name, _), type_ref in zip(
                    expr.bindings,
                    workflow_ref_type.param_type_refs,
                    strict=True,
                )
            }
            signature_name = expr.callee_name
            return_type = workflow_ref_type.return_type_ref
            ordered_params = tuple(
                (binding_name, type_ref)
                for (binding_name, _), type_ref in zip(
                    expr.bindings,
                    workflow_ref_type.param_type_refs,
                    strict=True,
                )
            )
        else:
            signature = workflow_catalog.signatures_by_name.get(expr.callee_name)
            if signature is None:
                _raise_error(
                    f"unknown workflow callee `{expr.callee_name}`",
                    code="workflow_call_unknown",
                    span=expr.span,
                    form_path=expr.form_path,
                )
            expected_bindings = dict(signature.params)
            signature_name = signature.name
            return_type = signature.return_type_ref
            ordered_params = signature.params
        if not isinstance(workflow_ref_type, WorkflowRefTypeRef):
            defaulted_bindings = frozenset(signature.param_defaults)
        else:
            defaulted_bindings = frozenset()
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
            if isinstance(expected_type, WorkflowRefTypeRef):
                typed_binding = _typecheck_workflow_ref_argument(
                    binding_expr,
                    expected_type=expected_type,
                    value_env=value_env,
                    workflow_catalog=workflow_catalog,
                )
                binding_summaries.append(typed_binding.effect_summary)
                if not isinstance(binding_expr, (WorkflowRefLiteralExpr, NameExpr)):
                    _raise_error(
                        "workflow-ref arguments must be literals or forwarded workflow-ref bindings",
                        code="workflow_ref_literal_required",
                        span=binding_expr.span,
                        form_path=binding_expr.form_path,
                    )
                if typed_binding.type_ref != expected_type:
                    _raise_error(
                        f"workflow ref argument `{binding_name}` does not match `{expected_type.name}`",
                        code="workflow_ref_signature_invalid",
                        span=binding_expr.span,
                        form_path=binding_expr.form_path,
                    )
                continue
            if isinstance(expected_type, ProcRefTypeRef):
                typed_binding, _ = _typecheck_proc_ref_argument(
                    binding_expr,
                    expected_type=expected_type,
                    value_env=value_env,
                    procedure_catalog=procedure_catalog,
                    proc_ref_resolution_context=proc_ref_resolution_context,
                )
                binding_summaries.append(typed_binding.effect_summary)
                if typed_binding.type_ref != expected_type:
                    _raise_error(
                        f"procedure ref argument `{binding_name}` does not match `{expected_type.name}`",
                        code="proc_ref_signature_invalid",
                        span=binding_expr.span,
                        form_path=binding_expr.form_path,
                    )
                continue
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
                proc_ref_resolution_context=proc_ref_resolution_context,
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
        missing_bindings = [
            name
            for name, expected_type in ordered_params
            if name not in seen_bindings
            and name not in defaulted_bindings
            and not _hidden_context_omission_allowed(
                callee_signature=signature if not isinstance(workflow_ref_type, WorkflowRefTypeRef) else None,
                param_name=name,
                expected_type=expected_type,
                span=expr.span,
                form_path=expr.form_path,
            )
        ]
        if missing_bindings:
            _raise_error(
                f"call is missing required binding `{missing_bindings[0]}`",
                code="workflow_signature_mismatch",
                span=expr.span,
                form_path=expr.form_path,
            )
        call_summary = effect_summary_from_direct(
            direct_effects=(CallsWorkflowEffect(subject=(signature_name,)),),
        )
        return _typed(
            expr=expr,
            type_ref=return_type,
            effect=merge_effect_summaries(
                *binding_summaries,
                call_summary,
                workflow_effects_by_name.get(signature_name, EMPTY_EFFECT_SUMMARY),
            ),
        )
    if isinstance(expr, ProcedureCallExpr):
        from .procedure_typecheck import ProcedureTypecheckContext, typecheck_procedure_call_expr

        return typecheck_procedure_call_expr(
            expr,
            context=ProcedureTypecheckContext(
                value_env=value_env,
                workflow_catalog=workflow_catalog,
                procedure_catalog=procedure_catalog,
                extern_environment=extern_environment,
                command_boundary_environment=command_boundary_environment,
                procedure_effects_by_name=procedure_effects_by_name,
                workflow_effects_by_name=workflow_effects_by_name,
                proc_ref_resolution_context=proc_ref_resolution_context,
                active_proc_ref_value_env=_ACTIVE_PROC_REF_VALUE_ENV,
                generated_local_procedure_state=_ACTIVE_LET_PROC_REWRITE_RESULTS,
            ),
            recurse=lambda node: _typecheck(
                node,
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
            ),
            typecheck_workflow_ref_argument=lambda arg_expr, expected_type: _typecheck_workflow_ref_argument(
                arg_expr,
                expected_type=expected_type,
                value_env=value_env,
                workflow_catalog=workflow_catalog,
            ),
            typecheck_proc_ref_argument=lambda arg_expr, expected_type: _typecheck_proc_ref_argument(
                arg_expr,
                expected_type=expected_type,
                value_env=value_env,
                procedure_catalog=procedure_catalog,
                proc_ref_resolution_context=proc_ref_resolution_context,
            ),
            typed_factory=_typed,
            raise_error=_raise_error,
            type_label=_type_label,
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
                proc_ref_resolution_context=proc_ref_resolution_context,
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
    if isinstance(expr, StdlibSpecializationExpr):
        return _typecheck_stdlib_specialization_expr(
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
            proc_ref_resolution_context=proc_ref_resolution_context,
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
            proc_ref_resolution_context=proc_ref_resolution_context,
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
def _typecheck_stdlib_specialization_expr(
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
    typed_ctx = _typecheck(
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
    _require_normative_phase_ctx_type(
        typed_ctx.type_ref,
        span=ctx_expr.span,
        form_path=ctx_expr.form_path,
    )
    _require_phase_scope_name_match(
        active_phase_scope,
        authored_name=loop_name,
        form_name="review-revise-loop",
        span=expr.span,
        form_path=expr.form_path,
    )
    typed_completed = _typecheck(
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
    typed_inputs = _typecheck(
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
    typed_review_provider = _typecheck_expected_extern_operand(
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
    typed_fix_provider = _typecheck_expected_extern_operand(
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
    typed_review_prompt = _typecheck_expected_extern_operand(
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
    typed_fix_prompt = _typecheck_expected_extern_operand(
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
    typed_max = _typecheck(
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
    _validate_review_loop_result_contract(return_type, type_env=type_env, span=expr.span, form_path=expr.form_path)
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
    _register_generated_union_type(
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
    _register_generated_record_type(
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
                _generated_relpath_seed_expr(
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
    review_signature = _generated_procedure_signature(
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
    review_definition = _generated_procedure_definition(
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
    generated_catalog = _temporary_procedure_catalog(
        procedure_catalog,
        definition=review_definition,
        signature=review_signature,
    )
    typed_review = _typecheck_generated_procedure(
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
    fix_signature = _generated_procedure_signature(
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
    fix_definition = _generated_procedure_definition(
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
    generated_catalog = _temporary_procedure_catalog(
        generated_catalog,
        definition=fix_definition,
        signature=fix_signature,
    )
    typed_fix = _typecheck_generated_procedure(
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

    helper_signature = _generated_procedure_signature(
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
    helper_definition = _generated_procedure_definition(
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
    generated_catalog = _temporary_procedure_catalog(
        generated_catalog,
        definition=helper_definition,
        signature=helper_signature,
    )
    typed_helper = _typecheck_generated_procedure(
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
    _ACTIVE_GENERATED_LOCAL_PROCEDURES[review_wrapper_name] = typed_review
    _ACTIVE_GENERATED_LOCAL_PROCEDURES[fix_wrapper_name] = typed_fix
    _ACTIVE_GENERATED_LOCAL_PROCEDURES[helper_name] = typed_helper

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
    return _typecheck(
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
    return _generated_relpath_seed_expr(
        type_ref=last_review_report_type,
        literal_path="artifacts/review/last-review-report.md",
        seed_role="review_loop_last_review_report_seed",
        span=generated_span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
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
    )


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
            value_env={},
            workflow_catalog=workflow_catalog,
            procedure_catalog=procedure_catalog,
            extern_environment=extern_environment,
            command_boundary_environment=command_boundary_environment,
            procedure_effects_by_name=procedure_effects_by_name,
            workflow_effects_by_name=workflow_effects_by_name,
            proc_ref_resolution_context=proc_ref_resolution_context,
            active_proc_ref_value_env=_ACTIVE_PROC_REF_VALUE_ENV,
            generated_local_procedure_state=_ACTIVE_LET_PROC_REWRITE_RESULTS,
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

    if _ACTIVE_WORKFLOW_SIGNATURE is None:
        return ()
    return derive_reusable_state_public_input_hash_basis(_ACTIVE_WORKFLOW_SIGNATURE)


def _derive_resume_producer_fingerprint_basis(
    *,
    return_type_name: str,
    structured_contract_kind: str,
    expected_contract_fingerprint: str,
    target_dsl_version: str,
    reusable_variants: tuple[str, ...],
):
    from .contracts import derive_reusable_state_producer_fingerprint_basis

    if _ACTIVE_WORKFLOW_SIGNATURE is None:
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
            "command_boundary_bindings": {},
            "imported_workflow_fingerprints": {},
            "compile_inputs_fingerprint": "<unknown>",
        }
    return derive_reusable_state_producer_fingerprint_basis(
        signature=_ACTIVE_WORKFLOW_SIGNATURE,
        return_type_name=return_type_name,
        structured_contract_kind=structured_contract_kind,
        expected_contract_fingerprint=expected_contract_fingerprint,
        target_dsl_version=target_dsl_version,
        reusable_variants=reusable_variants,
        producer_context=_ACTIVE_REUSABLE_STATE_PRODUCER_CONTEXT,
    )


def _typed(*, expr: ExprNode, type_ref: TypeRef, effect: EffectSummary) -> TypedExpr:
    return TypedExpr(
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


def _type_refs_compatible(expected: TypeRef, actual: TypeRef) -> bool:
    from .contracts import review_findings_types_compatible

    if expected == actual:
        return True
    return review_findings_types_compatible(expected, actual)


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


def _typecheck_let_proc(
    expr: LetProcExpr,
    *,
    type_env: FrontendTypeEnvironment,
    value_env: dict[str, TypeRef],
    proof_scope: ProofScope,
    workflow_catalog: "WorkflowCatalog | None",
    procedure_catalog: ProcedureCatalog | None,
    extern_environment: "ExternEnvironment | None",
    command_boundary_environment: "CommandBoundaryEnvironment | None",
    active_phase_scope: PhaseScope | None,
    procedure_effects_by_name: Mapping[str, EffectSummary],
    workflow_effects_by_name: Mapping[str, EffectSummary],
    proc_ref_resolution_context: ProcRefResolutionContext | None,
) -> TypedExpr:
    global _ACTIVE_GENERATED_LOCAL_PROCEDURES, _ACTIVE_PROC_REF_VALUE_ENV, _ACTIVE_VALUE_EXPR_ENV, _ACTIVE_LET_PROC_REWRITE_RESULTS

    if procedure_catalog is None:
        raise TypeError("procedure_catalog is required for let-proc expressions")

    if (
        expr.binding.local_name in value_env
        or expr.binding.local_name in procedure_catalog.signatures_by_name
    ):
        _raise_error(
            (
                f"`let-proc` local procedure `{expr.binding.local_name}` collides "
                "with an existing value or procedure binding"
            ),
            code="let_proc_name_collision",
            span=expr.binding.span,
            form_path=expr.binding.form_path,
            expansion_stack=expr.binding.expansion_stack,
        )

    capture_params: list[ProcedureParam] = []
    capture_signature_params: list[tuple[str, TypeRef]] = []
    bound_capture_args: list[BoundProcArg] = []
    capture_bindings: list[tuple[str, ExprNode]] = []
    local_proc_ref_env: dict[str, ResolvedProcRefValue] = {}
    seen_capture_names: set[str] = set()
    for capture_name in expr.binding.capture_names:
        capture_type = value_env.get(capture_name)
        if capture_type is None:
            _raise_error(
                f"unknown `let-proc` capture `{capture_name}`",
                code="let_proc_capture_unknown",
                span=expr.binding.span,
                form_path=expr.binding.form_path,
                expansion_stack=expr.binding.expansion_stack,
            )
        if capture_name in seen_capture_names:
            _raise_error(
                f"duplicate `let-proc` capture `{capture_name}`",
                code="let_proc_capture_duplicate",
                span=expr.binding.span,
                form_path=expr.binding.form_path,
                expansion_stack=expr.binding.expansion_stack,
            )
        seen_capture_names.add(capture_name)
        if any(param.name == capture_name for param in expr.binding.params):
            _raise_error(
                f"`let-proc` capture `{capture_name}` collides with a local parameter",
                code="let_proc_capture_duplicate",
                span=expr.binding.span,
                form_path=expr.binding.form_path,
                expansion_stack=expr.binding.expansion_stack,
            )
        capture_params.append(
            ProcedureParam(
                name=capture_name,
                type_name=capture_type.name,
                span=expr.binding.span,
                form_path=expr.binding.form_path,
                expansion_stack=expr.binding.expansion_stack,
            )
        )
        capture_signature_params.append((capture_name, capture_type))
        if isinstance(capture_type, ProcRefTypeRef):
            capture_value = _ACTIVE_PROC_REF_VALUE_ENV.get(capture_name)
            if capture_value is not None:
                local_proc_ref_env[capture_name] = capture_value
        capture_value_expr = _ACTIVE_VALUE_EXPR_ENV.get(capture_name)
        if capture_value_expr is None:
            capture_value_expr = NameExpr(
                name=capture_name,
                span=expr.binding.span,
                form_path=expr.binding.form_path,
                expansion_stack=expr.binding.expansion_stack,
            )
        capture_bindings.append((capture_name, capture_value_expr))
        bound_capture_args.append(
            BoundProcArg(
                name=capture_name,
                value_expr=capture_value_expr,
                type_ref=capture_type,
                source_identity=_expr_source_identity(capture_value_expr),
                keyword_span=expr.binding.span,
                keyword_form_path=expr.binding.form_path,
                keyword_expansion_stack=expr.binding.expansion_stack,
            )
        )

    local_body_expr = _rewrite_local_proc_references(
        expr.binding.local_body,
        local_bindings={
            expr.binding.local_name: LocalProcRewriteBinding(
                generated_name="",
                capture_bindings=tuple(capture_bindings),
                allow_reference=False,
            ),
        },
    )
    generated_name = let_proc_generated_name(
        owner_callable_name=expr.form_path[-1],
        local_name=expr.binding.local_name,
        origin_span=expr.binding.span,
        param_type_names=tuple(
            [capture_type.name for _, capture_type in capture_signature_params]
            + [param.type_name for param in expr.binding.params]
        ),
        return_type_name=expr.binding.return_type_name,
        capture_names=expr.binding.capture_names,
        semantic_body_identity=_semantic_identity(local_body_expr),
    )
    generated_metadata = GeneratedLocalProcedure(
        authored_local_name=expr.binding.local_name,
        generated_name=generated_name,
        owner_callable_name=expr.form_path[-1],
        residual_params=tuple((param.name, param.type_name) for param in expr.binding.params),
        return_type_name=expr.binding.return_type_name,
        capture_names=expr.binding.capture_names,
        origin_span=expr.binding.span,
        consumer_proc_ref_spans=_collect_proc_ref_use_spans(
            expr.body,
            authored_name=expr.binding.local_name,
        ),
    )
    return_type_ref = type_env.resolve_type(
        expr.binding.return_type_name,
        span=expr.binding.span,
        form_path=expr.binding.form_path,
        expansion_stack=expr.binding.expansion_stack,
    )
    residual_signature_params = tuple(
        (
            param.name,
            type_env.resolve_type(
                param.type_name,
                span=param.span,
                form_path=param.form_path,
                expansion_stack=param.expansion_stack,
            ),
        )
        for param in expr.binding.params
    )
    generated_signature = ProcedureSignature(
        name=generated_name,
        params=tuple(capture_signature_params) + residual_signature_params,
        return_type_ref=return_type_ref,
        declared_effects=frozenset(),
        requested_lowering_mode=ProcedureLoweringMode.AUTO,
        span=expr.binding.span,
        form_path=expr.binding.form_path,
    )
    generated_definition = ProcedureDef(
        name=generated_name,
        params=tuple(capture_params) + expr.binding.params,
        return_type_name=expr.binding.return_type_name,
        declared_effects=frozenset(),
        requested_lowering_mode=generated_signature.requested_lowering_mode,
        body=expr.binding.local_body,
        span=expr.binding.span,
        form_path=expr.binding.form_path,
        expansion_stack=expr.binding.expansion_stack,
        generated_local_procedure=generated_metadata,
    )
    rewrite_binding = LocalProcRewriteBinding(
        generated_name=generated_name,
        capture_bindings=tuple(capture_bindings),
        allow_reference=True,
    )
    local_body_expr = _rewrite_local_proc_references(
        expr.binding.local_body,
        local_bindings={expr.binding.local_name: replace(rewrite_binding, allow_reference=False)},
    )
    outer_body_expr = _rewrite_local_proc_references(
        expr.body,
        local_bindings={expr.binding.local_name: rewrite_binding},
    )
    _ACTIVE_LET_PROC_REWRITE_RESULTS[id(expr)] = outer_body_expr
    generated_catalog = _temporary_procedure_catalog(
        procedure_catalog,
        definition=generated_definition,
        signature=generated_signature,
    )
    if _expr_returns_local_proc_value(
        outer_body_expr,
        generated_name,
        procedure_catalog=generated_catalog,
    ):
        _raise_error(
            f"`let-proc` local procedure `{expr.binding.local_name}` escaped its lexical scope",
            code="let_proc_scope_escape",
            span=expr.body.span,
            form_path=expr.body.form_path,
            expansion_stack=expr.body.expansion_stack,
        )

    local_value_env = {name: type_ref for name, type_ref in capture_signature_params}
    local_value_env.update(dict(residual_signature_params))
    previous_proc_ref_env = _ACTIVE_PROC_REF_VALUE_ENV
    _ACTIVE_PROC_REF_VALUE_ENV = local_proc_ref_env
    try:
        typed_local_body = _typecheck(
            local_body_expr,
            type_env=type_env,
            value_env=local_value_env,
            proof_scope=proof_scope,
            workflow_catalog=workflow_catalog,
            procedure_catalog=generated_catalog,
            extern_environment=extern_environment,
            command_boundary_environment=command_boundary_environment,
            active_phase_scope=active_phase_scope,
            procedure_effects_by_name=procedure_effects_by_name,
            workflow_effects_by_name=workflow_effects_by_name,
            proc_ref_resolution_context=proc_ref_resolution_context,
        )
    finally:
        _ACTIVE_PROC_REF_VALUE_ENV = previous_proc_ref_env
    if typed_local_body.type_ref != return_type_ref:
        _raise_error(
            (
                f"`let-proc` local procedure `{expr.binding.local_name}` declared "
                f"`{expr.binding.return_type_name}` but returned `{getattr(typed_local_body.type_ref, 'name', type(typed_local_body.type_ref).__name__)}`"
            ),
            code="let_proc_return_type_invalid",
            span=expr.binding.local_body.span,
            form_path=expr.binding.local_body.form_path,
            expansion_stack=expr.binding.local_body.expansion_stack,
        )
    _ACTIVE_GENERATED_LOCAL_PROCEDURES[generated_name] = TypedProcedureDef(
        definition=generated_definition,
        signature=generated_signature,
        typed_body=typed_local_body,
        direct_effect_summary=typed_local_body.effect_summary,
        transitive_effect_summary=typed_local_body.effect_summary,
    )

    bound_local_proc = ResolvedProcRefValue(
        procedure_name=generated_name,
        signature_params=generated_signature.params,
        return_type_ref=generated_signature.return_type_ref,
        authority_source=ProcRefAuthoritySource(
            kind="lexical_local_procedure",
            procedure_name=generated_name,
        ),
        bound_args=tuple(bound_capture_args),
    )
    outer_proc_ref_env = dict(_ACTIVE_PROC_REF_VALUE_ENV)
    outer_proc_ref_env[expr.binding.local_name] = bound_local_proc
    previous_proc_ref_env = _ACTIVE_PROC_REF_VALUE_ENV
    _ACTIVE_PROC_REF_VALUE_ENV = outer_proc_ref_env
    try:
        typed_outer_body = _typecheck(
            outer_body_expr,
            type_env=type_env,
            value_env=value_env,
            proof_scope=proof_scope,
            workflow_catalog=workflow_catalog,
            procedure_catalog=generated_catalog,
            extern_environment=extern_environment,
            command_boundary_environment=command_boundary_environment,
            active_phase_scope=active_phase_scope,
            procedure_effects_by_name=procedure_effects_by_name,
            workflow_effects_by_name=workflow_effects_by_name,
            proc_ref_resolution_context=proc_ref_resolution_context,
        )
    finally:
        _ACTIVE_PROC_REF_VALUE_ENV = previous_proc_ref_env
    return replace(typed_outer_body, expr=outer_body_expr)


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


def _rewrite_local_proc_references(
    node: object,
    *,
    local_bindings: Mapping[str, LocalProcRewriteBinding],
):
    if isinstance(node, ProcRefLiteralExpr):
        binding = local_bindings.get(node.authored_name)
        if binding is None:
            return node
        if not binding.allow_reference:
            _raise_error(
                f"`let-proc` local procedure `{node.authored_name}` cannot reference itself",
                code="let_proc_recursive_unsupported",
                span=node.span,
                form_path=node.form_path,
                expansion_stack=node.expansion_stack,
            )
        return _bind_local_proc_reference(node, binding)
    if isinstance(node, LetProcExpr):
        return node
    if isinstance(node, tuple):
        return tuple(_rewrite_local_proc_references(item, local_bindings=local_bindings) for item in node)
    if isinstance(node, list):
        return [_rewrite_local_proc_references(item, local_bindings=local_bindings) for item in node]
    if is_dataclass(node):
        updates = {}
        for field in fields(node):
            current = getattr(node, field.name)
            rewritten = _rewrite_local_proc_references(current, local_bindings=local_bindings)
            if rewritten is not current:
                updates[field.name] = rewritten
        if updates:
            return replace(node, **updates)
    return node


def _bind_local_proc_reference(
    expr: ProcRefLiteralExpr,
    binding: LocalProcRewriteBinding,
) -> ExprNode:
    base_expr = ProcRefLiteralExpr(
        target_name=binding.generated_name,
        authored_name=expr.authored_name,
        span=expr.span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    if not binding.capture_bindings:
        return base_expr
    return BindProcExpr(
        base_expr=base_expr,
        bindings=tuple(
            BindProcBinding(
                name=capture_name,
                value_expr=capture_expr,
                keyword_span=expr.span,
                keyword_form_path=expr.form_path,
                keyword_expansion_stack=expr.expansion_stack,
            )
            for capture_name, capture_expr in binding.capture_bindings
        ),
        span=expr.span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )


def _expr_returns_local_proc_value(
    expr: ExprNode,
    generated_name: str,
    *,
    value_bindings: Mapping[str, bool] | None = None,
    procedure_catalog: ProcedureCatalog | None = None,
    proc_ref_env: Mapping[str, ResolvedProcRefValue] | None = None,
    visited_calls: frozenset[tuple[str, frozenset[str]]] = frozenset(),
) -> bool:
    bindings = dict(value_bindings or {})
    active_proc_ref_env = dict(proc_ref_env or {})
    if isinstance(expr, ProcRefLiteralExpr):
        return expr.target_name == generated_name
    if isinstance(expr, BindProcExpr):
        if _expr_returns_local_proc_value(
            expr.base_expr,
            generated_name,
            value_bindings=bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=active_proc_ref_env,
            visited_calls=visited_calls,
        ):
            return True
        return any(
            _expr_returns_local_proc_value(
                binding.value_expr,
                generated_name,
                value_bindings=bindings,
                procedure_catalog=procedure_catalog,
                proc_ref_env=active_proc_ref_env,
                visited_calls=visited_calls,
            )
            for binding in expr.bindings
        )
    if isinstance(expr, NameExpr):
        return bindings.get(expr.name, False)
    if isinstance(expr, ProcedureCallExpr):
        return _procedure_call_returns_local_proc_value(
            expr,
            generated_name,
            value_bindings=bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=active_proc_ref_env,
            visited_calls=visited_calls,
        )
    if isinstance(expr, FunctionCallExpr):
        return _function_call_returns_local_proc_value(
            expr,
            generated_name,
            value_bindings=bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=active_proc_ref_env,
            visited_calls=visited_calls,
        )
    if isinstance(expr, RecordExpr):
        return any(
            _expr_returns_local_proc_value(
                field_expr,
                generated_name,
                value_bindings=bindings,
                procedure_catalog=procedure_catalog,
                proc_ref_env=active_proc_ref_env,
                visited_calls=visited_calls,
            )
            for _field_name, field_expr in expr.fields
        )
    if isinstance(expr, LetStarExpr):
        local_bindings = dict(bindings)
        for binding_name, binding_expr in expr.bindings:
            local_bindings[binding_name] = _expr_returns_local_proc_value(
                binding_expr,
                generated_name,
                value_bindings=local_bindings,
                procedure_catalog=procedure_catalog,
                proc_ref_env=active_proc_ref_env,
                visited_calls=visited_calls,
            )
        return _expr_returns_local_proc_value(
            expr.body,
            generated_name,
            value_bindings=local_bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=active_proc_ref_env,
            visited_calls=visited_calls,
        )
    if isinstance(expr, IfExpr):
        return _expr_returns_local_proc_value(
            expr.then_expr,
            generated_name,
            value_bindings=bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=active_proc_ref_env,
            visited_calls=visited_calls,
        ) or _expr_returns_local_proc_value(
            expr.else_expr,
            generated_name,
            value_bindings=bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=active_proc_ref_env,
            visited_calls=visited_calls,
        )
    if isinstance(expr, MatchExpr):
        for arm in expr.arms:
            arm_bindings = dict(bindings)
            arm_bindings[arm.binding_name] = False
            if _expr_returns_local_proc_value(
                arm.body,
                generated_name,
                value_bindings=arm_bindings,
                procedure_catalog=procedure_catalog,
                proc_ref_env=active_proc_ref_env,
                visited_calls=visited_calls,
            ):
                return True
        return False
    if isinstance(expr, WithPhaseExpr):
        return _expr_returns_local_proc_value(
            expr.body,
            generated_name,
            value_bindings=bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=active_proc_ref_env,
            visited_calls=visited_calls,
        )
    if isinstance(expr, ContinueExpr):
        return _expr_returns_local_proc_value(
            expr.state_expr,
            generated_name,
            value_bindings=bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=active_proc_ref_env,
            visited_calls=visited_calls,
        )
    if isinstance(expr, DoneExpr):
        return _expr_returns_local_proc_value(
            expr.result_expr,
            generated_name,
            value_bindings=bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=active_proc_ref_env,
            visited_calls=visited_calls,
        )
    if isinstance(expr, LoopRecurExpr):
        loop_bindings = dict(bindings)
        loop_bindings[expr.binding_name] = False
        return _expr_returns_local_proc_value(
            expr.initial_state_expr,
            generated_name,
            value_bindings=bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=active_proc_ref_env,
            visited_calls=visited_calls,
        ) or _expr_returns_local_proc_value(
            expr.body_expr,
            generated_name,
            value_bindings=loop_bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=active_proc_ref_env,
            visited_calls=visited_calls,
        )
    if isinstance(expr, ResumeOrStartExpr):
        return _expr_returns_local_proc_value(
            expr.resume_from_expr,
            generated_name,
            value_bindings=bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=active_proc_ref_env,
            visited_calls=visited_calls,
        ) or _expr_returns_local_proc_value(
            expr.start_expr,
            generated_name,
            value_bindings=bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=active_proc_ref_env,
            visited_calls=visited_calls,
        )
    return False


def _procedure_call_returns_local_proc_value(
    expr: ProcedureCallExpr,
    generated_name: str,
    *,
    value_bindings: Mapping[str, bool],
    procedure_catalog: ProcedureCatalog | None,
    proc_ref_env: Mapping[str, ResolvedProcRefValue],
    visited_calls: frozenset[tuple[str, frozenset[str]]],
) -> bool:
    if procedure_catalog is None:
        return False
    callee_value = proc_ref_env.get(expr.callee_name)
    if callee_value is not None:
        definition = procedure_catalog.definitions_by_name.get(callee_value.procedure_name)
        signature_params = callee_value.signature_params
        bound_args = callee_value.bound_args
    else:
        definition = procedure_catalog.definitions_by_name.get(expr.callee_name)
        signature = procedure_catalog.signatures_by_name.get(expr.callee_name)
        if definition is None or signature is None:
            return False
        signature_params = signature.params
        bound_args = ()
    local_bindings = dict(value_bindings)
    local_proc_ref_env: dict[str, ResolvedProcRefValue] = {}
    for bound_arg in bound_args:
        local_bindings[bound_arg.name] = _expr_returns_local_proc_value(
            bound_arg.value_expr,
            generated_name,
            value_bindings=value_bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=proc_ref_env,
            visited_calls=visited_calls,
        )
        if isinstance(bound_arg.type_ref, ProcRefTypeRef):
            resolved_bound_arg = resolve_proc_ref_value(
                bound_arg.value_expr,
                procedure_catalog=procedure_catalog,
                proc_ref_env=proc_ref_env,
            )
            if resolved_bound_arg is not None:
                local_proc_ref_env[bound_arg.name] = resolved_bound_arg
    residual_params = [
        (param_name, param_type)
        for param_name, param_type in signature_params
        if param_name not in {bound_arg.name for bound_arg in bound_args}
    ]
    if len(expr.args) != len(residual_params):
        return False
    for arg_expr, (param_name, param_type) in zip(expr.args, residual_params, strict=True):
        local_bindings[param_name] = _expr_returns_local_proc_value(
            arg_expr,
            generated_name,
            value_bindings=value_bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=proc_ref_env,
            visited_calls=visited_calls,
        )
        if isinstance(param_type, ProcRefTypeRef):
            resolved_arg = resolve_proc_ref_value(
                arg_expr,
                procedure_catalog=procedure_catalog,
                proc_ref_env=proc_ref_env,
            )
            if resolved_arg is not None:
                local_proc_ref_env[param_name] = resolved_arg
    call_key = (definition.name, frozenset(name for name, escapes in local_bindings.items() if escapes))
    if call_key in visited_calls:
        return False
    body_expr = definition.body
    if isinstance(body_expr, SyntaxNode):
        body_expr = elaborate_expression(
            body_expr,
            bound_names=frozenset(name for name, _ in signature_params),
            procedure_names=frozenset(procedure_catalog.signatures_by_name),
        )
    return _expr_returns_local_proc_value(
        body_expr,
        generated_name,
        value_bindings=local_bindings,
        procedure_catalog=procedure_catalog,
        proc_ref_env=local_proc_ref_env,
        visited_calls=visited_calls | {call_key},
    )


def _function_call_returns_local_proc_value(
    expr: FunctionCallExpr,
    generated_name: str,
    *,
    value_bindings: Mapping[str, bool],
    procedure_catalog: ProcedureCatalog | None,
    proc_ref_env: Mapping[str, ResolvedProcRefValue],
    visited_calls: frozenset[tuple[str, frozenset[str]]],
) -> bool:
    if _ACTIVE_FUNCTION_CATALOG is None:
        return False
    definition = _ACTIVE_FUNCTION_CATALOG.definitions_by_name.get(expr.callee_name)
    signature = _ACTIVE_FUNCTION_CATALOG.signatures_by_name.get(expr.callee_name)
    if definition is None or signature is None or len(expr.args) != len(signature.params):
        return False
    local_bindings = dict(value_bindings)
    for arg_expr, (param_name, _param_type) in zip(expr.args, signature.params, strict=True):
        local_bindings[param_name] = _expr_returns_local_proc_value(
            arg_expr,
            generated_name,
            value_bindings=value_bindings,
            procedure_catalog=procedure_catalog,
            proc_ref_env=proc_ref_env,
            visited_calls=visited_calls,
        )
    call_key = (
        f"function:{definition.name}",
        frozenset(name for name, escapes in local_bindings.items() if escapes),
    )
    if call_key in visited_calls:
        return False
    body_expr = definition.body
    if isinstance(body_expr, SyntaxNode):
        body_expr = elaborate_expression(
            body_expr,
            bound_names=frozenset(name for name, _ in signature.params),
            procedure_names=(
                frozenset()
                if procedure_catalog is None
                else frozenset(procedure_catalog.signatures_by_name)
            ),
            function_names=frozenset(_ACTIVE_FUNCTION_CATALOG.signatures_by_name),
        )
    return _expr_returns_local_proc_value(
        body_expr,
        generated_name,
        value_bindings=local_bindings,
        procedure_catalog=procedure_catalog,
        proc_ref_env=proc_ref_env,
        visited_calls=visited_calls | {call_key},
    )


def _expr_source_identity(expr: ExprNode) -> str:
    if isinstance(expr, LiteralExpr):
        return f"literal:{expr.literal_kind}:{expr.value!r}"
    if isinstance(expr, FieldAccessExpr):
        return f"field:{expr.base.name}:{'.'.join(expr.fields)}"
    if isinstance(expr, NameExpr):
        return f"name:{expr.name}"
    start = expr.span.start
    return f"{start.path}:{start.line}:{start.column}"


def _collect_proc_ref_use_spans(
    node: object,
    *,
    authored_name: str,
) -> tuple[SourceSpan, ...]:
    if isinstance(node, ProcRefLiteralExpr):
        return (node.span,) if node.authored_name == authored_name else ()
    if isinstance(node, LetProcExpr):
        return ()
    if isinstance(node, tuple):
        return tuple(
            span
            for item in node
            for span in _collect_proc_ref_use_spans(item, authored_name=authored_name)
        )
    if isinstance(node, list):
        return tuple(
            span
            for item in node
            for span in _collect_proc_ref_use_spans(item, authored_name=authored_name)
        )
    if is_dataclass(node):
        return tuple(
            span
            for field in fields(node)
            for span in _collect_proc_ref_use_spans(getattr(node, field.name), authored_name=authored_name)
        )
    return ()


def _semantic_identity(value: object) -> str:
    if is_dataclass(value):
        return (
            f"{type(value).__name__}("
            + ",".join(
                f"{field.name}={_semantic_identity(getattr(value, field.name))}"
                for field in fields(value)
                if field.name not in {"span", "form_path", "expansion_stack"}
            )
            + ")"
        )
    if isinstance(value, tuple):
        return "(" + ",".join(_semantic_identity(item) for item in value) + ")"
    if isinstance(value, list):
        return "[" + ",".join(_semantic_identity(item) for item in value) + "]"
    if isinstance(value, Mapping):
        return (
            "{"
            + ",".join(
                f"{_semantic_identity(key)}:{_semantic_identity(value[key])}"
                for key in sorted(value, key=repr)
            )
            + "}"
        )
    if isinstance(value, frozenset):
        return "frozenset(" + ",".join(sorted(_semantic_identity(item) for item in value)) + ")"
    return repr(value)


def _replace_eliminated_let_procs(node: object):
    replacement = _ACTIVE_LET_PROC_REWRITE_RESULTS.get(id(node))
    if replacement is not None:
        return _replace_eliminated_let_procs(replacement)
    if isinstance(node, tuple):
        return tuple(_replace_eliminated_let_procs(item) for item in node)
    if isinstance(node, list):
        return [_replace_eliminated_let_procs(item) for item in node]
    if is_dataclass(node):
        updates = {}
        for field in fields(node):
            current = getattr(node, field.name)
            rewritten = _replace_eliminated_let_procs(current)
            if rewritten is not current:
                updates[field.name] = rewritten
        if updates:
            return replace(node, **updates)
    return node


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
