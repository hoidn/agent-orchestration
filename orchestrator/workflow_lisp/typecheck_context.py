"""Shared typecheck context, diagnostics, and session state."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .effects import EMPTY_EFFECT_SUMMARY, EffectSummary
from .expressions import ExprNode
from .lints import required_lint_diagnostic
from .loops import LoopControlTypeRef
from .phase_stdlib import (
    DEFAULT_REVIEW_LOOP_LEGACY_BRIDGE_POLICY,
    ReviewLoopLegacyBridgePolicy,
)
from .parametric_constraints import SharedUnionFieldCapability
from .procedure_refs import ResolvedProcRefValue
from .procedures import TypedProcedureDef
from .spans import SourceSpan
from .type_env import TypeRef

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
    reusable_state_producer_context: Mapping[str, object] | None = None
    shared_union_field_capabilities: tuple[SharedUnionFieldCapability, ...] = ()
    review_loop_legacy_bridge_policy: ReviewLoopLegacyBridgePolicy = (
        DEFAULT_REVIEW_LOOP_LEGACY_BRIDGE_POLICY
    )


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
        reusable_state_producer_context=(
            None
            if state.reusable_state_producer_context is None
            else dict(state.reusable_state_producer_context)
        ),
        shared_union_field_capabilities=tuple(state.shared_union_field_capabilities),
        review_loop_legacy_bridge_policy=state.review_loop_legacy_bridge_policy,
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
    state.reusable_state_producer_context = snapshot.reusable_state_producer_context
    state.shared_union_field_capabilities = tuple(snapshot.shared_union_field_capabilities)
    state.review_loop_legacy_bridge_policy = snapshot.review_loop_legacy_bridge_policy


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
