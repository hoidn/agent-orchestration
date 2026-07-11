"""Shared typecheck context, diagnostics, and session state."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .effects import EMPTY_EFFECT_SUMMARY, EffectSummary
from .expressions import ExprNode, LiteralExpr
from .lints import required_lint_diagnostic
from .loops import LoopControlTypeRef
from .parametric_constraints import SharedUnionFieldCapability
from .phase import (
    IMPLEMENTATION_ATTEMPT_PHASE_CONTEXT_NAME,
    PHASE_CONTEXT_NAME,
    PhaseScope,
    is_record_definition_named,
)
from .procedure_refs import ResolvedProcRefValue
from .procedures import TypedProcedureDef
from .spans import SourceSpan
from .type_env import TypeRef, UnionTypeRef, VariantCaseTypeRef, type_refs_compatible

if TYPE_CHECKING:
    from .functions import FunctionCatalog


@dataclass(frozen=True)
class TypedExpr:
    """One expression paired with its resolved Workflow Lisp type."""

    expr: ExprNode
    type_ref: TypeRef | LoopControlTypeRef
    span: SourceSpan
    form_path: tuple[str, ...]
    effect_summary: EffectSummary = EMPTY_EFFECT_SUMMARY


ValueEnvironment = Mapping[str, TypeRef]


@dataclass(frozen=True)
class LoopTypecheckContext:
    """Active loop typing contract for nested `continue` and `done` forms."""

    state_type_ref: TypeRef
    result_type_ref: TypeRef | None = None


@dataclass
class TypecheckSessionState:
    """Mutable compiler-pass-local typing state."""

    function_catalog: FunctionCatalog | None = None
    proc_ref_value_env: Mapping[str, ResolvedProcRefValue] = field(default_factory=dict)
    value_expr_env: Mapping[str, ExprNode] = field(default_factory=dict)
    loop_context: list[LoopTypecheckContext] = field(default_factory=list)
    generated_local_procedures: dict[str, TypedProcedureDef] = field(default_factory=dict)
    let_proc_rewrite_results: dict[int, ExprNode] = field(default_factory=dict)
    workflow_signature: object | None = None
    procedure_hidden_context_signature: object | None = None
    reusable_state_producer_context: Mapping[str, object] | None = None
    shared_union_field_capabilities: tuple[SharedUnionFieldCapability, ...] = ()


@dataclass(frozen=True)
class TypecheckContext:
    """Recursive typecheck inputs carried through dispatch owners."""

    type_env: object
    value_env: ValueEnvironment
    proof_scope: object
    workflow_catalog: object | None
    procedure_catalog: object | None
    extern_environment: object | None
    command_boundary_environment: object | None
    active_phase_scope: object | None
    procedure_effects_by_name: Mapping[str, EffectSummary]
    workflow_effects_by_name: Mapping[str, EffectSummary]
    proc_ref_resolution_context: object | None
    shared_union_field_capabilities: tuple[SharedUnionFieldCapability, ...]
    session_state: TypecheckSessionState


_SESSION_STATE = TypecheckSessionState()


def get_session_state() -> TypecheckSessionState:
    return _SESSION_STATE


def snapshot_session_state() -> TypecheckSessionState:
    state = get_session_state()
    return TypecheckSessionState(
        function_catalog=state.function_catalog,
        proc_ref_value_env=dict(state.proc_ref_value_env),
        value_expr_env=dict(state.value_expr_env),
        loop_context=list(state.loop_context),
        generated_local_procedures=dict(state.generated_local_procedures),
        let_proc_rewrite_results=dict(state.let_proc_rewrite_results),
        workflow_signature=state.workflow_signature,
        procedure_hidden_context_signature=state.procedure_hidden_context_signature,
        reusable_state_producer_context=(
            None
            if state.reusable_state_producer_context is None
            else dict(state.reusable_state_producer_context)
        ),
        shared_union_field_capabilities=tuple(state.shared_union_field_capabilities),
    )


def restore_session_state(snapshot: TypecheckSessionState) -> None:
    state = get_session_state()
    state.function_catalog = snapshot.function_catalog
    state.proc_ref_value_env = snapshot.proc_ref_value_env
    state.value_expr_env = snapshot.value_expr_env
    state.loop_context = list(snapshot.loop_context)
    state.generated_local_procedures = dict(snapshot.generated_local_procedures)
    state.let_proc_rewrite_results = dict(snapshot.let_proc_rewrite_results)
    state.workflow_signature = snapshot.workflow_signature
    state.procedure_hidden_context_signature = snapshot.procedure_hidden_context_signature
    state.reusable_state_producer_context = snapshot.reusable_state_producer_context
    state.shared_union_field_capabilities = tuple(snapshot.shared_union_field_capabilities)


def consume_generated_local_procedures() -> tuple[TypedProcedureDef, ...]:
    """Return and clear generated `let-proc` procedures from the active pass."""

    state = get_session_state()
    procedures = tuple(state.generated_local_procedures.values())
    state.generated_local_procedures = {}
    return procedures


def reset_generated_local_procedure_state() -> None:
    """Clear compiler-pass-local `let-proc` generated state."""

    state = get_session_state()
    state.generated_local_procedures = {}
    state.let_proc_rewrite_results = {}


def set_active_workflow_signature(signature) -> None:
    """Record the current workflow signature for nested typecheck helpers."""

    get_session_state().workflow_signature = signature


def clear_active_workflow_signature() -> None:
    """Clear the active workflow signature after finishing one workflow body."""

    get_session_state().workflow_signature = None


def set_active_reusable_state_producer_context(context: Mapping[str, object] | None) -> None:
    """Record compiler-owned reuse identity inputs for the active workflow body."""

    get_session_state().reusable_state_producer_context = context


def clear_active_reusable_state_producer_context() -> None:
    """Clear the active compiler-owned reuse identity inputs."""

    get_session_state().reusable_state_producer_context = None


def raise_required_lint(
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


def raise_error(
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


def _require_normative_phase_ctx_type(
    type_ref: TypeRef,
    *,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> None:
    if is_record_definition_named(type_ref, IMPLEMENTATION_ATTEMPT_PHASE_CONTEXT_NAME):
        raise_error(
            "generic phase stdlib forms require `PhaseCtx`; the legacy bridge is reserved for the Stage 4 implementation-attempt regression",
            code="phase_ctx_legacy_bridge_invalid",
            span=span,
            form_path=form_path,
        )
    if not is_record_definition_named(type_ref, PHASE_CONTEXT_NAME):
        raise_error(
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
    raise_error(
        f"`{form_name}` name `{authored_name}` must match the active `with-phase` scope `{active_phase_scope.phase_name}`",
        code="phase_scope_name_mismatch",
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


def _literal_string(expr: ExprNode) -> str | None:
    if isinstance(expr, LiteralExpr) and expr.literal_kind == "string" and isinstance(expr.value, str):
        return expr.value
    return None


def _variant_has_field(variant_type: VariantCaseTypeRef, field_name: str) -> bool:
    return any(field.name == field_name for field in variant_type.definition.fields)


def _union_has_any_field(union_type: UnionTypeRef, field_name: str) -> bool:
    return any(field.name == field_name for variant in union_type.definition.variants for field in variant.fields)


def _span_contains(outer: SourceSpan | None, inner: SourceSpan) -> bool:
    if outer is None:
        return False
    if outer.start.path != inner.start.path or outer.end.path != inner.end.path:
        return False
    return outer.start.offset <= inner.start.offset and inner.end.offset <= outer.end.offset
